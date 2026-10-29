"""P2_C2 (AMENDMENT-007 §R2): convergence verification on the v2 geometry, revisit windows and XMODEL arms.

  c2_conv.py run --field F --group LH|RV --out D       regenerate the S1V2 DEV inputs of one field; every batch arm
  c2_conv.py aggregate --shards D --out D             (env S1V2_DEV_RUN = committed S1V2 DEV run dir name)

For every (field, window, cell, sensor, batch arm) the deployable estimator E (= S1V2 batch_map_v2_ms) is compared with an
always-run start grid (heading k*sd_psi, k=-3..3; +1 sd in x; +1 sd in y) and the true-theta start. C* = best cost found.
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
import manifest as MF  # noqa: E402
import s0_math as S0  # noqa: E402
import s0v2 as S0V2  # noqa: E402
import s1_mc as M  # noqa: E402
import s1v2 as V  # noqa: E402
import world as Wd  # noqa: E402

GROUPS = {"LH": ("LOW", "HIGH"), "RV": ("REV60", "FWD60")}
P0M = M.P0


def kink_count(X, taps):
    h, H = Wd.h_H_tap(X, "A", taps); Hf = np.zeros_like(H)
    for j in range(4):
        d = np.zeros(4); d[j] = 1e-6
        Hf[:, :, j] = (Wd.h_H_tap(X + d, "A", taps)[0] - Wd.h_H_tap(X - d, "A", taps)[0]) / 2e-6
    dev = np.abs(Hf - H).max(axis=(1, 2)) / np.abs(H).max()
    return int((dev > 1e-4).sum())


def end_diff_sd(Xa, Xb, Pend):
    d = Xa[-1] - Xb[-1]; d[2] = FL.wrap(d[2])
    return float(np.max(np.abs(d) / np.sqrt(np.diag(Pend))))


def cmd_run(field, group, out):
    lk = S0V2.lock_v2(); M.check_code_lock(lk)
    if field not in lk["splits"]["S_field"]["DEV"]:
        raise SystemExit("ERR_SPLIT_LEAK C2 runs on DEV only")
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    S = V.setup(lk); root = M.seed_root(); rows = []
    for cn, cell in S["cells"].items():
        wins = [S["wins"][r] for r in GROUPS[group] if cn in S["wins"][r]["cells"]]
        if not wins:
            continue
        pf = S["Lhalf"] @ M.rng(root, S0V2.CELL_ID_V2[cn], field, 1).standard_normal((S["Lhalf"].shape[1], 2)) if cell["alphas"][0] else None
        for w in wins:
            for sn in M.SENSOR_SEEDS:
                eps, _, _ = V.draw(S, root, field, cn, w, sn, pf); z = w["htrue"] + eps
                sr = M.rng(root, 0, field, 4, w["j"], sn)
                x0 = w["Xtrue"][0] + np.linalg.cholesky(P0M) @ sr.standard_normal(4); x0[2] = float(FL.wrap(x0[2]))
                vn = sr.standard_normal((V.N, 2)) * np.sqrt(w["q"]); dsm = w["ds"] + vn[:, 0]; gym = w["dth"] + vn[:, 1]
                Sig = S["Sig"][(w["role"], cn)]; ht = lambda X, t=w["taps"]: Wd.h_H_tap(X, "A", t)  # noqa: E731
                mu = np.zeros((V.N, 2)); sd0 = np.sqrt(np.diag(P0M))
                arms = {"IID_BATCH": S0.blockdiag(Sig), "ORACLE_CORR_BATCH": Sig}
                if w["role"] in ("REV60", "FWD60") and cn in S0V2.XMODEL:
                    arms["XMODEL_BATCH"] = S["Sig"][(w["role"], S0V2.XMODEL[cn])]
                for arm, Sm in arms.items():
                    XE, PE, IE = FL.batch_map_v2_ms(ht, z, mu, Sm, dsm, gym, w["dts"], x0, P0M)
                    PendE = PE[-1]
                    starts = {f"psi{k:+d}": (np.r_[x0[:2], FL.wrap(x0[2] + k * sd0[2]), x0[3]], np.zeros((V.N, 2))) for k in FL.MS_K}
                    starts["x+1"] = (x0 + np.r_[sd0[0], 0, 0, 0], np.zeros((V.N, 2))); starts["y+1"] = (x0 + np.r_[0, sd0[1], 0, 0], np.zeros((V.N, 2)))
                    starts["truth"] = (w["Xtrue"][0].copy(), -vn)
                    sol = {"E": (IE["cost"], XE, IE["status"])}
                    for nm, th in starts.items():
                        Xs, Ps, Is = FL.batch_map_v2(ht, z, mu, Sm, dsm, gym, w["dts"], x0, P0M, theta0=th)
                        sol[nm] = (Is["cost"], Xs, Is["status"])
                    cstar = min(v[0] for v in sol.values()); best = min(sol, key=lambda k: sol[k][0])
                    near = [k for k, v in sol.items() if v[0] <= cstar + 1e-3]
                    spread = max((end_diff_sd(sol[a][1], sol[b][1], PendE) for a in near for b in near), default=0.0)
                    rec = dict(field=field, role=w["role"], cell=cn, sensor_seed=sn, arm=arm, E_status=IE["status"], E_rescued=IE["rescued"],
                               E_ms_triggered=IE["ms_triggered"], E_cost=IE["cost"], C_star=cstar, best_start=best, gap_E=IE["cost"] - cstar,
                               E_vs_best_sd=end_diff_sd(XE, sol[best][1], PendE), near_opt_n=len(near), near_opt_spread_sd=spread,
                               truth_gap=sol["truth"][0] - cstar, n_starts_gross_worse=int(sum(v[0] > cstar + 1.0 for v in sol.values())),
                               kink_poses_at_E=kink_count(XE, w["taps"]), E_shift_sd=IE["gn_shift_end_sd"], E_dec=IE["newton_decrement"],
                               **{f"e_{a}": v for a, v in zip(S0.STATES, (IC_rot(w, XE)))}, **{f"P_{a}": v for a, v in zip(S0.STATES, IC_Prot(w, PendE))})
                    if IE["status"] != "CONVERGED":
                        X3, P3, I3 = FL.batch_map_v2_ms(ht, z, mu, Sm, dsm, gym, w["dts"], x0, P0M, max_iter=300)
                        rec.update(E300_status=I3["status"], E300_vs_E_sd=end_diff_sd(X3, XE, PendE), E300_cost_minus_E=I3["cost"] - IE["cost"])
                    else:
                        rec.update(E300_status="IDENTICAL_BY_DETERMINISM", E300_vs_E_sd=0.0, E300_cost_minus_E=0.0)
                    rows.append(rec)
            print("C2", field, group, cn, len(rows), flush=True)
    pd.DataFrame(rows).to_csv(out / f"C2_ROWS_{field}_{group}.csv", index=False, float_format="%.12g")
    return 0


def IC_rot(w, X):
    import info_core as IC
    e4 = w["Xtrue"][-1] - X[-1]; e4[2] = float(FL.wrap(e4[2]))
    return IC.rotation_rt(w["Xtrue"][-1], Wd.ANCHORS["A"]) @ e4


def IC_Prot(w, P):
    import info_core as IC
    T = IC.rotation_rt(w["Xtrue"][-1], Wd.ANCHORS["A"])
    return np.diag(T @ P @ T.T)


def cmd_aggregate(shards, out):
    lk = S0V2.lock_v2(); M.check_code_lock(lk); out = Path(out); out.mkdir(parents=True, exist_ok=True)
    fs = sorted(glob.glob(str(Path(shards) / "**" / "C2_ROWS_*.csv"), recursive=True))
    C = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True) if fs else pd.DataFrame()
    C.to_csv(out / "C2_ROWS.csv", index=False, float_format="%.12g")
    dev = Wd.EXP / "results" / os.environ["S1V2_DEV_RUN"]
    D = pd.read_csv(dev / "S1V2_RESULTS_DEV.csv"); D = D[D.arm.str.endswith("_BATCH")].set_index(["field", "role", "cell", "sensor_seed", "arm"])
    ok_rows = []
    for _, r in C.iterrows():
        s = D.loc[(r.field, r.role, r.cell, r.sensor_seed, r.arm)]
        ok_rows.append(max(max(abs(r[f"e_{a}"] - s[f"e_{a}"]) / math.sqrt(s[f"P_{a}"]) for a in S0.STATES),
                           max(abs(r[f"P_{a}"] - s[f"P_{a}"]) / s[f"P_{a}"] for a in S0.STATES)))
    C["s1v2_repro_dev"] = ok_rows
    n_exp = len(lk["splits"]["S_field"]["DEV"]) * 3 * (2 * len(V.LH_CELLS) * 2 + 2 * (len(S0V2.REV_CELLS) * 2 + 2))
    g = C.groupby(["arm", "role", "cell"])
    nc = g.E_status.apply(lambda s: int((s == "NONCONVERGED").sum())); nn = g.size()
    per_arm = C.groupby("arm").apply(lambda d: dict(n=len(d), frac_state_le_05=float((d.E_vs_best_sd <= 0.5).mean()), max_state=float(d.E_vs_best_sd.max()),
                                                    frac_strict_cost=float((d.gap_E <= 1e-3).mean()), max_gap=float(d.gap_E.max())), include_groups=False).to_dict()
    flag = (C.E_status != "CONVERGED") | (C.gap_E > 1e-3)
    crit = dict(
        C2a_inputs_identical_to_S1V2_DEV=dict(pass_=bool(len(C) == n_exp and C.s1v2_repro_dev.max() <= 1e-3), n=len(C), n_expected=n_exp, max=float(C.s1v2_repro_dev.max())),
        C2b_no_wrong_basin=dict(pass_=bool((C.gap_E <= 1.0).all()), max_gap=float(C.gap_E.max()), n_gt_1=int((C.gap_E > 1.0).sum())),
        C2c_state_stability=dict(pass_=bool(all(v["frac_state_le_05"] >= 0.99 for v in per_arm.values()) and (C.E_vs_best_sd <= 1.0).all()), per_arm=per_arm),
        C2c_strict_cost_REPORTED=dict(pass_=bool(all(v["frac_strict_cost"] >= 0.99 for v in per_arm.values())), gating=False),
        C2d_nonconverged_per_cell_original=dict(pass_=bool(all(nc[k] <= 0.01 * nn[k] for k in nc.index)),
                                                cells_failing={"|".join(k): f"{nc[k]}/{nn[k]}" for k in nc.index if nc[k] > 0.01 * nn[k]},
                                                pooled=float((C.E_status == "NONCONVERGED").mean())),
        C2e_iter_cap=dict(pass_=bool((C[C.E_status != "CONVERGED"].E300_vs_E_sd <= 0.1).all()), max_sd=float(C.E300_vs_E_sd.max()),
                          frac_not_converged=float((C.E_status != "CONVERGED").mean())),
        C2f_kink_hypothesis_REPORTED=dict(frac_kink_flagged=float((C[flag].kink_poses_at_E > 0).mean()) if flag.any() else None,
                                          frac_kink_converged=float((C[~flag].kink_poses_at_E > 0).mean()) if (~flag).any() else None,
                                          n_flagged=int(flag.sum()), near_opt_spread_sd_max=float(C.near_opt_spread_sd.max())),
        C2g_xmodel_REPORTED=dict(rows=int((C.arm == "XMODEL_BATCH").sum()), max_gap=float(C[C.arm == "XMODEL_BATCH"].gap_E.max()) if (C.arm == "XMODEL_BATCH").any() else None,
                                 trigger_frac=float(C[C.arm == "XMODEL_BATCH"].E_ms_triggered.mean()) if (C.arm == "XMODEL_BATCH").any() else None,
                                 truth_start_worse_than_E_frac=float((C.truth_gap > C.gap_E + 1e-6).mean())))
    gating = [k for k, v in crit.items() if "REPORTED" not in k]
    status = "PASS" if all(crit[k]["pass_"] for k in gating) else "FAIL"
    # R1/R3: original-contract judgement of the earlier C1 run (no retroactive PASS)
    c1 = pd.read_csv(Wd.EXP / "results" / "P0_GEO2_run_40857100181" / "P0G_C1.csv"); g1 = c1.groupby(["arm", "role", "cell"])
    c1nc = g1.v2t_status.apply(lambda s: int((s == "NONCONVERGED").sum())); c1n = g1.size()
    c1j = dict(run="40857100181", C1f_per_cell_original=dict(pass_=bool(all(c1nc[k] <= 0.01 * c1n[k] for k in c1nc.index)),
                                                              cells_failing={"|".join(k): f"{c1nc[k]}/{c1n[k]}" for k in c1nc.index if c1nc[k] > 0.01 * c1n[k]}),
               C1d_strict_A004=dict(pass_=bool((c1.ms_cost_diff >= -1e-3).mean() >= 0.99), frac=float((c1.ms_cost_diff >= -1e-3).mean())),
               C1d_A005_auxiliary_wrong_basin=dict(pass_=bool((c1.ms_cost_diff >= -1.0).all())),
               judgement="C1 under the ORIGINAL contract = FAIL (C1-d strict and C1-f per-cell). A005 auxiliary PASS is an engineering check only; no retroactive PASS.")
    # S1V2 DEV QA under the ORIGINAL per-cell rule (R1/R7)
    q = json.loads((dev / "S1V2_QA.json").read_text())
    dqa = dict(run=dev.name, nonconverged_by_cell=q.get("nonconverged_by_cell"), qa_pass_as_recorded=q.get("pass"),
               per_cell_original_pass=bool(all(v <= 0.01 for v in (q.get("nonconverged_by_cell") or {}).values())))
    res = dict(status=status, gating=gating, criteria=crit, C1_original_contract=c1j, S1V2_DEV_original_rule=dqa,
               holdout2_allowed=False,
               holdout2_note="HOLDOUT2 additionally requires the AMENDMENT-007 lock re-audit by an independent auditor (audit 2026-10-29 sequence step 3)")
    (out / "C2_STATUS.json").write_text(json.dumps(res, indent=1, default=float))
    MF.write_manifest(out, phase="P2_S1", status=status, contract_sha=MF.sha256_file(MF.CONTRACT),
                      config_files=[Wd.EXP / "config/PLAN_PARAMETERS.json"] + [Wd.EXP / f"contracts/AMENDMENT-00{i}.md" for i in (3, 4, 5, 6, 7)],
                      input_lock=Path(os.environ.get("REFLECT_ROOT", ".")) / "out" / "INPUT_LOCK.sha256", outputs=sorted(out.glob("C2_*")),
                      seed_ledger=None, verdict="NOT_EVALUATED", unit="mathematical_deterministic",
                      limitations=["technical convergence verification on DEV inputs only", "SELF_REVIEW_ONLY"],
                      extra=dict(sub_phase="P2_C2", amendment="AMENDMENT-007"))
    print("C2", status, {k: crit[k]["pass_"] for k in gating})
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
