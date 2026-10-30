"""P2_BTAP (AMENDMENT-009 option B): tap-knowledge robustness of the S1V4 conclusions on DEV2 (sensitivity, not confirmatory).

  b_tap.py run --fields 10 --out D
  b_tap.py aggregate --shards D --out D          (env S0V2_RESULTS_DIR)

The generator is unchanged (z from the true-tap FFD model). Only the estimator's tap information changes:
  TAP_ORACLE  estimator uses the true first-path taps (= S1V3/S1V4 design)
  TAP_ERR_1   observed tap = true tap +- 1 detector index at 10 % of poses (5 % each sign), seeded per (field, window, sensor)
  TAP_ERR_4   as TAP_ERR_1 with +- 4 indices (= one raw tap at the 4x zero-padded grid)
  TAP_STATE   no tap observation: the detector tap is re-derived from the current state at every evaluation (world.h_H)
Batch arms IID_BATCH / ORACLE_CORR_BATCH via s1v4.eval_batch (E' + post-fit P + class v3.1). EKF tap alignment: IID_EKF_NOGATE
with the state-derived tap (the S1V2 EKF) and with the true tap (EKF_ORACLE_TAP), same R, x0 and controls.
Windows LOW/HIGH, cells LOWCORR / POSE_HIGH, sensors 0-2.
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
import filters as FL  # noqa: E402
import manifest as MF  # noqa: E402
import s0_math as S0  # noqa: E402
import s0v2 as S0V2  # noqa: E402
import s1_mc as M  # noqa: E402
import s1v2 as V  # noqa: E402
import s1v3 as B3  # noqa: E402
import s1v4 as S4  # noqa: E402
import world as Wd  # noqa: E402

CONDS = ("TAP_ORACLE", "TAP_ERR_1", "TAP_ERR_4", "TAP_STATE")
CELLS = ("LOWCORR", "POSE_HIGH"); ROLES = ("LOW", "HIGH"); ARMS = ("IID_BATCH", "ORACLE_CORR_BATCH")
ERR_RATE = 0.10; N = S4.N; P0M = S4.P0M


def observed_taps(root, f, w, sn, mag):
    r = M.rng(root, 9, f, w["j"], sn, mag)
    u = r.random(N); d = np.where(u < ERR_RATE / 2, -mag, np.where(u < ERR_RATE, mag, 0))
    return np.asarray(w["taps"], int) + d.astype(int)


def hb_for(cond, w, root, f, sn):
    if cond == "TAP_ORACLE":
        return S4.hb_true_tap(w), 0
    if cond == "TAP_STATE":
        return (lambda X: Wd.h_H(X, "A")), -1
    t = observed_taps(root, f, w, sn, 1 if cond == "TAP_ERR_1" else 4)
    return (lambda X, t=t: Wd.h_H_tap(X, "A", t)), int((t != np.asarray(w["taps"])).sum())


def ekf_pair(S, w, cn, z, inp):
    """IID_EKF_NOGATE with state-derived tap (as S1V2) and with the true tap (EKF_ORACLE_TAP)."""
    Sig = S["Sig"][(w["role"], cn)]; Rk = [Sig[2 * k:2 * k + 2, 2 * k:2 * k + 2] for k in range(N)]; mu = np.zeros((N, 2))
    mdl = Wd.model(); sp = Wd.spec("A"); ax = np.array(Wd.ANCHORS["A"][:2]); out = []
    for arm in ("EKF_STATE_TAP", "EKF_ORACLE_TAP"):
        cnt = [0]

        def h_fn(x, cnt=cnt, arm=arm):
            k = cnt[0]; cnt[0] += 1
            if arm == "EKF_STATE_TAP":
                h, H = mdl.batch(np.asarray(x)[None], sp)
                return np.asarray(h)[0], np.asarray(H)[0]
            h, H = Wd.h_H_tap(np.asarray(x)[None], "A", np.asarray(w["taps"])[k:k + 1])
            return h[0], H[0]
        X, PX, _, _ = FL.ekf(h_fn, z, mu, lambda k, sg: Rk[k], inp["ds_m"], inp["gy_m"], w["dts"], inp["x0"], P0M, anchor_xy=ax)
        r = dict(arm=arm, cond="EKF", status="OK", conv="NA_RECURSIVE"); r.update(V._row_from(w, X, PX[-1], "A")); out.append(r)
    return out


def cmd_run(fields, out):
    lk = S4.lock_v4(); M.check_code_lock(lk); plan = lk["run_plan"]["BTAP"]
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    bad = [f for f in fields if f not in plan["fields"]]
    if bad:
        raise SystemExit(f"ERR_SPLIT_LEAK fields {bad} not in BTAP plan")
    root = M.seed_root(); S = V.setup(lk); rows = []
    for f in fields:
        for cn in CELLS:
            cell = S["cells"][cn]
            pf = S["Lhalf"] @ M.rng(root, S0V2.CELL_ID_V2[cn], f, 1).standard_normal((S["Lhalf"].shape[1], 2)) if cell["alphas"][0] else None
            for role in ROLES:
                w = S["wins"][role]
                for sn in M.SENSOR_SEEDS:
                    inp = B3.make_inputs(S, root, f, cn, w, sn, pf); _, models = B3.arm_models(S, w, cn)
                    base = dict(split="DEV2", field=f, sensor_seed=sn, window=w["id"], role=role, cell=cn)
                    rows += [dict(base, **r) for r in ekf_pair(S, w, cn, inp["z"], inp)]
                    for cond in CONDS:
                        hb, n_err = hb_for(cond, w, root, f, sn)
                        for arm in ARMS:
                            try:
                                r = S4.eval_batch(w, arm, models[arm], inp, ("BTAP", cond, f, role, cn, sn, arm), hb=hb)[0]
                                keep = {k: r[k] for k in ("conv", "class_v31", "cost", "cost_E", "polish_steps", "polish_E_vs_Ep_dref", "rel_spread",
                                                          "KINK_P_UNCERTAIN", "nees4_C10", "nees4", "win_head_ms_deg2", "win_xy_ms_cm2")}
                                keep.update({f"e_{a}": r[f"e_{a}"] for a in S4.STATES})
                                keep.update({f"P_{a}": r[f"P_{AJ.PRIMARY}_{a}"] for a in S4.STATES})      # primary convention
                                rr = dict(arm=arm, cond=cond, status="OK", n_tap_errors=n_err, **keep)
                            except Exception as ex:  # noqa: BLE001
                                rr = dict(arm=arm, cond=cond, status=f"FAILED:{type(ex).__name__}:{ex}")
                            rows.append(dict(base, **rr))
        print("BTAP field", f, "rows", len(rows), flush=True)
    pd.DataFrame(rows).to_csv(out / f"BTAP_ROWS_{'_'.join(map(str, fields))}.csv", index=False, float_format="%.17g")
    return 0


def _ft(rows, arm, role, cell, a):
    return M.field_table(rows, arm, role, cell)[[f"mse_{a}", f"claim_{a}"]]


def summary(rows, pred, did_pred, eff):
    """Per condition: H1 (primary cells, tan/psi), H2 DID (tan, psi), H3 oracle/iid ratio, window RMSEs; verdicts via the
    frozen s1v2.decide_v2 (LOW/HIGH parts only)."""
    out = {}; tabs = []
    rvpred = pd.DataFrame(columns=["role", "cell", "arm"]).set_index(["role", "cell", "arm"])
    for cond in CONDS:
        r = rows[(rows.cond == cond) | (rows.cond == "EKF")]
        lf = math.log(eff["equivalence_factor"]); res = dict(H1=[], H2=[], H3=[], CAL=[])
        li = lambda m, a: math.log(m[0][f"mse_{a}"] / m[0][f"claim_{a}"])  # noqa: E731
        for role in ROLES:
            for cell in CELLS:
                for a in ("tan", "psi"):
                    ft = _ft(r, "IID_BATCH", role, cell, a); p = float(pred.loc[(role, cell), f"infl_iid_{a}"])
                    b = V._boot([ft], lambda m, a=a, p=p: li(m, a) - math.log(p))
                    res["H1"].append(dict(role=role, cell=cell, state=a, log_dev=b["est"], lo=b["lo"], hi=b["hi"], verdict=M.band_verdict(b["lo"], b["hi"], lf)))
                    fo = _ft(r, "ORACLE_CORR_BATCH", role, cell, a); bo = V._boot([fo], lambda m, a=a: li(m, a))
                    res["CAL"].append(dict(role=role, cell=cell, state=a, log_dev=bo["est"], lo=bo["lo"], hi=bo["hi"], verdict=M.band_verdict(bo["lo"], bo["hi"], lf)))
        keys = [(ro, c) for ro in ROLES for c in CELLS]
        for a in ("psi", "tan"):
            fts = [_ft(r, "IID_BATCH", ro, c, a) for ro, c in keys]

            def did(ms, a=a):
                v = {k: li([m], a) for k, m in zip(keys, ms)}
                return (v[("LOW", "POSE_HIGH")] - v[("LOW", "LOWCORR")]) - (v[("HIGH", "POSE_HIGH")] - v[("HIGH", "LOWCORR")])
            b = V._boot(fts, did); p = float(did_pred[(did_pred.state == a) & (did_pred.quantity == "infl_iid")].DID_log.iloc[0])
            res["H2"].append(dict(state=a, DID=b["est"], lo=b["lo"], hi=b["hi"], DID_S0=p, verdict=V._sided(b, p, eff)))
        for role in ROLES:
            for a in ("tan", "psi"):
                fo = M.field_table(r, "ORACLE_CORR_BATCH", role, "POSE_HIGH")[[f"mse_{a}"]]; fi = M.field_table(r, "IID_BATCH", role, "POSE_HIGH")[[f"mse_{a}"]]
                b = V._boot([fo, fi], lambda m, a=a: math.log(m[0][f"mse_{a}"] / m[1][f"mse_{a}"])); p = float(pred.loc[(role, "POSE_HIGH"), f"mse_ratio_oracle_iid_{a}"])
                app = p <= eff["oracle_gain_ratio_max"]
                res["H3"].append(dict(role=role, state=a, log_ratio=b["est"], lo=b["lo"], hi=b["hi"], applicable=app,
                                      verdict="NOT_APPLICABLE" if not app else ("PASS" if b["hi"] < 0 else ("FAIL" if b["lo"] > 0 else "UNDETERMINED"))))
        out[cond] = {k: [x["verdict"] for x in v] for k, v in res.items()}
        for k, v in res.items():
            tabs += [dict(cond=cond, test=k, **x) for x in v]
        bb = r[(r.cond == cond) & (r.status == "OK")]
        out[cond]["not_certified"] = int((bb.class_v31 == "NOT_CERTIFIED").sum()); out[cond]["failed"] = int((r[r.cond == cond].status != "OK").sum())
        out[cond]["head_rmse_deg"] = {a: float(math.sqrt(bb[bb.arm == a].win_head_ms_deg2.mean())) for a in ARMS}
        out[cond]["xy_rmse_cm"] = {a: float(math.sqrt(bb[bb.arm == a].win_xy_ms_cm2.mean())) for a in ARMS}
    return out, pd.DataFrame(tabs)


def cmd_aggregate(shards, out):
    lk = S4.lock_v4(); M.check_code_lock(lk); out = Path(out); out.mkdir(parents=True, exist_ok=True)
    eff = lk["resolved"]["EFFECT_SIZE_RULES"]; plan = lk["run_plan"]["BTAP"]
    fs = sorted(glob.glob(str(Path(shards) / "**" / "BTAP_ROWS_*.csv"), recursive=True))
    rows = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True) if fs else pd.DataFrame(columns=["field", "status", "cond", "arm"])
    rows.to_csv(out / "BTAP_RESULTS_DEV2.csv", index=False, float_format="%.17g")
    s0d = Path(os.environ["S0V2_RESULTS_DIR"])
    pred = pd.read_csv(s0d / "S0V2_PREDICTIONS.csv").set_index(["role", "cell"]); did_pred = pd.read_csv(s0d / "S0V2_DID.csv")
    got = sorted(int(x) for x in rows.field.unique()) if len(rows) else []
    n_exp = len(plan["fields"]) * len(M.SENSOR_SEEDS) * len(ROLES) * len(CELLS) * (len(CONDS) * len(ARMS) + 2)
    rows_ok = bool(got == sorted(plan["fields"]) and len(rows) == n_exp)
    summ, tab = summary(rows, pred, did_pred, eff) if rows_ok else ({}, pd.DataFrame())
    tab.to_csv(out / "BTAP_TESTS_DEV2.csv", index=False, float_format="%.8g")
    e = rows[rows.cond == "EKF"]
    ekf = {a: dict(head_rmse_deg=float(math.sqrt(e[e.arm == a].win_head_ms_deg2.mean())), xy_rmse_cm=float(math.sqrt(e[e.arm == a].win_xy_ms_cm2.mean())))
           for a in ("EKF_STATE_TAP", "EKF_ORACLE_TAP")} if len(e) else {}
    same = lambda c: all(summ[c][k] == summ["TAP_ORACLE"][k] for k in ("H1", "H2", "H3", "CAL"))  # noqa: E731
    res = dict(rows_ok=rows_ok, n_rows=int(len(rows)), n_rows_expected=n_exp,
               rule="pre-registered: ROBUST if every H1/H2/H3/CAL verdict under TAP_ERR_1 equals TAP_ORACLE, else TAP_SENSITIVE; "
                    "TAP_ERR_4 / TAP_STATE reported (expected to degrade)",
               TAP_ERR_1=("ROBUST" if same("TAP_ERR_1") else "TAP_SENSITIVE") if summ else "NOT_EVALUATED",
               TAP_ERR_4_same_as_oracle=same("TAP_ERR_4") if summ else None, TAP_STATE_same_as_oracle=same("TAP_STATE") if summ else None,
               per_condition=summ, ekf_tap_alignment=ekf,
               interpretation_note="IID_BATCH (TAP_ORACLE) vs EKF_ORACLE_TAP compares estimators with the same tap knowledge; "
                                   "EKF_STATE_TAP vs EKF_ORACLE_TAP isolates the value of knowing the tap.",
               scope="DEV2 sensitivity (fields already used by S1V3/S1V4); synthetic; not confirmatory")
    (out / "BTAP_SUMMARY_DEV2.json").write_text(json.dumps(res, indent=1, default=M._json))
    status = "PASS" if rows_ok else "FAIL"
    MF.write_manifest(out, phase="P2_S1", status=status, contract_sha=MF.sha256_file(MF.CONTRACT),
                      config_files=[Wd.EXP / "config/PLAN_PARAMETERS.json", Wd.EXP / "contracts/AMENDMENT-009.md"],
                      input_lock=Path(os.environ.get("REFLECT_ROOT", ".")) / "out" / "INPUT_LOCK.sha256", outputs=sorted(out.glob("BTAP_*")),
                      seed_ledger=None, verdict="NOT_EVALUATED", unit="field_realization",
                      limitations=["sensitivity study on DEV2, not confirmatory", "synthetic tap errors (no complex channel)", "SELF_REVIEW_ONLY"],
                      extra=dict(sub_phase="P2_BTAP", amendment="AMENDMENT-009"))
    print("BTAP", status, res["TAP_ERR_1"])
    return 0 if status == "PASS" else 1


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd"); ap.add_argument("--fields"); ap.add_argument("--out", required=True); ap.add_argument("--shards")
    a = ap.parse_args()
    if a.cmd == "run":
        return cmd_run([int(x) for x in a.fields.split(",") if x != ""], a.out)
    return cmd_aggregate(a.shards, a.out)


if __name__ == "__main__":
    raise SystemExit(main())
