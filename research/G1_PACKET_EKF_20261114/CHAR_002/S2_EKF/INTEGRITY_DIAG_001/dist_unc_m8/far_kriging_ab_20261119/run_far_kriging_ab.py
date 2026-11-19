#!/usr/bin/env python3
"""Paired Corridor F2SKRWV POWER-vs-far-Kriging EKF replay.

Requires the frozen original M7/M8 workspace and its LFS/NPZ inputs:
  /home/claude/m8/, /home/claude/m8cal/, /home/claude/rel/
Run:
  python run_far_kriging_ab.py smoke
  python run_far_kriging_ab.py explore
This program never changes any frozen file and fails closed on baseline
POINT_B.csv parity. All Kriging inference uses EKF PRIOR, not evaluator truth.
"""
import csv
import json
import math
import sys
import os
from pathlib import Path
import numpy as np

M8 = Path("/home/claude/m8")
M8CAL = Path("/home/claude/m8cal")
ROOT = Path("/home/claude/sionna-resimulation")
S3_BASE = ROOT / "research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/dist_unc_m8/step3_fair"
RESULTS = M8 / "far_kriging_ab_20261119"

for p in (M8, M8CAL, ROOT):
    if not p.exists():
        raise SystemExit(f"EXECUTION_BLOCKED: required frozen workspace missing: {p}")
sys.path[:0] = [str(M8CAL), str(M8), str(ROOT)]

import common as C
import krige_online as KO
import m8_replay as M
import m8s3_score as S

ROUTES = ("R2", "R4", "R5")
CONDS = ("B0", "L2_GYRO_ARW")
BASE = "F2SKRWV"
FAR = "F2SKRWV_FAR_K"
ARMS = ("H2", "H2S", BASE, FAR)
ZERO = dict(knots_m=[0., 20.], sigma_b=[0., 0.])
S.ARMS = ARMS
S.REFS = ("H2", "H2S")
PAIR_PARAMS = ("heading_rmse_deg", "xy_rmse_cm", "pose95_coverage",
               "heading95_coverage", "mean_nees3")

def asjson(v):
    if hasattr(v, "item"):
        return v.item()
    if hasattr(v, "tolist"):
        return v.tolist()
    raise TypeError(type(v).__name__)

def baseline_packet(p, mu_r, mu_s, rrr, rss):
    # Adapted exactly from frozen run_m8s3.sweep_packet, with no
    # donor calibration field, evaluator label or selection of observations.
    q = {k: p[k] for k in ("t", "pose_id", "z", "x0", "P0", "ds", "gy", "dt")}
    q["muMB"] = np.c_[mu_r, mu_s]
    q["muBASE"] = q["muMB"].copy()
    q["D"] = np.zeros(len(p["t"]))
    R = np.zeros((len(p["t"]), 2, 2))
    R[:, 0, 0] = rrr
    R[:, 1, 1] = rss
    q["R"] = R
    return q

def load_frozen():
    for p in (M8CAL / "SWEEP_CAL_B.npz", M8CAL / "KRIGE_PARAMS.json",
              M8CAL / "SWEEP_FEATURES.csv.gz",
              M8CAL / "SWEEP_TABLE_V.json", S3_BASE / "tables/POINT_B.csv"):
        if not p.is_file():
            raise SystemExit(f"EXECUTION_BLOCKED: frozen input missing: {p}")
    B = np.load(M8CAL / "SWEEP_CAL_B.npz")
    v = json.loads((M8CAL / "SWEEP_TABLE_V.json").read_text())
    table = {k:v[k] for k in ("edges", "c1", "c0")}
    points = {}
    with (S3_BASE / "tables/POINT_B.csv").open(newline="") as fp:
        for row in csv.DictReader(fp):
            key = (row["cond"], int(row["seed"]), row["arm"], row["group"])
            points[key] = {k:float(row[k]) for k in PAIR_PARAMS}
    return B, table, points

def static_policy_check(far_mu):
    # The only independent knob must be the distance threshold (6 -> 10 m).
    old = KO.krige_s
    try:
        KO.krige_s = lambda *args, **kwargs: -0.789
        base = KO.make_fn(far_mu, near_limit=6.0)
        cand = KO.make_fn(far_mu, near_limit=10.0)
        nav = np.array([5., 0., 0., 0.])
        for rho in (0.1, 2.99, 3., 5.999, 6., 7.99, 9.99, 10.0, 11.0):
            ov0, ov1 = base(nav,rho,0), cand(nav,rho,0)
            if rho < 6.0:
                assert ov0 == ov1 == -0.789
            elif rho < 10.:
                assert ov0 == float(far_mu[0]) and ov1 == -0.789
            else:
                assert ov0 == ov1 == float(far_mu[0])
    finally:
        KO.krige_s = old

def report_one(cond, seed, env, scorer, B, table, published, *,
               allow_baseline_mismatch=False, trace_dir=None):
    from_trace, scores_with_blocks, branch_metrics = scorer
    truth, times, traces = {}, {}, {}
    dmax = 0.
    far_count = {}
    for route in ROUTES:
        original = C.packet(cond, seed, route)
        truth[route] = C.TRUTH[route]["truth"]
        times[route] = original["t"]
        tr = {}
        tr["H2"] = C.R7.replay(original, env, "H2",
                               **C.m7_kwargs("H2", route, cond, "own"))
        mu_r,mu_s,rrr,rss = (B[f"{route}/{k}"] for k in ("mu_r", "mu_s", "Rrr", "Rss"))
        pk = baseline_packet(original, mu_r, mu_s, rrr, rss)
        tr["H2S"] = C.R7.replay(pk, env, "H2", condition=cond,
                                rref_policy="own", sigma_b=ZERO, sigma_rad=0.)
        static_policy_check(mu_s)
        settings = dict(table=table, sigma_b=ZERO, condition=cond,
                        **M.ARM_MODES["F2"])
        tr[BASE] = M.replay_m8(pk, env, BASE, mu_s_fn=KO.make_fn(mu_s, near_limit=6.), **settings)
        tr[FAR] = M.replay_m8(pk, env, FAR, mu_s_fn=KO.make_fn(mu_s, near_limit=10.), **settings)
        assert np.array_equal(tr[BASE]["t"],tr[FAR]["t"])
        assert np.array_equal(tr[BASE]["pose_id"],tr[FAR]["pose_id"])
        n = len(original["t"])
        far_mask = np.asarray(tr[BASE]["distance"]) >= 6.
        far_count[route] = {"n":n, "n_baseline_far":int(far_mask.sum()),
                            "n_candidate_far":int((np.asarray(tr[FAR]["distance"])>=6.).sum())}
        traces[route] = tr
        if trace_dir is not None:
            trace_dir.mkdir(parents=True, exist_ok=True)
            for arm, trace in tr.items():
                np.savez_compressed(trace_dir / f"{route}_{arm}.npz", **trace)
    g = S.score(seed, cond, "own", traces, truth, times,
                from_trace=from_trace, scores_with_blocks=scores_with_blocks,
                branch_metrics=branch_metrics)
    # Fail closed before using any candidate result: verify replay of original F2SKRWV.
    parity_checks = []
    for route in (*ROUTES, "pooled"):
        for arm in ("H2", "H2S", BASE):
            rec=published.get((cond, seed, arm, route))
            if rec is None:
                raise RuntimeError(f"PARITY_FAIL missing frozen POINT_B {cond}/{seed}/{arm}/{route}")
            score=g["point"][route][arm]
            for field in PAIR_PARAMS:
                gap=abs(float(score[field])-rec[field])
                if not np.isfinite(gap):
                    raise RuntimeError(f"NONFINITE_BASELINE {cond}/{seed}/{arm}/{route}/{field}")
                dmax=max(dmax,gap)
                parity_checks.append(dict(route=route, arm=arm, metric=field,
                    expected=rec[field], actual=float(score[field]), abs_gap=gap,
                    passed=gap <= 1e-8))
                if gap > 1e-8 and not allow_baseline_mismatch:
                    raise RuntimeError(f"PARITY_FAIL {cond}/{seed}/{arm}/{route}/{field}: "
                                       f"expected={rec[field]} new={score[field]}, gap={gap}")
    g["far_exposure"] = far_count
    g["frozen_parity_max_abs"] = dmax
    g["frozen_parity_pass"] = all(row["passed"] for row in parity_checks)
    g["frozen_parity_checks"] = parity_checks
    g["baseline_mismatch_authorized"] = bool(allow_baseline_mismatch)
    g["model_change"] = "mu_s>=6m POWER->same-bin station sweep Kriging (no R change)"
    return g

def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("smoke","explore"):
        raise SystemExit("usage: python run_far_kriging_ab.py {smoke|explore}")
    mode = sys.argv[1]
    seeds=range(30,31) if mode=="smoke" else range(30,50)
    conds=("B0",) if mode=="smoke" else CONDS
    B,table,published=load_frozen()
    env=C.env()
    scorers=C.scorers()
    missing=[]
    for cond in conds:
        for seed in seeds:
            for route in ROUTES:
                for arm in ("H2", "H2S", BASE):
                    if (cond,seed,arm,route) not in published:
                        missing.append((cond,seed,arm,route))
    if missing:
        raise SystemExit(f"EXECUTION_BLOCKED: published baseline missing {len(missing)} entries")
    out=RESULTS / mode
    out.mkdir(parents=True,exist_ok=True)
    for cond in conds:
        for seed in seeds:
            path=out / cond / f"seed{seed}" / "RESULT.json"
            if path.exists():
                print("SKIP",path,flush=True)
                continue
            print("RUN",cond,seed,flush=True)
            result=report_one(cond,seed,env,scorers,B,table,published)
            path.parent.mkdir(parents=True,exist_ok=True)
            tmp=path.with_suffix(".tmp")
            tmp.write_text(json.dumps(result,default=asjson,ensure_ascii=False),encoding="utf-8")
            tmp.replace(path)
            for route in (*ROUTES,"pooled"):
                q0,q1=result["point"][route][BASE],result["point"][route][FAR]
                print(f"{route}: XY {q0['xy_rmse_cm']:.3f}->{q1['xy_rmse_cm']:.3f} cm; "
                      f"heading {q0['heading_rmse_deg']:.3f}->{q1['heading_rmse_deg']:.3f} deg; "
                      f"Pose95 {q0['pose95_coverage']:.3f}->{q1['pose95_coverage']:.3f}",
                      flush=True)
            print("BASELINE_PARITY_PASS",result["frozen_parity_max_abs"],flush=True)
    print("FINISHED",mode,"outputs",out,flush=True)

if __name__=="__main__":
    main()
