"""P1_S0: exact linear-Gaussian mechanism (SCIENCE_SPEC §2), deterministic. Requires the FROZEN contract lock.

Outputs: S0_UNIT_TESTS.json, S0_INFORMATION.csv (S0-COV / S0-H / S0-JOINT), S0_PREDICTIONS.csv (every S1 cell),
S0_ORACLE_PARITY.csv (batch_map vs conditioning at truth), MANIFEST.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import filters as FL  # noqa: E402
import info_core as IC  # noqa: E402
import manifest as MF  # noqa: E402
import world as Wd  # noqa: E402

sys.path.insert(0, str(Wd.EXP / "scripts"))
import validate_contract as VC  # noqa: E402

STATES = ("rad", "tan", "psi", "bg")


import contract_lock as CL  # noqa: E402


def lock():
    lk = CL.effective_lock()
    if not lk or lk.get("status") != "FROZEN":
        raise SystemExit("ERR_CONTRACT_DRAFT: S0 requires FROZEN_LOCK")
    return lk


def window(defn: str):
    """'A|T1_HORIZONTAL|0' -> dict with poses, anchor, motion, H."""
    a, tr, st = defn.split("|"); st = int(st)
    fn = Wd.traj_fn(tr)
    P = fn()[st:st + 60]
    X, F, Q, ds, dth = Wd.motion_window(P, 0.5)
    h, H = Wd.h_H(X, a)
    return dict(id=defn, anchor=a, poses=P, X=X, F=F, Q=Q, ds=ds, dth=dth, h=h, H=H, t=np.arange(len(P)) * 0.5)


def cells(cfg):
    s1 = cfg["synthetic_s1"]; hi = s1["high_spatial"]; lo = s1["low_spatial"]; tm = s1["time_only_sensitivity"]
    out = {"LOWCORR": dict(alphas=(lo["alpha_pose"], lo["alpha_time"], lo["alpha_iid"]), tau=0.0, c=s1["r_s_corr"]),
           "POSE_HIGH": dict(alphas=(hi["alpha_pose"], hi["alpha_time"], hi["alpha_iid"]), tau=0.0, c=s1["r_s_corr"])}
    for tau in tm["tau_seconds"]:          # time-only negative control: alpha_p = 0, alpha_t = 0.3, alpha_w = 0.7 (PLAN_PARAMETERS)
        out[f"TIME_{tau:g}"] = dict(alphas=(0.0, tm["alpha_time"], 1.0 - tm["alpha_time"]), tau=float(tau), c=s1["r_s_corr"])
    out["POSE_HIGH_C03"] = dict(alphas=(hi["alpha_pose"], hi["alpha_time"], hi["alpha_iid"]), tau=0.0, c=s1["r_s_sensitivity_corr"])
    for nm, c in out.items():
        if abs(sum(c["alphas"]) - 1.0) > 1e-15 or min(c["alphas"]) < 0:
            raise SystemExit(f"ERR_S1_COV alphas of {nm} do not sum to 1")
    return out


CELL_ID = {"LOWCORR": 1, "POSE_HIGH": 2, "TIME_1": 3, "TIME_5": 4, "POSE_HIGH_C03": 5}   # RNG key component (SCIENCE_SPEC §3)


def sigma_for(w, cell, cfg):
    s1 = cfg["synthetic_s1"]; n = len(w["poses"])
    sig = np.tile([s1["sigma_r_m"], s1["sigma_s"]], (n, 1))
    Kp = IC.k_pose(w["poses"][:, :2], w["poses"][:, 2], s1["pose_corr_length_m"], math.radians(s1["pose_corr_yaw_deg"]))
    Kt = IC.k_time(w["t"], cell["tau"]) if cell["tau"] > 0 else None
    return IC.obs_covariance(Kp, Kt, cell["alphas"], sig, cell["c"])


def blockdiag(S):
    B = np.zeros_like(S)
    for k in range(0, S.shape[0], 2):
        B[k:k + 2, k:k + 2] = S[k:k + 2, k:k + 2]
    return B


def evaluate(F, Q, H, P0, Sig, p_ref, anchor):
    n = len(H)
    SX = IC.joint_prior(P0, F, Q); Hb = IC.stack_H(list(H), list(range(n)), n)
    Bd = blockdiag(Sig)
    P_corr, _ = IC.condition(SX, Hb, Sig)                  # correct model
    P_iid, E_iid = IC.condition(SX, Hb, Bd, Sig)           # iid-claimed model, true error under Sig
    T = IC.rotation_rt(p_ref, Wd.ANCHORS[anchor]); k = n - 1
    blocks = {nm: IC.marginal_block(M, k, T) for nm, M in (("prior", SX), ("corr", P_corr), ("iid", P_iid), ("iid_true", E_iid))}
    d = {nm: np.diag(b) for nm, b in blocks.items()}
    out = {}
    for i, a in enumerate(STATES):
        I_prior = 1 / d["prior"][i]; I_c = 1 / d["corr"][i]; I_i = 1 / d["iid"][i]
        out.update({f"Pprior_{a}": d["prior"][i], f"Pcorr_{a}": d["corr"][i], f"Piid_claim_{a}": d["iid"][i],
                    f"Piid_true_{a}": d["iid_true"][i],
                    f"OC_post_{a}": d["corr"][i] / d["iid"][i],
                    f"OC_data_{a}": (I_i - I_prior) / (I_c - I_prior) if I_c - I_prior > 0 else np.nan,
                    f"infl_iid_{a}": d["iid_true"][i] / d["iid"][i],
                    f"mse_ratio_oracle_iid_{a}": d["corr"][i] / d["iid_true"][i],
                    f"Inondim_corr_{a}": IC.STATE_SCALES[i] ** 2 / d["corr"][i]})
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    lk = lock(); cfg = Wd.PARAMS; status = "PASS"; problems = []
    contract_sha = MF.sha256_file(MF.CONTRACT)
    P0 = np.diag(IC.STATE_SCALES ** 2)
    # ---- S0-A analytic
    ut = []
    for rho in cfg["mathematical_s0"]["rho"]:
        for sgn in (+1, -1):
            num = IC.two_obs_ratio(rho, sgn); ref = 1 / (1 + rho) if sgn > 0 else 1 / (1 - rho)
            ut.append(dict(rho=rho, sign=sgn, numeric=num, closed_form=ref, abs_err=abs(num - ref), ok=abs(num - ref) <= 1e-10))
    c09 = dict(same=IC.two_obs_ratio(0.9, 1), opp=IC.two_obs_ratio(0.9, -1))
    contract_ok = abs(c09["same"] - 0.5263157894736842) <= 1e-10 and abs(c09["opp"] - 10.0) <= 1e-10
    (out / "S0_UNIT_TESTS.json").write_text(json.dumps(dict(cases=ut, rho09=c09, contract_constants_ok=contract_ok), indent=1))
    if not (contract_ok and all(u["ok"] for u in ut)):
        problems.append("ERR_S0_MATH")
    # ---- fixed designs
    hg = lk["resolved"]["HGEOMETRY_CHOICE"]
    WL, WH = window(hg["low"]), window(hg["high"])
    C = cells(cfg)
    rows = []
    # S0-COV: H fixed (each window), Sigma varied
    for w in (WL, WH):
        for cn, cell in C.items():
            r = evaluate(w["F"], w["Q"], w["H"], P0, sigma_for(w, cell, cfg), w["poses"][-1], w["anchor"])
            rows.append(dict(experiment="S0-COV/S0-JOINT", window=w["id"], role="LOW" if w is WL else "HIGH", cell=cn, **r))
    # S0-H: Sigma and F,Q,P0,times fixed to the LOW window; H varied
    for role, Hs in (("LOW", WL["H"]), ("HIGH", WH["H"])):
        for cn in ("LOWCORR", "POSE_HIGH"):
            r = evaluate(WL["F"], WL["Q"], Hs, P0, sigma_for(WL, C[cn], cfg), WL["poses"][-1], WL["anchor"])
            rows.append(dict(experiment="S0-H(fixed F,Q,Sigma of LOW)", window=f"H_from_{role}", role=role, cell=cn, **r))
    D = pd.DataFrame(rows); D.to_csv(out / "S0_INFORMATION.csv", index=False, float_format="%.12g")
    # predicted DID (log OC_post and log infl) for S1 primary
    pred = []
    J = D[D.experiment == "S0-COV/S0-JOINT"].set_index(["role", "cell"])
    Hx = D[D.experiment.str.startswith("S0-H")].set_index(["role", "cell"])
    for a_ in STATES:
        for kind, tab in (("JOINT", J), ("FIXED_SIGMA_F", Hx)):
            for q in ("OC_post", "infl_iid"):
                did = (math.log(tab.loc[("LOW", "POSE_HIGH"), f"{q}_{a_}"]) - math.log(tab.loc[("LOW", "LOWCORR"), f"{q}_{a_}"])) - \
                      (math.log(tab.loc[("HIGH", "POSE_HIGH"), f"{q}_{a_}"]) - math.log(tab.loc[("HIGH", "LOWCORR"), f"{q}_{a_}"]))
                pred.append(dict(state=a_, design=kind, quantity=q, DID_log=did))
    P = pd.DataFrame(pred); P.to_csv(out / "S0_DID.csv", index=False, float_format="%.12g")
    D[D.experiment == "S0-COV/S0-JOINT"][["window", "role", "cell"] + [c for c in D.columns if c.startswith(("infl_iid_", "OC_post_", "mse_ratio_", "Piid_", "Pcorr_"))]] \
        .to_csv(out / "S0_PREDICTIONS.csv", index=False, float_format="%.12g")
    # ---- oracle parity: batch_map at truth (noise-free) vs conditioning
    par = []
    for w in (WL, WH):
        for cn in ("LOWCORR", "POSE_HIGH"):
            Sig = sigma_for(w, C[cn], cfg)
            hb = lambda X, a=w["anchor"]: Wd.h_H(X, a)  # noqa: E731
            dts = np.full(60, 0.5)
            # model-consistent truth: noise-free rollout from the first ledger pose (ledger reproduced to ~3e-6 m)
            Xr, Fs, Gs = FL._rollout(w["X"][0], np.zeros((60, 2)), w["ds"], w["dth"], dts)
            hr, Hr = Wd.h_H(Xr, w["anchor"])
            Xh, Pst, info = FL.batch_map(hb, hr, np.zeros_like(hr), Sig, w["ds"], w["dth"], dts, Xr[0], P0)
            Qs = [np.zeros((4, 4))] + [Gs[k] @ np.diag([FL.Q_DS * abs(w["ds"][k]), FL.Q_GY * dts[k]]) @ Gs[k].T for k in range(1, 60)]
            SX = IC.joint_prior(P0, Fs, Qs); Hb = IC.stack_H(list(Hr), list(range(60)), 60)
            Pc, _ = IC.condition(SX, Hb, Sig)
            w["Xr"] = Xr
            ref = Pc[-4:, -4:]; got = Pst[-1]
            par.append(dict(window=w["id"], cell=cn, state_err_max=float(np.max(np.abs(Xh - Xr))),
                            ledger_vs_rollout_max_m=float(np.max(np.abs(Xr[:, :2] - w["X"][:, :2]))),
                            cov_rel_err=float(np.max(np.abs(got - ref)) / np.max(np.abs(ref))), iters=info["iters"]))
    PA = pd.DataFrame(par); PA["ok"] = (PA.cov_rel_err <= 1e-6) & (PA.state_err_max <= 1e-6)
    PA.to_csv(out / "S0_ORACLE_PARITY.csv", index=False, float_format="%.6g")
    if not PA.ok.all():
        problems.append("ERR_S0_Q oracle parity")
    if problems:
        status = "FAIL"
    (out / "S0_STATUS.json").write_text(json.dumps(dict(status=status, problems=problems, low=hg["low"], high=hg["high"]), indent=1))
    lock_path = Path(__import__("os").environ.get("REFLECT_ROOT", ".")) / "out" / "INPUT_LOCK.sha256"
    MF.write_manifest(out, phase="P1_S0", status=status, contract_sha=contract_sha, config_files=[Wd.EXP / "config/PLAN_PARAMETERS.json"],
                      input_lock=lock_path, outputs=sorted(out.glob("S0_*")), seed_ledger=None, verdict="NOT_EVALUATED",
                      unit="mathematical_deterministic",
                      limitations=["linear-Gaussian algebra at truth linearisation; no noise realisations",
                                   "FFD LOS Jacobians only", "auditor SELF_REVIEW_ONLY"])
    print("S0", status, problems)
    raise SystemExit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    main()
