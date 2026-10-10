# A24 gate G-A24-0 attempted on the assistant's CPU environment (2026-10-10) — descriptive, not a gate result

Inputs: the user's published A23 inputs (H_R2_aA_m0 sha256 1c40aea5…, LUT 711e12ee…, freqs fe0bcfeb…, timeline/rf_poses equal to S1 in this repo) and the stored S6 `results_R2_aA_m0.csv` (sha256 16428ad0…, from `codex/a23-results-20261010`). `check-a0`, R2-A m0, drifts 0–2, seeds 0–49 (150 keys), 4 workers.

| run | numpy | inference_valid | max abs diff (heading deg / pos m / NEES) |
|---|---|---|---|
| `--filter-variant F0aug` | 2.5.3 | false | 1.29e-3 / 5.66e-4 / 32.3 |
| `--filter-variant F0` (stored path) | 2.5.3 | false | identical to the row above |
| `--filter-variant F0aug`, numpy 2.4.6 + pandas 3.0.6 (Snowball versions), 1 BLAS thread | 2.4.6 | false | identical to the row above |

Findings:
- F0aug and F0 are **bit-identical** on all 40 numeric columns of the 150 A0 rows (same code, same platform): the augmentation switch-off is equivalent to the stored filter here.
- The mismatch against the stored S6 is not the numpy version, not the H store and not the observation chain: the noise-free-plus-noise observations (`obs_s`, `obs_range`, `detected`, `power`) of seed 0 / drift 0 are bit-identical to the user's trace; the sensor input `ds_odom` differs from the user's trace at 1.4e-17 from sample 47 (`np.hypot`/libm level) and `cov6` differs at ~1e-6 from sample 13 (matrix-product kernel level); the closed loop (gates, first-path-dependent updates) amplifies this to 4.7e-4 in the estimate for that run.
- Across the 150 runs the median absolute difference to S6 is 1.1e-8 (NEES), 2.3e-9 (heading RMSE), 2.3e-10 (position RMSE); p90 4.9e-7 / 1.2e-7 / 1.0e-8; maximum 32.3 / 1.3e-3 / 5.7e-4. Means over the 150 runs: NEES 106.38 vs 106.52 stored, heading 10.4028 vs 10.4028 deg, position 0.9169 vs 0.9169 m.
- Reading: the pre-registered 1e-9 reproduction of the stored S6 holds only on the platform that produced S6 (Snowball container); on another CPU/libm the aggregates agree but individual runs can differ by large amounts in a few seeds. The earlier remark "local H does not reproduce Snowball S6" (A23 spec) was therefore not attributable to the H store alone.
- G-A24-0 is **not** claimed as passed. Platform: the assistant's Linux container (Python 3.13.16), not the Snowball image (Python 3.11.15).
