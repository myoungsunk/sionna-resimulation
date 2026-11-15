"""Post-hoc S2 diagnostics with frozen RF, common gate and component swaps."""

import argparse
from datetime import datetime, timezone
from itertools import product
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import numpy as np

from metrics_s2 import _summarize
from replay_s2 import geometry, parity, read_npz, sha, student_variance, validate_trace
from run_s2 import models
from verify_s2 import check_metric_rows, from_trace


FACTORS = ("range_mean", "range_variance", "polarization_mean", "polarization_variance")
COMBOS = tuple("".join(str(bit) for bit in bits) for bits in product((0, 1), repeat=4))
EXTRAS = {
    "R2_S1": ("R2", "S1", None),
    "R1_S2": ("R1", "S2", None),
    "E2": ("R2", "S2", None),
    "S3_GAUSS": ("R2", "S3", None),
    "S3_FIXED_BASE_T": ("R2", "S3", "fixed_base"),
    "E3": ("R2", "S3", "cumulative"),
}
STAGES = ("2a", "2b", "2c")
ROUTES = ("R2", "R4", "R5")


def read_json(path):
    return json.loads(path.read_bytes())


def write_json(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")


def ensure_hash(path, expected):
    actual = sha(path)
    if actual != expected:
        raise ValueError(f"Hash mismatch: {path} ({actual})")


def read_input(info):
    path = Path(info["path"])
    ensure_hash(path, info["sha256"])
    return read_npz(path)


def fixed_base_variance(residual, projected_var, base, nu):
    variance = base
    for _ in range(3):
        weight = (nu + 1.) / (nu + residual**2 / (projected_var + variance))
        variance = base / weight
    return variance


def replay_swaps(packet, mask, core, online, model, spec, learned, nu):
    names = COMBOS + tuple(EXTRAS)
    switches = np.asarray([tuple(int(bit) for bit in name) for name in COMBOS] +
                          [(1, 1, 1, 1)] * len(EXTRAS), dtype=bool)
    n = len(packet["t"])
    start = np.r_[packet["x0"][:3], 0.]
    x = np.tile(start, (len(names), 1))
    P = np.repeat(packet["P0"][None], len(names), axis=0)
    controls = {key: packet[key] for key in ("ds", "gy", "dt")}
    fields = {"x": (4,), "P": (4, 4), "prior": (4,), "Pprior": (4, 4),
              "h": (2,), "H": (2, 4), "mu": (2,), "Rvar": (2, 2), "Reff": (2, 2),
              "K": (4, 2), "nu": (2,)}
    values = {field: np.empty((n, len(names), *shape)) for field, shape in fields.items()}
    anchor = np.asarray(spec["anchor"][:2])
    for k, measurement in enumerate(packet["z"]):
        rho = np.hypot(*(x[:, :2] - anchor).T)
        native_scale = np.interp(rho, [0., 1.5, 3., 6., 10.], [.011, .020, .050, .120, .240])
        priors = [online.predict(core, x[i], P[i], k, controls) for i in range(len(names))]
        xp, pp = (np.stack(value) for value in zip(*priors, strict=True))
        h, H = model.batch(xp, spec)
        d, bearing = geometry(xp, spec)
        r_predictions = {key: learned[key].predict(bearing, d) for key in ("R1", "R2")}
        s_predictions = {key: learned[key].predict(bearing, d)[1] for key in ("S1", "S2", "S3")}
        mu = np.tile(packet["muMB"][k], (len(names), 1))
        Rvar = np.repeat(packet["R"][k][None], len(names), axis=0)
        Rvar[:, 1, 1] += native_scale**2
        for i, name in enumerate(names):
            r_model, s_model, _ = EXTRAS.get(name, ("R1", "S1", None))
            r_mean, r_std = r_predictions[r_model]
            if switches[i, 0]:
                mu[i, 0] = r_mean[i]
            if switches[i, 1]:
                Rvar[i, 0, 0] = r_std[i]**2
            if switches[i, 2]:
                mu[i, 1] = 0.
            if switches[i, 3]:
                Rvar[i, 1, 1] = s_predictions[s_model][i]**2
        innovation = measurement - h - mu
        R = Rvar.copy()
        K = np.empty((len(names), 4, 2))
        for i, name in enumerate(names):
            method = EXTRAS.get(name, (None, None, None))[2]
            if method:
                variance = H[i, 1] @ pp[i] @ H[i, 1]
                reweight = student_variance if method == "cumulative" else fixed_base_variance
                R[i, 1, 1] = reweight(innovation[i, 1], variance, Rvar[i, 1, 1], nu)
            x[i], P[i], K[i], _ = online.joseph(xp[i], pp[i], H[i], innovation[i], R[i], mask[k], 1.)
        for key, value in zip(fields, (x, P, xp, pp, h, H, mu, Rvar, R, K, innovation), strict=True):
            values[key][k] = value
    return {name: {key: value[:, i] for key, value in values.items()} | {"mask": mask}
            for i, name in enumerate(names)}


def summarize(trace, truth):
    rows = from_trace(trace, truth)
    metrics = _summarize(rows)
    metrics["median_heading_sigma_deg"] = float(np.median(np.rad2deg(np.sqrt(trace["P"][:, 2, 2]))))
    mask = trace["mask"]
    for channel, index in (("r", 0), ("s", 1)):
        metrics[f"accepted_sigma_{channel}"] = float(np.median(np.sqrt(trace["Reff"][mask, index, index])))
        metrics[f"accepted_gain_abs_heading_{channel}"] = float(np.median(np.abs(trace["K"][mask, 2, index])))
    return metrics, rows


def contributions(scores, key):
    effect = {}
    for i, factor in enumerate(FACTORS):
        marginal = 0.
        for combo in COMBOS:
            if combo[i] == "0":
                new = combo[:i] + "1" + combo[i + 1:]
                weight = 1 / (len(FACTORS) * math.comb(len(FACTORS) - 1, combo.count("1")))
                marginal += weight * (scores[new][key] - scores[combo][key])
        effect[factor] = marginal
    expected = scores["1111"][key] - scores["0000"][key]
    if not math.isclose(sum(effect.values()), expected, rel_tol=1e-11, abs_tol=1e-12):
        raise ValueError(f"Factorial aggregation mismatch for {key}")
    return effect


def evaluate(args):
    run, native, fit, out, governance = (p.resolve() for p in
                                        (args.run, args.native, args.fit, args.out, args.governance))
    out.mkdir(parents=True, exist_ok=False)
    start = datetime.now(timezone.utc).isoformat()
    contract_path = run / "RUN_CONTRACT.json"
    contract = read_json(contract_path)
    contract_hash = sha(contract_path)
    for name, digest in contract["governance"].items():
        ensure_hash(governance / name, digest)
    for name in ("metrics_s2.py", "replay_s2.py"):
        ensure_hash(Path(__file__).with_name(name), contract["s2_code_sha256"][name])
    for name, digest in contract["native_source_hashes"].items():
        ensure_hash(native / Path(name.replace("\\", "/")), digest)
    ensure_hash(fit, contract["fit_sha256"])
    learned = models(read_json(fit))
    sys.path.insert(0, str(native / "src"))
    from qclean_uwb.fp_sc.e0_baseline import SPEC, load_original_model

    write_json(out / "DIAGNOSTIC_CONTRACT.json", {
        "question_id": "G1-CHAR-002-S2-ACCURACY-DIAG", "role": "IMPLEMENTER",
        "started_utc": start, "command": [sys.executable, *sys.argv],
        "python": sys.version, "numpy": np.__version__,
        "workspace_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent, text=True).strip(),
        "script_sha256": sha(__file__), "s2_run_contract_sha256": contract_hash,
        "governance": contract["governance"], "spec_commit": contract["spec_commit"],
        "native_commit": contract["native_commit"], "frozen_fit_sha256": sha(fit),
        "stages": (args.stage,) if args.stage else STAGES,
        "routes": ROUTES, "seals": contract["seals"],
        "controls": "same packets, initialization, motion, Q, observer and archived E0 gate",
        "factor_bits": dict(enumerate(FACTORS)),
        "factor_direction": "0=native E0, 1=E1, including zero polarization mean",
        "extras": EXTRAS, "diagnostic_only": True, "parity_limit": 1e-10,
        "claim_boundary": "Post-hoc performance on frozen seed10 cases with frozen E0 gate only.",
    })
    core, online, model, _ = load_original_model(native)
    for stage in (args.stage,) if args.stage else STAGES:
        stage_dir = run / stage
        spec = SPEC | {"anchor": (4., 0., 2.65)} if stage == "2c" else SPEC
        exe = read_json(stage_dir / "EXECUTION.json")
        if exe["status"] != "PASS_EXECUTION" or exe["run_contract_sha256"] != contract_hash:
            raise ValueError(f"Existing execution evidence mismatch: {stage}")
        for name in ("INPUTS.json", "RESULTS.json"):
            ensure_hash(stage_dir / name, exe["outputs"][name])
        inputs = read_json(stage_dir / "INPUTS.json")
        official = read_json(stage_dir / "RESULTS.json")["by_case"]
        result = {}
        for route in ROUTES:
            stop_file = os.environ.get("MANAGED_PROCESS_STOP_FILE")
            if stop_file and Path(stop_file).exists():
                raise SystemExit("Stopped before next replay")
            packet = read_input(inputs[route]["online"])
            if np.any(packet["R"][:, (0, 1), (1, 0)] != 0):
                raise ValueError("Factorial swaps require diagonal native R")
            reference = {}
            for arm in ("E0", "E1", "E2", "E3", "E4"):
                name = f"{route}_{arm}_trace.npz"
                ensure_hash(stage_dir / name, exe["outputs"][name])
                reference[arm] = read_npz(stage_dir / name)
            traces = replay_swaps(packet, reference["E0"]["mask"], core, online, model,
                                  spec, learned, contract["student_t"]["nu/E3-E4"])
            checks = {}
            for variant, arm in (("0000", "E0"), ("1111", "E1"), ("E2", "E2"), ("E3", "E3")):
                trace = traces[variant]
                checks[arm] = parity(trace, {key: reference[arm][key] for key in trace})
            evaluator = read_input(inputs[route]["evaluator"])
            for trace in (packet, *reference.values()):
                if any(not np.array_equal(trace[key], evaluator[key]) for key in ("t", "pose_id")):
                    raise ValueError(f"Wrong evaluator grid: {stage}/{route}")
            scores = {}
            for name, trace in (traces | {"E4": reference["E4"]}).items():
                if name != "E4":
                    validate_trace(trace)
                scores[name], rows = summarize(trace, evaluator["truth"])
                if name in ("0000", "1111", "E2", "E3", "E4"):
                    arm = {"0000": "E0", "1111": "E1"}.get(name, name)
                    check_metric_rows(rows, official[route][arm])
            result[route] = {
                "scores": scores,
                "e1_minus_e0_factor_contributions": {
                    key: contributions(scores, key)
                    for key in ("heading_rmse_deg", "xy_rmse_cm", "pose95_coverage", "heading95_coverage")
                },
                "parity": checks,
                "input_receipts": inputs[route],
            }
            print(f"PASS {stage}/{route}", flush=True)
            write_json(out / f"{stage}_{route}.json", result[route])
        write_json(out / f"{stage}.json", result)
    write_json(out / "EXECUTION.json", {
        "status": "PASS_EXECUTION_AND_SELF_CHECK", "exit_code": 0,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "outputs": {p.name: sha(p) for p in out.glob("*.json")},
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "native", "fit", "out", "governance"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--stage", choices=STAGES)
    evaluate(parser.parse_args())
