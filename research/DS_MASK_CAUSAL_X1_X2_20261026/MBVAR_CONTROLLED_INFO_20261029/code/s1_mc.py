"""P2_S1: known-generative synthetic Monte Carlo (SCIENCE_SPEC §3-§5). Requires the FROZEN lock (incl. code hashes).

  s1_mc.py run --fields 0,8 --split DEV --out <dir>
  s1_mc.py aggregate --shards <dir> --split DEV|HOLDOUT|SMOKE --out <dir>     (env S0_RESULTS_DIR = committed S0 run)

Independent unit: field_realization_id. Sensor seeds 0..2 are repeated measures inside a field.
Observation: z_k = h_LOS(x_true,k) + eps_k (mu = 0, no clipping). Truth = noise-free core.predict rollout of the ledger window.
Synthetic sensor (frozen): odometry/gyro control noise v_k ~ N(0, q_k) exactly the filter's Q; x0_hat ~ N(x0_true, P0).
RNG key hierarchy (SCIENCE_SPEC §3): (contract_sha256, cell_id, field_id, stream, window, sensor_seed).
  pose stream  (cell, field, 1)                    one world field shared by the LOW and HIGH windows (same anchor A world)
  iid stream   (cell, field, 2, window, sensor)    new white draw per sensor repetition
  time stream  (cell, field, 3, window, sensor)    new OU draw per sensor repetition
  sensor       (0,    field, 4, window, sensor)    shared by every cell (paired controls / x0)
All arms of one (field, cell, window, sensor) consume identical z, controls and x0.
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
import p0_preflight as P0P  # noqa: E402
import s0_math as S0  # noqa: E402
import world as Wd  # noqa: E402

STATES = S0.STATES
SENSOR_SEEDS = (0, 1, 2)
ARMS = ("IID_EKF_NOGATE", "IID_EKF_SELFGATE", "MB_VAR_NOGATE", "IID_BATCH", "ORACLE_CORR_BATCH")
PRIMARY = ("LOWCORR", "POSE_HIGH")
GATE = 9.210340371976184
N, DT = 60, 0.5
P0 = np.diag(IC.STATE_SCALES ** 2)


def check_code_lock(lk):
    want = lk.get("code_sha256", {}); have = MF.code_hashes()
    bad = sorted(k for k in set(want) | set(have) if have.get(k) != want.get(k))
    if not want or bad:
        raise SystemExit(f"ERR_SOURCE_HASH code differs from the frozen lock: {bad}")


def rng(root, *keys):
    return np.random.default_rng(np.random.SeedSequence([root, *[int(k) for k in keys]]))


def seed_root():
    return int(MF.sha256_file(MF.CONTRACT)[:15], 16)


# ----------------------------------------------------------------------------- setup
def setup(lk):
    cfg = Wd.PARAMS; s1 = cfg["synthetic_s1"]; hg = lk["resolved"]["HGEOMETRY_CHOICE"]
    wins = {"LOW": S0.window(hg["low"]), "HIGH": S0.window(hg["high"])}
    anchor = wins["LOW"]["anchor"]
    if wins["HIGH"]["anchor"] != anchor:
        raise SystemExit("ERR_S1_COV LOW/HIGH windows must share the world field (same anchor)")
    keys = {}; xs = []
    for a, tr, fn in P0P.candidate_sets():           # whole anchor-A ledger = the world in which one field is drawn
        if a != anchor:
            continue
        for p in fn():
            k = Wd.pose_key("FFD_ONLY_P0", a, *p)
            if k not in keys:
                keys[k] = len(xs); xs.append(p)
    LP = np.array(xs)
    Kp = IC.k_pose(LP[:, :2], LP[:, 2], s1["pose_corr_length_m"], math.radians(s1["pose_corr_yaw_deg"]))
    Lhalf, wmin, wmax = IC.psd_sqrt(Kp)
    dts = np.full(N, DT); tgrid = np.arange(N) * DT
    for j, (role, w) in enumerate(wins.items()):
        w.update(role=role, j=j, dts=dts)
        w["key_idx"] = np.array([keys[Wd.pose_key("FFD_ONLY_P0", anchor, *p)] for p in w["poses"]])
        Xr, _, _ = FL._rollout(w["X"][0], np.zeros((N, 2)), w["ds"], w["dth"], dts)
        w["Xtrue"] = Xr; w["htrue"] = Wd.h_H(Xr, anchor)[0]
        w["q"] = np.array([[FL.Q_DS * abs(w["ds"][k]), FL.Q_GY * dts[k]] for k in range(N)]); w["q"][0] = 0
        if not np.allclose(w["t"], tgrid):
            raise SystemExit("ERR_S1_COV time grid")
    spin = Wd.t5_spin()
    spin_idx = (keys[Wd.pose_key("FFD_ONLY_P0", anchor, *spin[0])], keys[Wd.pose_key("FFD_ONLY_P0", anchor, *spin[-1])])
    C = S0.cells(cfg)
    Sig = {(r, c): S0.sigma_for(w, C[c], cfg) for r, w in wins.items() for c in C}
    Lt = {tau: IC.psd_sqrt(IC.k_time(tgrid, tau))[0] for tau in sorted({c["tau"] for c in C.values() if c["tau"] > 0})}
    return dict(cfg=cfg, s1=s1, wins=wins, anchor=anchor, Lhalf=Lhalf, psd=(wmin, wmax), spin_idx=spin_idx, cells=C, Sig=Sig,
                Lt=Lt, n_world_poses=len(LP))


def draw_eps(S, root, f, cn, w, sensor, pose_field):
    cell = S["cells"][cn]; s1 = S["s1"]; a_p, a_t, a_w = cell["alphas"]; cid = S0.CELL_ID[cn]
    Lc = np.linalg.cholesky(np.array([[1.0, cell["c"]], [cell["c"], 1.0]]))
    U = math.sqrt(a_w) * (rng(root, cid, f, 2, w["j"], sensor).standard_normal((N, 2)) @ Lc.T)
    if a_p:
        U = U + math.sqrt(a_p) * (pose_field[w["key_idx"]] @ Lc.T)
    if a_t:
        Lt = S["Lt"][cell["tau"]]
        U = U + math.sqrt(a_t) * ((Lt @ rng(root, cid, f, 3, w["j"], sensor).standard_normal((Lt.shape[1], 2))) @ Lc.T)
    return U * np.array([s1["sigma_r_m"], s1["sigma_s"]])[None, :]


def pose_field_for(S, root, f, cn):
    return S["Lhalf"] @ rng(root, S0.CELL_ID[cn], f, 1).standard_normal((S["Lhalf"].shape[1], 2))


def run_arms(S, w, cn, z, sensor_rng):
    anchor = S["anchor"]; ax = np.array(Wd.ANCHORS[anchor][:2])
    x0 = w["Xtrue"][0] + np.linalg.cholesky(P0) @ sensor_rng.standard_normal(4); x0[2] = float(FL.wrap(x0[2]))
    vn = sensor_rng.standard_normal((N, 2)) * np.sqrt(w["q"])
    ds_m = w["ds"] + vn[:, 0]; gy_m = w["dth"] + vn[:, 1]
    Sig = S["Sig"][(w["role"], cn)]; Bd = S0.blockdiag(Sig)
    Rk = [Sig[2 * k:2 * k + 2, 2 * k:2 * k + 2] for k in range(N)]
    mdl = Wd.model(); sp = Wd.spec(anchor)

    def h_fn(x):
        h, H = mdl.batch(np.asarray(x)[None], sp)
        return np.asarray(h)[0], np.asarray(H)[0]
    hb = lambda X: Wd.h_H(X, anchor)  # noqa: E731
    mu = np.zeros((N, 2)); rows = []
    for arm in ARMS:
        try:
            if arm in ("IID_BATCH", "ORACLE_CORR_BATCH"):
                X, Pst, info = FL.batch_map(hb, z, mu, Sig if arm == "ORACLE_CORR_BATCH" else Bd, ds_m, gy_m, w["dts"], x0, P0)
                Pf = Pst[-1]; n_used = N; iters = info["iters"]
            else:
                if arm == "MB_VAR_NOGATE":          # original MB_VAR rule: R_ss += sig(rho_hat)^2 on top of the per-packet R
                    Rfn = lambda k, sg: Rk[k] + np.diag([0.0, sg ** 2])  # noqa: E731
                else:
                    Rfn = lambda k, sg: Rk[k]  # noqa: E731
                X, PX, _, used = FL.ekf(h_fn, z, mu, Rfn, ds_m, gy_m, w["dts"], x0, P0,
                                        gate_thr=GATE if arm == "IID_EKF_SELFGATE" else None, anchor_xy=ax,
                                        sig_fn=Wd.PB.sig if arm == "MB_VAR_NOGATE" else None)
                Pf = PX[-1]; n_used = int(used.sum()); iters = 0
            e4 = w["Xtrue"][-1] - X[-1]; e4[2] = float(FL.wrap(e4[2]))
            T = IC.rotation_rt(w["Xtrue"][-1], Wd.ANCHORS[anchor]); er = T @ e4; pr = np.diag(T @ Pf @ T.T)
            ea = w["Xtrue"] - X; ea[:, 2] = np.angle(np.exp(1j * ea[:, 2]))
            row = dict(arm=arm, status="OK", n_used=n_used, iters=iters, nees4=float(e4 @ np.linalg.solve(Pf, e4)),
                       win_head_ms_deg2=float(np.mean(np.degrees(ea[:, 2]) ** 2)), win_xy_ms_cm2=float(np.mean(1e4 * np.sum(ea[:, :2] ** 2, 1))))
            row.update({f"e_{a}": float(er[i]) for i, a in enumerate(STATES)})
            row.update({f"P_{a}": float(pr[i]) for i, a in enumerate(STATES)})
        except Exception as ex:  # noqa: BLE001
            row = dict(arm=arm, status=f"FAILED:{type(ex).__name__}:{ex}")
        rows.append(row)
    return rows


def cmd_run(fields, split, out):
    lk = S0.lock(); check_code_lock(lk)
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    allowed = set(lk["splits"]["S_field"][split]); bad = [f for f in fields if f not in allowed]
    if bad:
        raise SystemExit(f"ERR_SPLIT_LEAK fields {bad} not in frozen {split}")
    root = seed_root(); S = setup(lk); rows = []; qa = []; seeds = []
    for f in fields:
        for cn, cell in S["cells"].items():
            pf = pose_field_for(S, root, f, cn) if cell["alphas"][0] else None
            if pf is not None:
                pf2 = pose_field_for(S, root, f, cn)
                qa.append(dict(field=f, cell=cn, check="pose_field_redraw_identical", value=float(np.max(np.abs(pf - pf2)))))
                qa.append(dict(field=f, cell=cn, check="spin_0_360_same_draw", value=float(np.max(np.abs(pf[S["spin_idx"][0]] - pf[S["spin_idx"][1]])))))
            for w in S["wins"].values():
                for sn in SENSOR_SEEDS:
                    eps = draw_eps(S, root, f, cn, w, sn, pf)
                    Sg = S["Sig"][(w["role"], cn)]; ev = eps.reshape(-1)
                    qa.append(dict(field=f, cell=cn, role=w["role"], sensor_seed=sn, check="mahalanobis_per_dim",
                                   value=float(ev @ np.linalg.solve(Sg, ev)) / (2 * N)))
                    z = w["htrue"] + eps
                    base = dict(split=split, field=f, sensor_seed=sn, window=w["id"], role=w["role"], cell=cn)
                    seeds.append(dict(base, seed_root=root, cell_id=S0.CELL_ID[cn], window_j=w["j"]))
                    if np.any(np.abs(z[:, 1]) > Wd.PARAMS["synthetic_s1"]["physical_s_domain_abs_max"]) or not np.all(np.isfinite(z)):
                        rows.append(dict(base, arm="ALL", status="STOP_UNPHYSICAL_OBSERVATION")); continue
                    for r in run_arms(S, w, cn, z, rng(root, 0, f, 4, w["j"], sn)):
                        rows.append(dict(base, **r))
        print("S1 field", f, "rows", len(rows), flush=True)
    tag = "_".join(map(str, fields))
    pd.DataFrame(rows).to_csv(out / f"S1_ROWS_{split}_{tag}.csv", index=False, float_format="%.12g")
    pd.DataFrame(qa).to_csv(out / f"S1_QA_{split}_{tag}.csv", index=False, float_format="%.12g")
    pd.DataFrame(seeds).to_csv(out / f"S1_SEEDS_{split}_{tag}.csv", index=False)
    (out / f"S1_SETUP_{split}_{tag}.json").write_text(json.dumps(dict(n_world_poses=S["n_world_poses"], pose_psd_min_eig=S["psd"][0],
                                                                      pose_psd_max_eig=S["psd"][1], windows={r: w["id"] for r, w in S["wins"].items()}), indent=1))
    return 0


# ----------------------------------------------------------------------------- statistics (field = unit)
def field_table(df, arm, role, cell):
    d = df[(df.arm == arm) & (df.role == role) & (df.cell == cell) & (df.status == "OK")]
    agg = {f"mse_{a}": (f"e_{a}", lambda v: float(np.mean(np.square(v)))) for a in STATES}
    agg.update({f"claim_{a}": (f"P_{a}", "mean") for a in STATES})
    agg.update(nees=("nees4", "mean"), head_ms=("win_head_ms_deg2", "mean"), xy_ms=("win_xy_ms_cm2", "mean"))
    return d.groupby("field").agg(**agg)


def boot(tables, fn, B=4000, seed=20261029):
    """tables: per-field DataFrames on the same field index; fn(list of column-mean Series) -> scalar. Field bootstrap."""
    idx = tables[0].index.values
    for t in tables[1:]:
        if not np.array_equal(t.index.values, idx):
            raise ValueError("unpaired field index")
    r = np.random.default_rng(seed); vals = np.empty(B)
    arrs = [t.to_numpy() for t in tables]; cols = [t.columns for t in tables]
    for b in range(B):
        s = r.integers(0, len(idx), len(idx))
        vals[b] = fn([pd.Series(a[s].mean(0), index=c) for a, c in zip(arrs, cols)])
    est = fn([t.mean() for t in tables])
    return dict(est=float(est), lo=float(np.quantile(vals, 0.025)), hi=float(np.quantile(vals, 0.975)), se=float(np.std(vals, ddof=1)), n_fields=len(idx))


def band_verdict(lo, hi, half):
    """Equivalence on a log scale: PASS if CI inside [-half, half]; FAIL if CI disjoint from it; else UNDETERMINED."""
    if lo >= -half and hi <= half:
        return "PASS"
    if lo > half or hi < -half:
        return "FAIL"
    return "UNDETERMINED"


def decide(rows, pred, did_pred, eff):
    lf = math.log(eff["equivalence_factor"]); out = dict(H1=[], H2=[], H3=[], CAL=[], SENS=[])
    log_infl = lambda m, a: math.log(m[0][f"mse_{a}"] / m[0][f"claim_{a}"])  # noqa: E731
    # H1: IID_BATCH realised inflation reproduces the exact S0 sandwich inflation (primary cells, tan & psi, both windows)
    for role in ("LOW", "HIGH"):
        for cell in S0.cells(Wd.PARAMS):
            for a in STATES:
                ft = field_table(rows, "IID_BATCH", role, cell)[[f"mse_{a}", f"claim_{a}"]]
                p = float(pred.loc[(role, cell), f"infl_iid_{a}"])
                b = boot([ft], lambda m, a=a, p=p: log_infl(m, a) - math.log(p))
                rec = dict(role=role, cell=cell, state=a, infl_S1=math.exp(b["est"]) * p, infl_S0=p, log_dev=b["est"], lo=b["lo"], hi=b["hi"], se=b["se"],
                           verdict=band_verdict(b["lo"], b["hi"], lf))
                (out["H1"] if (cell in PRIMARY and a in ("tan", "psi")) else out["SENS"]).append(dict(rec, test="H1_reproduction"))
    # H2: geometry x correlation interaction on log inflation (DID), sign and size registered from S0 (JOINT design)
    for a in ("tan", "psi"):
        keys = [(r, c) for r in ("LOW", "HIGH") for c in PRIMARY]
        fts = [field_table(rows, "IID_BATCH", r, c)[[f"mse_{a}", f"claim_{a}"]] for r, c in keys]

        def did(ms, a=a):
            v = {k: log_infl([m], a) for k, m in zip(keys, ms)}
            return (v[("LOW", "POSE_HIGH")] - v[("LOW", "LOWCORR")]) - (v[("HIGH", "POSE_HIGH")] - v[("HIGH", "LOWCORR")])
        b = boot(fts, did)
        p = float(did_pred[(did_pred.state == a) & (did_pred.design == "JOINT") & (did_pred.quantity == "infl_iid")].DID_log.iloc[0])
        testable = abs(p) >= math.log(eff["did_min_predicted_factor"])
        sgn = math.copysign(1.0, p); lo_s, hi_s = sorted((sgn * b["lo"], sgn * b["hi"]))   # oriented so that the prediction is > 0
        if not testable:
            v = "NOT_TESTABLE"
        elif lo_s > 0:
            v = "PASS"
        elif hi_s < abs(p) * eff["did_min_fraction_of_prediction"]:
            v = "FAIL"
        else:
            v = "UNDETERMINED"
        out["H2"].append(dict(test="H2_interaction", state=a, DID_S1=b["est"], lo=b["lo"], hi=b["hi"], se=b["se"], DID_S0=p, testable=testable, verdict=v))
    # H3: estimator consequence under POSE_HIGH: oracle/iid MSE ratio where S0 predicts a material gain
    for role in ("LOW", "HIGH"):
        for a in ("tan", "psi"):
            fo = field_table(rows, "ORACLE_CORR_BATCH", role, "POSE_HIGH")[[f"mse_{a}"]]
            fi = field_table(rows, "IID_BATCH", role, "POSE_HIGH")[[f"mse_{a}"]]
            b = boot([fo, fi], lambda m, a=a: math.log(m[0][f"mse_{a}"] / m[1][f"mse_{a}"]))
            p = float(pred.loc[(role, "POSE_HIGH"), f"mse_ratio_oracle_iid_{a}"])
            app = p <= eff["oracle_gain_ratio_max"]
            v = "NOT_APPLICABLE" if not app else ("PASS" if b["hi"] < 0 else ("FAIL" if b["lo"] > 0 else "UNDETERMINED"))
            out["H3"].append(dict(test="H3_oracle_gain", role=role, state=a, ratio_S1=math.exp(b["est"]), lo=math.exp(b["lo"]), hi=math.exp(b["hi"]),
                                  se_log=b["se"], ratio_S0=p, applicable=app, verdict=v))
    # CAL: the oracle (true Sigma) is calibrated: realised/claimed variance within the equivalence band (tan, psi; primary cells)
    for role in ("LOW", "HIGH"):
        for cell in PRIMARY:
            for a in ("tan", "psi"):
                ft = field_table(rows, "ORACLE_CORR_BATCH", role, cell)[[f"mse_{a}", f"claim_{a}"]]
                b = boot([ft], lambda m, a=a: log_infl(m, a))
                out["CAL"].append(dict(test="CAL_oracle", role=role, cell=cell, state=a, infl=math.exp(b["est"]), log_dev=b["est"], lo=b["lo"], hi=b["hi"],
                                       se=b["se"], verdict=band_verdict(b["lo"], b["hi"], lf)))
    h1 = [r["verdict"] for r in out["H1"]]
    tested = [r for r in out["H2"] if r["testable"]] + [r for r in out["H3"] if r["applicable"]]
    cons = [r["verdict"] for r in tested] + [r["verdict"] for r in out["CAL"]]
    if "FAIL" in h1:
        verdict = "NOT_SUPPORTED"
    elif "UNDETERMINED" in h1 or not tested:
        verdict = "INCONCLUSIVE"
    elif all(v == "PASS" for v in cons):
        verdict = "SUPPORTED"
    elif "PASS" in cons or "FAIL" in cons:
        verdict = "MIXED"
    else:
        verdict = "INCONCLUSIVE"
    out["verdict"] = verdict
    return out


def power(dec, n_dev, plan, eff):
    """Pre-registered: projected 95% half-width at n must fit inside the decision margin of every primary contrast."""
    lf = math.log(eff["equivalence_factor"]); need = []
    for r in dec["H1"] + dec["CAL"]:
        need.append((r["test"], r.get("role"), r.get("cell"), r["state"], r["se"], lf - abs(r["log_dev"])))
    for r in dec["H2"]:
        if r["testable"]:
            need.append((r["test"], None, None, r["state"], r["se"], abs(r["DID_S0"]) / 2))
    for r in dec["H3"]:
        if r["applicable"]:
            need.append((r["test"], r["role"], "POSE_HIGH", r["state"], r["se_log"], abs(math.log(r["ratio_S0"])) / 2))
    rows = []; ok = {}
    for n in (plan["n_confirm_default"], plan["n_confirm_large"]):
        good = True
        for t, ro, ce, st, se, room in need:
            hw = 1.96 * se * math.sqrt(n_dev / n); g = bool(room > 0 and hw <= room)
            rows.append(dict(n=n, test=t, role=ro, cell=ce, state=st, se_dev=se, projected_halfwidth=hw, required=room, ok=g)); good &= g
        ok[n] = good
    n_conf = plan["n_confirm_default"] if ok[plan["n_confirm_default"]] else plan["n_confirm_large"]
    return dict(rule=plan["power_rule"], n_confirm=n_conf, underpowered_at_max=not ok[plan["n_confirm_large"]], rows=rows)


def _json(o):
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    raise TypeError(type(o))


def cmd_aggregate(shards, split, out):
    lk = S0.lock(); check_code_lock(lk); out = Path(out); out.mkdir(parents=True, exist_ok=True)
    plan = lk["run_plan"]["S1"]; eff = lk["resolved"]["EFFECT_SIZE_RULES"]

    def cat(pat):
        fs = sorted(glob.glob(str(Path(shards) / "**" / pat), recursive=True))
        return pd.concat([pd.read_csv(f) for f in fs], ignore_index=True) if fs else pd.DataFrame(columns=["field", "status", "check", "value"])
    rows = cat(f"S1_ROWS_{split}_*.csv"); qa = cat(f"S1_QA_{split}_*.csv"); seeds = cat(f"S1_SEEDS_{split}_*.csv")
    req = json.loads((Wd.EXP / "RUN_REQUEST.json").read_text())
    expected = sorted(req["field_ids"])
    if split == "HOLDOUT":
        prefix_ok = expected == sorted(lk["splits"]["S_field"]["HOLDOUT"][:len(expected)]) and len(expected) in (plan["n_confirm_default"], plan["n_confirm_large"])
    elif split == "DEV":
        prefix_ok = expected == sorted(plan["fields_DEV"])
    else:
        prefix_ok = set(expected) <= set(lk["splits"]["S_field"][split])
    got = sorted(int(x) for x in rows.field.unique()) if len(rows) else []
    rows.to_csv(out / f"S1_RESULTS_{split}.csv", index=False, float_format="%.12g"); seeds.to_csv(out / "SEED_LEDGER.csv", index=False)
    qa.to_csv(out / f"S1_QA_{split}.csv", index=False, float_format="%.12g")
    # ---- generator / execution QA (technical)
    m = qa[qa.check == "mahalanobis_per_dim"].groupby("cell").value.mean()
    mtol = 4 * math.sqrt(2 / (2 * N)) / math.sqrt(max(len(got), 1))
    red = qa[qa.check == "pose_field_redraw_identical"].value; spin = qa[qa.check == "spin_0_360_same_draw"].value
    qaj = dict(fields_expected=expected, fields_got=got, request_field_rule_ok=bool(prefix_ok),
               pose_redraw_max=float(red.max()) if len(red) else None, spin_0_360_max=float(spin.max()) if len(spin) else None,
               mahalanobis_mean_by_cell={k: float(v) for k, v in m.items()}, mahalanobis_tol=mtol,
               stops=int((rows.status == "STOP_UNPHYSICAL_OBSERVATION").sum()),
               failures=int(rows.status.astype(str).str.startswith("FAILED").sum()),
               n_rows=int(len(rows)), n_rows_expected=len(expected) * len(SENSOR_SEEDS) * 2 * len(S0.CELL_ID) * len(ARMS))
    qaj["pass"] = bool(got == expected and prefix_ok and qaj["pose_redraw_max"] == 0.0 and qaj["spin_0_360_max"] == 0.0
                       and len(m) == len(S0.CELL_ID) and all(abs(v - 1) <= mtol for v in m.values)
                       and qaj["stops"] == 0 and qaj["failures"] == 0 and qaj["n_rows"] == qaj["n_rows_expected"])
    (out / "S1_COVARIANCE_QA.json").write_text(json.dumps(qaj, indent=1, default=_json))
    # ---- S0 predictions (committed run under the same frozen contract)
    s0dir = Path(os.environ["S0_RESULTS_DIR"]); s0m = json.loads((s0dir / "MANIFEST.json").read_text())
    s0_ok = s0m.get("status") == "PASS" and s0m.get("contract_sha256") == MF.sha256_file(MF.CONTRACT)
    pred = pd.read_csv(s0dir / "S0_PREDICTIONS.csv").set_index(["role", "cell"]); did_pred = pd.read_csv(s0dir / "S0_DID.csv")
    # ---- descriptive table (all arms, all cells; not decisional)
    st = []
    for arm in ARMS:
        for role in ("LOW", "HIGH"):
            for cell in S0.CELL_ID:
                ft = field_table(rows, arm, role, cell)
                if ft.empty:
                    continue
                d = dict(arm=arm, role=role, cell=cell, n_fields=len(ft), nees4=float(ft.nees.mean()), head_rmse_deg=math.sqrt(ft.head_ms.mean()),
                         xy_rmse_cm=math.sqrt(ft.xy_ms.mean()))
                for a in STATES:
                    d.update({f"rmse_{a}": math.sqrt(ft[f"mse_{a}"].mean()), f"claim_sd_{a}": math.sqrt(ft[f"claim_{a}"].mean()),
                              f"infl_{a}": ft[f"mse_{a}"].mean() / ft[f"claim_{a}"].mean()})
                st.append(d)
    pd.DataFrame(st).to_csv(out / f"S1_STATS_{split}.csv", index=False, float_format="%.8g")
    ok = qaj["pass"] and s0_ok
    dec = decide(rows, pred, did_pred, eff) if ok else dict(verdict="INCONCLUSIVE", H1=[], H2=[], H3=[], CAL=[], SENS=[])
    for k in ("H1", "H2", "H3", "CAL", "SENS"):
        pd.DataFrame(dec[k]).to_csv(out / f"S1_{k}_{split}.csv", index=False, float_format="%.8g")
    res = dict(split=split, scientific_verdict_track_S=dec["verdict"] if split == "HOLDOUT" else "NOT_EVALUATED (pilot/smoke split)",
               split_level_rule_outcome=dec["verdict"], qa_pass=qaj["pass"], s0_reference=s0dir.name, s0_reference_ok=s0_ok,
               release="TECHNICAL_QA_ONLY (independent audit pending; SELF_REVIEW_ONLY)",
               scope="Track S synthetic known-generative only; no physical-RF, deployability or MB_VAR-superiority claim")
    if split == "DEV" and ok:
        pw = power(dec, len(got), plan, eff)
        pd.DataFrame(pw.pop("rows")).to_csv(out / "S1_POWER_DEV.csv", index=False, float_format="%.6g")
        pw["holdout_fields"] = lk["splits"]["S_field"]["HOLDOUT"][:pw["n_confirm"]]
        res["power"] = pw
    (out / f"S1_DECISION_{split}.json").write_text(json.dumps(res, indent=1, default=_json))
    status = "PASS" if ok else "FAIL"
    lock_path = Path(os.environ.get("REFLECT_ROOT", ".")) / "out" / "INPUT_LOCK.sha256"
    MF.write_manifest(out, phase="P2_S1", status=status, contract_sha=MF.sha256_file(MF.CONTRACT),
                      config_files=[Wd.EXP / "config/PLAN_PARAMETERS.json"], input_lock=lock_path,
                      outputs=sorted(out.glob("S1_*")), seed_ledger=out / "SEED_LEDGER.csv",
                      verdict=dec["verdict"] if (split == "HOLDOUT" and ok) else "NOT_EVALUATED", unit="field_realization",
                      limitations=["synthetic additive observation noise on the FFD LOS model; not RF physics",
                                   "q-consistent synthetic control noise; x0 drawn from P0", "anchor A windows only (anchor C outside the |h_s| domain)",
                                   "auditor SELF_REVIEW_ONLY; release TECHNICAL_QA_ONLY",
                                   "DEV split = pilot (power only)" if split == "DEV" else f"{split} split"])
    print("S1 aggregate", split, status, dec["verdict"])
    return 0 if status == "PASS" else 1


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd"); ap.add_argument("--fields"); ap.add_argument("--split", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--shards")
    a = ap.parse_args()
    if a.cmd == "run":
        return cmd_run([int(x) for x in a.fields.split(",") if x != ""], a.split, a.out)
    return cmd_aggregate(a.shards, a.split, a.out)


if __name__ == "__main__":
    raise SystemExit(main())
