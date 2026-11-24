import json, numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
S = json.load(open("SUMMARY.json")); INK, INK2, BLUE, SURF = "#0b0b0b", "#52514e", "#2a78d6", "#fcfcfb"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2})
f, axs = plt.subplots(6, 1, figsize=(11, 12.5), facecolor=SURF)
for ax, k in zip(axs, S):
    D = pd.read_csv(f"{k}_trajectory.csv"); s = S[k]; ax.set_facecolor(SURF)
    ax.add_patch(Rectangle((1.2, -0.45), 17.55, 0.9, color="#e9e8e4", zorder=0, lw=0))                 # sweep grid area
    for yw, ls in ((1.2, "-"), (-1.2, "-"), (0.96, "--"), (-0.96, "--")): ax.axhline(yw, color=INK2, lw=1.0 if ls == "-" else 0.8, ls=ls, zorder=1)
    ax.plot(D.x, D.y, color=BLUE, lw=2, zorder=3, solid_capstyle="round")
    q = D.iloc[::40]; ax.quiver(q.x, q.y, np.cos(q.yaw), np.sin(q.yaw), color=INK, scale=55, width=0.0022, headwidth=4, zorder=4)
    R = D[D["mode"] == "rotate"]; ax.scatter(R.x, R.y, s=46, facecolors="none", edgecolors=INK2, lw=0.8, zorder=4)
    ax.scatter(D.x.iloc[0], D.y.iloc[0], s=70, color=BLUE, edgecolors=SURF, lw=2, zorder=5)
    ax.scatter(D.x.iloc[-1], D.y.iloc[-1], s=60, marker="s", color=SURF, edgecolors=BLUE, lw=2, zorder=5)
    ax.scatter(10, 0, s=90, marker="^", color=INK, zorder=6)
    ax.set_xlim(0, 20); ax.set_ylim(-1.3, 1.3); ax.set_aspect("equal"); ax.set_yticks([-1.2, -0.45, 0, 0.45, 1.2])
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    ax.set_title(f"{k}  {s['name']}", loc="left", color=INK, fontsize=10, fontweight="bold", pad=3)
    ax.text(20, 1.42, f"{s['duration_s']:.0f} s · {s['path_m']} m · start ρ {s['start_rho_m']} m · anchor passes {s['anchor_passes']} ({'/'.join(s['pass_sides'])}) · ρ<3 m {int(100*s['near_frac_rho_lt3'])}% · in-place rotation {int(100*s['rotate_frac'])}%",
            ha="right", va="bottom", color=INK2, fontsize=8.2)
axs[-1].set_xlabel("x (m)"); [a.set_ylabel("y (m)") for a in axs]
h = [plt.Line2D([], [], color=BLUE, lw=2, label="path"), plt.Line2D([], [], marker="o", ls="", color=BLUE, label="start"),
     plt.Line2D([], [], marker="s", ls="", mfc=SURF, mec=BLUE, mew=2, label="end"), plt.Line2D([], [], marker="^", ls="", color=INK, label="anchor (10, 0, 2.65 m)"),
     plt.Line2D([], [], marker="o", ls="", mfc="none", mec=INK2, label="in-place rotation"), plt.Line2D([], [], marker=r"$\rightarrow$", ls="", color=INK, ms=10, label="heading (every 8 s)"),
     Rectangle((0, 0), 1, 1, color="#e9e8e4", label="sweep grid (|y| ≤ 0.45 m)"), plt.Line2D([], [], color=INK2, lw=1, label="RT corridor wall (±1.2 m)"),
     plt.Line2D([], [], color=INK2, lw=0.8, ls="--", label="real corridor wall (±0.96 m)")]
f.legend(handles=h, loc="upper center", ncol=5, frameon=False, fontsize=8.5, bbox_to_anchor=(0.5, 0.995))
f.tight_layout(rect=(0, 0, 1, 0.965)); f.savefig("CANDIDATE_TRAJECTORIES.png", dpi=150, facecolor=SURF)
