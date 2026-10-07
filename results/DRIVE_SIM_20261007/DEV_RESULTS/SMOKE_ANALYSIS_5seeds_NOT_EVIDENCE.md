# DRIVE_SIM v1 analysis (simulation only, placeholder parameters; `s` is not q_clean)

runs: 1800; failed runs: 2; ekf runs used for H1-H4: 1080

## Summary by baseline (EKF, all conditions)

| baseline | heading_rmse_median | pos_rmse_median | wrong_branch_mean | nees_mean | nis_s_mean | s_reject_mean | probes | duration_s |
|---|---|---|---|---|---|---|---|---|
| gyro_only | 9.12 | 1.19 | 0.182 | 3.57 | nan | nan | 0 | 183 |
| inverse_heading_P0 | 5.39 | 0.66 | 0.115 | 281 | 15.4 | 0.297 | 0 | 183 |
| odom_imu | 7.45 | 0.981 | 0.0915 | 3.31 | nan | nan | 0 | 183 |
| range | 6.53 | 0.865 | 0.126 | 97.8 | nan | nan | 0 | 183 |
| range_s_P0 | 2.39 | 0.569 | 0 | 38.3 | 0.854 | 0.024 | 0 | 183 |
| range_s_P0_noturn | 2.97 | 0.572 | 0.124 | 116 | 0.94 | 0.025 | 0 | 183 |
| range_s_P1_T10 | 1.52 | 0.302 | 0 | 23.8 | 0.946 | 0.0275 | 17 | 306 |
| range_s_P1_T20 | 2.09 | 0.42 | 0 | 30.4 | 0.832 | 0.0238 | 8 | 241 |
| range_s_P1_T60 | 1.69 | 0.389 | 0 | 27.4 | 0.832 | 0.0239 | 2 | 198 |



## H1 (vs_odom_imu): range+s (P0) vs reference, 0/24 conditions improved, 0 worse

## H1 (vs_gyro_only): range+s (P0) vs reference, 0/24 conditions improved, 0 worse

## H2: s as measurement vs heading inverted from s: 0/24 improved, 0 worse

## H3 / H3_alt (passive P0, mount 45 vs 0): 45 deg better in 0/12 conditions (H3), 0 deg better in 0 (H3_alt)

## H4: largest probe period with wrong-branch upper bound <= 10 %

| lateral | mount_deg | drift | snr_db | ub_T10 | ub_T20 | ub_T60 | ub_P0 | largest_T_ok |
|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 10 | 0 | 0 | 0 | 0 | 60 |
| 0 | 0 | 0 | 30 | 0 | 0 | 0 | 0 | 60 |
| 0 | 0 | 1 | 10 | 0 | 0 | 0 | 0 | 60 |
| 0 | 0 | 1 | 30 | 0 | 0 | 0 | 0 | 60 |
| 0 | 0 | 2 | 10 | 0 | 0 | 0 | 0 | 60 |
| 0 | 0 | 2 | 30 | 0 | 0 | 0 | 0 | 60 |
| 0 | 45 | 0 | 10 | 0 | 0 | 0 | 0 | 60 |
| 0 | 45 | 0 | 30 | 0 | 0 | 0 | 0 | 60 |
| 0 | 45 | 1 | 10 | 0 | 0 | 0 | 0 | 60 |
| 0 | 45 | 1 | 30 | 0 | 0 | 0 | 0 | 60 |
| 0 | 45 | 2 | 10 | 0 | 0 | 0 | 0 | 60 |
| 0 | 45 | 2 | 30 | 0 | 0 | 0 | 0 | 60 |
| 0.35 | 0 | 0 | 10 | 0 | 0 | 0 | 0 | 60 |
| 0.35 | 0 | 0 | 30 | 0 | 0 | 0 | 0 | 60 |
| 0.35 | 0 | 1 | 10 | 0 | 0 | 0 | 0 | 60 |
| 0.35 | 0 | 1 | 30 | 0 | 0 | 0 | 0 | 60 |
| 0.35 | 0 | 2 | 10 | 0 | 0 | 0 | 0 | 60 |
| 0.35 | 0 | 2 | 30 | 0 | 0 | 0 | 0 | 60 |
| 0.35 | 45 | 0 | 10 | 0 | 0 | 0 | 0 | 60 |
| 0.35 | 45 | 0 | 30 | 0 | 0 | 0 | 0 | 60 |
| 0.35 | 45 | 1 | 10 | 0 | 0 | 0 | 0 | 60 |
| 0.35 | 45 | 1 | 30 | 0 | 0 | 0 | 0 | 60 |
| 0.35 | 45 | 2 | 10 | 0 | 0 | 0 | 0 | 60 |
| 0.35 | 45 | 2 | 30 | 0 | 0 | 0 | 0 | 60 |



## Filter types (EKF vs IEKF/UKF/GSF)

| baseline | filter | heading_rmse_median | nees_mean | s_reject_mean |
|---|---|---|---|---|
| range_s_P0 | ekf | 2.39 | 38.3 | 0.024 |
| range_s_P0 | gsf | 3.93 | 38.3 | 0.0225 |
| range_s_P0 | iekf | 2.47 | 39.5 | 0.024 |
| range_s_P0 | ukf | 2.36 | 36.8 | 0.0237 |
| range_s_P1_T20 | ekf | 2.09 | 30.4 | 0.0238 |
| range_s_P1_T20 | gsf | 2.91 | 24.3 | 0.0222 |
| range_s_P1_T20 | iekf | 2.1 | 25.7 | 0.0238 |
| range_s_P1_T20 | ukf | 2.16 | 24.7 | 0.0238 |



## Failed runs: 2 (see failed_runs.csv)
