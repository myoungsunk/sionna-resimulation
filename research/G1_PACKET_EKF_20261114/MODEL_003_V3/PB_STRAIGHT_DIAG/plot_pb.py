from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np

root = Path(sys.argv[1]).resolve()
fig, axes = plt.subplots(2, 3, sharex=True, sharey="row", figsize=(10, 5.1), layout="constrained")
colors = {"S-V": "#be5c00", "S-C": "#005b99", "DR": "#454545"}
for col, anchor in enumerate("ABC"):
    heading_ax, slope_ax = axes[:, col]
    heading_ax.set_title(f"Anchor {anchor}")
    for arm in ("S-V", "S-C"):
        with np.load(root/"capture"/f"G-T1_{anchor}_P-B_B0_{arm}.npz", allow_pickle=False) as data:
            distance = data["distance_m"]
            straight = (data["motion"] == "straight") & (np.diff(distance, prepend=0.0) > 0.0)
            x = distance[straight]
            errors = [("post_error_rad", arm)]
            if arm == "S-V":
                errors.insert(0, ("dr_error_rad", "DR"))
            for key, label in errors:
                rmse = np.sqrt(np.mean(np.degrees(data[key][straight]) ** 2, axis=1))
                heading_ax.plot(x, rmse, label=label, color=colors[label], lw=1.35,
                                linestyle="--" if label == "DR" else "-")
            median_j = np.nanmedian(np.abs(data["jac_s_per_rad"][straight]), axis=1)
            slope_ax.plot(x, median_j, color=colors[arm], lw=1.15)
    for ax in (heading_ax, slope_ax):
        ax.grid(alpha=0.22)
        ax.set_xlim(0.0, 5.1)
    slope_ax.set_xlabel("Distance from start (m)")
axes[0, 0].set_ylabel("Heading RMSE (°)")
axes[1, 0].set_ylabel("Median |ds/dψ| per radian")
axes[0, 0].set_ylim(0.0, 13.0)
axes[1, 0].set_ylim(bottom=0.0)
axes[0, 0].legend(loc="upper left", frameon=False)
fig.suptitle("P-B straight travel · B0 · DIAGNOSTIC_ONLY", fontweight="bold")
fig.savefig(root/"PLOT_B0.png", dpi=185)
