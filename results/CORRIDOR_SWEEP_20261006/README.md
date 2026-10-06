# CORRIDOR_SWEEP_20261006

Sionna RT 2.0.1 yaw sweep, LP +45/-45 port pair, 4 robot positions x 19 yaws (0-180 deg) x 257 bins.

- `pos*/position_*_H.npy`: complex128 H, layout `[yaw, bin, rx_port(+45,-45), tx_port(+45,-45)]`.
- `pos*/position_*_receipt.json`: versions, bank/runner SHA256, timing, materials.
- `ratio_table.csv`, `ratio_series.json`, `VALIDATION.json`, `LOS_CHECK.json`: analysis and checks.
- `pos*/position_*_sweep.npz` (path lists: a, tau, interactions; ~34 MB total) are NOT in git because the
  environment cannot upload Git LFS objects. Regenerate with:
  `python scripts/corridor_sionna_run.py --out results/CORRIDOR_SWEEP_20261006/pos<N> --position <N>`
  (about 16 min per position on one core; needs sionna-rt 2.0.1, mitsuba 3.8.0, drjit 1.3.1 and the LP_plus45/LP_minus45 FFD banks).
  `scripts/corridor_analyze.py` needs these npz files for the LoS-only curve.
