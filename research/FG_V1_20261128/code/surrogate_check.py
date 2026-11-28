"""Surrogate vs FFD: h errors at random box points and along R2/R4/R5 truth (and perturbed truth); single-call timing."""
import json, time, numpy as np
from common import *
import surrogate as S
e = env(); m = e["model"]; sp = e["spec"]
def ffd(X):
    h, H = m.batch(np.c_[X, np.zeros(len(X))], sp); return h, H[:, :, :3]
rng = np.random.default_rng(7); res = {}
P = np.c_[rng.uniform(1, 19, 2000), rng.uniform(-0.6, 0.6, 2000), rng.uniform(-np.pi, np.pi, 2000)]; pts = {"random_box": P}
for r in ("R2", "R4", "R5"):
    T = truth(r); pts[r + "_truth"] = T; pts[r + "_truth_perturbed"] = T + rng.normal(0, [0.15, 0.15, np.radians(5)], T.shape)
for k, X in pts.items():
    h0, H0 = ffd(X); h1, H1 = S.batch(X); err = h1 - h0; rel = np.linalg.norm(H1 - H0, axis=(1, 2)) / np.linalg.norm(H0, axis=(1, 2))
    res[k] = dict(n=len(X), range_err_p95=float(np.percentile(abs(err[:, 0]), 95)), range_err_max=float(abs(err[:, 0]).max()),
                  s_err_p95=float(np.percentile(abs(err[:, 1]), 95)), s_err_max=float(abs(err[:, 1]).max()), H_rel_p95=float(np.percentile(rel, 95)))
    print(k, {a: round(b, 4) for a, b in res[k].items()})
t = time.time(); [S.sur_h(P[i]) for i in range(1000)]; ts = (time.time() - t) / 1000
t = time.time(); [m.batch(np.r_[P[i], 0][None], sp) for i in range(200)]; tf = (time.time() - t) / 200
res["timing_ms"] = dict(surrogate_single=ts * 1e3, ffd_single=tf * 1e3)
res["spec"] = dict(x=[0.5, 19.5, 0.025], y=[-1.0, 1.0, 0.05], psi_deg_step=4, interp="trilinear h and H", noise_ref=dict(sigma_r_median=0.097, sigma_s_median=0.108))
json.dump(res, open(OUT + "/SURROGATE_CHECK.json", "w"), indent=1)
