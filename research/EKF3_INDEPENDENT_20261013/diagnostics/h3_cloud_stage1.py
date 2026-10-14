#!/usr/bin/env python3
"""Frozen G3 numerical failure: GitHub Actions Phase-1 reproduction and hypothesis audit."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
import time
import traceback
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
from numpy.polynomial.hermite import hermgauss

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ARCHIVE = HERE / "h3_offline" / "results" / "H3_OFFLINE_20261014_01a1380d"
sys.path.insert(0, str(ARCHIVE))
import d6_d9_common as c
import h3_offline as h
h.REPO = REPO
EXPECTED_TV = 0.38706501555739936
CASE, CONDITION, LEVEL, SEED, SAMPLE = "R2_aA_m0", "gyro_bias", 2, 0, 978


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probabilities(lp):
    if not np.isfinite(lp).all():
        raise RuntimeError("Nonfinite log posterior")
    return np.exp(lp - logsumexp(lp))


def total_variation(p, q):
    if p.shape != q.shape:
        raise RuntimeError("Posterior TV compared across unequal grids")
    return float(np.abs(p - q).sum() / 2)


def frozen_snapshot():
    p0 = c.check_inputs(full_p0=False)
    case = next(v for v in p0["cases"] if v["id"] == CASE)
    t, truth, pose_ids, motion, _ = c.case_motion(p0, case, SEED, LEVEL, CONDITION)
    if len(t) <= SAMPLE or abs(float(t[SAMPLE]) - 195.6) > 1e-9:
        raise RuntimeError("Original sample/time mismatch")
    f = c.DiagnosticFilter(c.initial_state(truth[0], SEED))
    X, P = [], []
    for i in range(len(t)):
        if i:
            f.predict(float(motion["ds_odom"][i]),
                      float(motion["dtheta_gyro"][i]),
                      float(motion["dt_s"][i]))
        X.append(f.pose.copy())
        P.append(f.Ppose.copy())
    X, P = np.asarray(X), np.asarray(P)
    m = t >= 30
    d = h.wrap(X[m, 2] - truth[m, 2])
    dr_rmse = float(np.sqrt(np.mean(d*d)) * h.RAD)
    with (ARCHIVE / "STAGE4_SMOKE_01" / "D0_PARITY.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        matches = [row for row in csv.DictReader(stream)
                   if row["case"] == CASE and row["condition"] == CONDITION
                   and int(row["level"]) == LEVEL and int(row["seed"]) == SEED]
    if len(matches) != 1:
        raise RuntimeError("Archived D0 parity row missing")
    expected = float(matches[0]["heading_rmse_deg"])
    if abs(dr_rmse - expected) > 1e-8:
        raise RuntimeError(f"D0 parity failed: current={dr_rmse}; archived={expected}")
    lut = c.original_lut(p0)
    obs = c.rf_case(p0, case, "los", c.spectrum(p0), pose_ids)
    zs = float(obs["s"][SAMPLE])
    zr = float(obs["range_raw_m"][SAMPLE] - c.B_OLD)
    x, p = X[SAMPLE], P[SAMPLE]
    if not np.isfinite([zs, zr]).all() or np.linalg.eigvalsh(p).min() <= 0:
        raise RuntimeError("Invalid RF input / non-PD prior")
    inputs = [
        REPO / case["los_path"], REPO / case["samples_path"],
        REPO / next(v["path"] for v in p0["routes"] if v["id"] == "R2"),
        REPO / "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy",
        REPO / "research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json",
    ]
    snapshot = dict(
        case=CASE, condition=CONDITION, level=LEVEL, seed=SEED,
        channel="los", range_model="B_OLD", sample=SAMPLE,
        time_s=float(t[SAMPLE]), x=x.tolist(), P=p.tolist(),
        s=zs, r_m=zr, dr_heading_rmse_deg=dr_rmse,
        frozen_input_sha256={str(q.relative_to(REPO)): sha256(q) for q in inputs},
    )
    return snapshot, case, lut, x, p, zs, zr


def range_only_logfun(x, p, zr, case, order):
    gh, gw = hermgauss(order)
    xx, yy = np.meshgrid(gh, gh, indexing="ij")
    nodes = np.stack([xx.ravel(), yy.ravel()], axis=1) * math.sqrt(2)
    logweights = np.log(np.outer(gw, gw).ravel() / math.pi)
    var = p[2, 2]
    cross = p[:2, 2] / var
    cov = p[:2, :2] - np.outer(p[:2, 2], p[2, :2]) / var
    transformed = nodes @ np.linalg.cholesky(cov).T
    anchor = np.asarray(case["anchor"][:2])
    dz2 = (float(case["robot_z_m"]) - float(case["anchor"][2]))**2

    def fn(psis):
        psis = np.asarray(psis)
        pieces = []
        for start in range(0, psis.size, 128):
            a = psis.reshape(-1)[start:start+128]
            d = h.wrap(a-x[2])
            xy = x[:2] + d[:, None, None]*cross + transformed[None, :, :]
            slant = np.sqrt(np.sum((xy-anchor)**2, axis=-1) + dz2)
            ll = -.5*(zr-slant)**2/c.RR
            pieces.append(logsumexp(ll+logweights, axis=1) +
                          h.wrapped_logprior(a, x[2], var))
        return np.concatenate(pieces).reshape(psis.shape)
    return fn


def family(kind, case, lut, x, p, zs, zr, orders, grid, output):
    rows = []
    for order in orders:
        before = time.perf_counter()
        if kind == "JOINT":
            fn = h.integrated_logfun(lut, x, p, zs, zr, case, np.zeros(2),
                                     np.diag([c.RS, c.RR]), order)
        elif kind == "S_ONLY":
            fn = h.integrated_logfun(lut, x, p, zs, zr, case, np.zeros(2),
                                     np.diag([c.RS, c.RR]), order,
                                     conditional=True)
        elif kind == "RANGE_ONLY":
            fn = range_only_logfun(x, p, zr, case, order)
        else:
            raise ValueError(kind)
        lp = fn(grid)
        pr = probabilities(lp)
        record = dict(
            kind=kind, order=order, angle_bins=len(grid),
            log_evidence=float(logsumexp(lp)+math.log(2*math.pi/len(grid))),
            MAP_grid_rad=float(grid[np.argmax(pr)]),
            time_s=time.perf_counter()-before,
            tv_previous=total_variation(pr, rows[-1]["prob"]) if rows else None,
            prob=pr, logp=lp,
        )
        rows.append(record)
        print(f"{kind} GH{order}: TV={record['tv_previous']}; "
              f"wall={record['time_s']:.2f}s", flush=True)
    if len(rows) >= 2:
        np.savez_compressed(output/(kind.lower()+"_posterior.npz"),
                            angle_rad=grid, order41=rows[0]["prob"],
                            order65=rows[1]["prob"], log41=rows[0]["logp"],
                            log65=rows[1]["logp"])
    return rows


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    report = {
        "stage": 1, "status": "RUNNING", "scientific_PASS": False,
        "recursive_fusion": "NOT_RUN", "frozen_gh41_gh65_TV": EXPECTED_TV,
        "frozen_position_TV_gate": 0.001,
        "hypotheses": [
            "H0: GH41->65 joint TV ~0.387065 is reproducible",
            "H1: Range-only TV>0.001, S-only TV<=0.001",
            "H2: original Range NIS gate rejects sample 978",
        ],
        "confirmed": [], "contradicted": [], "unresolved": [],
        "next_action": "STOP_IF_INPUT_OR_NUMERICAL_GATE_FAILS",
    }
    diagnostics = []
    exit_code = 2
    try:
        snapshot, case, lut, x, P, zs, zr = frozen_snapshot()
        report["snapshot"] = snapshot
        report["commit_sha"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip()
        import scipy
        report["environment"] = dict(python=sys.version, numpy=np.__version__,
                                     scipy=scipy.__version__)
        _, _, range_status = h.range_update(x, P, zr, case, 0.0, c.RR, True)
        predicted, H = c.range_h(x, case["anchor"], case["robot_z_m"])
        nis = float((zr-predicted)**2/(H@P@H+c.RR))
        report["range_gate"] = dict(status=range_status, NIS=nis,
                                    residual_m=zr-predicted)
        if range_status == "rejected_NIS":
            report["confirmed"].append("H2: original Range gate rejects")
        else:
            report["contradicted"].append("H2: gate is not rejected")

        with (ARCHIVE/"STAGE4_SMOKE_01"/"SMOKE_PARTIAL.csv").open(
            newline="", encoding="utf-8-sig"
        ) as stream:
            originals = [v for v in csv.DictReader(stream)
                         if v["case"] == CASE and
                         v["condition"] == CONDITION and int(v["level"]) == LEVEL and
                         int(v["seed"]) == SEED and
                         v["channel"] == "los" and v["range_model"] == "B_OLD" and
                         int(v["sample"]) == SAMPLE and v["method"] == "G0"]
        if len(originals) != 1:
            raise RuntimeError("Frozen Stage4 G0 reference missing")
        g0 = h.posterior(h.fixed_logfun(lut, x, P, zs, case))
        g0_error = float(abs(h.wrap(g0["MAP"]-float(originals[0]["MAP_rad"]))))
        report["G0_MAP_parity_rad"] = g0_error
        if g0_error > 1e-7:
            raise RuntimeError(f"G0 MAP parity failed: {g0_error}")

        grid = np.linspace(-math.pi, math.pi, 1440, endpoint=False)
        groups = {}
        for kind in ("JOINT", "S_ONLY", "RANGE_ONLY"):
            rows = family(kind, case, lut, x, P, zs, zr, (41,65), grid, out)
            groups[kind] = rows
            diagnostics += [{k:v for k,v in row.items() if k not in ("prob","logp")}
                            for row in rows]
        observed = {kind:float(rows[-1]["tv_previous"]) for kind,rows in groups.items()}
        report["TV_41_65"] = observed
        report["joint_TV_minus_archived"] = observed["JOINT"]-EXPECTED_TV
        h0 = abs(observed["JOINT"]-EXPECTED_TV)<=0.005 and observed["JOINT"]>0.001
        h1 = observed["RANGE_ONLY"]>0.001 and observed["S_ONLY"]<=0.001
        report["confirmed" if h0 else "contradicted"].append("H0: archived joint TV")
        report["confirmed" if h1 else "contradicted"].append(
            "H1: range-only instability / S-only stability"
        )
        if not h0 or not h1 or range_status != "rejected_NIS":
            # One bounded follow-up probe; no auto retuning / speculative progression.
            followup = {}
            for kind, rows in groups.items():
                low = family(kind, case, lut, x, P, zs, zr, (25,), grid, out)[0]
                diagnostics.append({k:v for k,v in low.items() if k not in ("prob","logp")})
                followup[kind] = dict(
                    gh25_gh41_TV=total_variation(low["prob"], rows[0]["prob"]),
                    gh25_log_evidence=low["log_evidence"],
                    gh41_log_evidence=rows[0]["log_evidence"],
                    gh65_log_evidence=rows[1]["log_evidence"],
                )
            report["followup_gh25"] = followup
            report["status"] = "HYPOTHESIS_CONTRADICTED_STOP"
            report["next_action"] = ("Review input/G0 parity and GH25/41/65 evidence; "
                                     "re-specify the cause before Phase2.")
            report["unresolved"].append("Numerical cause not uniquely identified.")
            exit_code = 3
        else:
            report["status"] = "PASS_PHASE1_REPRODUCTION_AND_RANGE_EVIDENCE"
            report["next_action"] = ("Implement independent reference integrator in Phase2, "
                                     "then validate unchanged TV=0.001 threshold.")
            report["unresolved"].append(
                "Whether an independent integral reference converges; G2/G3 accuracy.")
            exit_code = 0
    except Exception as exc:
        report["status"] = "FAIL_CLOSED_BLOCKED"
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
        report["unresolved"].append("Data, code, or input parity blocks diagnosis.")
        exit_code = 2
    finally:
        if diagnostics:
            fields = list(dict.fromkeys(key for row in diagnostics for key in row))
            with (out/"STAGE1_DIAGNOSTIC.csv").open(
                "w", newline="", encoding="utf-8"
            ) as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(diagnostics)
        (out/"STAGE1_REPORT.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8")
        print("FINAL_RECEIPT "+json.dumps({
            key:report[key] for key in
            ("status","confirmed","contradicted","unresolved","next_action")
        }, ensure_ascii=False), flush=True)
    return exit_code


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,required=True)
    return run(parser.parse_args().out)


if __name__ == "__main__":
    sys.exit(main())
