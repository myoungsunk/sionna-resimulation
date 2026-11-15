"""G1-CHAR-001 figures from ERRORS_*.npz and C*_*.json. Usage: python -I char_figures.py <out dir> <fig dir>"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

S = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"]
INK, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID, "grid.linewidth": .6,
                     "axes.facecolor": SURF, "figure.facecolor": SURF, "axes.spines.top": False,
                     "axes.spines.right": False, "lines.linewidth": 2, "legend.frameon": False})
out, fig = Path(sys.argv[1]), Path(sys.argv[2])
fig.mkdir(parents=True, exist_ok=True)
c4 = json.load(open(out / "C4_GEOMETRY.json"))
c3 = json.load(open(out / "C3_SCALES.json"))
c7 = json.load(open(out / "C7_COMPARE.json"))

# F1 sigma_s(d) log-log
f, ax = plt.subplots(1, 2, figsize=(9, 3.4), sharey=True)
for a, cases, title in ((ax[0], ("G-T1_A", "G-T1_B", "G-T1_C"), "New RT G-T1 (mount 0)"),
                        (ax[1], ("R2_aA_m0", "R2_aB_m0", "R4_aA_m0", "R4_aB_m0", "R5_aA_m0", "R5_aB_m0"),
                         "BLOCK_C old RT (mount 0)")):
    for i, c in enumerate(cases):
        b = c4[c]["e_s"]["by_distance"]
        d = np.array([int(k) + .5 for k in b])
        s = np.array([v["std"] for v in b.values()])
        a.plot(d, s, "-o", ms=4, color=S[i], label=f"{c} (slope {c4[c]['e_s']['loglog_slope']:.1f})")
    a.set_xscale("log"); a.set_yscale("log"); a.set_title(title, color=INK, loc="left")
    a.set_xlabel("anchor distance d [m]"); a.legend(fontsize=7)
ax[0].set_ylabel("std of e_s per 1 m bin (thinned)")
f.tight_layout(); f.savefig(fig / "F1_sigma_s_vs_distance.png", dpi=150); plt.close(f)

# F2 e_s by dtap class (G-T1 pooled + BLOCK_C pooled)
f, ax = plt.subplots(1, 2, figsize=(9, 3.2), sharey=True)
for a, cases, title in ((ax[0], ("G-T1_A", "G-T1_B", "G-T1_C"), "New RT G-T1"),
                        (ax[1], ("R2_aA_m0", "R2_aB_m0", "R4_aA_m0", "R4_aB_m0", "R5_aA_m0", "R5_aB_m0"), "BLOCK_C m0")):
    zs = [np.load(out / f"ERRORS_{c}.npz") for c in cases]
    ms = [~np.isin(z["set"], ["P-A_REPEAT", "P-D", "P-E"]) for z in zs]
    e = np.concatenate([z["e_s"][m] for z, m in zip(zs, ms)])
    dt = np.concatenate([z["dtap"][m] for z, m in zip(zs, ms)])
    groups = [("Δtap=0", dt == 0), ("Δtap=−1", dt == -1), ("Δtap=+1", dt == 1), ("Δtap≥+2", dt >= 2)]
    bins = np.linspace(-1.2, 1.2, 97)
    for i, (lab, m) in enumerate(groups):
        a.hist(e[m], bins=bins, histtype="step", density=True, color=S[i], lw=1.6,
               label=f"{lab}  {m.mean()*100:.0f}%  σ={e[m].std():.2f}")
    a.set_yscale("log"); a.set_title(title, color=INK, loc="left"); a.set_xlabel("e_s = s_full − s_LoS")
    a.legend(fontsize=7)
ax[0].set_ylabel("density (log)")
f.tight_layout(); f.savefig(fig / "F2_e_s_by_tap_shift.png", dpi=150); plt.close(f)

# F3 revisit correlation vs offset
f, a = plt.subplots(figsize=(4.8, 3.2))
offs = [0.005, 0.01, 0.02, 0.05, 0.1]
for i, c in enumerate(("G-T1_A", "G-T1_B", "G-T1_C")):
    r = c3[c]["revisit"]
    a.plot([o * 100 for o in offs], [r[f"P-D_{o:.3f}"]["rho_e_s"] for o in offs], "-o", ms=4, color=S[i], label=c)
a.axhline(0, color=MUTED, lw=.8)
a.set_xscale("log"); a.set_xlabel("revisit position offset [cm] (λ≈4.6 cm)"); a.set_ylabel("corr(e_s, e_s′)")
a.set_title("Same-pose repeat ρ≥0.99; decorrelates within 2–5 cm", color=INK, loc="left", fontsize=8)
a.legend(fontsize=7); f.tight_layout(); f.savefig(fig / "F3_revisit_correlation.png", dpi=150); plt.close(f)

# F4 mount comparison prior-pipeline heading RMSE (low drift)
e = c7["mount_R2_aA_prior_pipeline_ekf"]
keys = [k for k in e if k.endswith("|low")]
keys = sorted(keys, key=lambda k: e[k]["heading_rmse_median_m0"])
f, a = plt.subplots(figsize=(8, 3.6))
y = np.arange(len(keys))
a.barh(y - .2, [e[k]["heading_rmse_median_m0"] for k in keys], .38, color=S[0], label="mount 0")
a.barh(y + .2, [e[k]["heading_rmse_median_m45"] for k in keys], .38, color=S[1], label="mount 45")
a.set_yticks(y, [k.replace("|low", "") for k in keys], fontsize=7); a.set_xlabel("median heading RMSE [deg] (100 runs, low drift)")
a.set_title("R2_aA prior BLOCK_C pipeline: heading RMSE by mount", color=INK, loc="left")
a.legend(fontsize=7); f.tight_layout(); f.savefig(fig / "F4_mount_heading_rmse_R2_aA.png", dpi=150); plt.close(f)
print("figures written")
