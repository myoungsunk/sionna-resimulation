"""Audit of cross_term_cv_20261119 (same input CSV, same LOQO fit).
A. In-sample 360-deg decomposition: cross term identity check.
B. Null calibration of the LOQO gamma: e* = a*delta + b + roll(r, k) per station (k = 1..35, k != 18), i.e. residuals kept
   with their yaw autocorrelation but de-aligned from a. Same LOQO procedure -> gamma_null distribution.
C. The quantity F2 uses: E[eps^2 | rho, a]. Regress eps^2 on [1, a, a^2] per bin; a nonzero linear term is what a
   cross term 2a*E[delta*(b+r)|a] would add. Station bootstrap (10,000) for the linear coefficient and its share."""
import numpy as np, pandas as pd, json, argparse
from pathlib import Path
ap = argparse.ArgumentParser(); ap.add_argument("--input", type=Path, default=Path(__file__).parent / "../../frozen/STATION_SWEEP_ERRORS.csv")
ap.add_argument("--out", type=Path, default=Path(__file__).parent / "regenerated_AUDIT_CROSS.json"); opt = ap.parse_args()
D = pd.read_csv(opt.input).sort_values(["st", "yaw"]).reset_index(drop=True)
D["rho"] = (D.x - 10).abs()
BINS = [(0, 3), (3, 6), (6, 10)]
st_ids = sorted(D.st.unique()); S = {s: D[D.st == s] for s in st_ids}
def fit(a, e):
    A = np.c_[np.ones(len(a)), a]; b, d = np.linalg.lstsq(A, e, rcond=None)[0]; return d, b
def loqo(a, e, yaw):
    q = ((yaw + 180) // 90).astype(int); acc = dict(e2=0., cross=0.)
    for f in range(4):
        tr, te = q != f, q == f; d, b = fit(a[tr], e[tr]); h = a[te] * d
        acc["e2"] += np.sum(e[te]**2); acc["cross"] += np.sum(2 * h * (e[te] - h))
    return acc
out = {"A_insample": {}, "B_null": {}, "C_moment": {}}
# A + B
obs = {s: loqo(S[s].a.to_numpy(), S[s].es.to_numpy(), S[s].yaw.to_numpy()) for s in st_ids}
null = {s: [] for s in st_ids}; ins = {}
for s in st_ids:
    a, e, yaw = S[s].a.to_numpy(), S[s].es.to_numpy(), S[s].yaw.to_numpy(); d, b = fit(a, e); r = e - a * d - b
    ins[s] = dict(cross=float(np.mean(2 * a * d * (b + r))), e2=float(np.mean(e**2)), mean_a=float(a.mean()))
    for k in [k for k in range(1, 36) if k != 18]:
        null[s].append(loqo(a, a * d + b + np.roll(r, k), yaw))
for lo, hi in BINS:
    ss = [s for s in st_ids if lo <= S[s].rho.iloc[0] < hi]
    g_obs = sum(obs[s]["cross"] for s in ss) / sum(obs[s]["e2"] for s in ss)
    g_null = np.array([sum(null[s][j]["cross"] for s in ss) / sum(null[s][j]["e2"] for s in ss) for j in range(34)])
    out["A_insample"][f"{lo}-{hi}"] = dict(gamma_insample=sum(ins[s]["cross"] for s in ss) / sum(ins[s]["e2"] for s in ss),
                                           max_abs_mean_a=max(abs(ins[s]["mean_a"]) for s in ss))
    out["B_null"][f"{lo}-{hi}"] = dict(gamma_obs=g_obs, gamma_null_mean=float(g_null.mean()), gamma_null_p2_5=float(np.quantile(g_null, .025)),
                                       gamma_null_p97_5=float(np.quantile(g_null, .975)), frac_null_le_obs=float(np.mean(g_null <= g_obs)))
# C
rng = np.random.default_rng(20261119)
for lo, hi in BINS:
    d = D[(D.rho >= lo) & (D.rho < hi)]; ss = d.st.unique()
    def coef(df):
        X = np.c_[np.ones(len(df)), df.a, df.a**2]; return np.linalg.lstsq(X, df.es.to_numpy()**2, rcond=None)[0]
    b0, b1, b2 = coef(d); am = float(np.median(np.abs(d.a)))
    boots = []
    for _ in range(10000):
        pick = rng.choice(ss, len(ss)); boots.append(coef(pd.concat([d[d.st == s] for s in pick])))
    boots = np.array(boots)
    share = lambda c: abs(c[1]) * am / (c[0] + c[2] * am**2)
    out["C_moment"][f"{lo}-{hi}"] = dict(n_st=int(len(ss)), b0=float(b0), b1_linear=float(b1), b2=float(b2), median_abs_a=am,
                                         b1_ci95=[float(np.quantile(boots[:, 1], .025)), float(np.quantile(boots[:, 1], .975))],
                                         linear_share_at_median_abs_a=float(share((b0, b1, b2))),
                                         linear_share_ci95=[float(np.quantile([share(c) for c in boots], .025)), float(np.quantile([share(c) for c in boots], .975))])
opt.out.parent.mkdir(parents=True, exist_ok=True); json.dump(out, open(opt.out, "w"), indent=1)
for k, v in out.items(): print("==", k); print(pd.DataFrame(v).T.to_string())
