"""Aggregate run_bb outputs by the frozen judging rules (PLAN_BIAS_FFD_KO.md section 3)."""
import json, glob, numpy as np, pandas as pd
ROUTES = ("R2", "R4", "R5"); ARMS = ("H2S", "BV0", "BVK", "P0", "P1", "P2", "P3", "P4")
COMP = {"P0": "BV0", "P1": "BV0", "P2": "BVK", "P3": "BVK", "P4": "BVK"}
rows, drows = [], []
for f in sorted(glob.glob("/home/claude/bb/out/*/seed*/GROUP.json")):
    g = json.load(open(f)); cond = f.split("/")[-3]; seed = int(f.split("seed")[-1].split("/")[0])
    for a in ARMS:
        P = g["point"]; n = np.array([P[r][a]["n"] for r in ROUTES], float); w = n / n.sum()
        rows.append(dict(cond=cond, seed=seed, arm=a,
                         xy=float(np.sqrt(w @ [P[r][a]["xy_rmse_cm"] ** 2 for r in ROUTES])),
                         hd=float(np.sqrt(w @ [P[r][a]["heading_rmse_deg"] ** 2 for r in ROUTES])),
                         pose95=P["pooled"][a]["pose95_coverage"], h95=P["pooled"][a]["heading95_coverage"], xy95=P["pooled"][a]["xy95_coverage"],
                         nees3=P["pooled"][a]["mean_nees3"], I=bool(g["seed_assessments"]["H2S"][a]["I_seed"]) if a != "H2S" else np.nan,
                         mirror=int(sum(g["mirror"][r][a] for r in ROUTES))))
        for r in ROUTES:
            for b, v in g["diag"][r][a]["by_bin"].items():
                drows.append(dict(cond=cond, seed=seed, arm=a, route=r, bin=int(b), hbias=v["hbias_deg"], hrms=v["hrms_deg"], zrms=v["zrms"]))
D = pd.DataFrame(rows); DD = pd.DataFrame(drows)
D.to_csv("/home/claude/bb/BB_PERSEED.csv", index=False); DD.to_csv("/home/claude/bb/BB_DIAG_BIN.csv", index=False)
rng = np.random.default_rng(0)
def boot(x, B=10000):
    x = np.asarray(x); idx = rng.integers(0, len(x), (B, len(x))); return float(np.median(x)), float(np.quantile(np.median(x[idx], 1), .975))
summ = []
for c in sorted(D.cond.unique()):
    q = D[D.cond == c]
    for a in ARMS:
        s = q[q.arm == a]
        row = dict(cond=c, arm=a, n_seeds=len(s), N_I=int(s.I.sum()) if a != "H2S" else None, mirror_seeds=int((s.mirror > 0).sum()),
                   xy_med=s.xy.median(), hd_med=s.hd.median(), pose95=s.pose95.median(), h95=s.h95.median(), xy95=s.xy95.median(), nees3=s.nees3.median())
        if a in COMP:
            ref = q[q.arm == COMP[a]].set_index("seed"); t = s.set_index("seed").loc[ref.index]
            row["vs"] = COMP[a]
            row["xy_ratio_med"], row["xy_ratio_u975"] = boot(t.xy / ref.xy)
            row["hd_ratio_med"], row["hd_ratio_u975"] = boot(t.hd / ref.hd)
            row["N_I_ref"] = int(ref.I.sum()); row["mirror_ref"] = int((ref.mirror > 0).sum())
        summ.append(row)
S = pd.DataFrame(summ); S.to_csv("/home/claude/bb/BB_SUMMARY.csv", index=False)
jud = []
for c in sorted(D.cond.unique()):
    s = S[S.cond == c].set_index("arm")
    p0 = s.loc["P0"]; jud.append(dict(cond=c, q="Q0 P0~BV0", verdict=bool(0.97 <= p0.xy_ratio_med <= 1.03 and 0.97 <= p0.hd_ratio_med <= 1.03)))
    p1 = s.loc["P1"]; jud.append(dict(cond=c, q="Q1 P1>BV0", verdict=bool(p1.xy_ratio_u975 < 1 and p1.hd_ratio_u975 < 1 and p1.N_I > p1.N_I_ref)))
    for a, qn in (("P2", "Q2"), ("P3", "Q3"), ("P4", "Q4")):
        x = s.loc[a]; jud.append(dict(cond=c, q=f"{qn} {a} non-inferior to BVK",
                                      verdict=bool(x.N_I >= x.N_I_ref - 1 and x.xy_ratio_u975 <= 1.10 and x.hd_ratio_u975 <= 1.10 and x.mirror_seeds <= x.mirror_ref)))
J = pd.DataFrame(jud); J.to_csv("/home/claude/bb/BB_JUDGE.csv", index=False)
pd.set_option("display.width", 250)
print(S.round(3).to_string(index=False)); print(J.to_string(index=False))
print(DD.groupby(["cond", "arm", "bin"])[["hbias", "zrms"]].median().unstack("bin").round(2).loc["B0"].to_string())
