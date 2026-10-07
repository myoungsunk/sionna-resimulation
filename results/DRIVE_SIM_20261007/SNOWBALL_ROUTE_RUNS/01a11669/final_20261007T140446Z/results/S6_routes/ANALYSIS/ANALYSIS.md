# DRIVE_SIM routes R2/R4/R5, anchors A/B (simulation only, placeholder parameters; `s` is not q_clean)

runs 54000; failed 0; EKF runs used 32400

## heading RMSE median [deg] by route / anchor / mount (EKF, drift and SNR pooled)

| route | anchor | mount_deg | odom_imu | gyro_only | range | range_s_P0 | range_s_P0_noturn | range_s_P1_T60 | range_s_P1_T20 | range_s_P1_T10 | inverse_heading_P0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R2 | A | 0 | 9.74 | 8.34 | 7.08 | 10.7 | 12.6 | 6.5 | 4.79 | 2.77 | 14.9 |
| R2 | A | 45 | 9.74 | 8.34 | 6.87 | 1.61 | 2.3 | 1.83 | 1.91 | 2.67 | 1.83 |
| R2 | B | 0 | 9.74 | 8.34 | 6.35 | 2.31 | 3.93 | 1.78 | 1.73 | 1.66 | 18.7 |
| R2 | B | 45 | 9.74 | 8.34 | 6.02 | 3.79 | 3.38 | 3.47 | 4.05 | 2.18 | 4.37 |
| R4 | A | 0 | 5.39 | 7.4 | 4.75 | 1.66 | 1.47 | 1.67 | 1.35 | 1.62 | 1.86 |
| R4 | A | 45 | 5.39 | 7.4 | 5.22 | 2.05 | 1.39 | 1.48 | 0.87 | 1.51 | 1.7 |
| R4 | B | 0 | 5.39 | 7.4 | 2.62 | 1.68 | 1.76 | 1.65 | 1.64 | 1.88 | 1.51 |
| R4 | B | 45 | 5.39 | 7.4 | 2.64 | 2.31 | 1.27 | 2.15 | 1.72 | 2.48 | 1.77 |
| R5 | A | 0 | 10.3 | 9.64 | 5.29 | 5.53 | 6.15 | 7.03 | 6.96 | 3.06 | 21.4 |
| R5 | A | 45 | 10.3 | 9.64 | 6.69 | 4.59 | 4.3 | 5.36 | 3.89 | 3.8 | 3.18 |
| R5 | B | 0 | 10.3 | 9.64 | 10.3 | 2.98 | 2.98 | 2.11 | 2.38 | 1.96 | 33.1 |
| R5 | B | 45 | 10.3 | 9.64 | 6.88 | 2.69 | 2.42 | 2.61 | 1.76 | 1.6 | 3.85 |



## position RMSE median [m]

| route | anchor | mount_deg | odom_imu | gyro_only | range | range_s_P0 | range_s_P0_noturn | range_s_P1_T60 | range_s_P1_T20 | range_s_P1_T10 | inverse_heading_P0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R2 | A | 0 | 1.28 | 1.41 | 0.7 | 0.93 | 0.99 | 0.86 | 0.64 | 0.22 | 1.96 |
| R2 | A | 45 | 1.28 | 1.41 | 0.68 | 0.35 | 0.4 | 0.35 | 0.33 | 0.52 | 0.27 |
| R2 | B | 0 | 1.28 | 1.41 | 0.48 | 0.32 | 0.26 | 0.27 | 0.35 | 0.28 | 1.92 |
| R2 | B | 45 | 1.28 | 1.41 | 0.49 | 0.65 | 0.62 | 0.58 | 0.68 | 0.45 | 0.94 |
| R4 | A | 0 | 0.9 | 1.13 | 0.54 | 0.39 | 0.39 | 0.4 | 0.41 | 0.5 | 0.31 |
| R4 | A | 45 | 0.9 | 1.13 | 0.55 | 0.3 | 0.2 | 0.24 | 0.15 | 0.2 | 0.32 |
| R4 | B | 0 | 0.9 | 1.13 | 0.23 | 0.17 | 0.17 | 0.16 | 0.15 | 0.19 | 0.2 |
| R4 | B | 45 | 0.9 | 1.13 | 0.23 | 0.2 | 0.15 | 0.19 | 0.16 | 0.24 | 0.23 |
| R5 | A | 0 | 1.38 | 1.36 | 0.62 | 0.78 | 0.83 | 0.87 | 1.01 | 0.4 | 2.45 |
| R5 | A | 45 | 1.38 | 1.36 | 0.79 | 0.5 | 0.49 | 0.56 | 0.42 | 0.39 | 0.37 |
| R5 | B | 0 | 1.38 | 1.36 | 0.84 | 0.3 | 0.27 | 0.28 | 0.29 | 0.29 | 2.63 |
| R5 | B | 45 | 1.38 | 1.36 | 0.61 | 0.52 | 0.5 | 0.49 | 0.23 | 0.22 | 0.88 |



## displacement (loop-closure) error median [m]: |(x_end - x_start)_est - (x_end - x_start)_true|; for R2 the true displacement is ~0

| route | anchor | mount_deg | gyro_only | odom_imu | range | range_s_P0 | range_s_P1_T10 | range_s_P1_T20 |
|---|---|---|---|---|---|---|---|---|
| R2 | A | 0 | 1.01 | 2.14 | 1.3 | 0.417 | 0.286 | 0.175 |
| R2 | A | 45 | 1.01 | 2.14 | 1.43 | 0.146 | 0.941 | 0.137 |
| R2 | B | 0 | 1.01 | 2.14 | 1.14 | 0.275 | 0.334 | 0.324 |
| R2 | B | 45 | 1.01 | 2.14 | 1.03 | 0.31 | 0.194 | 0.268 |
| R4 | A | 0 | 2.2 | 1.33 | 0.894 | 0.882 | 1.15 | 0.892 |
| R4 | A | 45 | 2.2 | 1.33 | 0.966 | 0.715 | 0.549 | 0.379 |
| R4 | B | 0 | 2.2 | 1.33 | 0.429 | 0.174 | 0.272 | 0.194 |
| R4 | B | 45 | 2.2 | 1.33 | 0.485 | 0.307 | 0.418 | 0.192 |
| R5 | A | 0 | 2.9 | 2.05 | 1.39 | 0.787 | 0.458 | 0.388 |
| R5 | A | 45 | 2.9 | 2.05 | 1.56 | 0.333 | 0.455 | 0.293 |
| R5 | B | 0 | 2.9 | 2.05 | 2.01 | 0.316 | 0.402 | 0.392 |
| R5 | B | 45 | 2.9 | 2.05 | 1.44 | 0.283 | 0.227 | 0.275 |



## H1 (vs_odom_imu) per route/anchor: conditions improved / worse

| route | anchor | conditions | improved | worse | median_rel_improvement |
|---|---|---|---|---|---|
| R2 | A | 12 | 6 | 0 | 0.496 |
| R2 | B | 12 | 12 | 0 | 0.715 |
| R4 | A | 12 | 12 | 0 | 0.66 |
| R4 | B | 12 | 12 | 0 | 0.629 |
| R5 | A | 12 | 12 | 0 | 0.519 |
| R5 | B | 12 | 12 | 0 | 0.719 |



## H1 (vs_gyro_only) per route/anchor: conditions improved / worse

| route | anchor | conditions | improved | worse | median_rel_improvement |
|---|---|---|---|---|---|
| R2 | A | 12 | 8 | 4 | 0.612 |
| R2 | B | 12 | 11 | 0 | 0.603 |
| R4 | A | 12 | 12 | 0 | 0.67 |
| R4 | B | 12 | 12 | 0 | 0.674 |
| R5 | A | 12 | 8 | 0 | 0.486 |
| R5 | B | 12 | 11 | 0 | 0.672 |



## H2 (s as measurement vs inverted heading)

| route | anchor | conditions | improved | worse | median_rel_improvement |
|---|---|---|---|---|---|
| R2 | A | 12 | 8 | 0 | 0.213 |
| R2 | B | 12 | 11 | 0 | 0.531 |
| R4 | A | 12 | 3 | 6 | -0.0769 |
| R4 | B | 12 | 0 | 6 | -0.112 |
| R5 | A | 12 | 6 | 6 | 0.228 |
| R5 | B | 12 | 12 | 0 | 0.579 |



## H5: mount 45 vs 0 (median_rel_improvement > 0: 45 deg better; < 0: 0 deg better). Registered: R4 -> 0 deg better, R2/R5 -> 45 deg better

| route | anchor | conditions | mount45_better | mount0_better | median_rel |
|---|---|---|---|---|---|
| R2 | A | 6 | 6 | 0 | 0.835 |
| R2 | B | 6 | 0 | 4 | -0.379 |
| R4 | A | 6 | 0 | 6 | -0.253 |
| R4 | B | 6 | 0 | 6 | -0.365 |
| R5 | A | 6 | 4 | 0 | 0.214 |
| R5 | B | 6 | 2 | 0 | 0.0416 |



## H6: range+s (P0) vs odom+IMU on the displacement error

| route | anchor | conditions | improved | worse | median_rel_improvement |
|---|---|---|---|---|---|
| R2 | A | 12 | 12 | 0 | 0.883 |
| R2 | B | 12 | 12 | 0 | 0.865 |
| R4 | A | 12 | 9 | 0 | 0.421 |
| R4 | B | 12 | 12 | 0 | 0.83 |
| R5 | A | 12 | 12 | 0 | 0.779 |
| R5 | B | 12 | 12 | 0 | 0.855 |



## H7 (exploratory): anchor B vs A on heading RMSE of range+s (P0); median_rel_improvement > 0 means B better

| route | conditions | improved | worse | median_rel_improvement |
|---|---|---|---|---|
| R2 | 12 | 6 | 6 | -0.0737 |
| R4 | 12 | 0 | 6 | -0.0849 |
| R5 | 12 | 12 | 0 | 0.447 |



## H4 at 20 deg: largest probe period with the wrong-branch upper bound <= 10 % (None = P1 never reaches it)

| route | anchor | mount_deg | largest_T_ok |
|---|---|---|---|
| R2 | A | 0 | [60] |
| R2 | A | 45 | [60] |
| R2 | B | 0 | [60] |
| R2 | B | 45 | [60] |
| R4 | A | 0 | [60] |
| R4 | A | 45 | [60] |
| R4 | B | 0 | [60] |
| R4 | B | 45 | [60] |
| R5 | A | 0 | [60] |
| R5 | A | 45 | [60] |
| R5 | B | 0 | [60] |
| R5 | B | 45 | [60] |



## H4 at 10 deg: largest probe period with the wrong-branch upper bound <= 10 % (None = P1 never reaches it)

| route | anchor | mount_deg | largest_T_ok |
|---|---|---|---|
| R2 | A | 0 | [20] |
| R2 | A | 45 | [60] |
| R2 | B | 0 | [60] |
| R2 | B | 45 | [60] |
| R4 | A | 0 | [60] |
| R4 | A | 45 | [60] |
| R4 | B | 0 | [60] |
| R4 | B | 45 | [60] |
| R5 | A | 0 | [10] |
| R5 | A | 45 | [20, 60] |
| R5 | B | 0 | [60] |
| R5 | B | 45 | [60] |



## Filter types

| route | baseline | filter | heading_rmse_median | nees_mean |
|---|---|---|---|---|
| R2 | range_s_P0 | ekf | 2.76 | 73.6 |
| R2 | range_s_P0 | gsf | 5.94 | 72.8 |
| R2 | range_s_P0 | iekf | 2.84 | 94.4 |
| R2 | range_s_P0 | ukf | 2.79 | 39.9 |
| R2 | range_s_P1_T20 | ekf | 2.65 | 40.9 |
| R2 | range_s_P1_T20 | gsf | 3.92 | 57 |
| R2 | range_s_P1_T20 | iekf | 2.68 | 43.3 |
| R2 | range_s_P1_T20 | ukf | 2.66 | 32.9 |
| R4 | range_s_P0 | ekf | 1.84 | 13.5 |
| R4 | range_s_P0 | gsf | 2.7 | 12.1 |
| R4 | range_s_P0 | iekf | 1.83 | 13.3 |
| R4 | range_s_P0 | ukf | 1.85 | 13.3 |
| R4 | range_s_P1_T20 | ekf | 1.44 | 11.8 |
| R4 | range_s_P1_T20 | gsf | 2.65 | 12.5 |
| R4 | range_s_P1_T20 | iekf | 1.43 | 11.7 |
| R4 | range_s_P1_T20 | ukf | 1.48 | 11.8 |
| R5 | range_s_P0 | ekf | 4.4 | 45.5 |
| R5 | range_s_P0 | gsf | 4.37 | 39.6 |
| R5 | range_s_P0 | iekf | 4.42 | 48.3 |
| R5 | range_s_P0 | ukf | 4.38 | 35.6 |
| R5 | range_s_P1_T20 | ekf | 3.05 | 47.2 |
| R5 | range_s_P1_T20 | gsf | 2.42 | 37 |
| R5 | range_s_P1_T20 | iekf | 3.07 | 47.9 |
| R5 | range_s_P1_T20 | ukf | 3.07 | 44.6 |


