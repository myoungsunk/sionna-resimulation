"""P2_S1V2 (AMENDMENT-003): S1 on the v2 geometry + revisit experiment, batch arms = batch_map_v2 with the tap-conditioned
FFD model, convergence classes, Q-consistency, canary traces.

  s1v2.py run --fields 0,1 --split DEV --out D
  s1v2.py aggregate --shards D --split DEV|HOLDOUT2 --out D        (env S0V2_RESULTS_DIR)

RNG keys as s1_mc (root = frozen contract sha256; cell ids CELL_ID_V2; windows LOW 0, HIGH 1, REV60 2, FWD60 3).
The world pose field is drawn on the union of the four windows' canonical poses (exact GP marginal of the world field).
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import filters as FL  # noqa: E402
import info_core as IC  # noqa: E402
import manifest as MF  # noqa: E402
import s0_math as S0  # noqa: E402
import s0v2 as S0V2  # noqa: E402
import s1_mc as M  # noqa: E402
import world as Wd  # noqa: E402

STATES = S0.STATES
N, DT = 60, 0.5
P0M = M.P0
LH_CELLS = tuple(S0.CELL_ID)                                          # LOW/HIGH: the five frozen cells
LH_ARMS = ("IID_EKF_NOGATE", "IID_EKF_SELFGATE", "MB_VAR_NOGATE", "IID_BATCH", "ORACLE_CORR_BATCH")
RV_ARMS = ("IID_BATCH", "ORACLE_CORR_BATCH", "XMODEL_BATCH")
ROLE_J = {"LOW": 0, "HIGH": 1, "REV60": 2, "FWD60": 3}
CANARY_FIELD, CANARY_SENSOR = 0, 0


def setup(lk):
    cfg = Wd.PARAMS; s1 = cfg["synthetic_s1"]; W = S0V2.windows_v2(lk); anchor = "A"
    keys = {}; xs = []
    for role, w in W.items():
        if w["anchor"] != anchor:
            raise SystemExit("ERR_S1_COV all v2 windows must be anchor A")
        for p in w["poses"]:
            k = Wd.pose_key("FFD_ONLY_P0", anchor, *p)
            if k not in keys:
                keys[k] = len(xs); xs.append(p)
    LP = np.array(xs)
    Kp = IC.k_pose(LP[:, :2], LP[:, 2], s1["pose_corr_length_m"], math.radians(s1["pose_corr_yaw_deg"]))
    Lhalf, wmin, wmax = IC.psd_sqrt(Kp)
    dts = np.full(N, DT); tgrid = np.arange(N) * DT; C = S0V2.cells_v2(cfg)
    for role, w in W.items():
        w.update(role=role, j=ROLE_J[role], dts=dts)
        w["key_idx"] = np.array([keys[Wd.pose_key("FFD_ONLY_P0", anchor, *p)] for p in w["poses"]])
        Xr, _, _ = FL._rollout(w["X"][0], np.zeros((N, 2)), w["ds"], w["dth"], dts)
        w["Xtrue"] = Xr; w["htrue"] = Wd.h_H(Xr, anchor)[0]; w["taps"] = Wd.taps_of(Xr, anchor)
        w["q"] = np.array([[FL.Q_DS * abs(w["ds"][k]), FL.Q_GY * dts[k]] for k in range(N)]); w["q"][0] = 0
        w["cells"] = LH_CELLS if role in ("LOW", "HIGH") else S0V2.REV_CELLS
        if not np.allclose(w["t"], tgrid):
            raise SystemExit("ERR_S1_COV time grid")
    Sig = {(r, c): S0.sigma_for(w, C[c], cfg) for r, w in W.items() for c in set(w["cells"]) | ({"POSE_HIGH", "TIME_HIGH_5"} if r in ("REV60", "FWD60") else set())}
    Lt = {tau: IC.psd_sqrt(IC.k_time(tgrid, tau))[0] for tau in sorted({c["tau"] for c in C.values() if c["tau"] > 0})}
    return dict(cfg=cfg, s1=s1, wins=W, anchor=anchor, Lhalf=Lhalf, psd=(wmin, wmax), cells=C, Sig=Sig, Lt=Lt, n_world_poses=len(LP))


def draw(S, root, f, cn, w, sensor, pf):
    """Returns eps and its three unit components (for the revisit QA)."""
    cell = S["cells"][cn]; s1 = S["s1"]; a_p, a_t, a_w = cell["alphas"]; cid = S0V2.CELL_ID_V2[cn]
    Lc = np.linalg.cholesky(np.array([[1.0, cell["c"]], [cell["c"], 1.0]]))
    Ui = M.rng(root, cid, f, 2, w["j"], sensor).standard_normal((N, 2)) @ Lc.T
    Up = pf[w["key_idx"]] @ Lc.T if a_p else np.zeros((N, 2))
    Ut = np.zeros((N, 2))
    if a_t:
        Lt = S["Lt"][cell["tau"]]; Ut = (Lt @ M.rng(root, cid, f, 3, w["j"], sensor).standard_normal((Lt.shape[1], 2))) @ Lc.T
    U = math.sqrt(a_w) * Ui + math.sqrt(a_p) * Up + math.sqrt(a_t) * Ut
    return U * np.array([s1["sigma_r_m"], s1["sigma_s"]])[None, :], Up, Ut


def _row_from(w, X, Pf, anchor):
    e4 = w["Xtrue"][-1] - X[-1]; e4[2] = float(FL.wrap(e4[2]))
    T = IC.rotation_rt(w["Xtrue"][-1], Wd.ANCHORS[anchor]); er = T @ e4; pr = np.diag(T @ Pf @ T.T)
    ea = w["Xtrue"] - X; ea[:, 2] = np.angle(np.exp(1j * ea[:, 2]))
    r = dict(nees4=float(e4 @ np.linalg.solve(Pf, e4)), win_head_ms_deg2=float(np.mean(np.degrees(ea[:, 2]) ** 2)),
             win_xy_ms_cm2=float(np.mean(1e4 * np.sum(ea[:, :2] ** 2, 1))))
    r.update({f"e_{a}": float(er[i]) for i, a in enumerate(STATES)}); r.update({f"P_{a}": float(pr[i]) for i, a in enumerate(STATES)})
    return r


def run_arms(S, w, cn, z, sensor_rng, trace=None):
    anchor = S["anchor"]; ax = np.array(Wd.ANCHORS[anchor][:2])
    x0 = w["Xtrue"][0] + np.linalg.cholesky(P0M) @ sensor_rng.standard_normal(4); x0[2] = float(FL.wrap(x0[2]))
    vn = sensor_rng.standard_normal((N, 2)) * np.sqrt(w["q"]); ds_m = w["ds"] + vn[:, 0]; gy_m = w["dth"] + vn[:, 1]
    q_rel = float(np.max(np.abs(np.abs(ds_m[1:]) / np.abs(w["ds"][1:]) - 1.0)))            # §F: q(ds_meas)/q(ds_true) - 1
    Sig = S["Sig"][(w["role"], cn)]; Bd = S0.blockdiag(Sig); Rk = [Sig[2 * k:2 * k + 2, 2 * k:2 * k + 2] for k in range(N)]
    mdl = Wd.model(); sp = Wd.spec(anchor); taps = w["taps"]

    def h_fn(x):
        h, H = mdl.batch(np.asarray(x)[None], sp)
        return np.asarray(h)[0], np.asarray(H)[0]
    hb = lambda X: Wd.h_H_tap(X, anchor, taps)  # noqa: E731
    mu = np.zeros((N, 2)); rows = []
    arms = LH_ARMS if w["role"] in ("LOW", "HIGH") else tuple(a for a in RV_ARMS if a != "XMODEL_BATCH" or cn in S0V2.XMODEL)
    for arm in arms:
        try:
            if arm.endswith("_BATCH"):
                Sm = {"IID_BATCH": Bd, "ORACLE_CORR_BATCH": Sig}.get(arm)
                if arm == "XMODEL_BATCH":
                    Sm = S["Sig"][(w["role"], S0V2.XMODEL[cn])]
                X, Pst, info = FL.batch_map_v2_ms(hb, z, mu, Sm, ds_m, gy_m, w["dts"], x0, P0M)
                Pf = Pst[-1]
                row = dict(arm=arm, status="OK", conv=info["status"], stop_reason=info["stop_reason"], iters=info["iters"], n_used=N,
                           cost=info["cost"], newton_decrement=info["newton_decrement"], gn_shift_end_sd=info["gn_shift_end_sd"], n_reject=info["n_reject"],
                           ms_triggered=info["ms_triggered"], ms_best_k=info["ms_best_k"], ms_n_distinct_minima=info["ms_n_distinct_minima"],
                           ms_final_misfit=info["ms_final_misfit"], ms_cost_start0=info["ms_cost_start0"], rescued=info["rescued"])
                if trace is not None:
                    hh, _ = hb(X); Lm = np.linalg.cholesky(0.5 * (Sm + Sm.T)); wr = np.linalg.solve(Lm, (z - hh).reshape(-1)).reshape(N, 2)
                    for k in range(N):
                        trace.append(dict(arm=arm, k=k, x=X[k, 0], y=X[k, 1], psi=X[k, 2], bg=X[k, 3], **{f"Pd{i}": Pst[k][i, i] for i in range(4)},
                                          z_r=z[k, 0], z_s=z[k, 1], h_r=hh[k, 0], h_s=hh[k, 1], wres_r=wr[k, 0], wres_s=wr[k, 1], tap=int(taps[k])))
            else:
                Rfn = (lambda k, sg: Rk[k] + np.diag([0.0, sg ** 2])) if arm == "MB_VAR_NOGATE" else (lambda k, sg: Rk[k])
                X, PX, NIS, used = FL.ekf(h_fn, z, mu, Rfn, ds_m, gy_m, w["dts"], x0, P0M, gate_thr=M.GATE if arm == "IID_EKF_SELFGATE" else None,
                                          anchor_xy=ax, sig_fn=Wd.PB.sig if arm == "MB_VAR_NOGATE" else None)
                Pf = PX[-1]; row = dict(arm=arm, status="OK", conv="NA_RECURSIVE", iters=0, n_used=int(used.sum()))
                if trace is not None:
                    _ekf_trace(trace, arm, h_fn, z, mu, Rfn, ds_m, gy_m, w["dts"], x0, ax, arm == "IID_EKF_SELFGATE", arm == "MB_VAR_NOGATE")
            row.update(_row_from(w, X, Pf, anchor)); row["q_rel_diff_max"] = q_rel
        except Exception as ex:  # noqa: BLE001
            row = dict(arm=arm, status=f"FAILED:{type(ex).__name__}:{ex}")
        rows.append(row)
    return rows, dict(ds_m=ds_m, gy_m=gy_m)


def _ekf_trace(trace, arm, h_fn, z, mu, Rfn, ds, gy, dt, x0, ax, gate, mbvar):
    """Re-runs filters.ekf arithmetic step by step and records prior/posterior, H, innovation, S, K, NIS, used."""
    x = np.asarray(x0, float).copy(); P = P0M.copy()
    for k in range(len(z)):
        rh = math.hypot(x[0] - ax[0], x[1] - ax[1]); sg = Wd.PB.sig(rh) if mbvar else 0.0
        if k:
            x, P, _, _ = FL.predict(x, P, float(ds[k]), float(gy[k]), float(dt[k]), FL.qmat(float(ds[k]), float(dt[k])))
        xp = x.copy(); Pp = P.copy(); h, H = h_fn(x); Rk = Rfn(k, sg); v = z[k] - h - mu[k]
        S_ = H @ P @ H.T + Rk; S_ = 0.5 * (S_ + S_.T); nis = float(v @ np.linalg.solve(S_, v)); ok = (nis <= M.GATE) if gate else True
        K = np.linalg.solve(S_, H @ P).T
        if ok:
            y = x + K @ v; y[2] = FL.wrap(y[2]); A_ = np.eye(4) - K @ H; Pn = A_ @ P @ A_.T + K @ Rk @ K.T; x = y; P = 0.5 * (Pn + Pn.T)
        trace.append(dict(arm=arm, k=k, **{f"prior_{i}": xp[i] for i in range(4)}, **{f"priorPd{i}": Pp[i, i] for i in range(4)},
                          **{f"post_{i}": x[i] for i in range(4)}, **{f"Pd{i}": P[i, i] for i in range(4)}, z_r=z[k, 0], z_s=z[k, 1], h_r=h[0], h_s=h[1],
                          **{f"H{r}{c}": H[r, c] for r in range(2) for c in range(4)}, nu_r=v[0], nu_s=v[1], S00=S_[0, 0], S01=S_[0, 1], S11=S_[1, 1],
                          **{f"K{r}{c}": K[r, c] for r in range(4) for c in range(2)}, NIS=nis, used=bool(ok)))


def cmd_run(fields, split, out):
    lk = S0V2.lock_v2(); M.check_code_lock(lk)
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    allowed = set(lk["splits"]["S_field"][split]); bad = [f for f in fields if f not in allowed]
    if bad:
        raise SystemExit(f"ERR_SPLIT_LEAK fields {bad} not in frozen {split}")
    root = M.seed_root(); S = setup(lk); rows = []; qa = []; seeds = []; traces = []; qsens = []
    rev = S["wins"]["REV60"]; first = {}; pairs = []
    for i, k in enumerate(rev["key_idx"]):
        if k in first:
            pairs.append((first[k], i))
        else:
            first[k] = i
    for f in fields:
        for cn, cell in S["cells"].items():
            if not any(cn in w["cells"] for w in S["wins"].values()):
                continue
            pf = S["Lhalf"] @ M.rng(root, S0V2.CELL_ID_V2[cn], f, 1).standard_normal((S["Lhalf"].shape[1], 2)) if cell["alphas"][0] else None
            for w in S["wins"].values():
                if cn not in w["cells"]:
                    continue
                for sn in M.SENSOR_SEEDS:
                    eps, Up, Ut = draw(S, root, f, cn, w, sn, pf)
                    Sg = S["Sig"][(w["role"], cn)]; ev = eps.reshape(-1)
                    qa.append(dict(field=f, cell=cn, role=w["role"], sensor_seed=sn, check="mahalanobis_per_dim", value=float(ev @ np.linalg.solve(Sg, ev)) / (2 * N)))
                    if w["role"] == "REV60" and pairs:
                        if cell["alphas"][0]:
                            qa.append(dict(field=f, cell=cn, role="REV60", sensor_seed=sn, check="revisit_pose_identical_maxdiff",
                                           value=float(max(np.max(np.abs(Up[i] - Up[j])) for i, j in pairs))))
                        if cell["alphas"][1]:
                            qa.append(dict(field=f, cell=cn, role="REV60", sensor_seed=sn, check="revisit_time_differs_mindiff",
                                           value=float(min(np.max(np.abs(Ut[i] - Ut[j])) for i, j in pairs))))
                    z = w["htrue"] + eps
                    base = dict(split=split, field=f, sensor_seed=sn, window=w["id"], role=w["role"], cell=cn)
                    seeds.append(dict(base, seed_root=root, cell_id=S0V2.CELL_ID_V2[cn], window_j=w["j"]))
                    if np.any(np.abs(z[:, 1]) > S["s1"]["physical_s_domain_abs_max"]) or not np.all(np.isfinite(z)):
                        rows.append(dict(base, arm="ALL", status="STOP_UNPHYSICAL_OBSERVATION")); continue
                    tr = [] if (f == CANARY_FIELD and sn == CANARY_SENSOR and split == "DEV") else None
                    rr, ctl = run_arms(S, w, cn, z, M.rng(root, 0, f, 4, w["j"], sn), trace=tr)
                    rows += [dict(base, **r) for r in rr]
                    if tr is not None:
                        traces += [dict(base, **t) for t in tr]
                        if cn == "POSE_HIGH" and w["role"] in ("LOW", "HIGH"):         # §F S0 sensitivity to q(ds_meas)
                            Xm, Fm, Gm = FL._rollout(w["X"][0], np.zeros((N, 2)), w["ds"], w["dth"], w["dts"])
                            Qm = [np.zeros((4, 4))] + [Gm[k] @ np.diag([FL.Q_DS * abs(ctl["ds_m"][k]), FL.Q_GY * DT]) @ Gm[k].T for k in range(1, N)]
                            a0 = S0.evaluate(w["F"], w["Q"], w["H"], P0M, Sg, w["poses"][-1], "A"); a1 = S0.evaluate(w["F"], Qm, w["H"], P0M, Sg, w["poses"][-1], "A")
                            qsens.append(dict(role=w["role"], **{f"infl_rel_change_{a}": a1[f"infl_iid_{a}"] / a0[f"infl_iid_{a}"] - 1 for a in STATES}))
        print("S1V2 field", f, "rows", len(rows), flush=True)
    tag = "_".join(map(str, fields))
    pd.DataFrame(rows).to_csv(out / f"S1V2_ROWS_{split}_{tag}.csv", index=False, float_format="%.12g")
    pd.DataFrame(qa).to_csv(out / f"S1V2_QA_{split}_{tag}.csv", index=False, float_format="%.12g")
    pd.DataFrame(seeds).to_csv(out / f"S1V2_SEEDS_{split}_{tag}.csv", index=False)
    if traces:
        pd.DataFrame(traces).to_csv(out / f"S1V2_CANARY_TRACE_{split}_{tag}.csv", index=False, float_format="%.10g")
        pd.DataFrame(qsens).to_csv(out / f"S1V2_Q_SENSITIVITY_{split}_{tag}.csv", index=False, float_format="%.6g")
    return 0


# ----------------------------------------------------------------------------- decision (AMENDMENT-003 §H)
def _boot(tables, fn):
    """Field bootstrap on the fields common to all tables (identical to s1_mc.boot when the tables are paired)."""
    idx = sorted(set.intersection(*[set(t.index) for t in tables]))
    if not idx:
        return dict(est=np.nan, lo=np.nan, hi=np.nan, se=np.nan, n_fields=0)
    return M.boot([t.loc[idx] for t in tables], fn)


def decide_v2(rows, pred, did_pred, rvpred, sep_pred, eff):
    lf = math.log(eff["equivalence_factor"]); out = dict(H1=[], H2=[], H3=[], CAL=[], SENS=[], H4=[], H4_REPRO=[])
    li = lambda m, a: math.log(m[0][f"mse_{a}"] / m[0][f"claim_{a}"])  # noqa: E731
    for role in ("LOW", "HIGH"):
        for cell in LH_CELLS:
            for a in STATES:
                ft = M.field_table(rows, "IID_BATCH", role, cell)[[f"mse_{a}", f"claim_{a}"]]; p = float(pred.loc[(role, cell), f"infl_iid_{a}"])
                b = _boot([ft], lambda m, a=a, p=p: li(m, a) - math.log(p))
                rec = dict(test="H1_reproduction", role=role, cell=cell, state=a, infl_S1=math.exp(b["est"]) * p, infl_S0=p, log_dev=b["est"],
                           lo=b["lo"], hi=b["hi"], se=b["se"], verdict=M.band_verdict(b["lo"], b["hi"], lf))
                (out["H1"] if (cell in M.PRIMARY and a in ("tan", "psi")) else out["SENS"]).append(rec)
    keys = [(r, c) for r in ("LOW", "HIGH") for c in M.PRIMARY]
    for a in ("psi", "tan"):
        fts = [M.field_table(rows, "IID_BATCH", r, c)[[f"mse_{a}", f"claim_{a}"]] for r, c in keys]

        def did(ms, a=a):
            v = {k: li([m], a) for k, m in zip(keys, ms)}
            return (v[("LOW", "POSE_HIGH")] - v[("LOW", "LOWCORR")]) - (v[("HIGH", "POSE_HIGH")] - v[("HIGH", "LOWCORR")])
        b = _boot(fts, did); p = float(did_pred[(did_pred.state == a) & (did_pred.quantity == "infl_iid")].DID_log.iloc[0])
        out["H2"].append(dict(test="H2_interaction", state=a, primary=a == "psi", DID_S1=b["est"], lo=b["lo"], hi=b["hi"], se=b["se"], DID_S0=p,
                              testable=abs(p) >= math.log(eff["did_min_predicted_factor"]), verdict=_sided(b, p, eff)))
    for role in ("LOW", "HIGH"):
        for a in ("tan", "psi"):
            fo = M.field_table(rows, "ORACLE_CORR_BATCH", role, "POSE_HIGH")[[f"mse_{a}"]]; fi = M.field_table(rows, "IID_BATCH", role, "POSE_HIGH")[[f"mse_{a}"]]
            b = _boot([fo, fi], lambda m, a=a: math.log(m[0][f"mse_{a}"] / m[1][f"mse_{a}"])); p = float(pred.loc[(role, "POSE_HIGH"), f"mse_ratio_oracle_iid_{a}"])
            app = p <= eff["oracle_gain_ratio_max"]
            out["H3"].append(dict(test="H3_oracle_gain", role=role, state=a, ratio_S1=math.exp(b["est"]), lo=math.exp(b["lo"]), hi=math.exp(b["hi"]), se_log=b["se"],
                                  ratio_S0=p, applicable=app, verdict="NOT_APPLICABLE" if not app else ("PASS" if b["hi"] < 0 else ("FAIL" if b["lo"] > 0 else "UNDETERMINED"))))
    for role in ("LOW", "HIGH"):
        for cell in M.PRIMARY:
            for a in ("tan", "psi"):
                ft = M.field_table(rows, "ORACLE_CORR_BATCH", role, cell)[[f"mse_{a}", f"claim_{a}"]]; b = _boot([ft], lambda m, a=a: li(m, a))
                out["CAL"].append(dict(test="CAL_oracle", role=role, cell=cell, state=a, infl=math.exp(b["est"]), log_dev=b["est"], lo=b["lo"], hi=b["hi"],
                                       se=b["se"], verdict=M.band_verdict(b["lo"], b["hi"], lf)))
    # H4: revisit separability and reproduction
    for dc in S0V2.XMODEL:
        for arm in ("XMODEL_BATCH", "IID_BATCH"):
            for a in ("psi", "tan"):
                fr = M.field_table(rows, arm, "REV60", dc)[[f"mse_{a}", f"claim_{a}"]]; ff = M.field_table(rows, arm, "FWD60", dc)[[f"mse_{a}", f"claim_{a}"]]
                b = _boot([fr, ff], lambda m, a=a: li([m[0]], a) - li([m[1]], a))
                sp = sep_pred[(sep_pred.cell == dc) & (sep_pred.arm == arm) & (sep_pred.state == a)].iloc[0]
                out["H4"].append(dict(test="H4b_separability", cell=dc, arm=arm, state=a, SEP_S1=b["est"], lo=b["lo"], hi=b["hi"], se=b["se"],
                                      SEP_S0=float(sp.SEP_log), testable=bool(sp.testable), verdict=_sided(b, float(sp.SEP_log), eff)))
    for role in ("REV60", "FWD60"):
        for dc in S0V2.REV_CELLS:
            for arm in RV_ARMS:
                if arm == "XMODEL_BATCH" and dc not in S0V2.XMODEL:
                    continue
                for a in ("psi", "tan"):
                    ft = M.field_table(rows, arm, role, dc)[[f"mse_{a}", f"claim_{a}"]]; p = float(rvpred.loc[(role, dc, arm), f"infl_{a}"])
                    b = _boot([ft], lambda m, a=a, p=p: li(m, a) - math.log(p))
                    out["H4_REPRO"].append(dict(test="H4_repro", role=role, cell=dc, arm=arm, state=a, infl_S1=math.exp(b["est"]) * p, infl_S0=p, log_dev=b["est"],
                                                lo=b["lo"], hi=b["hi"], se=b["se"], verdict=M.band_verdict(b["lo"], b["hi"], lf)))
    h1 = [r["verdict"] for r in out["H1"]]; h2p = [r for r in out["H2"] if r["primary"]][0]
    cons = [h2p["verdict"]] + [r["verdict"] for r in out["H3"] if r["applicable"]] + [r["verdict"] for r in out["CAL"]]
    if "FAIL" in h1:
        v = "NOT_SUPPORTED"
    elif "UNDETERMINED" in h1 or not h2p["testable"]:
        v = "INCONCLUSIVE"
    elif all(x == "PASS" for x in cons):
        v = "SUPPORTED"
    elif "PASS" in cons or "FAIL" in cons:
        v = "MIXED"
    else:
        v = "INCONCLUSIVE"
    out["verdict"] = v
    return out


def _sided(b, p, eff):
    if abs(p) < math.log(eff["did_min_predicted_factor"]):
        return "NOT_TESTABLE"
    s = math.copysign(1.0, p); lo, hi = sorted((s * b["lo"], s * b["hi"]))
    if lo > 0:
        return "PASS"
    if hi < abs(p) * eff["did_min_fraction_of_prediction"]:
        return "FAIL"
    return "UNDETERMINED"


def cmd_reeval(src, out):
    """AMENDMENT-006: copy the committed shard outputs of an earlier S1V2 run (no recomputation) for re-aggregation."""
    out = Path(out); out.mkdir(parents=True, exist_ok=True); src = Wd.EXP / src; man = {}
    for f in sorted(os.listdir(src)):
        if f.startswith(("S1V2_ROWS_", "S1V2_QA_", "S1V2_SEEDS_", "S1V2_CANARY_TRACE_", "S1V2_Q_SENSITIVITY_")) and f.count("_") >= 3 and not f.endswith(("_DEV.csv", "_HOLDOUT2.csv")):
            (out / f).write_bytes((src / f).read_bytes()); man[f] = MF.sha256_file(src / f)
    (out / "S1V2_REEVAL_SOURCE.json").write_text(json.dumps(dict(source_run_dir=src.name, files=man), indent=1))
    return 0


def cmd_aggregate(shards, split, out):
    lk = S0V2.lock_v2(); M.check_code_lock(lk); out = Path(out); out.mkdir(parents=True, exist_ok=True)
    plan = lk["run_plan"]["S1V2"]; eff = lk["resolved"]["EFFECT_SIZE_RULES"]

    def cat(pat):
        fs = sorted(glob.glob(str(Path(shards) / "**" / pat), recursive=True))
        return pd.concat([pd.read_csv(f) for f in fs], ignore_index=True) if fs else pd.DataFrame(columns=["field", "status", "check", "value", "conv", "arm"])
    rows = cat(f"S1V2_ROWS_{split}_*.csv"); qa = cat(f"S1V2_QA_{split}_*.csv"); seeds = cat(f"S1V2_SEEDS_{split}_*.csv")
    tr = cat(f"S1V2_CANARY_TRACE_{split}_*.csv"); qs = cat(f"S1V2_Q_SENSITIVITY_{split}_*.csv")
    req = json.loads((Wd.EXP / "RUN_REQUEST.json").read_text()); expected = sorted(req["field_ids"])
    if split == "HOLDOUT2":
        rule_ok = expected == sorted(lk["splits"]["S_field"]["HOLDOUT2"][:len(expected)]) and len(expected) in (plan["n_confirm_default"], plan["n_confirm_large"])
    elif split == "DEV":
        rule_ok = expected == sorted(plan["fields_DEV"])
    else:
        rule_ok = set(expected) <= set(lk["splits"]["S_field"][split])
    got = sorted(int(x) for x in rows.field.unique()) if len(rows) else []
    rows.to_csv(out / f"S1V2_RESULTS_{split}.csv", index=False, float_format="%.12g"); seeds.to_csv(out / "SEED_LEDGER.csv", index=False)
    qa.to_csv(out / f"S1V2_QA_{split}.csv", index=False, float_format="%.12g")
    if len(tr):
        tr.to_csv(out / f"S1V2_CANARY_TRACE_{split}.csv", index=False, float_format="%.10g"); qs.to_csv(out / f"S1V2_Q_SENSITIVITY_{split}.csv", index=False)
    mm = qa[qa.check == "mahalanobis_per_dim"].groupby(["role", "cell"]).value.mean(); mtol = 4 * math.sqrt(2 / (2 * N)) / math.sqrt(max(len(got), 1))
    rp = qa[qa.check == "revisit_pose_identical_maxdiff"].value; rt = qa[qa.check == "revisit_time_differs_mindiff"].value
    b = rows[rows.arm.astype(str).str.endswith("_BATCH") & (rows.status == "OK")]
    ncf = b.groupby(["arm", "role", "cell"]).conv.apply(lambda c: float((c == "NONCONVERGED").mean())) if len(b) else pd.Series(dtype=float)
    ncn = b.groupby(["arm", "role", "cell"]).conv.apply(lambda c: (int((c == "NONCONVERGED").sum()), len(c))) if len(b) else pd.Series(dtype=object)
    nc_cell_ok = all(k <= max(1, math.ceil(0.01 * n)) for k, n in ncn.values)               # AMENDMENT-006 granularity rule
    nc_pooled = float((b.conv == "NONCONVERGED").mean()) if len(b) else 0.0
    n_exp = len(expected) * len(M.SENSOR_SEEDS) * (2 * len(LH_CELLS) * len(LH_ARMS) + 2 * (len(S0V2.REV_CELLS) * 3 - 1))
    qaj = dict(fields_expected=expected, fields_got=got, request_field_rule_ok=bool(rule_ok), mahalanobis_tol=mtol,
               mahalanobis_mean={f"{k[0]}|{k[1]}": float(v) for k, v in mm.items()},
               H4a_revisit_pose_identical_max=float(rp.max()) if len(rp) else None, H4a_revisit_time_differs_min=float(rt.min()) if len(rt) else None,
               nonconverged_frac_max=float(ncf.max()) if len(ncf) else None, nonconverged_by_cell={"|".join(k): v for k, v in ncf.items()},
               conv_counts=b.conv.value_counts().to_dict() if len(b) else {}, nonconverged_pooled_frac=nc_pooled, A006_granularity_rule_ok_REPORTED=bool(nc_cell_ok),
               nonconverged_rule="AMENDMENT-007: ORIGINAL AMENDMENT-003 rule, NONCONVERGED <= 1% per (arm,window,cell) (A006 granularity rule reported only)",
               stops=int((rows.status == "STOP_UNPHYSICAL_OBSERVATION").sum()), failures=int(rows.status.astype(str).str.startswith("FAILED").sum()),
               n_rows=int(len(rows)), n_rows_expected=n_exp, q_rel_diff_max=float(rows.q_rel_diff_max.max()) if "q_rel_diff_max" in rows else None)
    qaj["pass"] = bool(got == expected and rule_ok and all(abs(v - 1) <= mtol for v in mm.values) and qaj["H4a_revisit_pose_identical_max"] == 0.0
                       and (qaj["H4a_revisit_time_differs_min"] or 0) > 0 and (qaj["nonconverged_frac_max"] or 0) <= 0.01
                       and qaj["stops"] == 0 and qaj["failures"] == 0 and qaj["n_rows"] == n_exp)
    (out / "S1V2_QA.json").write_text(json.dumps(qaj, indent=1, default=float))
    s0d = Path(os.environ["S0V2_RESULTS_DIR"]); s0m = json.loads((s0d / "MANIFEST.json").read_text())
    s0_ok = s0m.get("execution_status") == "PASS" and s0m.get("contract_sha256") == MF.sha256_file(MF.CONTRACT)
    pred = pd.read_csv(s0d / "S0V2_PREDICTIONS.csv").set_index(["role", "cell"]); did_pred = pd.read_csv(s0d / "S0V2_DID.csv")
    rvpred = pd.read_csv(s0d / "S0V2_REVISIT.csv").set_index(["role", "cell", "arm"]); sep_pred = pd.read_csv(s0d / "S0V2_SEP.csv")
    ok = qaj["pass"] and s0_ok
    st = []
    for (arm, role, cell), _ in rows[rows.status == "OK"].groupby(["arm", "role", "cell"]):
        ft = M.field_table(rows, arm, role, cell)
        d = dict(arm=arm, role=role, cell=cell, n_fields=len(ft), nees4=float(ft.nees.mean()), head_rmse_deg=math.sqrt(ft.head_ms.mean()), xy_rmse_cm=math.sqrt(ft.xy_ms.mean()))
        d.update({f"infl_{a}": ft[f"mse_{a}"].mean() / ft[f"claim_{a}"].mean() for a in STATES}); d.update({f"rmse_{a}": math.sqrt(ft[f"mse_{a}"].mean()) for a in STATES})
        st.append(d)
    pd.DataFrame(st).to_csv(out / f"S1V2_STATS_{split}.csv", index=False, float_format="%.8g")
    empty = dict(verdict="INCONCLUSIVE", H1=[], H2=[], H3=[], CAL=[], SENS=[], H4=[], H4_REPRO=[])
    dec = decide_v2(rows, pred, did_pred, rvpred, sep_pred, eff) if ok else empty
    decc = decide_v2(rows[(rows.conv == "CONVERGED") | (rows.conv == "NA_RECURSIVE")], pred, did_pred, rvpred, sep_pred, eff) if ok else empty
    for k in ("H1", "H2", "H3", "CAL", "SENS", "H4", "H4_REPRO"):
        pd.DataFrame(dec[k]).to_csv(out / f"S1V2_{k}_{split}.csv", index=False, float_format="%.8g")
        pd.DataFrame(decc[k]).to_csv(out / f"S1V2_{k}_{split}_CONVERGED_ONLY.csv", index=False, float_format="%.8g")
    res = dict(split=split, scientific_verdict_track_S=dec["verdict"] if split == "HOLDOUT2" else "NOT_EVALUATED (pilot)", split_level_rule_outcome=dec["verdict"],
               converged_only_sensitivity_outcome=decc["verdict"], H4_summary=[{k: r[k] for k in ("cell", "arm", "state", "testable", "verdict")} for r in dec["H4"]],
               qa_pass=qaj["pass"], s0_reference=s0d.name, s0_reference_ok=s0_ok, release="TECHNICAL_QA_ONLY (SELF_REVIEW_ONLY)",
               scope="Track S synthetic known-generative only; no physical-RF, deployability or MB_VAR-superiority claim")
    if split == "DEV" and ok:
        pw = M.power(dict(H1=dec["H1"], CAL=dec["CAL"], H2=[r for r in dec["H2"]], H3=dec["H3"]), len(got), plan, eff)
        pd.DataFrame(pw.pop("rows")).to_csv(out / "S1V2_POWER_DEV.csv", index=False, float_format="%.6g")
        pw["holdout2_fields"] = lk["splits"]["S_field"]["HOLDOUT2"][:pw["n_confirm"]]; res["power"] = pw
    (out / f"S1V2_DECISION_{split}.json").write_text(json.dumps(res, indent=1, default=M._json))
    status = "PASS" if ok else "FAIL"
    MF.write_manifest(out, phase="P2_S1", status=status, contract_sha=MF.sha256_file(MF.CONTRACT),
                      config_files=[Wd.EXP / "config/PLAN_PARAMETERS.json", Wd.EXP / "contracts/AMENDMENT-003.md", Wd.EXP / "contracts/AMENDMENT-004.md", Wd.EXP / "contracts/AMENDMENT-005.md", Wd.EXP / "contracts/AMENDMENT-006.md", Wd.EXP / "contracts/AMENDMENT-007.md"],
                      input_lock=Path(os.environ.get("REFLECT_ROOT", ".")) / "out" / "INPUT_LOCK.sha256", outputs=sorted(out.glob("S1V2_*")),
                      seed_ledger=out / "SEED_LEDGER.csv", verdict=dec["verdict"] if (split == "HOLDOUT2" and ok) else "NOT_EVALUATED", unit="field_realization",
                      limitations=["synthetic additive noise on the FFD LOS model; not RF physics", "batch arms: tap-conditioned FFD model (detector index observed)",
                                   "anchor A only", "SELF_REVIEW_ONLY; TECHNICAL_QA_ONLY", f"{split} split"], extra=dict(sub_phase="P2_S1V2", amendment="AMENDMENT-003..007"))
    print("S1V2 aggregate", split, status, dec["verdict"], "| converged-only", decc["verdict"])
    return 0 if status == "PASS" else 1


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd"); ap.add_argument("--fields"); ap.add_argument("--split", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--shards"); ap.add_argument("--src")
    a = ap.parse_args()
    if a.cmd == "run":
        return cmd_run([int(x) for x in a.fields.split(",") if x != ""], a.split, a.out)
    if a.cmd == "reeval":
        return cmd_reeval(a.src, a.out)
    return cmd_aggregate(a.shards, a.split, a.out)


if __name__ == "__main__":
    raise SystemExit(main())
