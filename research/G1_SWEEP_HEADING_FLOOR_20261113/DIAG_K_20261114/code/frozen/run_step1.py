"""G1-FLOOR-001: frozen input checks, inventory, parity, and sweep cost curves."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

BLOCK = "results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449"
LUT = "results/DRIVE_SIM_20261007/CAUSE_CHECK_A23_EXECUTION_20261010"
SPEC = "research/G1_SWEEP_HEADING_FLOOR_20261113"
GRID = np.arange(-180., 180., 0.25)
FIELDS = ("case route group x y dist_xy theta_geo_deg snr_db seed span_deg actual_span_deg n_pose "
          "imu_k xy_arm prior_sigma e_prior window window_miss channel err_deg J margin n_valid").split()


def wrap(a):
    return (np.asarray(a) + 180.) % 360. - 180.


def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def verify(root, receipt):
    provenance = json.loads(receipt.read_text(encoding="utf-8-sig"))
    for rel, info in provenance["inputs"].items():
        if sha(root / rel) != info["sha256"]:
            raise ValueError(f"Input hash changed: {rel}")


def get_groups(s):
    grouped = defaultdict(list)
    for i, row in enumerate(s):
        grouped[round(row["x"], 4), round(row["y"], 4)].append(i)
    return [np.array(v) for v in grouped.values() if len(v) >= 3]


def get_selections(yaw):
    rel = wrap(yaw - yaw[0])
    span = np.ptp(rel)
    middle = (rel.max() + rel.min()) / 2
    cuts = [(40, np.flatnonzero(np.abs(rel - middle) <= 20. + 1e-6))]
    probe = np.unique([np.argmin(np.abs(wrap(rel - goal))) for goal in [0., 10., 20.]])
    if len(probe) == 3:
        cuts.append((20, probe))
    if len(yaw) == 19 and abs(span - 90.) < 1e-6:
        cuts.insert(0, (90, np.arange(len(yaw))))
    return rel, cuts


def solve(cost, allowed, n_valid):
    finite = np.isfinite(cost)
    if n_valid < 3 or not np.any(allowed & finite):
        return math.nan, math.nan, math.nan
    idx = np.argmin(np.where(allowed, cost, np.inf))
    j = cost[idx]
    far = allowed & finite & (np.abs(wrap(GRID - GRID[idx])) >= 20.)
    margin = (cost[far].min() - j) / max(j, 1e-12) if far.any() else math.nan
    return GRID[idx], float(j), float(margin)


def evaluate_case(c, root, out, freqs, lut, L, O):
    name = c["case"]
    route = name.split("_")[0]
    block = root / BLOCK / "BLOCK_C"
    f_path = block / "FULL_RF" / f"H_{name}.npy"
    l_path = block / f"H_LoS_{name}.npy"
    if sha(f_path) != c["input_H_sha256"] or sha(l_path) != c["H_sha256"]:
        raise ValueError(f"Channel SHA mismatch: {name}")
    h = np.load(f_path, allow_pickle=False)
    hl = np.load(l_path, allow_pickle=False)
    s = json.loads((block / name / "SAMPLES.json").read_bytes())
    if h.shape != hl.shape or h.shape != (len(s), len(freqs), 2, 2):
        raise ValueError(f"Input shape mismatch: {name}")
    x, y, yaw = (np.array([r[k] for r in s]) for k in ("x", "y", "yaw_body_deg"))
    groups = get_groups(s)
    anchor = c["anchor_xyz"]
    z, mount = c["robot_z"], c["mount_deg"]
    dist = np.hypot(x - anchor[0], y - anchor[1])
    theta = np.degrees(np.arctan2(dist, anchor[2] - z))
    inventory = dict(case=name, route=route, mount_deg=mount, h_shape=list(h.shape),
                     h_dtype=str(h.dtype), n_groups=len(groups), groups=[])
    for i, ids in enumerate(groups):
        j = ids[0]
        angles = np.sort(wrap(yaw[ids] - yaw[j]))
        inventory["groups"].append(dict(group=i, x=x[j], y=y[j], yaw_deg=yaw[j],
                                         dist_xy=dist[j], theta_geo_deg=theta[j],
                                         n_pose=len(ids), span_deg=float(np.ptp(angles)),
                                         yaw_steps_deg=np.diff(angles).tolist()))
    inventory["n_90"] = sum(g["n_pose"] == 19 and abs(g["span_deg"] - 90.) < 1e-6
                            for g in inventory["groups"])
    slo0 = O.observe(hl, freqs, None, None, tx=0)["s"]
    sm, jac = L.s_model(lut, anchor, z, x, y, np.radians(yaw), mount, with_jac=True)
    delta = np.abs(slo0 - sm)
    eligible = delta[np.isfinite(delta)]
    if len(eligible):
        med, p90 = np.quantile(eligible, [0.5, 0.9])
        parity = dict(median_abs=float(med), p90_abs=float(p90), n=len(eligible),
                      n_pose=len(s), passed=bool(med <= 0.005 and p90 <= 0.02))
    else:
        parity = dict(median_abs=None, p90_abs=None, n=0, n_pose=len(s), passed=False)
    print(f"{name}: parity {parity}; {inventory['n_90']} full-span stations", flush=True)
    if not parity["passed"]:
        return inventory, parity, None
    sfull0 = O.observe(h, freqs, None, None, tx=0)["s"]
    observations = {0: np.repeat(np.stack([sfull0, slo0])[None, :, :], 20, axis=0)}
    for snr in (30, 10):
        nv = O.noise_var_from_snr(snr)
        rows = []
        for seed in range(20):
            rng = np.random.default_rng(seed)
            rows.append([O.observe(v, freqs, nv, rng, tx=0)["s"] for v in (h, hl)])
        observations[snr] = np.array(rows)
    xy_offsets = np.random.default_rng(2026111301).normal(0., .1, (len(groups), 20, 2))
    prior_offsets = np.random.default_rng(2026111302).normal(size=(len(groups), 20, 2))
    curve_path = out / f"S1_J_{name}.npy"
    index_path = out / f"S1_J_INDEX_{name}.csv"
    max_curves = sum(len(get_selections(yaw[ids])[1]) for ids in groups) * 3 * 20 * 2 * 2 * 2
    curves = np.lib.format.open_memmap(curve_path, mode="w+", dtype="float64", shape=(max_curves, len(GRID)))
    index_fields = "row group seed snr_db span_deg imu_k xy_arm channel n_valid yaw_deg".split()
    row = 0
    with ((out / f"S1_SWEEP_ERRORS_{name}.csv").open("w", newline="", encoding="utf-8") as output,
          index_path.open("w", newline="", encoding="utf-8") as index_file):
        writer = csv.DictWriter(output, FIELDS)
        writer.writeheader()
        index = csv.writer(index_file)
        index.writerow(index_fields)
        for group, ids in enumerate(groups):
            j = ids[0]
            rel, cuts = get_selections(yaw[ids])
            for span, sub in cuts:
                angle = rel[sub]
                actual_span = float(np.ptp(angle))
                for k in (0., .0085):
                    radians = np.radians(GRID[:, None] + angle + k * np.abs(angle))
                    for xy in ("XY-T", "XY-P"):
                        for seed in range(20):
                            ex, ey = xy_offsets[group, seed] if xy == "XY-P" else (0., 0.)
                            pred = L.s_model(lut, anchor, z, x[j] + ex, y[j] + ey, radians, mount)
                            if not np.isfinite(pred).all():
                                raise ValueError(f"Nonfinite LUT prediction: {name}, {group}, {seed}")
                            for snr, obs in observations.items():
                                snr_label = snr or ""
                                for channel_idx, channel in enumerate(("full", "los")):
                                    obs_s = obs[seed, channel_idx, ids[sub]]
                                    ok = np.isfinite(obs_s)
                                    n_valid = int(ok.sum())
                                    cost = (np.square(pred[:, ok] - obs_s[ok]).sum(axis=1)
                                            if n_valid >= 3 else np.full(len(GRID), np.nan))
                                    curves[row] = cost
                                    index.writerow((row, group, seed, snr, span, k, xy, channel, n_valid, yaw[j]))
                                    row += 1
                                    for pidx, sigma in enumerate((2., 5.)):
                                        e_prior = sigma * prior_offsets[group, seed, pidx]
                                        offset = np.abs(wrap(GRID - yaw[j] - e_prior))
                                        for window in (180., 30., 10.):
                                            psi, value, margin = solve(cost, offset <= window + 1e-10, n_valid)
                                            writer.writerow(dict(case=name, route=route, group=group, x=x[j], y=y[j],
                                                dist_xy=dist[j], theta_geo_deg=theta[j], snr_db=snr_label, seed=seed,
                                                span_deg=span, actual_span_deg=actual_span, n_pose=len(sub), imu_k=k,
                                                xy_arm=xy, prior_sigma=sigma, e_prior=e_prior, window=window,
                                                window_miss=abs(e_prior) > window if window < 180 else False,
                                                channel=channel, err_deg=float(wrap(psi - yaw[j])), J=value,
                                                margin=margin, n_valid=n_valid))
    if row != max_curves:
        raise RuntimeError(f"Curve count mismatch: {name}: {row} != {max_curves}")
    curves.flush()
    return inventory, parity, dict(route=route, x=x, y=y, yaw_deg=yaw, s_full=sfull0, s_los=slo0,
                                   jac_yaw=jac[:, 2], sweep_indices=groups)


def run(root, out, receipt, only_case=None, analyze=True):
    verify(root, receipt)
    sys.path.insert(0, str(root / LUT / "retrieved/source/src"))
    from qclean_uwb.drivesim import hs_lut as L
    from qclean_uwb.drivesim import observation as O
    block = root / BLOCK
    freqs = np.load(block / "freqs_hz.npy", allow_pickle=False)
    lut = L.HsLut(dict(theta_deg=np.arange(0., 91., 2.), phi_deg=np.arange(-180., 180., 2.),
                       s=np.load(root / LUT / "INPUTS/hs_lut_2deg.npy", allow_pickle=False)))
    cases = json.loads((block / "BLOCK_C/CASES.json").read_bytes())
    inventories, parities, spatial = {}, {}, {}
    dump(out / "S1_J_GRID.json", dict(start_deg=-180, step_deg=.25, count=len(GRID), units="deg"))
    for c in cases:
        name = c["case"]
        if only_case is not None and name != only_case:
            continue
        inventories[name], parities[name], sp = evaluate_case(c, root, out, freqs, lut, L, O)
        if sp is not None:
            spatial[name] = sp
        dump(out / "S1_INVENTORY.json", inventories)
        dump(out / "S1_PARITY.json", parities)
    if not inventories:
        raise ValueError("No requested case found")
    if analyze and spatial:
        from s1_analysis import analyze as aggregate
        rho = aggregate(out, inventories, spatial)
        dump(out / "S1_RHO.json", rho)
    return parities


def aggregate_existing(root, out, receipt):
    """Recompute only spatial inputs and aggregate existing per-sweep outputs."""
    verify(root, receipt)
    from s1_analysis import analyze
    sys.path.insert(0, str(root / LUT / "retrieved/source/src"))
    from qclean_uwb.drivesim import hs_lut as L
    from qclean_uwb.drivesim import observation as O
    freqs = np.load(root / BLOCK / "freqs_hz.npy", allow_pickle=False)
    lut = L.HsLut(dict(theta_deg=np.arange(0., 91., 2.), phi_deg=np.arange(-180., 180., 2.),
                       s=np.load(root / LUT / "INPUTS/hs_lut_2deg.npy", allow_pickle=False)))
    block = root / BLOCK / "BLOCK_C"
    inventories = json.loads((out / "S1_INVENTORY.json").read_bytes())
    parities = json.loads((out / "S1_PARITY.json").read_bytes())
    spatial = {}
    for c in json.loads((block / "CASES.json").read_bytes()):
        name = c["case"]
        if not parities.get(name, {}).get("passed", False):
            continue
        s = json.loads((block / name / "SAMPLES.json").read_bytes())
        x, y, yaw = (np.array([r[k] for r in s]) for k in ("x", "y", "yaw_body_deg"))
        v = [O.observe(np.load(p, allow_pickle=False), freqs, None, None, tx=0)["s"]
             for p in (block / "FULL_RF" / f"H_{name}.npy", block / f"H_LoS_{name}.npy")]
        _, jac = L.s_model(lut, c["anchor_xyz"], c["robot_z"], x, y, np.radians(yaw),
                           c["mount_deg"], with_jac=True)
        spatial[name] = dict(route=name.split("_")[0], x=x, y=y, yaw_deg=yaw,
                             s_full=v[0], s_los=v[1], jac_yaw=jac[:, 2], sweep_indices=get_groups(s))
    rho = analyze(out, inventories, spatial)
    dump(out / "S1_RHO.json", rho)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    p.add_argument("--only-case")
    p.add_argument("--skip-analysis", action="store_true")
    p.add_argument("--aggregate-existing", action="store_true")
    a = p.parse_args()
    if a.aggregate_existing:
        aggregate_existing(a.inputs, a.out, a.receipt)
        return
    a.out.mkdir(parents=True, exist_ok=False)
    run(a.inputs, a.out, a.receipt, a.only_case, not a.skip_analysis)


if __name__ == "__main__":
    main()

