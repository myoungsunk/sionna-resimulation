import sys, json, glob, numpy as np, pandas as pd
OUT = sys.argv[1]; rng = np.random.default_rng(20261123)
rows = []
for f in sorted(glob.glob(f"{OUT}/*/seed*/RES.json")):
    cond = f.split("/")[-3]; seed = int(f.split("seed")[-1].split("/")[0]); R = json.load(open(f))
    for arm in R["R2"]:
        for grp in ("R2", "R5", "R2+R5"):
            rs = ("R2", "R5") if grp == "R2+R5" else (grp,)
            n = sum(R[r][arm]["n"] for r in rs); s = np.sum([R[r][arm]["sums"] for r in rs], 0)
            rows.append(dict(cond=cond, seed=seed, arm=arm, grp=grp, head=np.sqrt(s[0] / n), xy=np.sqrt(s[1] / n), nees3=s[2] / n,
                             pose95=s[3] / n, xy95=s[4] / n, head95=s[5] / n, mirror=sum(R[r][arm]["mirror"] for r in rs),
                             hbias=np.mean([R[r][arm]["hbias_deg"] for r in rs])))
D = pd.DataFrame(rows); D.to_csv(f"{OUT}/V1_PERSEED.csv", index=False)
med = D.groupby(["cond", "grp", "arm"]).agg(head=("head", "median"), xy=("xy", "median"), pose95=("pose95", "median"), head95=("head95", "median"),
        xy95=("xy95", "median"), nees3=("nees3", "median"), mirror_seeds=("mirror", lambda m: int((m > 0).sum()))).round(3)
print(med.to_string())
def ub(x):
    x = np.asarray(x); b = np.median(x[rng.integers(0, len(x), (10000, len(x)))], 1); return float(np.median(x)), float(np.quantile(b, .975))
print("\nratio H2S-SWB / ref, pooled R2+R5 (median, bootstrap 97.5% upper)")
J = {}
for cond in D.cond.unique():
    P = D[(D.cond == cond) & (D.grp == "R2+R5")].pivot(index="seed", columns="arm")
    for ref in ("H0", "H1S", "H2"):
        for m in ("xy", "head"):
            J[(cond, ref, m)] = ub(P[m]["H2S-SWB"] / P[m][ref])
    for k, v in J.items():
        if k[0] == cond: print(k, np.round(v, 3))
    mir = D[(D.cond == cond) & (D.grp == "R5") & (D.arm == "H2S-SWB")].mirror
    print(cond, "R5 mirror seeds H2S-SWB:", int((mir > 0).sum()), "seeds", sorted(D[(D.cond == cond) & (D.grp == "R5") & (D.arm == "H2S-SWB") & (D.mirror > 0)].seed.tolist()))
json.dump({"|".join(k): v for k, v in J.items()}, open(f"{OUT}/V1_RATIOS.json", "w"), indent=1)
