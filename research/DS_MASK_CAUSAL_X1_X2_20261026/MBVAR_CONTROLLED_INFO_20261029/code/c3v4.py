"""P2_C3V4 (AMENDMENT-009): C3 applied to the committed S1V4 DEV2 run (generated from c3_verify.py by fixed substitutions:
S1V3->S1V4, class_v3->class_v31, lock_v3->lock_v4, C3->C3V4 names; c3_verify.py itself is frozen under AMENDMENT-008).

  c3v4.py run --field F --group LH|RV --out D      regenerate one field's inputs, compare with the S1V3 receipts,
                                                        re-run E + post-fit P + class v3 + the C2 start grid
  c3v4.py aggregate --shards D --out D            (env S1V4_RUN = committed S1V4 DEV2 run dir name)

Gates: INPUT_REPRO, STATE_COST_REPRO, P_REPRO, STATUS_REPRO, NO_WRONG_BASIN, STATE_STABILITY_FIXED, ITER_CAP, LINEAR_EXACT,
KINK_FIXTURES. Reported: analytic-P reproducibility, old-class changes, P-normalised stability, XMODEL-only truth-start (F7).
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
import info_core as IC  # noqa: E402
import manifest as MF  # noqa: E402
import s0v2 as S0V2  # noqa: E402
import s1_mc as M  # noqa: E402
import s1v2 as V  # noqa: E402
import s1v4 as T  # noqa: E402
import world as Wd  # noqa: E402

GROUPS = {"LH": ("LOW", "HIGH"), "RV": ("REV60", "FWD60")}
D_REF = T.D_REF                                                         # fixed external scale (2 cm, 2 cm, 0.25 deg, 0.01 deg/s)
TOL = dict(z=1e-9, ctl=1e-12, fp_rel=1e-12, state_dref=1e-6, cost=1e-6, P_rel=1e-3, basin=1.0, stab1=1.0, stab2=2.0, stab_frac=0.99,
           itercap_dref=0.1, linear_rel=1e-3, probe_power_frac=0.99)
N = V.N; P0M = M.P0
SPLIT = "DEV2"


dref_diff = T.dref_diff


def s1v4_dir():
    return Wd.EXP / "results" / os.environ["S1V4_RUN"]


def load_receipts(d):
    rec = {}
    for f in sorted(d.glob(f"S1V4_INPUTS_{SPLIT}_*.zip")):
        with np.load(f, allow_pickle=False) as z:
            rec.update({k: z[k] for k in z.files})
    return rec


def input_diffs(rec, kb, inp, w, Sig, models):
    """A8-1: per-component comparison of regenerated inputs with the S1V3 receipt."""
    if f"{kb}|z" not in rec:
        return dict(receipt_found=False)
    rel = lambda a, b: float(np.max(np.abs(a - b) / np.maximum(np.abs(b), 1e-300)))  # noqa: E731
    out = dict(receipt_found=True,
               d_z=float(np.max(np.abs(inp["z"] - rec[f"{kb}|z"]))), d_ds=float(np.max(np.abs(inp["ds_m"] - rec[f"{kb}|ds_m"]))),
               d_gy=float(np.max(np.abs(inp["gy_m"] - rec[f"{kb}|gy_m"]))), d_x0=float(np.max(np.abs(inp["x0"] - rec[f"{kb}|x0"]))),
               taps_equal=bool(np.array_equal(np.asarray(w["taps"]), rec[f"{kb}|taps"])),
               pose_keys_equal=bool(str(rec[f"{kb}|pose_keys_sha"]) == T.pose_keys_sha(w)),
               d_sig_true_rel=rel(T.sig_fp(Sig), rec[f"{kb}|Sig_true_fp"]))
    out["d_sig_model_rel"] = max((rel(T.sig_fp(Sm), rec[f"{kb}|{arm}|Sig_model_fp"]) if f"{kb}|{arm}|Sig_model_fp" in rec else float("inf"))
                                 for arm, Sm in models.items())
    return out


def cmd_run(field, group, out):
    lk = T.lock_v4(); M.check_code_lock(lk)
    if field not in lk["run_plan"]["C3V4"]["fields"]:
        raise SystemExit("ERR_SPLIT_LEAK C3V4 runs on the S1V4 DEV2 fields only")
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    S = V.setup(lk); root = M.seed_root(); rows = []; rec = load_receipts(s1v4_dir())
    sd0 = np.sqrt(np.diag(P0M))
    for cn, cell in S["cells"].items():
        wins = [S["wins"][r] for r in GROUPS[group] if cn in S["wins"][r]["cells"]]
        if not wins:
            continue
        pf = S["Lhalf"] @ M.rng(root, S0V2.CELL_ID_V2[cn], field, 1).standard_normal((S["Lhalf"].shape[1], 2)) if cell["alphas"][0] else None
        for w in wins:
            for sn in M.SENSOR_SEEDS:
                inp = T.make_inputs(S, root, field, cn, w, sn, pf); Sig, models = T.arm_models(S, w, cn)
                kb = f"{field}|{w['role']}|{cn}|{sn}"; idf = input_diffs(rec, kb, inp, w, Sig, models)
                ht = lambda X, t=w["taps"]: Wd.h_H_tap(X, "A", t)  # noqa: E731
                z, x0, dsm, gym = inp["z"], inp["x0"], inp["ds_m"], inp["gy_m"]; mu = np.zeros((N, 2))
                Tr = IC.rotation_rt(w["Xtrue"][-1], Wd.ANCHORS["A"])
                for arm, Sm in models.items():
                    skey = (field, w["role"], cn, sn, arm)
                    r, XE, IE, thp = T.eval_batch(w, arm, Sm, inp, skey)          # XE = X' (polished E); r["cost"] = cost(E')
                    starts = {f"psi{k:+d}": (np.r_[x0[:2], FL.wrap(x0[2] + k * sd0[2]), x0[3]], np.zeros((N, 2))) for k in FL.MS_K}
                    starts["x+1"] = (x0 + np.r_[sd0[0], 0, 0, 0], np.zeros((N, 2))); starts["y+1"] = (x0 + np.r_[0, sd0[1], 0, 0], np.zeros((N, 2)))
                    starts["truth"] = (w["Xtrue"][0].copy(), -inp["vn"])
                    sol = {"E": (r["cost"], XE)}
                    for nm, th in starts.items():
                        Xs, _, Is = FL.batch_map_v2(ht, z, mu, Sm, dsm, gym, w["dts"], x0, P0M, theta0=th)
                        sol[nm] = (Is["cost"], Xs)
                    cstar = min(v[0] for v in sol.values()); best = min(sol, key=lambda k: sol[k][0])
                    pc10 = np.array([r[f"P_{AJ.PRIMARY}_{a}"] for a in T.STATES])
                    de = XE[-1] - sol[best][1][-1]; de[2] = FL.wrap(de[2])
                    rec_ = dict(field=field, role=w["role"], cell=cn, sensor_seed=sn, arm=arm, **idf,
                                **{k: r[k] for k in ("conv", "class_v31", "cost", "cost_E", "ms_best_k", "rescued", "ms_triggered", "kink_poses_at_E",
                                                     "probe_min_dcost", "dec_A_fixed", "rel_spread", "KINK_P_UNCERTAIN", "polish_steps",
                                                     "polish_cost_decrease", "polish_E_vs_Ep_dref", "nees4_C10")},
                                **{f"xend_{i}": r[f"xend_{i}"] for i in range(4)}, **{f"xendE_{i}": r[f"xendE_{i}"] for i in range(4)},
                                **{f"P_{m}_{a}": r[f"P_{m}_{a}"] for m in ("A", AJ.PRIMARY) for a in T.STATES},
                                C_star=cstar, best_start=best, gap_E=r["cost"] - cstar, E_vs_best_dref=dref_diff(XE[-1], sol[best][1][-1]),
                                E_vs_best_sdC10=float(np.max(np.abs(Tr @ de) / np.sqrt(pc10))),
                                truth_gap=sol["truth"][0] - cstar, n_starts_gross_worse=int(sum(v[0] > cstar + 1.0 for v in sol.values())),
                                **T.probe_power(ht, z, Sm, dsm, gym, w["dts"], x0, thp, T.key_seed("PP", field, w["role"], cn, sn, arm) % (2 ** 62)))
                    if IE["status"] != "CONVERGED":
                        _, I3, _, X3p, c3p, _ = T.estimate(w, Sm, inp, skey, max_iter=300)
                        rec_.update(E300_status=I3["status"], E300_vs_E_dref=dref_diff(X3p[-1], XE[-1]), E300_cost_minus_E=c3p - r["cost"])
                    else:
                        rec_.update(E300_status="NOT_RUN_CONVERGED", E300_vs_E_dref=0.0, E300_cost_minus_E=0.0)
                    rows.append(rec_)
        print("C3V4", field, group, cn, len(rows), flush=True)
    pd.DataFrame(rows).to_csv(out / f"C3V4_ROWS_{field}_{group}.csv", index=False, float_format="%.17g")
    return 0


def linear_exact():
    """LINEAR_EXACT: on an affine h with the real window controls, every P convention equals the analytic-H P (rel <= 1e-3)."""
    lk = T.lock_v4(); S = V.setup(lk); w = S["wins"]["LOW"]; hb = AJ.linear_h()
    rg = np.random.default_rng(7); z = hb(w["Xtrue"])[0] + 0.05 * rg.standard_normal((N, 2)); Sm = np.eye(2 * N) * 0.05 ** 2
    x0 = w["Xtrue"][0].copy(); theta = (x0.copy(), np.zeros((N, 2)))
    Tr = IC.rotation_rt(w["Xtrue"][-1], Wd.ANCHORS["A"])
    pf = T.post_fit_P(hb, z, Sm, w["ds"], w["dth"], w["dts"], x0, theta, Tr)
    ref = np.array([pf[f"P_A_{a}"] for a in T.STATES])
    worst = max(float(np.max(np.abs(np.array([pf[f"P_{m}_{a}"] for a in T.STATES]) - ref) / ref)) for m in AJ.METHODS)
    return dict(pass_=bool(worst <= TOL["linear_rel"] and all(pf[f"pd_{m}"] for m in AJ.METHODS)), max_rel=worst)


def kink_fixtures():
    hv, Xk, Xs = AJ.fixture_piecewise()
    L = AJ.fd_H(hv, Xk, *AJ.METHODS["L"]); R = AJ.fd_H(hv, Xk, *AJ.METHODS["R"]); Cc = AJ.fd_H(hv, Xk, *AJ.METHODS[AJ.PRIMARY])
    an = np.zeros((len(Xs), 2, 4)); an[:, 0, 0] = 5.0; an[:, 0, 1] = 0.1; an[:, 1, 1] = Xs[:, 1]; an[:, 1, 2] = 0.3
    smooth = max(float(np.max(np.abs(AJ.fd_H(hv, Xs, *AJ.METHODS[m]) - an))) for m in AJ.METHODS if AJ.METHODS[m] is not None)
    ok = bool(np.allclose(L[:, 0, 0], 2.0, atol=1e-6) and np.allclose(R[:, 0, 0], 5.0, atol=1e-6) and np.allclose(Cc[:, 0, 0], 3.5, atol=1e-9) and smooth <= 1e-6)
    return dict(pass_=ok, left=float(L[0, 0, 0]), right=float(R[0, 0, 0]), central=float(Cc[0, 0, 0]), smooth_control_max_abs=smooth)


def cmd_aggregate(shards, out):
    lk = T.lock_v4(); M.check_code_lock(lk); out = Path(out); out.mkdir(parents=True, exist_ok=True)
    fs = sorted(glob.glob(str(Path(shards) / "**" / "C3V4_ROWS_*.csv"), recursive=True))
    C = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True) if fs else pd.DataFrame()
    src = s1v4_dir(); D = pd.read_csv(src / f"S1V4_RESULTS_{SPLIT}.csv")
    D = D[D.arm.astype(str).str.endswith("_BATCH") & (D.status == "OK")].set_index(["field", "role", "cell", "sensor_seed", "arm"])
    fields = lk["run_plan"]["C3V4"]["fields"]
    n_exp = len(fields) * len(M.SENSOR_SEEDS) * (2 * len(V.LH_CELLS) * 2 + 2 * (len(S0V2.REV_CELLS) * 2 + len(S0V2.XMODEL)))
    cmp = []
    for _, r in C.iterrows():
        k = (r.field, r.role, r.cell, r.sensor_seed, r.arm)
        if k not in D.index:
            cmp.append(dict(found=False)); continue
        s = D.loc[k]
        cmp.append(dict(found=True, d_state_dref=dref_diff([r[f"xend_{i}"] for i in range(4)], [s[f"xend_{i}"] for i in range(4)]),
                        d_cost=abs(r.cost - s.cost), same_best_k=int(r.ms_best_k) == int(s.ms_best_k),
                        d_stateE_dref=dref_diff([r[f"xendE_{i}"] for i in range(4)], [s[f"xendE_{i}"] for i in range(4)]), d_costE=abs(r.cost_E - s.cost_E),
                        d_P_C10_rel=max(abs(r[f"P_{AJ.PRIMARY}_{a}"] - s[f"P_{AJ.PRIMARY}_{a}"]) / s[f"P_{AJ.PRIMARY}_{a}"] for a in T.STATES),
                        d_P_A_rel=max(abs(r[f"P_A_{a}"] - s[f"P_A_{a}"]) / s[f"P_A_{a}"] for a in T.STATES),
                        same_class_v31=r.class_v31 == s.class_v31, same_old_class=r.conv == s.conv))
    C = pd.concat([C, pd.DataFrame(cmp, index=C.index)], axis=1) if len(C) else C
    C.to_csv(out / "C3V4_ROWS.csv", index=False, float_format="%.17g")
    allrows = bool(len(C) == n_exp and C.found.all()) if len(C) else False
    rf = C.receipt_found.astype(bool) if len(C) else pd.Series(dtype=bool)
    per_arm = C.groupby("arm").apply(lambda d: dict(n=len(d), frac_le_1dref=float((d.E_vs_best_dref <= TOL["stab1"]).mean()),
                                                    max_dref=float(d.E_vs_best_dref.max()), max_sdC10_REPORTED=float(d.E_vs_best_sdC10.max())),
                                     include_groups=False).to_dict() if len(C) else {}
    xm = C[C.arm == "XMODEL_BATCH"] if len(C) else C
    nc = C[C.conv != "CONVERGED"] if len(C) else C
    crit = dict(
        INPUT_REPRO=dict(pass_=bool(allrows and rf.all() and (C.d_z <= TOL["z"]).all() and (C[["d_ds", "d_gy", "d_x0"]].max(axis=1) <= TOL["ctl"]).all()
                                    and C.taps_equal.astype(bool).all() and C.pose_keys_equal.astype(bool).all()
                                    and (C[["d_sig_true_rel", "d_sig_model_rel"]].max(axis=1) <= TOL["fp_rel"]).all()),
                         max_z=float(C.d_z.max()), max_ctl=float(C[["d_ds", "d_gy", "d_x0"]].max().max()),
                         max_sig_fp_rel=float(C[["d_sig_true_rel", "d_sig_model_rel"]].max().max())),
        STATE_COST_REPRO=dict(pass_=bool(allrows and (C.d_state_dref <= TOL["state_dref"]).all() and (C.d_cost <= TOL["cost"]).all() and C.same_best_k.all()),
                              max_state_dref=float(C.d_state_dref.max()), max_cost=float(C.d_cost.max()), n_best_k_diff=int((~C.same_best_k.astype(bool)).sum()),
                              raw_E_max_state_dref_REPORTED=float(C.d_stateE_dref.max()), raw_E_max_cost_REPORTED=float(C.d_costE.max())),
        P_REPRO=dict(pass_=bool(allrows and (C.d_P_C10_rel <= TOL["P_rel"]).all()), max_C10_rel=float(C.d_P_C10_rel.max()),
                     analytic_A_max_rel_REPORTED=float(C.d_P_A_rel.max()), analytic_A_n_gt_tol_REPORTED=int((C.d_P_A_rel > TOL["P_rel"]).sum())),
        STATUS_REPRO=dict(pass_=bool(allrows and C.same_class_v31.all()), n_class_v31_diff=int((~C.same_class_v31.astype(bool)).sum()),
                          old_class_changes_REPORTED=int((~C.same_old_class.astype(bool)).sum())),
        NO_WRONG_BASIN=dict(pass_=bool(allrows and (C.gap_E <= TOL["basin"]).all()), max_gap=float(C.gap_E.max()), n_gt_1=int((C.gap_E > TOL["basin"]).sum()),
                            note="C* = best of E and 10 fixed starts (bounded search, not a global-optimum proof)"),
        STATE_STABILITY_FIXED=dict(pass_=bool(allrows and all(v["frac_le_1dref"] >= TOL["stab_frac"] for v in per_arm.values()) and (C.E_vs_best_dref <= TOL["stab2"]).all()),
                                   per_arm=per_arm, d_ref=D_REF.tolist()),
        ITER_CAP=dict(pass_=bool(allrows and (nc.E300_vs_E_dref <= TOL["itercap_dref"]).all()), max_dref=float(C.E300_vs_E_dref.max()),
                      n_not_converged=int(len(nc))),
        PROBE_POWER=dict(pass_=bool(allrows and (C.pp_class == "NOT_CERTIFIED").mean() >= TOL["probe_power_frac"]),
                         frac_not_certified=float((C.pp_class == "NOT_CERTIFIED").mean()), rise_min_max=[float(C.pp_rise.min()), float(C.pp_rise.max())],
                         note="negative control: displaced point (cost +~1 chi^2) must be NOT_CERTIFIED"),
        LINEAR_EXACT=linear_exact(),
        KINK_FIXTURES=kink_fixtures(),
        F7_XMODEL_truth_start_REPORTED=dict(rows=int(len(xm)), truth_start_worse_than_E_frac=float((xm.truth_gap > xm.gap_E + 1e-6).mean()) if len(xm) else None,
                                            all_arms_frac=float((C.truth_gap > C.gap_E + 1e-6).mean()) if len(C) else None),
        KINK_HYPOTHESIS_REPORTED=dict(frac_kink_KINK_P_UNCERTAIN=float((C[C.KINK_P_UNCERTAIN.astype(str).str.lower() == "true"].kink_poses_at_E > 0).mean())
                                      if (C.KINK_P_UNCERTAIN.astype(str).str.lower() == "true").any() else None,
                                      class_v31_counts=C.class_v31.value_counts().to_dict(), old_class_counts=C.conv.value_counts().to_dict()),
        rows=dict(pass_=allrows, n=int(len(C)), n_expected=n_exp))
    gating = [k for k in crit if "REPORTED" not in k]
    status = "PASS" if all(crit[k]["pass_"] for k in gating) else "FAIL"
    res = dict(status=status, gating=gating, criteria=crit, s1v4_run=src.name, tolerances=TOL,
               preserved=["C2 run 40871327417 FAIL", "C1 original-rule FAIL", "S1V2 DEV runs 40864089916 / 40867939262 FAIL"],
               holdout2_allowed=False, holdout2_note="requires independent re-audit of S1V3+C3 and S1V4+C3V4 (AMENDMENT-009)", p3="NO-GO")
    (out / "C3V4_STATUS.json").write_text(json.dumps(res, indent=1, default=float))
    MF.write_manifest(out, phase="P2_S1", status=status, contract_sha=MF.sha256_file(MF.CONTRACT),
                      config_files=[Wd.EXP / "config/PLAN_PARAMETERS.json"] + [Wd.EXP / f"contracts/AMENDMENT-00{i}.md" for i in range(3, 10)],
                      input_lock=Path(os.environ.get("REFLECT_ROOT", ".")) / "out" / "INPUT_LOCK.sha256", outputs=sorted(out.glob("C3V4_*")),
                      seed_ledger=None, verdict="NOT_EVALUATED", unit="mathematical_deterministic",
                      limitations=["technical reproducibility/convergence verification on DEV2 only", "SELF_REVIEW_ONLY"],
                      extra=dict(sub_phase="P2_C3V4", amendment="AMENDMENT-009"))
    print("C3V4", status, {k: crit[k]["pass_"] for k in gating})
    return 0 if status == "PASS" else 1


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd"); ap.add_argument("--out", required=True)
    ap.add_argument("--field", type=int); ap.add_argument("--group"); ap.add_argument("--shards")
    a = ap.parse_args()
    if a.cmd == "run":
        return cmd_run(a.field, a.group, a.out)
    return cmd_aggregate(a.shards, a.out)


if __name__ == "__main__":
    raise SystemExit(main())
