"""Implementer-side self-check of S0 by an independent algebraic path (NOT an independent auditor verdict).

S0 (s0_math.py) uses the covariance form: joint state prior Sigma_X (singular-Q aware), P = Sigma_X - Sigma_X H^T S^-1 H Sigma_X.
This check uses the information form over the minimal parameter theta = (x0, v_1..v_{n-1}) with x_k = J_k theta,
J built from fresh core.predict Jacobians, an element-wise (loop) construction of Sigma, and a central finite-difference
Jacobian of the FFD h. It reads S0_PREDICTIONS.csv and reports max relative differences.

  audit_s0_independent.py --s0 <dir with S0_PREDICTIONS.csv> --out <dir>
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
import s0_math as S0  # noqa: E402
import world as Wd  # noqa: E402

TOL = 1e-8


def sigma_loop(w, cell, cfg):
    s1 = cfg["synthetic_s1"]; n = len(w["poses"]); a_p, a_t, a_w = cell["alphas"]; c = cell["c"]
    lp, ly = s1["pose_corr_length_m"], math.radians(s1["pose_corr_yaw_deg"]); sd = (s1["sigma_r_m"], s1["sigma_s"])
    S = np.zeros((2 * n, 2 * n))
    for i in range(n):
        for j in range(n):
            pi, pj = w["poses"][i], w["poses"][j]
            kp = math.exp(-((pi[0] - pj[0]) ** 2 + (pi[1] - pj[1]) ** 2) / (2 * lp * lp)) * math.exp(-2 * math.sin((pi[2] - pj[2]) / 2) ** 2 / (ly * ly))
            kt = math.exp(-abs(w["t"][i] - w["t"][j]) / cell["tau"]) if cell["tau"] > 0 else float(i == j)
            k = a_p * kp + a_t * kt + a_w * float(i == j)
            for u in range(2):
                for v in range(2):
                    S[2 * i + u, 2 * j + v] = sd[u] * sd[v] * (1.0 if u == v else c) * k
    return S


def jac_theta(w):
    n = len(w["poses"]); X = w["X"]; nth = 4 + 2 * (n - 1)
    J = np.zeros((n, 4, nth)); J[0, :, :4] = np.eye(4); qd = np.zeros(nth); qd[:4] = np.nan
    for k in range(1, n):
        ds, dth = float(w["ds"][k]), float(w["dth"][k])
        q = np.diag([2e-5 * abs(ds), math.radians(0.015) ** 2 * 0.5, 0.0])
        _, _, F, G = Wd.predict(X[k - 1], np.zeros((4, 4)), ds, dth, 0.5, q)
        F = np.asarray(F); G = np.asarray(G)[:, :2]
        J[k] = F @ J[k - 1]; J[k, :, 4 + 2 * (k - 1):4 + 2 * k] += G
        qd[4 + 2 * (k - 1):4 + 2 * k] = (q[0, 0], q[1, 1])
    return J, qd


def fd_H(X, anchor, eps=1e-6):
    H = np.zeros((len(X), 2, 4))
    for j in range(4):
        d = np.zeros(4); d[j] = eps
        hp, _ = Wd.h_H(X + d, anchor); hm, _ = Wd.h_H(X - d, anchor)
        H[:, :, j] = (hp - hm) / (2 * eps)
    return H


def evaluate_info(w, H, Sig, P0):
    n = len(H); J, qd = jac_theta(w)
    A = np.einsum("kij,kjt->kit", H, J).reshape(2 * n, -1)
    L0 = np.zeros((A.shape[1], A.shape[1])); L0[:4, :4] = np.linalg.inv(P0); L0[4:, 4:] = np.diag(1 / qd[4:])
    B = np.zeros_like(Sig)
    for k in range(n):
        B[2 * k:2 * k + 2, 2 * k:2 * k + 2] = Sig[2 * k:2 * k + 2, 2 * k:2 * k + 2]
    Ic = L0 + A.T @ np.linalg.solve(Sig, A); Ii = L0 + A.T @ np.linalg.solve(B, A)
    Pc = np.linalg.inv(Ic); Pi = np.linalg.inv(Ii)
    W = np.linalg.solve(B, A); Et = Pi @ (L0 + W.T @ Sig @ W) @ Pi            # sandwich: true error covariance of the iid estimator
    Jn = J[-1]; T = np.eye(4); u = w["poses"][-1, :2] - np.array(Wd.ANCHORS[w["anchor"]][:2]); u /= np.linalg.norm(u)
    T[0, :2] = u; T[1, :2] = (-u[1], u[0])
    blk = lambda M: np.diag(T @ Jn @ M @ Jn.T @ T.T)  # noqa: E731
    return blk(Pc), blk(Pi), blk(Et)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--s0", required=True); ap.add_argument("--out", required=True); a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    lk = S0.lock(); cfg = Wd.PARAMS; hg = lk["resolved"]["HGEOMETRY_CHOICE"]
    pred = pd.read_csv(Path(a.s0) / "S0_PREDICTIONS.csv")
    P0 = np.diag(np.array([0.1, 0.1, math.radians(5), math.radians(0.2)]) ** 2)
    rows = []; fd = {}
    for role, defn in (("LOW", hg["low"]), ("HIGH", hg["high"])):
        w = S0.window(defn)
        dev = np.abs(fd_H(w["X"], w["anchor"], 1e-5) - w["H"]).max(axis=(1, 2)) / np.abs(w["H"]).max()
        fd[role] = dict(window=defn, max_rel_dev=float(dev.max()), kink_pose_idx=[int(i) for i in np.where(dev > 1e-4)[0]],
                        smooth_pose_max_rel_dev=float(dev[dev <= 1e-4].max()), kink_frac=float((dev > 1e-4).mean()))
        for cn, cell in S0.cells(cfg).items():
            Sig = sigma_loop(w, cell, cfg)
            dc, di, de = evaluate_info(w, w["H"], Sig, P0)
            r = pred[(pred.role == role) & (pred.cell == cn)].iloc[0]
            for i, st in enumerate(S0.STATES):
                for q, mine in (("infl_iid", de[i] / di[i]), ("OC_post", dc[i] / di[i]), ("mse_ratio_oracle_iid", dc[i] / de[i]),
                                ("Pcorr", dc[i]), ("Piid_claim", di[i])):
                    ref = float(r[f"{q}_{st}"])
                    rows.append(dict(role=role, cell=cn, state=st, quantity=q, s0=ref, independent=mine, rel_err=abs(mine - ref) / abs(ref)))
    D = pd.DataFrame(rows); D.to_csv(out / "S0_AUDIT_SELF_CHECK.csv", index=False, float_format="%.12g")
    res = dict(kind="IMPLEMENTER_SELF_CHECK (not an independent auditor verdict)", max_rel_err=float(D.rel_err.max()), tol=TOL,
               fd_jacobian=fd, fd_rule="AMENDMENT-002: kink pose = FD-vs-analytic deviation > 1e-4 of max|H|; window needs kink_frac <= 0.05; smooth poses <= 1e-6",
               n_compared=len(D))
    res["pass"] = bool(res["max_rel_err"] <= TOL and all(v["kink_frac"] <= 0.05 and v["smooth_pose_max_rel_dev"] <= 1e-6 for v in fd.values()))
    (out / "S0_AUDIT_SELF_CHECK.json").write_text(json.dumps(res, indent=1))
    print("S0 self-check", res)
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
