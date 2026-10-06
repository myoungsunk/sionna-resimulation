# CORRIDOR_SCAN_20261006

Robot x-scan (y = 0: x = 5.5, 7, 9, 11, 13) and y-scan (x = 7: y = -0.7, -0.35, +0.7) with the same yaw sweep (0-180 deg,
10 deg) and 257 bins as `CORRIDOR_SWEEP_20261006` (which supplies x = 4, 15 and (7, 0.35), (11, -0.5)).

- `run_scan.sh`: the two batches that produced the new positions (needs `PYTHON` = the Sionna venv).
- `*/<tag>_H.npy`, `*/<tag>_receipt.json`: H matrices and receipts. Path-level `*/<tag>_sweep.npz` are not in git (Git LFS upload is
  unavailable here); `scripts/corridor_reflection_fit.py` needs them and the originals in `CORRIDOR_SWEEP_20261006/pos*/`.
- `REFLECTION_FIT.json`: per-position fits, per-group first-path-tap contributions, attribution and Spearman associations.
- `corridor_reflection_fit.html`: the page (built by `scripts/corridor_render_reflection.py` with `LEDE.json`).
