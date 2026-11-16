"""G1-INT-DIAG-001/D1. A cell's frozen E0 and its shuffles."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


CONDITIONS = {"s_only": (1,), "r_only": (0,), "both": (0, 1), "both_paired": (0, 1)}
TRACE_FIELDS = ("x", "P", "prior", "Pprior", "h", "H", "mu", "Rvar", "Reff", "K", "nu", "mask")


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_file(receipt):
    path = Path(receipt["path"])
    if sha(path) != receipt["sha256"]:
        raise ValueError(f"Input hash mismatch: {path}")
    return path


def dump(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def strata(prior, spec, bearing):
    rho = np.linalg.norm(prior[:, :2] - np.asarray(spec["anchor"][:2]), axis=1)
    distance_bin = np.searchsorted([3., 6., 10.], rho, side="right")
    groups, blocked = [], []
    for is_oblique in (False, True):
        partitions = []
        for k in range(4):
            idx = np.flatnonzero((distance_bin == k) & ((bearing >= 30.) == is_oblique))
            if len(idx):
                partitions.append(([k], idx))
        while len(partitions) > 1:
            small = next((j for j, (_, idx) in enumerate(partitions) if len(idx) < 20), None)
            if small is None:
                break
            adjacent = [j for j in (small - 1, small + 1) if 0 <= j < len(partitions)]
            partner = min(adjacent, key=lambda j: (
                min(abs(a - b) for a in partitions[j][0] for b in partitions[small][0]), j))
            left, right = sorted((small, partner))
            bins = partitions[left][0] + partitions[right][0]
            idx = np.sort(np.concatenate([partitions[left][1], partitions[right][1]]))
            partitions[left:right + 1] = [(bins, idx)]
        for bins, idx in partitions:
            record = {"oblique": is_oblique, "distance_bins": bins, "idx": idx}
            (groups if len(idx) >= 20 else blocked).append(record)
    return groups, blocked


def physically_valid(z, channels):
    valid = np.all(np.isfinite(z), axis=-1)
    if 0 in channels:
        valid &= z[..., channels.index(0)] > 0.
    if 1 in channels:
        valid &= np.abs(z[..., channels.index(1)]) <= 1.
    return valid


def legal_swaps(groups, base, sigma, u, original, sibling_delta, channels):
    legal_groups = []
    for group in groups:
        idx = group["idx"]
        location = base[np.ix_(idx, channels)]
        scale = sigma[np.ix_(idx, channels)]
        residual = u[np.ix_(idx, channels)]
        z_reference = original[np.ix_(idx, channels)]
        targets = location[:, None, :] + scale[:, None, :] * residual[None, :, :]
        offsets = sibling_delta[np.ix_(idx, channels)]
        legal = physically_valid(targets, channels) & physically_valid(targets + offsets[:, None, :], channels)
        # Use original z for fixed points, including floating-point boundary values.
        legal[np.diag_indices(len(idx))] = (physically_valid(z_reference, channels) &
                                           physically_valid(z_reference + offsets, channels))
        if not np.all(np.diag(legal)):
            raise ValueError("Original RF is outside its physical support")
        legal_groups.append((idx, legal))
    return legal_groups


def draw_map(rng, legal_groups, count):
    """Sample legal permutations without clipping or repeatedly generating out-of-range RF."""
    identity = np.arange(count, dtype=np.int32)
    mapping = identity.copy()
    for idx, legal in legal_groups:
        shuffled = rng.permutation(len(idx))
        if not np.all(legal[np.arange(len(idx)), shuffled]):
            shuffled = np.arange(len(idx))
            # Random pairings with a symmetric accept/reject rule preserve exchangeability
            # over the reachable legal permutations. The 20-sweep cap is frozen.
            for _ in range(20):
                order = rng.permutation(len(idx))
                left, right = order[:len(order) - len(order) % 2].reshape(-1, 2).T
                swap = legal[left, shuffled[right]] & legal[right, shuffled[left]]
                left, right = left[swap], right[swap]
                shuffled[left], shuffled[right] = shuffled[right], shuffled[left]
        mapping[idx] = idx[shuffled]
    if not np.array_equal(np.sort(mapping), identity):
        raise ValueError("Donor map is not bijective")
    return mapping


def lag1(x):
    a, b = x[:-1], x[1:]
    a, b = a - a.mean(), b - b.mean()
    scale = np.linalg.norm(a) * np.linalg.norm(b)
    return float((a @ b) / scale) if scale > 0 else 0.


def cross(x):
    a, b = (x - x.mean(axis=0)).T
    scale = np.linalg.norm(a) * np.linalg.norm(b)
    return float((a @ b) / scale) if scale > 0 else 0.


def summarize_rows(trace, truth):
    from metrics_s2 import METRICS, POSE95_CUTOFF, XY95_CUTOFF
    from replay_s2 import wrap

    err = trace["x"][..., :3] - truth
    err[..., 2] = wrap(err[..., 2])
    covariance = trace["P"][..., :3, :3]
    chol = np.linalg.cholesky(covariance)
    normalized = np.linalg.solve(chol, err[..., None])[..., 0]
    nees = np.sum(normalized ** 2, axis=-1)
    rows = np.stack([np.rad2deg(err[..., 2]) ** 2, 1e4 * np.sum(err[..., :2] ** 2, axis=-1), nees,
                     nees <= POSE95_CUTOFF, np.sum(normalized[..., :2] ** 2, axis=-1) <= XY95_CUTOFF,
                     np.abs(err[..., 2]) <= 1.96 * np.sqrt(covariance[..., 2, 2])], axis=-1)
    if not np.isfinite(rows).all():
        raise ValueError("Nonfinite D1 score")
    means = rows.mean(axis=-2)
    means[..., :2] = np.sqrt(means[..., :2])
    return [dict(zip(METRICS, row.tolist())) for row in means]


def run(contract_path, cell_id):
    from e0_batch import replay_batch

    started = now()
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    root = contract_path.parent
    d0 = json.loads((root / "d0" / "EXECUTION.json").read_text(encoding="utf-8"))
    d5 = json.loads((root / "d5" / "EXECUTION.json").read_text(encoding="utf-8"))
    if any(e["status"] != "PASS_EXECUTION" or e["run_contract_sha256"] != sha(contract_path)
           for e in (d0, d5)):
        raise ValueError("D1 requires completed D0 then D5")
    cells = {f"{v['anchor']}_{v['bias']}_{v['route']}": v for v in contract["cells"]}
    cell = cells[cell_id]
    b0_id = f"{cell['anchor']}_B0_{cell['route']}"
    b0 = cells[b0_id]
    sys.path[:0] = [contract["s2"], str(Path(contract["native"]) / "src")]
    from qclean_uwb.fp_sc.e0_baseline import SPEC, load_original_model
    from replay_s2 import geometry, parity, read_npz
    from verify_s2 import check_metric_rows, from_trace

    packet = read_npz(verify_file(cell["online"]))
    reference = read_npz(verify_file(cell["evaluator"]))
    b0_packet = read_npz(verify_file(b0["online"]))
    d0_paths = {key: root / "d0" / f"{key}.npz" for key in {cell_id, b0_id}}
    for key, path in d0_paths.items():
        if sha(path) != d0["outputs"][path.name]:
            raise ValueError(f"D0 result hash mismatch: {key}")
    trace, b0_trace = (read_npz(d0_paths[key]) for key in (cell_id, b0_id))
    truth = reference["truth"]
    for key in ("t", "pose_id"):
        if not np.array_equal(packet[key], b0_packet[key]) or not np.array_equal(packet[key], reference[key]):
            raise ValueError(f"D1 packet grid mismatch: {key}")
    for key in ("z", "muMB", "R"):
        parity({key: packet[key]}, {key: b0_packet[key]})
    core, online, model, source_hashes = load_original_model(contract["native"])
    spec = dict(SPEC, anchor=tuple(contract["anchors"][cell["anchor"]]), mount_deg=contract["scope"]["mount_deg"])
    h_truth, _ = model.batch(np.column_stack([truth, np.zeros(len(truth))]), spec, gradient=False)
    base = h_truth + b0_packet["muMB"]
    epsilon = b0_packet["z"] - base
    sigma = np.sqrt(np.diagonal(b0_trace["Reff"], axis1=-2, axis2=-1))
    u = epsilon / sigma
    delta = packet["z"] - b0_packet["z"]
    if not physically_valid(packet["z"], (0, 1)).all():
        raise ValueError("Original z failed physical range check")
    _, bearing = geometry(b0_trace["prior"], spec)
    groups, blocked = strata(b0_trace["prior"], spec, np.minimum(bearing, 180. - bearing))
    mask = trace["mask"]
    original = u[mask]
    lags_before = [lag1(original[:, c]) for c in range(2)]
    if not np.isfinite(u).all() or len(original) < 20:
        raise ValueError("Insufficient valid standardization support")
    out = root / "d1" / cell_id
    out.mkdir(parents=True, exist_ok=False)

    identity = replay_batch(core, online, model, spec, packet, mask, packet["z"][None], return_trace=True)
    identity_errors = parity({k: identity[k][0] for k in TRACE_FIELDS}, {k: trace[k] for k in TRACE_FIELDS})
    identity_score = summarize_rows(identity, truth)[0]
    check_metric_rows(from_trace(trace, truth), dict(identity_score, n=len(truth)))
    print(f"{cell_id} identity passed", flush=True)

    seed = contract["D1"]["seed"]
    reps = contract["D1"]["repetitions"]
    a = ["B", "A"].index(cell["anchor"])
    route = ["R2", "R4", "R5"].index(cell["route"])
    channels_by_map = ((0,), (1,), (0, 1))
    # A common legal region preserves identical maps across B0/L2 even for sub-tolerance z drift.
    sibling_delta = np.zeros_like(b0_packet["z"])  # Single-level B/B0 contract
    padding = np.max(np.abs(sibling_delta), axis=0)
    legal_groups = [legal_swaps(groups, base, sigma, u, b0_packet["z"], sibling_delta, channels)
                    for channels in channels_by_map]
    maps = np.empty((reps, len(channels_by_map), len(u)), dtype=np.int32)
    for i in range(reps):
        for j, support in enumerate(legal_groups):
            rng = np.random.default_rng(np.random.SeedSequence([seed, a, route, i, j]))
            maps[i, j] = draw_map(rng, support, len(u))
    map_path = out / "permutations.npz"
    np.savez_compressed(map_path, maps=maps)

    all_results = {}
    indices = np.arange(len(u))
    for name, channels in CONDITIONS.items():
        observations = np.broadcast_to(packet["z"], (reps, *packet["z"].shape)).copy()
        stats = []
        for i in range(reps):
            reassigned = u.copy()
            changed_fractions = []
            for c in channels:
                mapping = maps[i, 2 if name == "both_paired" else c]
                reassigned[:, c] = u[mapping, c]
                changed = mapping != indices
                observations[i, changed, c] = (base[changed, c] + sigma[changed, c] * reassigned[changed, c]
                                                + delta[changed, c])
                changed_fractions.append(float(changed[mask].mean()))
            if not physically_valid(observations[i], (0, 1)).all():
                raise ValueError(f"D1 map failed physical support: {name}/{i}")
            accepted = reassigned[mask]
            lags = [lag1(accepted[:, c]) for c in range(2)]
            eligible = (min(changed_fractions) >= .80 and
                        all(abs(lags[c]) <= max(.10, .5 * abs(lags_before[c])) for c in channels))
            # The permutation preserves means in the supported strata over all assigned packets.
            max_mean_deviation = max((np.max(np.abs(reassigned[g["idx"]].mean(axis=0) -
                                                     u[g["idx"]].mean(axis=0))) for g in groups), default=0.)
            if max_mean_deviation > 1e-12:
                raise ValueError("D1 standardized stratum mean changed")
            stats.append(dict(repetition=i, valid=eligible, moved_fractions=changed_fractions, lag1=lags,
                              cross_correlation=cross(accepted), max_stratum_mean_deviation=float(max_mean_deviation),
                              raw_rms=np.sqrt(np.mean((sigma[mask] * accepted)**2, axis=0)).tolist(),
                              standardized_rms=np.sqrt(np.mean(accepted**2, axis=0)).tolist()))
        replay = replay_batch(core, online, model, spec, packet, mask, observations,
                              batch_size=contract["D1"]["batch_size"])
        for row, score in zip(stats, summarize_rows(replay, truth), strict=True):
            row["score"] = score
        all_results[name] = stats
        print(f"{cell_id} {name}: {sum(v['valid'] for v in stats)}/{reps} valid", flush=True)
    dump(out / "RESULTS.json", {
        "study": "G1-INT-DIAG-001/D1", "status": "PASS", "classification": "DIAGNOSTIC_ONLY",
        "cell": cell_id, "start_utc": started, "finish_utc": now(), "command": sys.argv,
        "python": sys.version, "numpy": np.__version__, "source_hashes": source_hashes,
        "contract_sha256": sha(contract_path), "d0_sha256": sha(root / "d0" / "RESULTS.json"),
        "d5_sha256": sha(root / "d5" / "RESULTS.json"),
        "n": len(truth), "accepted": int(mask.sum()), "identity": identity_score, "identity_errors": identity_errors,
        "lags_before": lags_before, "before_cross": cross(original),
        "before_rms": np.sqrt(np.mean(epsilon[mask]**2, axis=0)).tolist(),
        "interlevel_z_max_abs": padding.tolist(),
        "strata": [{"oblique": g["oblique"], "distance_bins": g["distance_bins"], "n": len(g["idx"]),
                    "permuted": any(g is supported for supported in groups)}
                   for g in groups + blocked],
        "permutations_sha256": sha(map_path), "conditions": all_results,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--cell", required=True)
    args = parser.parse_args()
    run(args.contract, args.cell)
