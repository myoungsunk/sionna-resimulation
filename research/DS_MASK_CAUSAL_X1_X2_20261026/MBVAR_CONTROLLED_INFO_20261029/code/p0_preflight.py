"""P0_PREFLIGHT (DRAFT contract): source / premise / parity / pose / geometry audit only. No performance comparison.

  REFLECT_ROOT=<inputs> MBVAR_GOVERNANCE_SHA=<40hex> python3 p0_preflight.py --out <dir> --rf-dir <dir with H_<case>.npy, SAMPLES_<case>.json>
Outputs: P0_SOURCES.json, P0_PREMISE.json, P0_PARITY.json, P0_POSE_LEDGER.csv, P0_GEOMETRY.csv, P0_HGEOMETRY.json, MANIFEST.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import filters as FL  # noqa: E402
import info_core as IC  # noqa: E402
import manifest as MF  # noqa: E402
import world as Wd  # noqa: E402

PB = Wd.PB; C = Wd.C
P0_CASES = ("R4_aB_m0", "R5_aA_m0")
WIN_N = 60; WIN_DT = 0.5; SIG_SEL = (0.05, 0.02)
P0_PRIOR = np.diag(IC.STATE_SCALES ** 2)


def sources(rf_dir: Path):
    root = Path(os.environ["REFLECT_ROOT"])
    files = {
        "repo:pol_bias_model/exp_pb.py": Wd.DSM / "pol_bias_model/exp_pb.py",
        "repo:reflect_model/common.py": Wd.DSM / "reflect_model/common.py",
        "repo:reflect_model/fetch_inputs.sh": Wd.DSM / "reflect_model/fetch_inputs.sh",
        "repo:config/PLAN_PARAMETERS.json": Wd.EXP / "config/PLAN_PARAMETERS.json",
        "repo:contract(draft)": MF.CONTRACT,
        "pinned:EKF4_RANGE_S_STAGED_20261014/core.py": root / "repo/research/EKF4_RANGE_S_STAGED_20261014/core.py",
        "pinned:FFD_P0P3_20261016/source_model.py": root / "repo/research/FFD_P0P3_20261016/source_model.py",
        "pinned:EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py": root / "repo/research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py",
    }
    src = root / "repo/results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src/qclean_uwb/drivesim"
    for f in ("observation.py", "pattern_apply.py", "sensor_v2.py"):
        files[f"pinned:qclean_uwb/drivesim/{f}"] = src / f
    out = {}
    for k, p in files.items():
        out[k] = dict(path=str(p), exists=p.exists(), sha256=MF.sha256_file(p) if p.exists() else None,
                      git_blob=MF.git_blob_sha(p) if p.exists() else None)
    for b, d in C.BANK_SHA.items():
        p = root / "banks" / b
        out[f"bank:{b}"] = dict(sha256=MF.sha256_file(p), expected=d, match=MF.sha256_file(p) == d)
    for c in P0_CASES:
        for nm in (f"H_{c}.npy", f"SAMPLES_{c}.json"):
            p = rf_dir / nm
            out[f"rf:{nm}"] = dict(exists=p.exists(), sha256=MF.sha256_file(p) if p.exists() else None,
                                   source="raw.githubusercontent.com @ 9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13 BLOCK_C")
    out["sionna_rt"] = "NOT_MATERIALIZED: RT is out of scope until a signed pre-P3 amendment"
    out["fetch_inputs_commit"] = "9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13"
    bad = [k for k, v in out.items() if isinstance(v, dict) and (v.get("exists") is False or v.get("match") is False)]
    return out, bad


def premise(rf_dir: Path):
    sys.path.insert(0, str(Path(os.environ["REFLECT_ROOT"]) / "repo/results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"))
    from qclean_uwb.drivesim import observation as OBS
    res = {}
    freqs = np.asarray(Wd.model().freqs)
    for c in P0_CASES:
        ref = C.load_control(c, "B0"); jb, jm = ref["jb"], ref["jm"]
        z = ref["nu"][:, jb] + ref["h"][:, jb] + ref["mu"][:, jb]
        pid = ref["pose_id"].astype(int)
        H = np.load(rf_dir / f"H_{c}.npy", mmap_mode="r"); ids = [int(p["pose_id"]) for p in json.loads((rf_dir / f"SAMPLES_{c}.json").read_text())]
        idx = {p: i for i, p in enumerate(ids)}; rows = np.array([idx.get(p, -1) for p in pid]); ok = rows >= 0
        o = OBS.observe(np.asarray(H[rows[ok]]), freqs, None, None)
        ds_ = z[ok, 1] - o["s"]; dr = z[ok, 0] - o["range_m"]
        gt = ref["truth_scoring_only"]
        key = np.round(np.c_[gt[:, 0], gt[:, 1], np.degrees(gt[:, 2]) % 360], 9)
        dup_pose = len(key) - len(np.unique(key, axis=0))
        res[c] = dict(matched=int(ok.sum()), packets=int(len(pid)), s_max_abs_diff=float(np.max(np.abs(ds_))),
                      s_identity=bool(np.max(np.abs(ds_)) <= 1e-12),
                      r_diff_mean_m=float(np.mean(dr)), r_diff_std_m=float(np.std(dr)), r_diff_max_abs_m=float(np.max(np.abs(dr))),
                      r_identity_with_observe_range=bool(np.max(np.abs(dr)) <= 1e-9),
                      duplicate_pose_ids=int(len(pid) - len(np.unique(pid))), duplicate_truth_poses=int(dup_pose),
                      repeat_pose_test="NOT_APPLICABLE_NO_REPEATED_POSES" if dup_pose == 0 else "TESTABLE",
                      mu_packet_keyed_distinct_BB_MB=float(np.max(np.abs(ref["mu"][:, jb] - ref["mu"][:, jm]))))
    allok = all(v["s_identity"] for v in res.values())
    return dict(cases=res, noise_free_s_identity=allok,
                interpretation=("z_s equals the noise-free first-path s of the pose channel (observe(noise_var=None)); "
                                "the old residual autocorrelation is pose-sampled structure, not an independent RF time process."),
                range_note="z_r is compared with observe().range_m (tap-quantised delay*c); a non-zero difference means the trace's "
                           "range extractor differs (calibration/continuous surrogate) and r identity is reported, not assumed.",
                mu_note="mu_B/mu_M are packet-keyed archived constants and must not be transferred to new poses (COMMON_CONTRACT II).",
                clearance_m=Wd.CLEARANCE_M, robot_body_m=Wd.ROBOT_BODY)


def parity():
    out = {}
    m = Wd.model()
    for c in P0_CASES:
        spec = C.CASES[c]; ref = C.load_control(c, "B0"); jb, jm = ref["jb"], ref["jm"]
        t = ref["t_s"]; gt = ref["truth_scoring_only"]
        z = ref["nu"][:, jb] + ref["h"][:, jb] + ref["mu"][:, jb]
        ds, gy, dt, x0 = PB.build_controls(t, gt[:, :3], "B0", 0)
        acc = PB.gated_mask(z, ref["mu"][:, jb], ref["R"][:, jb], ds, gy, dt, np.r_[x0, 0.0], ref["Pprior"][0, jb], spec, m)
        mask_mis = int(np.sum(acc != ref["acc"][:, jb].astype(bool)))
        hg, _ = m.batch(np.c_[gt[:, :3], np.zeros(len(t))], spec)
        D = dict(t=t, gt=gt, z=z, R=ref["R"][:, jb], acc=acc, ds=ds, gy=gy, dt=dt, x0=np.r_[x0, 0.0], P0=ref["Pprior"][0, jb],
                 spec=spec, anchor=np.array(spec["anchor"][:2]), hg=hg)
        mus = dict(BB=ref["mu"][:, jb], MB=ref["mu"][:, jm])
        h_fn = lambda x, spec=spec: tuple(a[0] for a in m.batch(x[None], spec))  # noqa: E731
        rows = {}
        for arm, bg, mode in (("BB_ORIG", "BB", "orig"), ("MB_ORIG", "MB", "orig"), ("MB_VAR", "MB", "var")):
            Xr, PXr, _, _ = PB.run(D, mus[bg], dict(mode=mode), m)
            R = D["R"]
            Rfn = (lambda k, sg, R=R: R[k].copy()) if mode == "orig" else (lambda k, sg, R=R: R[k] + np.diag([0.0, sg ** 2]))
            X, PX, _, _ = FL.ekf(h_fn, z, mus[bg], Rfn, ds, gy, dt, D["x0"], D["P0"], use=acc, anchor_xy=D["anchor"], sig_fn=PB.sig)
            r = dict(state_max_abs=float(np.max(np.abs(X - Xr))), cov_max_abs=float(np.max(np.abs(PX - PXr))))
            if mode == "orig":
                j = jb if bg == "BB" else jm
                r["exp_pb_vs_stored_trace_state"] = float(np.max(np.abs(Xr - ref["x"][:, j])))
                r["exp_pb_vs_stored_trace_cov"] = float(np.max(np.abs(PXr - ref["P"][:, j])))
            r["pass"] = r["state_max_abs"] <= 1e-10 and r["cov_max_abs"] <= 1e-10
            rows[arm] = r
        out[c] = dict(mask_mismatch_vs_trace=mask_mis, arms=rows)
    out["pass"] = all(all(a["pass"] for a in v["arms"].values()) and v["mask_mismatch_vs_trace"] == 0 for k, v in out.items() if k in P0_CASES)
    out["tolerance"] = dict(state_abs=1e-10, cov_abs=1e-10, note="FILTER-01: new filters.ekf vs pinned exp_pb.run, full trace")
    return out


def candidate_sets():
    """(anchor, trajectory, fn): original T1/T4/T5 for A and C + AMENDMENT-001 (anchor A)."""
    out = [(a, tr, fn) for a in Wd.PRIMARY_ANCHORS for tr, fn in Wd.TRAJ.items()]
    out += [(a, tr, fn) for a in Wd.AMEND1_ANCHORS for tr, fn in Wd.AMEND1.items()]
    return out


def pose_ledger():
    rows = []
    for a, tr, fn in candidate_sets():
        if True:
            P = fn(); h, H = Wd.h_H(P, a)
            for i, p in enumerate(P):
                chk = Wd.pose_checks(*p, a)
                rows.append(dict(scene="FFD_ONLY_P0", anchor=a, trajectory=tr, idx=i, x=p[0], y=p[1], yaw_rad=p[2],
                                 yaw_deg_canonical=Wd.canonical_yaw_deg(p[2]), pose_key=Wd.pose_key("FFD_ONLY_P0", a, *p),
                                 h_r=h[i, 0], h_s=h[i, 1], abs_hs_le_07=abs(h[i, 1]) <= 0.7, H_rank=int(np.linalg.matrix_rank(H[i])),
                                 **chk))
    df = pd.DataFrame(rows)
    spin = df[df.trajectory == "T5_SPIN"]
    df["amendment"] = np.where(df.trajectory.isin(list(Wd.AMEND1)), "AMENDMENT-001", "ORIGINAL")
    same = all(spin[spin.anchor == a].pose_key.iloc[0] == spin[spin.anchor == a].pose_key.iloc[-1] for a in Wd.PRIMARY_ANCHORS)
    return df, dict(spin_first_last_same_key=bool(same), anchor_B="RESERVE_NOT_EVALUATED")


def window_info(P, anchor):
    X, F, Q, ds, dth = Wd.motion_window(P, WIN_DT)
    h, H = Wd.h_H(X, anchor)
    SX = IC.joint_prior(P0_PRIOR, F, Q)
    Hb = IC.stack_H(list(H), list(range(len(P))), len(P))
    Sig = np.kron(np.eye(len(P)), np.diag(np.square(SIG_SEL)))
    Ppost, _ = IC.condition(SX, Hb, Sig)
    k = len(P) - 1; T = IC.rotation_rt(P[k], Wd.ANCHORS[anchor])
    post = IC.nondim_info(IC.marginal_block(Ppost, k, T)); prior = IC.nondim_info(IC.marginal_block(SX, k, T))
    return post, prior, h, H


JAC_FD_EPS = 1e-5        # AMENDMENT-002: central finite-difference step (m, m, rad, rad/s)
KINK_REL = 1e-4          # pose is non-differentiable if max|H_fd - H| > KINK_REL * max|H| (FD noise floor ~1e-8)
KINK_FRAC_MAX = 0.05     # window invalid if more than 5 % of its poses sit on a non-differentiable point of h


def kink_poses(X, H, anchor):
    Hf = np.zeros_like(H)
    for j in range(4):
        d = np.zeros(4); d[j] = JAC_FD_EPS
        Hf[:, :, j] = (Wd.h_H(X + d, anchor)[0] - Wd.h_H(X - d, anchor)[0]) / (2 * JAC_FD_EPS)
    dev = np.abs(Hf - H).max(axis=(1, 2)) / np.abs(H).max()
    return dev > KINK_REL, float(dev.max())


def geometry(ledger):
    rows = []
    for a, tr, fn in candidate_sets():
        if tr == "T5_SPIN":
            continue                                   # stationary diagnostic stratum, not a moving-window candidate
        if True:
            P = fn()
            for w, st in enumerate(range(0, len(P) - WIN_N + 1, WIN_N)):
                Pw = P[st:st + WIN_N]
                r = dict(anchor=a, trajectory=tr, window=w, start_idx=st, n=WIN_N, t_span_s=(WIN_N - 1) * WIN_DT)
                try:
                    post, prior, h, H = window_info(Pw, a)
                    a3 = np.array(Wd.ANCHORS[a]); rng3 = np.linalg.norm(np.c_[Pw[:, :2], np.full(WIN_N, Wd.ROBOT_Z)] - a3, axis=1)
                    ok_h = bool(np.max(np.abs(h[:, 1])) <= 0.7)
                    kink, kdev = kink_poses(np.c_[Pw, np.zeros(WIN_N)], H, a)
                    ok_s = bool(kink.mean() <= KINK_FRAC_MAX)
                    ratios = post / prior
                    valid = ok_h and ok_s and bool(np.all(np.isfinite(ratios))) and ratios[1] > 0 and ratios[2] > 0
                    G = 0.5 * math.log(ratios[2]) + 0.5 * math.log(ratios[1]) if valid else np.nan
                    r.update(max_abs_hs=float(np.max(np.abs(h[:, 1]))), hs_domain_ok=ok_h, range_median_m=float(np.median(rng3)),
                             range_iqr_m=float(np.subtract(*np.percentile(rng3, [75, 25]))),
                             **{f"Ipost_{n}": float(v) for n, v in zip(("rad", "tan", "psi", "bg"), post)},
                             **{f"Iprior_{n}": float(v) for n, v in zip(("rad", "tan", "psi", "bg"), prior)},
                             n_kink_poses=int(kink.sum()), jac_fd_max_rel_dev=kdev, h_smooth_ok=ok_s,
                             G=G, valid=valid, fail_reason="" if valid else ("HS_DOMAIN" if not ok_h else ("H_NONSMOOTH" if not ok_s else "INFO_RATIO")))
                except Exception as e:  # noqa: BLE001
                    r.update(valid=False, fail_reason=f"EXC:{e}")
                rows.append(r)
    G = pd.DataFrame(rows)
    cand = G[G.valid].to_dict("records"); pairs = []
    for lo in cand:
        for hi in cand:
            if lo is hi:
                continue
            overlap = (lo["trajectory"] == hi["trajectory"]) and (lo["start_idx"] == hi["start_idx"])   # same pose indices
            if overlap:
                continue
            if abs(lo["range_median_m"] - hi["range_median_m"]) > 0.5 or abs(lo["range_iqr_m"] - hi["range_iqr_m"]) > 0.5:
                continue
            d = hi["G"] - lo["G"]
            if d <= 0:
                continue
            pairs.append(dict(low=f'{lo["anchor"]}|{lo["trajectory"]}|{lo["start_idx"]}', high=f'{hi["anchor"]}|{hi["trajectory"]}|{hi["start_idx"]}',
                              dG=d, key=(lo["anchor"], lo["trajectory"], lo["start_idx"])))
    pairs.sort(key=lambda p: (-p["dG"], p["key"]))
    choice = pairs[0] if pairs else None
    return G, dict(status="RESOLVED" if choice else "BLOCKED_GEOMETRY_MATCH", chosen=choice, n_candidate_windows=len(G),
                   n_valid_windows=len(cand), n_pairs=len(pairs), all_pairs=pairs[:50],
                   rule="PLAN_P0_P6 §K: N=60 @0.5 s, Q-aware batch posterior at window end, D^T I D, G=1/2 log(Ipsi/Ipsi_prior)+1/2 log(Itan/Itan_prior), "
                        "|h_s|<=0.7, range median/IQR diff <=0.5 m, no shared pose indices, max dG, tie lexicographic; "
                        "AMENDMENT-002: <=5% of poses with FD-vs-analytic Jacobian deviation >1e-4 (h differentiable)",
                   sigma_obs_selection=SIG_SEL, prior_P0="diag(STATE_SCALES^2)", amendment="AMENDMENT-001 candidates + AMENDMENT-002 smoothness rule")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); ap.add_argument("--rf-dir", required=True)
    ap.add_argument("--draft-contract-sha256", required=True)
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True); rf = Path(a.rf_dir)
    status = "PASS"; problems = []
    try:
        src, bad = sources(rf); (out / "P0_SOURCES.json").write_text(json.dumps(src, indent=1))
        if bad:
            problems.append(f"ERR_SOURCE_HASH {bad}")
        prem = premise(rf); (out / "P0_PREMISE.json").write_text(json.dumps(prem, indent=1))
        if not prem["noise_free_s_identity"]:
            problems.append("PREMISE_S_IDENTITY_FAIL")
        par = parity(); (out / "P0_PARITY.json").write_text(json.dumps(par, indent=1))
        if not par["pass"]:
            problems.append("ERR_PARITY")
        led, lchk = pose_ledger(); led.to_csv(out / "P0_POSE_LEDGER.csv", index=False, float_format="%.12g")
        if not (led.room_ok.all() and led.C10_clear_ok.all() and led.C11_clear_ok.all() and lchk["spin_first_last_same_key"]):
            problems.append("POSE_CHECK_FAIL")
        geo, hgeo = geometry(led); geo.to_csv(out / "P0_GEOMETRY.csv", index=False, float_format="%.10g")
        hgeo["ledger_checks"] = lchk
        hgeo["pose_ledger_sha256"] = MF.sha256_file(out / "P0_POSE_LEDGER.csv")
        (out / "P0_HGEOMETRY.json").write_text(json.dumps(hgeo, indent=1, default=str))
        if hgeo["status"] != "RESOLVED":
            problems.append("BLOCKED_GEOMETRY_MATCH")
        # analytic gate (MATH-01) and unit invariance (MATH-03) recorded here as well as in pytest
        m1 = dict(same=IC.two_obs_ratio(0.9, +1), opp=IC.two_obs_ratio(0.9, -1))
        m1["pass"] = abs(m1["same"] - 0.5263157894736842) <= 1e-10 and abs(m1["opp"] - 10.0) <= 1e-10
        (out / "P0_MATH.json").write_text(json.dumps(m1, indent=1))
        if not m1["pass"]:
            problems.append("ERR_S0_MATH")
    except Exception as e:  # noqa: BLE001
        problems.append(f"EXCEPTION {type(e).__name__}: {e}"); traceback.print_exc()
    if problems:
        status = "BLOCKED" if any(p.startswith("BLOCKED") for p in problems) and len(problems) == 1 else "FAIL"
    (out / "P0_STATUS.json").write_text(json.dumps(dict(status=status, problems=problems), indent=1))
    outs = sorted(out.glob("P0_*"))
    lock = Path(os.environ["REFLECT_ROOT"]) / "out" / "INPUT_LOCK.sha256"
    MF.write_manifest(out, phase="P0_PREFLIGHT", status=status, contract_sha=a.draft_contract_sha256,
                      config_files=[Wd.EXP / "config/PLAN_PARAMETERS.json"], input_lock=lock, outputs=outs, seed_ledger=None,
                      verdict="NOT_EVALUATED", unit="mathematical_deterministic",
                      limitations=["P0_PREFLIGHT under DRAFT contract: source/math/geometry audit only",
                                   "FFD LOS model only; no RT scene materialised",
                                   "auditor: SELF_REVIEW_ONLY (no independent session)"],
                      extra=dict(pose_ledger_sha256=MF.sha256_file(out / "P0_POSE_LEDGER.csv") if (out / "P0_POSE_LEDGER.csv").exists() else None))
    print("P0", status, problems)
    raise SystemExit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    main()
