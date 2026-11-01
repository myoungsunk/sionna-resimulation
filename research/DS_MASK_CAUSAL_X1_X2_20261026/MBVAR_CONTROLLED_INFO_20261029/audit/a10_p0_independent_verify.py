"""Independent A010-P0 artifact audit. Reads committed evidence; imports no experiment code.

No historical run status is modified. This is an independent numerical *path*,
not a separate scientific-auditor signature from an independent human/agent.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd


def sha(b):
    return hashlib.sha256(b).hexdigest()


def sha_array(x):
    x = np.ascontiguousarray(np.asarray(x))
    return sha(x.dtype.str.encode() + str(x.shape).encode() + x.tobytes())


def require(cond, message, failures):
    if not bool(cond):
        failures.append(message)


def check(gen: Path, abl: Path):
    failures = []
    factor = json.loads((gen / "A010_GENERATOR_FACTOR_LOCK.json").read_text())
    Lbytes = (gen / "A010_LHALF_WORLDPOSE_V2.npy").read_bytes()
    Zbytes = (gen / "A010_CANONICAL_INPUTS.zip").read_bytes()
    require(sha(Lbytes) == factor["sha256"], "LOCK_LHALF_HASH", failures)
    require(sha(Zbytes) == factor["canonical_inputs"]["sha256"], "LOCK_CANON_HASH", failures)
    L = np.load(io.BytesIO(Lbytes), allow_pickle=False)
    require(L.shape == (180, 180) and L.dtype.str == "<f8", "LOCK_L_SHAPE_DTYPE", failures)
    require(np.isfinite(L).all(), "LOCK_L_FINITE", failures)
    M = L @ L.T
    d = float(np.max(np.abs(np.diag(M) - 1)))
    require(d <= 1e-10, "LOCK_L_DIAG", failures)
    require(np.max(np.abs(M - M.T)) <= 1e-12, "LOCK_L_SYMMETRY", failures)
    with zipfile.ZipFile(io.BytesIO(Zbytes)) as zf:
        with np.load(io.BytesIO(zf.read("canonical.npz")), allow_pickle=False) as zz:
            data = {k: zz[k] for k in zz.files}
    S = pd.read_csv(gen / "A010_INPUT_CANONICAL_SHA.csv")
    expected = S[(S.array != "z_S1V3_receipt") & (S.array != "Sigma_model_fp_check")]
    missing, wrong = [], []
    for r in expected.itertuples():
        key = f"{r.case}|{r.array}"
        if key not in data:
            missing.append(key)
        elif sha_array(data[key]) != r.sha256:
            wrong.append(key)
    require(len(expected) == 48 and len(data) == 48, "INPUT_COUNT", failures)
    require(not missing and not wrong, "INPUT_ARRAY_SHA", failures)
    # Independent 60-pose law check; S1V2 world-ledger starts with LOW.
    X = data["K1|poses"]
    require(np.array_equal(X, data["K3|poses"]), "POSE_LOW_MATCH", failures)
    require(np.array_equal(data["K2|poses"], data["K4|poses"]), "POSE_REV_MATCH", failures)
    dp = X[:, None, :2] - X[None, :, :2]
    dyaw = X[:, None, 2] - X[None, :, 2]
    K_low = np.exp(-np.sum(dp * dp, axis=-1) / (2 * 0.5**2)
                   - 2 * np.sin(dyaw / 2)**2 / math.radians(20)**2)
    low_law_error = float(np.max(np.abs(M[:60, :60] - K_low)))
    require(low_law_error <= 1e-10, "POSE_KERNEL_LOW_BLOCK", failures)
    input_checks = {}
    for cid in ("K1", "K2", "K3", "K4"):
        ok = True
        for key in ("z", "x0", "ds_m", "gy_m", "taps", "Sigma_true", "Sigma_model"):
            a = data[f"{cid}|{key}"]
            ok &= bool(np.isfinite(a).all())
        for suffix in ("Sigma_true", "Sigma_model"):
            a = data[f"{cid}|{suffix}"]
            ok &= bool(a.shape == (120, 120)
                       and np.max(np.abs(a - a.T)) < 1e-11
                       and np.linalg.eigvalsh(a)[0] > 0)
        input_checks[cid] = ok
        require(ok, f"INPUT_PSD_FINITE_{cid}", failures)
    # From the independent aggregate, verify original committed shards are represented.
    df = pd.read_csv(abl / "A010_DEV2_ABLATION.csv")
    xcols = [f"xend_{j}" for j in range(4)]
    pcols = [f"C10rot_{i}{j}" for i in range(4) for j in range(i, 4)]
    require(len(df) == 88, "ABL_88_ROWS", failures)
    require(not df.duplicated(["case", "rep", "variant"]).any(), "ABL_DUPLICATES", failures)
    rep_check = {}
    nees_errs = []
    for _, r in df.iterrows():
        P = np.zeros((4, 4))
        for i in range(4):
            for j in range(i, 4):
                P[i, j] = P[j, i] = float(r[f"C10rot_{i}{j}"])
        ev = np.array([float(r[f"e_{a}"]) for a in ("rad", "tan", "psi", "bg")])
        require(np.linalg.eigvalsh(P)[0] > 0, "POSTERIOR_PD", failures)
        nees = float(ev @ np.linalg.solve(P, ev))
        nees_errs.append(abs(nees - float(r["nees4_C10"])) / max(abs(nees), 1e-12))
    require(max(nees_errs) <= 1e-8, "NEES_FROM_FULL_C10", failures)
    for cid in ("K1", "K2", "K3", "K4"):
        a = df[(df.case == cid) & (df.rep == "A")].set_index("variant")
        b = df[(df.case == cid) & (df.rep == "B")].set_index("variant")
        require(len(a) == len(b) == 11 and set(a.index) == set(b.index),
                f"REPLICATE_KEYS_{cid}", failures)
        keys = a.index.intersection(b.index)
        c = float((a.loc[keys, "cost"] - b.loc[keys, "cost"]).abs().max())
        dx = float((a.loc[keys, xcols] - b.loc[keys, xcols]).abs().max().max())
        pa = a.loc[keys, pcols].to_numpy(float)
        pb = b.loc[keys, pcols].to_numpy(float)
        pp = float(np.max(np.abs(pa - pb) / np.maximum(np.maximum(np.abs(pa), np.abs(pb)), 1e-300)))
        rep_check[cid] = {"rows": len(keys), "cost_abs_max": c,
                          "state_abs_max": dx, "C10_full_rel_max": pp}
        require(c <= 1e-6 and pp <= 1e-3 and dx <= 1e-6,
                f"REPLICA_STRICT_{cid}", failures)
    # K2 has two distinct close solutions, verified from the actual coordinates.
    modes = pd.read_csv(abl / "A010_MODE_PROFILE.csv")
    mode_stats = {}
    DREF = np.array([.02, .02, math.radians(.25), math.radians(.01)])
    for rep in ("A", "B"):
        subset = modes[(modes.rep == rep) & (modes.polish == "deep")
                       & (~modes.oracle_only.astype(bool))]
        base = subset[subset.start == "psi+0"].iloc[0]
        best = subset.loc[subset.cost.idxmin()]
        dx = np.array([best[k] - base[k] for k in xcols], dtype=float)
        dx[2] = (dx[2] + math.pi) % (2 * math.pi) - math.pi
        dist = float(np.max(abs(dx) / DREF))
        gap = float(best.cost - base.cost)
        mode_stats[rep] = {"start": best.start, "delta_cost": gap,
                           "distance_dref": dist,
                           "x_difference_m": float(dx[0])}
        require(best.start == "psi+2" and -1 < gap < 0 and dist > 2,
                f"K2_NONTRUTH_AMBIGUITY_{rep}", failures)
    manifest_checks = {}
    for part, root in [("GEN", gen), ("ABL", abl)]:
        manifest = json.loads((root / "MANIFEST.json").read_text())
        bad = []
        for fn, expected_sha in manifest.get("output_sha256", {}).items():
            file = root / Path(fn).name
            if not file.is_file() or sha(file.read_bytes()) != expected_sha:
                bad.append(Path(fn).name)
        manifest_checks[part] = {"outputs": len(manifest.get("output_sha256", {})),
                                 "bad_sha": bad, "execution_status": manifest.get("execution_status")}
        require(not bad and manifest["execution_status"] == "PASS",
                f"MANIFEST_{part}", failures)
    fixtures = json.loads((abl / "A010_NEGATIVE_FIXTURES.json").read_text())
    require(all(bool(v["detected"]) for v in fixtures.values()),
            "NEGATIVE_FIXTURE_STATUS", failures)
    return {"status": "PASS_NUMERICAL_RECALC_ONLY" if not failures else "FAIL",
            "independence": "separate code path and GitHub runner; same assistant session is not distinct proposer/auditor signature",
            "n_arrays": len(expected), "n_abl_rows": len(df),
            "factor_sha": sha(Lbytes), "canonical_sha": sha(Zbytes),
            "factor_unit_diagonal_error": d, "low60_kernel_max_error": low_law_error,
            "input_checks": input_checks, "replica": rep_check,
            "NEES_recomputed_rel_max": max(nees_errs),
            "near_minima_K2": mode_stats,
            "manifest": manifest_checks,
            "negative_fixtures": fixtures,
            "failures": failures,
            "release_scope": "A010-P0 forensic only, not FROZEN A010, not DEV3, not HOLDOUT2, not RT"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--gen", type=Path, required=True)
    p.add_argument("--abl", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    result = check(a.gen, a.abl)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({"status": result["status"],
                      "failures": result["failures"],
                      "NEES_rel": result["NEES_recomputed_rel_max"],
                      "mode": result["near_minima_K2"]}, ensure_ascii=False))
    return 0 if result["status"] == "PASS_NUMERICAL_RECALC_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
