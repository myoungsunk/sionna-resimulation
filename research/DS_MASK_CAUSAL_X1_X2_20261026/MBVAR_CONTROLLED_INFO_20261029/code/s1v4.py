"""P2_S1V4 (AMENDMENT-009): S1V3 with the S1V3 design-audit fixes (audit/mbvar-info-s1v3-design-20261030, 353381b3).

  s1v4.py run --fields 10,11 --split DEV2 --out D
  s1v4.py aggregate --shards D --split DEV2 --out D        (env S0V2_RESULTS_DIR)

Changes vs s1v3 (s1v3.py itself is frozen under AMENDMENT-008 and unchanged):
  F1  class v3.1: a probe descent > tau makes a row NOT_CERTIFIED even when the analytic Newton decrement is ~0;
      CONVERGED_SMOOTH = decrement <= 1e-10 AND no probe descent > tau.
  F2  the polish runs whenever any probe finds descent > POLISH_TOL (not only when the analytic decrement is > 1e-10).
  F3  explicit one-sided axis probes: +- rho_a * sqrt(P0_jj) on each x0 coordinate, rho_a in {1e-2, 1e-3} (left/right
      directional cost change at a kink), added to the GN-line and random probes.
  F4  the full window-end C10 covariance (4x4) is stored and NEES is recomputed with it (nees4_C10); nees4 (analytic) kept.
Inputs, E, post-fit P conventions and the A8-5/A8-6 machinery are those of s1v3 (imported, not copied).
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
import a8_jac as AJ  # noqa: E402
import a9_class as A9  # noqa: E402
import filters as FL  # noqa: E402
import info_core as IC  # noqa: E402
import manifest as MF  # noqa: E402
import s0v2 as S0V2  # noqa: E402
import s1_mc as M  # noqa: E402
import s1v2 as V  # noqa: E402
import s1v3 as B3  # noqa: E402
import world as Wd  # noqa: E402

STATES = B3.STATES; N = B3.N; P0M = B3.P0M
TAU, RHO, N_DIR, GN_ALPHAS = B3.TAU, B3.RHO, B3.N_DIR, B3.GN_ALPHAS
AXIS_RHO = (1e-2, 1e-3)
POLISH_TOL, POLISH_MAX = B3.POLISH_TOL, B3.POLISH_MAX
POLISH_MAX_DREF, POLISH_MAX_DCOST = B3.POLISH_MAX_DREF, B3.POLISH_MAX_DCOST
D_REF = B3.D_REF; dref_diff = B3.dref_diff; key_seed = B3.key_seed
PREFIX = "S1V4"


def lock_v4():
    lk = B3.lock_v3()
    if "AMENDMENT-009" not in lk.get("applied_amendment_locks", []):
        raise SystemExit("ERR_CONTRACT_DRAFT: AMENDMENT-009 lock not FROZEN/applied")
    return lk


def hb_true_tap(w):
    return lambda X, t=w["taps"]: Wd.h_H_tap(X, "A", t)


def probe(hb, z, Sm, ds_m, gy_m, dts, x0, theta, seed, gn_steps):
    """F3 probe set: GN lines (6 conventions x GN_ALPHAS) + N_DIR random +- pairs (rho, prior-scaled) + one-sided axis
    probes on x0. Returns (min cost change, label, displacement). Uses cost values only, never P."""
    Lm, L0, qv = B3._mats(Sm, ds_m, dts); mu = np.zeros_like(z); th0, thv = theta; n = len(z)
    scale = np.r_[np.sqrt(np.diag(P0M)), np.sqrt(qv[1:].reshape(-1))]
    c0, _ = FL._v2_parts(hb, z, mu, Lm, L0, x0, qv, ds_m, gy_m, dts, th0, thv, jac=False)

    def dc(d):
        x1 = th0 + d[:4]; x1[2] = FL.wrap(x1[2]); v1 = thv.copy(); v1[1:] = thv[1:] + d[4:].reshape(n - 1, 2)
        return FL._v2_parts(hb, z, mu, Lm, L0, x0, qv, ds_m, gy_m, dts, x1, v1, jac=False)[0] - c0
    cand = [(a * s, f"gn_{m}_{a:g}") for m, s in gn_steps.items() for a in GN_ALPHAS]
    r = np.random.default_rng(seed)
    for i in range(N_DIR):
        u = r.standard_normal(len(scale)); d = RHO * scale * u / np.linalg.norm(u)
        cand += [(d, f"rand{i}+"), (-d, f"rand{i}-")]
    for ra in AXIS_RHO:
        for j in range(4):
            d = np.zeros(len(scale)); d[j] = ra * scale[j]
            cand += [(d, f"axis{j}+{ra:g}"), (-d, f"axis{j}-{ra:g}")]
    best = (np.inf, "", None)
    for d, lab in cand:
        v = dc(d)
        if v < best[0]:
            best = (v, lab, d)
    return float(best[0]), best[1], best[2]


def class_v31(dec_A, dmin):
    """F1: a descent found by any probe overrides the analytic decrement (a9_class.class_v31)."""
    return A9.class_v31(dec_A, dmin, TAU, FL.V2_DEC_TOL)


def polish(hb, z, Sm, ds_m, gy_m, dts, x0, theta, seed):
    """F2: best-probe descent while it lowers the cost by > POLISH_TOL, regardless of the analytic decrement."""
    th0, thv = theta[0].copy(), theta[1].copy(); n = len(z)
    for k in range(POLISH_MAX):
        pf = B3.post_fit_P(hb, z, Sm, ds_m, gy_m, dts, x0, (th0, thv), np.eye(4))
        dmin, _, d = probe(hb, z, Sm, ds_m, gy_m, dts, x0, (th0, thv), seed + k, pf["_gn_steps"])
        if not dmin < -POLISH_TOL:
            return (th0, thv), k, False
        th0 = th0 + d[:4]; th0[2] = FL.wrap(th0[2]); thv = thv.copy(); thv[1:] = thv[1:] + d[4:].reshape(n - 1, 2)
    return (th0, thv), POLISH_MAX, True


def estimate(w, Sm, inp, seed_key, max_iter=FL.V2_MAX_ITER, hb=None):
    """E' (v4) = batch_map_v2_ms (E, unchanged) + F2 polish. hb defaults to the true-tap model (B option overrides)."""
    hb = hb or hb_true_tap(w)
    z, x0, ds_m, gy_m, dts = inp["z"], inp["x0"], inp["ds_m"], inp["gy_m"], w["dts"]
    X, _, info = FL.batch_map_v2_ms(hb, z, np.zeros((N, 2)), Sm, ds_m, gy_m, dts, x0, P0M, max_iter=max_iter)
    thp, nst, cap = polish(hb, z, Sm, ds_m, gy_m, dts, x0, info["theta"], key_seed("POLISH", *seed_key))
    Lm, L0, qv = B3._mats(Sm, ds_m, dts)
    cp, Xp = FL._v2_parts(hb, z, np.zeros((N, 2)), Lm, L0, x0, qv, ds_m, gy_m, dts, thp[0], thp[1], jac=False)
    rec = dict(polish_steps=nst, polish_cost_decrease=float(info["cost"] - cp), polish_hit_cap=bool(cap), polish_E_vs_Ep_dref=dref_diff(X[-1], Xp[-1]))
    return X, info, thp, Xp, float(cp), rec


def c10_end(hb, z, Sm, ds_m, gy_m, dts, x0, theta):
    """F4: full window-end covariance under the primary convention (state coordinates)."""
    Lm, L0, qv = B3._mats(Sm, ds_m, dts)
    _, _, A, _, J = FL._v2_parts(AJ.h_batch_for(AJ.PRIMARY, hb), z, np.zeros_like(z), Lm, L0, x0, qv, ds_m, gy_m, dts, theta[0], theta[1])
    Nm = A.T @ A; Pe = J[-1] @ np.linalg.inv(0.5 * (Nm + Nm.T)) @ J[-1].T
    return 0.5 * (Pe + Pe.T)


def eval_batch(w, arm, Sm, inp, seed_key, hb=None):
    """E'(v4) + A8-3 + class v3.1 + F4 for one batch arm. Returns (row, X', info_E, theta')."""
    hb = hb or hb_true_tap(w)
    z, x0, ds_m, gy_m, dts = inp["z"], inp["x0"], inp["ds_m"], inp["gy_m"], w["dts"]
    XE, info, thp, Xp, cp, prec = estimate(w, Sm, inp, seed_key, hb=hb)
    T = IC.rotation_rt(w["Xtrue"][-1], Wd.ANCHORS["A"])
    pf = B3.post_fit_P(hb, z, Sm, ds_m, gy_m, dts, x0, thp, T); gn = pf.pop("_gn_steps"); PA = pf.pop("_PA_end"); pf.pop("_X")
    dmin, which, _ = probe(hb, z, Sm, ds_m, gy_m, dts, x0, thp, key_seed("CLASS", *seed_key), gn)
    P10 = c10_end(hb, z, Sm, ds_m, gy_m, dts, x0, thp)
    e4 = w["Xtrue"][-1] - Xp[-1]; e4[2] = float(FL.wrap(e4[2])); P10r = T @ P10 @ T.T
    row = dict(arm=arm, status="OK", conv=info["status"], class_v31=class_v31(pf["dec_A_fixed"], dmin),
               class_v3_A008_rule=B3.class_v3(pf["dec_A_fixed"], dmin), probe_min_dcost=dmin, probe_argmin=which,
               stop_reason=info["stop_reason"], iters=info["iters"], n_accept=info["n_accept"], n_reject=info["n_reject"], n_used=N,
               cost_E=info["cost"], cost=cp, cost_start0=info["ms_cost_start0"], newton_decrement=info["newton_decrement"],
               gn_shift_end_sd=info["gn_shift_end_sd"], ms_triggered=info["ms_triggered"], ms_best_k=info["ms_best_k"],
               ms_n_distinct_minima=info["ms_n_distinct_minima"], ms_final_misfit=info["ms_final_misfit"], rescued=info["rescued"],
               kink_poses_at_E=B3.kink_count(Xp, w["taps"]), nees4_C10=float(e4 @ np.linalg.solve(P10, e4)),
               **{f"C10rot_{i}{j}": float(P10r[i, j]) for i in range(4) for j in range(i, 4)}, **prec, **pf)
    row.update(V._row_from(w, Xp, PA, "A"))
    row.update({f"xend_{i}": float(Xp[-1, i]) for i in range(4)}); row.update({f"xendE_{i}": float(XE[-1, i]) for i in range(4)})
    return row, Xp, info, thp


def probe_power(hb, z, Sm, ds_m, gy_m, dts, x0, theta, seed, target=1.0):
    """PROBE_POWER negative control with the v4 probe set and class v3.1."""
    Lm, L0, qv = B3._mats(Sm, ds_m, dts); mu = np.zeros_like(z); th0, thv = theta; n = len(z)
    scale = np.r_[np.sqrt(np.diag(P0M)), np.sqrt(qv[1:].reshape(-1))]
    u = np.random.default_rng(seed).standard_normal(len(scale)); u = scale * u / np.linalg.norm(u)

    def disp(t):
        x1 = th0 + t * u[:4]; x1[2] = FL.wrap(x1[2]); v1 = thv.copy(); v1[1:] = thv[1:] + t * u[4:].reshape(n - 1, 2)
        return x1, v1
    c0 = FL._v2_parts(hb, z, mu, Lm, L0, x0, qv, ds_m, gy_m, dts, th0, thv, jac=False)[0]
    f = lambda t: FL._v2_parts(hb, z, mu, Lm, L0, x0, qv, ds_m, gy_m, dts, *disp(t), jac=False)[0] - c0  # noqa: E731
    lo, hi = 0.0, 1e-3
    while f(hi) < target and hi < 1e3:
        lo, hi = hi, 2 * hi
    for _ in range(30):
        if 0.5 * target <= f(hi) <= 2 * target:
            break
        mid = 0.5 * (lo + hi); (lo, hi) = (mid, hi) if f(mid) < target else (lo, mid)
    thd = disp(hi); rise = f(hi)
    pf = B3.post_fit_P(hb, z, Sm, ds_m, gy_m, dts, x0, thd, np.eye(4)); gn = pf.pop("_gn_steps")
    dmin, which, _ = probe(hb, z, Sm, ds_m, gy_m, dts, x0, thd, seed + 1, gn)
    return dict(pp_rise=float(rise), pp_dmin=dmin, pp_argmin=which, pp_class=class_v31(pf["dec_A_fixed"], dmin))


def cmd_run(fields, split, out):
    lk = lock_v4(); M.check_code_lock(lk)
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    allowed = set(lk["splits"]["S_field"][split]); bad = [f for f in fields if f not in allowed]
    if bad:
        raise SystemExit(f"ERR_SPLIT_LEAK fields {bad} not in frozen {split}")
    root = M.seed_root(); S = V.setup(lk); rows = []; qa = []; seeds = []; rec = {}; pairs = B3.revisit_pairs(S)
    for f in fields:
        for cn, cell in S["cells"].items():
            if not any(cn in w["cells"] for w in S["wins"].values()):
                continue
            pf = S["Lhalf"] @ M.rng(root, S0V2.CELL_ID_V2[cn], f, 1).standard_normal((S["Lhalf"].shape[1], 2)) if cell["alphas"][0] else None
            for w in S["wins"].values():
                if cn not in w["cells"]:
                    continue
                for sn in M.SENSOR_SEEDS:
                    inp = B3.make_inputs(S, root, f, cn, w, sn, pf); z = inp["z"]
                    Sig, models = B3.arm_models(S, w, cn); ev = inp["eps"].reshape(-1)
                    qa.append(dict(field=f, cell=cn, role=w["role"], sensor_seed=sn, check="mahalanobis_per_dim", value=float(ev @ np.linalg.solve(Sig, ev)) / (2 * N)))
                    if w["role"] == "REV60" and pairs:
                        if cell["alphas"][0]:
                            qa.append(dict(field=f, cell=cn, role="REV60", sensor_seed=sn, check="revisit_pose_identical_maxdiff",
                                           value=float(max(np.max(np.abs(inp["Up"][i] - inp["Up"][j])) for i, j in pairs))))
                        if cell["alphas"][1]:
                            qa.append(dict(field=f, cell=cn, role="REV60", sensor_seed=sn, check="revisit_time_differs_mindiff",
                                           value=float(min(np.max(np.abs(inp["Ut"][i] - inp["Ut"][j])) for i, j in pairs))))
                    kb = f"{f}|{w['role']}|{cn}|{sn}"
                    rec.update({f"{kb}|z": z, f"{kb}|ds_m": inp["ds_m"], f"{kb}|gy_m": inp["gy_m"], f"{kb}|x0": inp["x0"],
                                f"{kb}|taps": np.asarray(w["taps"]), f"{kb}|Sig_true_fp": B3.sig_fp(Sig), f"{kb}|pose_keys_sha": np.array(B3.pose_keys_sha(w))})
                    base = dict(split=split, field=f, sensor_seed=sn, window=w["id"], role=w["role"], cell=cn)
                    seeds.append(dict(base, seed_root=root, cell_id=S0V2.CELL_ID_V2[cn], window_j=w["j"]))
                    if np.any(np.abs(z[:, 1]) > S["s1"]["physical_s_domain_abs_max"]) or not np.all(np.isfinite(z)):
                        rows.append(dict(base, arm="ALL", status="STOP_UNPHYSICAL_OBSERVATION")); continue
                    if w["role"] in ("LOW", "HIGH"):
                        rr, ctl = B3.ekf_rows(S, w, cn, z, M.rng(root, 0, f, 4, w["j"], sn))
                        if not (np.array_equal(ctl["ds_m"], inp["ds_m"]) and np.array_equal(ctl["gy_m"], inp["gy_m"])):
                            raise SystemExit("ERR_INPUT_PATH: EKF and batch controls differ")
                        rows += [dict(base, **r) for r in rr]
                    for arm, Sm in models.items():
                        rec[f"{kb}|{arm}|Sig_model_fp"] = B3.sig_fp(Sm)
                        try:
                            r = eval_batch(w, arm, Sm, inp, (f, w["role"], cn, sn, arm))[0]
                        except Exception as ex:  # noqa: BLE001
                            r = dict(arm=arm, status=f"FAILED:{type(ex).__name__}:{ex}")
                        rows.append(dict(base, **r))
        print(PREFIX, "field", f, "rows", len(rows), flush=True)
    tag = "_".join(map(str, fields))
    pd.DataFrame(rows).to_csv(out / f"{PREFIX}_ROWS_{split}_{tag}.csv", index=False, float_format="%.17g")
    pd.DataFrame(qa).to_csv(out / f"{PREFIX}_QA_{split}_{tag}.csv", index=False, float_format="%.17g")
    pd.DataFrame(seeds).to_csv(out / f"{PREFIX}_SEEDS_{split}_{tag}.csv", index=False)
    with open(out / f"{PREFIX}_INPUTS_{split}_{tag}.zip", "wb") as fh:
        np.savez_compressed(fh, **rec)
    return 0


# ----------------------------------------------------------------------------- aggregate
STRATA = [(g, k, a) for g in ("LH", "RV") for k in (False, True) for a in ("tan", "psi")]


def calibration(b):
    """A8-5 with all 8 strata listed (an empty / single-field stratum is UNDETERMINED, G3) + NEES_C10 per window group."""
    out = []; lf = math.log(1.5)
    o = b[b.arm == "ORACLE_CORR_BATCH"].copy()
    o["grp"] = np.where(o.role.isin(["LOW", "HIGH"]), "LH", "RV"); o["kink"] = o.kink_poses_at_E.astype(float) > 0
    for grp, kink, a in STRATA:
        d = o[(o.grp == grp) & (o.kink == kink)]
        P = d[f"P_{AJ.PRIMARY}_{a}"].astype(float); e = d[f"e_{a}"].astype(float)
        t = pd.DataFrame(dict(field=d.field, z2=e ** 2 / P, cov=(e.abs() / np.sqrt(P) <= 1.96).astype(float)))
        ft = t.groupby("field")[["z2"]].mean()
        if len(ft) >= 2:
            bb = M.boot([ft], lambda m: math.log(m[0]["z2"])); v = M.band_verdict(bb["lo"], bb["hi"], lf)
            est, lo, hi = math.exp(bb["est"]), math.exp(bb["lo"]), math.exp(bb["hi"])
        else:
            est = float(ft.z2.mean()) if len(ft) else float("nan"); lo = hi = float("nan"); v = "UNDETERMINED"
        out.append(dict(group=grp, kink_at_E=kink, state=a, n_runs=len(d), n_fields=len(ft), evaluable=len(ft) >= 2, mean_z2=est, lo=lo, hi=hi,
                        coverage95=float(t["cov"].mean()) if len(t) else float("nan"), verdict=v))
    nees = []
    for grp in ("LH", "RV"):
        d = o[o.grp == grp]; ft = d.groupby("field")[["nees4_C10"]].mean()
        if len(ft) >= 2:
            bb = M.boot([ft], lambda m: math.log(m[0]["nees4_C10"] / 4.0))
            nees.append(dict(group=grp, n_runs=len(d), mean_nees4_C10=4 * math.exp(bb["est"]), lo=4 * math.exp(bb["lo"]), hi=4 * math.exp(bb["hi"]),
                             verdict=M.band_verdict(bb["lo"], bb["hi"], lf)))
    return pd.DataFrame(out), pd.DataFrame(nees)


def requested_fields():
    return sorted(json.loads((Wd.EXP / "RUN_REQUEST.json").read_text())["field_ids"])


def cmd_aggregate(shards, split, out):
    lk = lock_v4(); M.check_code_lock(lk); out = Path(out); out.mkdir(parents=True, exist_ok=True)
    plan = lk["run_plan"]["S1V4"]; eff = lk["resolved"]["EFFECT_SIZE_RULES"]

    def cat(pat):
        fs = sorted(glob.glob(str(Path(shards) / "**" / pat), recursive=True))
        return pd.concat([pd.read_csv(f) for f in fs], ignore_index=True) if fs else pd.DataFrame(columns=["field", "status", "check", "value", "arm", "class_v31", "conv"])
    rows = cat(f"{PREFIX}_ROWS_{split}_*.csv"); qa = cat(f"{PREFIX}_QA_{split}_*.csv"); seeds = cat(f"{PREFIX}_SEEDS_{split}_*.csv")
    zips = sorted(glob.glob(str(Path(shards) / "**" / f"{PREFIX}_INPUTS_{split}_*.zip"), recursive=True))
    for f in zips:
        (out / Path(f).name).write_bytes(Path(f).read_bytes())
    expected = requested_fields()
    rule_ok = expected == sorted(plan["fields"]) and set(expected) <= set(lk["splits"]["S_field"][split])
    got = sorted(int(x) for x in rows.field.unique()) if len(rows) else []
    rows.to_csv(out / f"{PREFIX}_RESULTS_{split}.csv", index=False, float_format="%.17g"); seeds.to_csv(out / "SEED_LEDGER.csv", index=False)
    qa.to_csv(out / f"{PREFIX}_QA_{split}.csv", index=False, float_format="%.17g")
    mm = qa[qa.check == "mahalanobis_per_dim"].groupby(["role", "cell"]).value.mean(); mtol = 4 * math.sqrt(2 / (2 * N)) / math.sqrt(max(len(got), 1))
    rp = qa[qa.check == "revisit_pose_identical_maxdiff"].value; rt = qa[qa.check == "revisit_time_differs_mindiff"].value
    b = rows[rows.arm.astype(str).str.endswith("_BATCH") & (rows.status == "OK")].copy()
    if len(b):
        b["KINK_P_UNCERTAIN"] = B3._bool(b.KINK_P_UNCERTAIN)
    g = b.groupby(["arm", "role", "cell"])
    nc = g.class_v31.apply(lambda c: (int((c == "NOT_CERTIFIED").sum()), len(c))) if len(b) else pd.Series(dtype=object)
    n_exp = len(expected) * len(M.SENSOR_SEEDS) * (2 * len(V.LH_CELLS) * len(V.LH_ARMS) + 2 * (len(S0V2.REV_CELLS) * 3 - 1))
    fail_nc = {"|".join(k): f"{v[0]}/{v[1]}" for k, v in nc.items() if v[0] > 0.01 * v[1]}
    scope = ((b.polish_E_vs_Ep_dref <= POLISH_MAX_DREF) & (b.polish_cost_decrease <= POLISH_MAX_DCOST)) if len(b) else pd.Series(dtype=bool)
    qaj = dict(fields_expected=expected, fields_got=got, request_field_rule_ok=bool(rule_ok), mahalanobis_tol=mtol,
               mahalanobis_mean={f"{k[0]}|{k[1]}": float(v) for k, v in mm.items()},
               revisit_pose_identical_max=float(rp.max()) if len(rp) else None, revisit_time_differs_min=float(rt.min()) if len(rt) else None,
               stops=int((rows.status == "STOP_UNPHYSICAL_OBSERVATION").sum()), failures=int(rows.status.astype(str).str.startswith("FAILED").sum()),
               n_rows=int(len(rows)), n_rows_expected=n_exp, n_input_receipt_files=len(zips),
               NOT_CERTIFIED_v31_cells_failing=fail_nc, NOT_CERTIFIED_v31_pooled_REPORTED=float((b.class_v31 == "NOT_CERTIFIED").mean()) if len(b) else None,
               G2_smooth_with_probe_descent=int(((b.newton_decrement <= FL.V2_DEC_TOL) & (b.probe_min_dcost < -TAU)).sum()) if len(b) else None,
               class_v31_counts=b.class_v31.value_counts().to_dict() if len(b) else {},
               class_v3_vs_v31={f"{k[0]}->{k[1]}": int(v) for k, v in b.groupby(["class_v3_A008_rule", "class_v31"]).size().items()} if len(b) else {},
               old_class_counts=b.conv.value_counts().to_dict() if len(b) else {},
               primary_P_pd_all=bool(B3._bool(b[f"pd_{AJ.PRIMARY}"]).all()) if len(b) else False,
               KINK_P_UNCERTAIN_frac=float(b.KINK_P_UNCERTAIN.mean()) if len(b) else None,
               rel_spread_q50_q90_q99_max=[float(x) for x in b.rel_spread.quantile([0.5, 0.9, 0.99, 1.0])] if len(b) else [],
               A82_polish_rows=int((b.polish_steps > 0).sum()) if len(b) else None, A82_polish_all_within_scope=bool(scope.all()) if len(b) else False,
               A82_polish_max_cost_decrease=float(b.polish_cost_decrease.max()) if len(b) else None,
               A82_polish_max_E_vs_Ep_dref=float(b.polish_E_vs_Ep_dref.max()) if len(b) else None,
               A82_polish_hit_cap_n=int(B3._bool(b.polish_hit_cap).sum()) if len(b) else None)
    qaj["pass"] = bool(got == expected and rule_ok and len(mm) and all(abs(v - 1) <= mtol for v in mm.values) and qaj["revisit_pose_identical_max"] == 0.0
                       and (qaj["revisit_time_differs_min"] or 0) > 0 and qaj["stops"] == 0 and qaj["failures"] == 0 and qaj["n_rows"] == n_exp
                       and not fail_nc and qaj["primary_P_pd_all"] and qaj["A82_polish_all_within_scope"])
    (out / f"{PREFIX}_QA.json").write_text(json.dumps(qaj, indent=1, default=float))
    s0d = Path(os.environ["S0V2_RESULTS_DIR"]); s0m = json.loads((s0d / "MANIFEST.json").read_text())
    s0_ok = s0m.get("execution_status") == "PASS" and s0m.get("contract_sha256") == MF.sha256_file(MF.CONTRACT)
    pred = pd.read_csv(s0d / "S0V2_PREDICTIONS.csv").set_index(["role", "cell"]); did_pred = pd.read_csv(s0d / "S0V2_DID.csv")
    rvpred = pd.read_csv(s0d / "S0V2_REVISIT.csv").set_index(["role", "cell", "arm"]); sep_pred = pd.read_csv(s0d / "S0V2_SEP.csv")
    ok = qaj["pass"] and s0_ok
    CAL, NEES = calibration(b) if len(b) else (pd.DataFrame(columns=["verdict", "evaluable"]), pd.DataFrame())
    CAL.to_csv(out / f"{PREFIX}_A85_CALIBRATION_{split}.csv", index=False, float_format="%.6g")
    NEES.to_csv(out / f"{PREFIX}_A85_NEES_C10_{split}.csv", index=False, float_format="%.6g")
    cal_fail = bool((CAL.verdict == "FAIL").any()); n_uneval = int((~CAL.evaluable.astype(bool)).sum()) if len(CAL) else 8
    sens = {}; prim = None
    if ok:
        for m in AJ.METHODS:
            dm = V.decide_v2(B3.with_P(rows, m), pred, did_pred, rvpred, sep_pred, eff); sens[m] = B3._summ(dm)
            if m == AJ.PRIMARY:
                prim = dm
        unc = rows.copy(); bb = unc.arm.astype(str).str.endswith("_BATCH") & (unc.status == "OK")
        unc = unc[~(bb & B3._bool(unc.KINK_P_UNCERTAIN.fillna(False)))]
        sens[f"{AJ.PRIMARY}_without_KINK_P_UNCERTAIN"] = B3._summ(V.decide_v2(B3.with_P(unc, AJ.PRIMARY), pred, did_pred, rvpred, sep_pred, eff))
        kin = rows.copy(); kin = kin[~(bb & (kin.kink_poses_at_E.fillna(0).astype(float) > 0))]
        sens[f"{AJ.PRIMARY}_without_kink_rows"] = B3._summ(V.decide_v2(B3.with_P(kin, AJ.PRIMARY), pred, did_pred, rvpred, sep_pred, eff))
        for k in ("H1", "H2", "H3", "CAL", "SENS", "H4", "H4_REPRO"):
            pd.DataFrame(prim[k]).to_csv(out / f"{PREFIX}_{k}_{split}_{AJ.PRIMARY}.csv", index=False, float_format="%.8g")
    conv_keys = [m for m in AJ.METHODS]
    multi_conv = len({json.dumps(sens[m], sort_keys=True) for m in conv_keys if m in sens}) > 1
    multi_excl = any(json.dumps(sens[k], sort_keys=True) != json.dumps(sens.get(AJ.PRIMARY), sort_keys=True)
                     for k in sens if k.startswith(f"{AJ.PRIMARY}_without"))
    res = dict(split=split, qa_pass=qaj["pass"], s0_reference=s0d.name, s0_reference_ok=s0_ok,
               A85_calibration_fail=cal_fail, A85_unevaluable_strata=n_uneval,
               A86_convention_outcome="MULTIPLE_RESULTS_NO_SINGLE_ADOPTION" if multi_conv else ("CONSISTENT_ACROSS_CONVENTIONS" if sens else "NOT_EVALUATED"),
               A86_exclusion_outcome="EXCLUSION_CHANGES_RESULT" if multi_excl else ("EXCLUSION_STABLE" if sens else "NOT_EVALUATED"),
               A86_sensitivity=sens, primary_convention=AJ.PRIMARY, primary_convention_note="numerical convention, validated only by A8-5",
               nees_note="nees4 = analytic convention; nees4_C10 uses the stored full C10 end covariance (F4)",
               scientific_verdict_track_S="NOT_EVALUATED (DEV2 pilot)", release="TECHNICAL_QA_ONLY (SELF_REVIEW_ONLY)",
               holdout2="NO-GO until independent re-audit", p3="NO-GO")
    if ok and prim is not None and not cal_fail and not multi_conv:
        pw = M.power(dict(H1=prim["H1"], CAL=prim["CAL"], H2=prim["H2"], H3=prim["H3"]), len(got), plan, eff)
        pd.DataFrame(pw.pop("rows")).to_csv(out / f"{PREFIX}_POWER_{split}.csv", index=False, float_format="%.6g")
        pw["holdout2_fields_if_opened_after_reaudit"] = lk["splits"]["S_field"]["HOLDOUT2"][:pw["n_confirm"]]; res["power"] = pw
    else:
        res["power"] = "NOT_COMPUTED (requires QA pass, no A8-5 CALIBRATION_FAIL, no convention multiplicity)"
    (out / f"{PREFIX}_DECISION_{split}.json").write_text(json.dumps(res, indent=1, default=M._json))
    status = "PASS" if ok else "FAIL"
    MF.write_manifest(out, phase="P2_S1", status=status, contract_sha=MF.sha256_file(MF.CONTRACT),
                      config_files=[Wd.EXP / "config/PLAN_PARAMETERS.json"] + [Wd.EXP / f"contracts/AMENDMENT-00{i}.md" for i in range(3, 10)],
                      input_lock=Path(os.environ.get("REFLECT_ROOT", ".")) / "out" / "INPUT_LOCK.sha256", outputs=sorted(out.glob(f"{PREFIX}_*")),
                      seed_ledger=out / "SEED_LEDGER.csv", verdict="NOT_EVALUATED", unit="field_realization",
                      limitations=["DEV2 pilot only (second DEV2 pass, after S1V3)", "post-fit P convention C10 is numerical; statistical validity only via A8-5",
                                   "synthetic additive noise on the FFD LOS model; not RF physics", "SELF_REVIEW_ONLY; TECHNICAL_QA_ONLY"],
                      extra=dict(sub_phase="P2_S1V4", amendment="AMENDMENT-009"))
    print(PREFIX, "aggregate", split, status, "| A8-5 fail", cal_fail, "| A8-6", res["A86_convention_outcome"], res["A86_exclusion_outcome"])
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


# helpers re-exported for c3v4 (identical objects from the frozen s1v3)
make_inputs = B3.make_inputs; arm_models = B3.arm_models; sig_fp = B3.sig_fp; pose_keys_sha = B3.pose_keys_sha; post_fit_P = B3.post_fit_P
