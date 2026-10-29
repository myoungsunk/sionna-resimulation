"""P1_S0V2 (AMENDMENT-003): exact linear-Gaussian predictions for the v2 geometry and the revisit experiment.

Outputs: S0V2_PREDICTIONS.csv (LOW/HIGH x cells), S0V2_DID.csv, S0V2_REVISIT.csv (REV60/FWD60 x data cell x model),
S0V2_SEP.csv (H4b separability), S0V2_ORACLE_PARITY.csv (batch_map_v2 + tap-conditioned h at truth vs conditioning),
S0V2_AUDIT_SELF_CHECK.json (information-form path), MANIFEST.json. Requires the FROZEN AMENDMENT-003 lock.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "audit"))
import filters as FL  # noqa: E402
import info_core as IC  # noqa: E402
import manifest as MF  # noqa: E402
import s0_math as S0  # noqa: E402
import world as Wd  # noqa: E402

STATES = S0.STATES
P0M = np.diag(IC.STATE_SCALES ** 2)


def cells_v2(cfg):
    c = S0.cells(cfg)
    c["TIME_HIGH_5"] = dict(alphas=(0.0, 0.7, 0.3), tau=5.0, c=cfg["synthetic_s1"]["r_s_corr"])
    return c


CELL_ID_V2 = dict(S0.CELL_ID, TIME_HIGH_5=6)
XMODEL = {"POSE_HIGH": "TIME_HIGH_5", "TIME_HIGH_5": "POSE_HIGH"}
REV_CELLS = ("LOWCORR", "POSE_HIGH", "TIME_HIGH_5")


def lock_v2():
    lk = S0.lock()
    if "AMENDMENT-003" not in lk.get("applied_amendment_locks", []):
        raise SystemExit("ERR_CONTRACT_DRAFT: AMENDMENT-003 lock not FROZEN/applied")
    return lk


def windows_v2(lk):
    r = lk["resolved"]; g = r["HGEOMETRY_CHOICE_V2"]; rv = r["REVISIT_CHOICE"]
    return {"LOW": S0.window(g["low"]), "HIGH": S0.window(g["high"]), "REV60": S0.window(rv["REV60"]), "FWD60": S0.window(rv["FWD60"])}


def model_eval(w, Sig_model, Sig_true):
    n = len(w["H"]); SX = IC.joint_prior(P0M, w["F"], w["Q"]); Hb = IC.stack_H(list(w["H"]), list(range(n)), n)
    Pm, Et = IC.condition(SX, Hb, Sig_model, Sig_true)
    T = IC.rotation_rt(w["poses"][-1], Wd.ANCHORS[w["anchor"]]); k = n - 1
    dm = np.diag(IC.marginal_block(Pm, k, T)); de = np.diag(IC.marginal_block(Et, k, T))
    return {f"Pclaim_{a}": dm[i] for i, a in enumerate(STATES)} | {f"Ptrue_{a}": de[i] for i, a in enumerate(STATES)} | \
        {f"infl_{a}": de[i] / dm[i] for i, a in enumerate(STATES)}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    lk = lock_v2(); cfg = Wd.PARAMS; C = cells_v2(cfg); W = windows_v2(lk); problems = []
    # ---- LOW/HIGH predictions (same quantities as S0)
    rows = []
    for role in ("LOW", "HIGH"):
        w = W[role]
        for cn in S0.CELL_ID:
            r = S0.evaluate(w["F"], w["Q"], w["H"], P0M, S0.sigma_for(w, C[cn], cfg), w["poses"][-1], w["anchor"])
            rows.append(dict(window=w["id"], role=role, cell=cn, **r))
    D = pd.DataFrame(rows); D.to_csv(out / "S0V2_PREDICTIONS.csv", index=False, float_format="%.12g")
    J = D.set_index(["role", "cell"]); did = []
    for st in STATES:
        for q in ("OC_post", "infl_iid"):
            v = (math.log(J.loc[("LOW", "POSE_HIGH"), f"{q}_{st}"]) - math.log(J.loc[("LOW", "LOWCORR"), f"{q}_{st}"])) - \
                (math.log(J.loc[("HIGH", "POSE_HIGH"), f"{q}_{st}"]) - math.log(J.loc[("HIGH", "LOWCORR"), f"{q}_{st}"]))
            did.append(dict(state=st, design="JOINT", quantity=q, DID_log=v))
    DD = pd.DataFrame(did); DD.to_csv(out / "S0V2_DID.csv", index=False, float_format="%.12g")
    dpsi = float(DD[(DD.state == "psi") & (DD.quantity == "infl_iid")].DID_log.iloc[0])
    if abs(dpsi - lk["resolved"]["HGEOMETRY_CHOICE_V2"]["DID_psi"]) > 1e-9:
        problems.append(f"ERR_S0_MATH DID_psi {dpsi} != P0_GEO2 {lk['resolved']['HGEOMETRY_CHOICE_V2']['DID_psi']}")
    # ---- revisit: REV60 / FWD60, data cell x estimator model
    rv = []
    for role in ("REV60", "FWD60"):
        w = W[role]
        for dc in REV_CELLS:
            St = S0.sigma_for(w, C[dc], cfg)
            models = {"IID_BATCH": S0.blockdiag(St), "ORACLE_CORR_BATCH": St}
            if dc in XMODEL:
                models["XMODEL_BATCH"] = S0.sigma_for(w, C[XMODEL[dc]], cfg)
            for arm, Sm in models.items():
                rv.append(dict(window=w["id"], role=role, cell=dc, arm=arm, model_cell=XMODEL.get(dc, dc) if arm == "XMODEL_BATCH" else dc, **model_eval(w, Sm, St)))
    RV = pd.DataFrame(rv); RV.to_csv(out / "S0V2_REVISIT.csv", index=False, float_format="%.12g")
    R = RV.set_index(["role", "cell", "arm"]); sep = []
    for dc in XMODEL:
        for arm in ("XMODEL_BATCH", "IID_BATCH"):
            for st in ("psi", "tan"):
                v = math.log(R.loc[("REV60", dc, arm), f"infl_{st}"]) - math.log(R.loc[("FWD60", dc, arm), f"infl_{st}"])
                sep.append(dict(cell=dc, arm=arm, state=st, SEP_log=v, testable=abs(v) >= math.log(1.25)))
    SP = pd.DataFrame(sep); SP.to_csv(out / "S0V2_SEP.csv", index=False, float_format="%.12g")
    # ---- oracle parity: batch_map_v2 (tap-conditioned h) at truth, noise-free
    par = []
    for role, w in W.items():
        dts = np.full(60, 0.5); Xr, Fs, Gs = FL._rollout(w["X"][0], np.zeros((60, 2)), w["ds"], w["dth"], dts)
        taps = Wd.taps_of(Xr, w["anchor"]); hr, Hr = Wd.h_H_tap(Xr, w["anchor"], taps)
        h0, H0 = Wd.h_H(Xr, w["anchor"])
        for cn in ("LOWCORR", "POSE_HIGH"):
            Sig = S0.sigma_for(w, C[cn], cfg)
            Xh, Pst, info = FL.batch_map_v2(lambda X, t=taps, a=w["anchor"]: Wd.h_H_tap(X, a, t), hr, np.zeros_like(hr), Sig, w["ds"], w["dth"], dts, Xr[0], P0M)
            Qs = [np.zeros((4, 4))] + [Gs[k] @ np.diag([FL.Q_DS * abs(w["ds"][k]), FL.Q_GY * dts[k]]) @ Gs[k].T for k in range(1, 60)]
            Pc, _ = IC.condition(IC.joint_prior(P0M, Fs, Qs), IC.stack_H(list(Hr), list(range(60)), 60), Sig)
            par.append(dict(window=w["id"], role=role, cell=cn, status=info["status"], state_err_max=float(np.max(np.abs(Xh - Xr))),
                            cov_rel_err=float(np.max(np.abs(Pst[-1] - Pc[-4:, -4:])) / np.max(np.abs(Pc[-4:, -4:]))),
                            tap_model_equals_free_at_truth=float(max(np.abs(hr - h0).max(), np.abs(Hr - H0).max()))))
    PA = pd.DataFrame(par); PA["ok"] = (PA.cov_rel_err <= 1e-6) & (PA.state_err_max <= 1e-6) & (PA.tap_model_equals_free_at_truth == 0)
    PA.to_csv(out / "S0V2_ORACLE_PARITY.csv", index=False, float_format="%.6g")
    if not PA.ok.all():
        problems.append("ERR_S0_Q oracle parity v2")
    # ---- implementer self-check, independent information-form path (audit/audit_s0_independent.py functions)
    import audit_s0_independent as AU
    chk = []
    for role in ("LOW", "HIGH"):
        w = W[role]
        for cn in S0.CELL_ID:
            dc, di, de = AU.evaluate_info(w, w["H"], AU.sigma_loop(w, C[cn], cfg), P0M)
            r = J.loc[(role, cn)]
            for i, st in enumerate(STATES):
                for q, mine in (("infl_iid", de[i] / di[i]), ("OC_post", dc[i] / di[i]), ("mse_ratio_oracle_iid", dc[i] / de[i])):
                    chk.append(abs(mine - float(r[f"{q}_{st}"])) / abs(float(r[f"{q}_{st}"])))
    for role in ("REV60", "FWD60"):
        w = W[role]
        for dc in XMODEL:
            St = AU.sigma_loop(w, C[dc], cfg); Sm = AU.sigma_loop(w, C[XMODEL[dc]], cfg)
            n = 60; Jt, qd = AU.jac_theta(w); A = np.einsum("kij,kjt->kit", w["H"], Jt).reshape(2 * n, -1)
            L0 = np.zeros((A.shape[1], A.shape[1])); L0[:4, :4] = np.linalg.inv(P0M); L0[4:, 4:] = np.diag(1 / qd[4:])
            Pm = np.linalg.inv(L0 + A.T @ np.linalg.solve(Sm, A)); Wm = np.linalg.solve(Sm, A); Et = Pm @ (L0 + Wm.T @ St @ Wm) @ Pm
            T = np.eye(4); u = w["poses"][-1, :2] - np.array(Wd.ANCHORS["A"][:2]); u /= np.linalg.norm(u); T[0, :2] = u; T[1, :2] = (-u[1], u[0])
            M = lambda Z: np.diag(T @ Jt[-1] @ Z @ Jt[-1].T @ T.T)  # noqa: E731
            mine = M(Et) / M(Pm); ref = R.loc[(role, dc, "XMODEL_BATCH")]
            chk += [abs(mine[i] - float(ref[f"infl_{st}"])) / float(ref[f"infl_{st}"]) for i, st in enumerate(STATES)]
    sc = dict(kind="IMPLEMENTER_SELF_CHECK (not an independent auditor verdict)", max_rel_err=float(max(chk)), n=len(chk), pass_=bool(max(chk) <= 1e-8))
    (out / "S0V2_AUDIT_SELF_CHECK.json").write_text(json.dumps(sc, indent=1))
    if not sc["pass_"]:
        problems.append("ERR_S0_MATH self-check")
    status = "FAIL" if problems else "PASS"
    (out / "S0V2_STATUS.json").write_text(json.dumps(dict(status=status, problems=problems, windows={k: v["id"] for k, v in W.items()},
                                                          DID_psi=dpsi, SEP=SP.to_dict("records")), indent=1, default=float))
    MF.write_manifest(out, phase="P1_S0", status=status, contract_sha=MF.sha256_file(MF.CONTRACT),
                      config_files=[Wd.EXP / "config/PLAN_PARAMETERS.json", Wd.EXP / "contracts/AMENDMENT-003.md"],
                      input_lock=Path(os.environ.get("REFLECT_ROOT", ".")) / "out" / "INPUT_LOCK.sha256", outputs=sorted(out.glob("S0V2_*")),
                      seed_ledger=None, verdict="NOT_EVALUATED", unit="mathematical_deterministic",
                      limitations=["linear-Gaussian algebra at truth linearisation", "FFD LOS Jacobians; tap-conditioned model equals free model at truth",
                                   "auditor SELF_REVIEW_ONLY"], extra=dict(sub_phase="P1_S0V2", amendment="AMENDMENT-003"))
    print("S0V2", status, problems)
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
