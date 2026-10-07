# DRIVE_SIM v1 analysis (simulation only, placeholder parameters; `s` is not q_clean)

runs: 18000; failed runs: 0; ekf runs used for H1-H4: 10800

## Summary by baseline (EKF, all conditions)

| baseline | heading_rmse_median | pos_rmse_median | wrong_branch_mean | nees_mean | nis_s_mean | s_reject_mean | probes | duration_s |
|---|---|---|---|---|---|---|---|---|
| gyro_only | 8.36 | 1.4 | 0.177 | 3.93 | nan | nan | 0 | 183 |
| inverse_heading_P0 | 5.71 | 0.708 | 0.124 | 307 | 15.3 | 0.292 | 0 | 183 |
| odom_imu | 7.79 | 1.23 | 0.0983 | 3.41 | nan | nan | 0 | 183 |
| range | 7.89 | 0.948 | 0.103 | 99.7 | nan | nan | 0 | 183 |
| range_s_P0 | 2.39 | 0.587 | 0 | 43.7 | 0.857 | 0.0244 | 0 | 183 |
| range_s_P0_noturn | 2.46 | 0.59 | 0.104 | 111 | 0.938 | 0.0255 | 0 | 183 |
| range_s_P1_T10 | 1.58 | 0.3 | 0 | 24.2 | 0.941 | 0.0273 | 17 | 306 |
| range_s_P1_T20 | 2.14 | 0.41 | 0 | 27.7 | 0.835 | 0.0239 | 8 | 241 |
| range_s_P1_T60 | 1.72 | 0.398 | 0 | 27.4 | 0.833 | 0.0238 | 2 | 198 |



## H1 (vs_odom_imu): range+s (P0) vs reference, 19/24 conditions improved, 0 worse

## H1 (vs_gyro_only): range+s (P0) vs reference, 18/24 conditions improved, 2 worse

## H2: s as measurement vs heading inverted from s: 24/24 improved, 0 worse

## H3 / H3_alt (passive P0, mount 45 vs 0): 45 deg better in 12/12 conditions (H3), 0 deg better in 0 (H3_alt)

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
| range_s_P0 | ekf | 2.39 | 43.7 | 0.0244 |
| range_s_P0 | gsf | 3.85 | 128 | 0.0233 |
| range_s_P0 | iekf | 2.44 | 45.2 | 0.0244 |
| range_s_P0 | ukf | 2.37 | 41 | 0.0243 |
| range_s_P1_T20 | ekf | 2.14 | 27.7 | 0.0239 |
| range_s_P1_T20 | gsf | 3.02 | 24 | 0.0224 |
| range_s_P1_T20 | iekf | 2.14 | 25.8 | 0.0239 |
| range_s_P1_T20 | ukf | 2.18 | 24.8 | 0.0239 |


