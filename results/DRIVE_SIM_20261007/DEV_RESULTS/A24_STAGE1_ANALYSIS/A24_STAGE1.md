# A24 stage 1 — summary (bands and limits approved 2026-10-10; verdicts in the JSON `verdicts` block)

## F0

| arm | NEES mean | pose cov95 | heading cov95 | tail lo | tail hi | heading RMSE ° | pos RMSE m | band flags |
|---|---|---|---|---|---|---|---|---|
| A0_real_real | 106.520 | 0.184 | 0.205 | 0.005 | 0.805 | 10.510 | 0.927 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| J1_ar_indep | 240.072 | 0.042 | 0.262 | 0.000 | 0.947 | 7.909 | 1.217 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| J2_ar_corr | 249.753 | 0.051 | 0.246 | 0.000 | 0.936 | 8.295 | 1.210 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| J3_joint_block | 52.050 | 0.202 | 0.579 | 0.003 | 0.761 | 3.289 | 0.627 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| M0_Rmatched_Rmatched | 2.334 | 0.967 | 0.928 | 0.048 | 0.021 | 1.563 | 0.191 | {'nees_mean': True, 'nees_cov95': True, 'heading_cov95': True, 'nees_tail_lo': True, 'nees_tail_hi': True} |
| R1_bias | 8.852 | 0.537 | 0.905 | 0.002 | 0.366 | 1.620 | 0.232 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': True, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R2_ar0 | 12.770 | 0.554 | 0.822 | 0.007 | 0.381 | 2.105 | 0.332 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R3_ar1 | 21.536 | 0.383 | 0.851 | 0.003 | 0.553 | 1.920 | 0.318 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R4_iid | 5.753 | 0.771 | 0.906 | 0.005 | 0.156 | 1.624 | 0.209 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': True, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R5_realdem | 15.981 | 0.454 | 0.760 | 0.003 | 0.457 | 2.570 | 0.433 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R6_distbin | 10.876 | 0.605 | 0.884 | 0.019 | 0.364 | 1.804 | 0.239 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R7_tapbin | 8.657 | 0.548 | 0.906 | 0.002 | 0.357 | 1.624 | 0.230 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': True, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R8_real | 11.767 | 0.629 | 0.876 | 0.021 | 0.327 | 1.829 | 0.242 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S1_bias | 42.578 | 0.138 | 0.564 | 0.001 | 0.831 | 3.565 | 0.827 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S2_ar0 | 119.908 | 0.185 | 0.310 | 0.002 | 0.783 | 6.670 | 0.967 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S3_ar1 | 208.987 | 0.109 | 0.258 | 0.001 | 0.873 | 8.324 | 1.215 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S4_iid | 33.385 | 0.512 | 0.814 | 0.003 | 0.396 | 2.167 | 0.461 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S5_iid0 | 3.777 | 0.904 | 0.971 | 0.009 | 0.063 | 1.633 | 0.295 | {'nees_mean': True, 'nees_cov95': True, 'heading_cov95': True, 'nees_tail_lo': True, 'nees_tail_hi': True} |
| S6_realdem | 30.847 | 0.188 | 0.488 | 0.000 | 0.767 | 4.342 | 0.959 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S7_block | 38.737 | 0.314 | 0.509 | 0.002 | 0.641 | 3.716 | 0.606 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S8_real | 99.949 | 0.209 | 0.200 | 0.007 | 0.780 | 11.240 | 0.941 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| W0_white_white | 5.039 | 0.867 | 0.881 | 0.023 | 0.091 | 1.789 | 0.234 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': True} |

## F2

| arm | NEES mean | pose cov95 | heading cov95 | tail lo | tail hi | heading RMSE ° | pos RMSE m | band flags |
|---|---|---|---|---|---|---|---|---|
| A0_real_real | 40.296 | 0.403 | 0.454 | 0.021 | 0.571 | 7.555 | 0.919 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| J1_ar_indep | 16.103 | 0.593 | 0.739 | 0.006 | 0.347 | 4.118 | 0.666 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| J2_ar_corr | 16.780 | 0.497 | 0.726 | 0.006 | 0.436 | 4.383 | 0.754 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| J3_joint_block | 21.522 | 0.721 | 0.848 | 0.017 | 0.238 | 3.414 | 0.561 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| M0_Rmatched_Rmatched | 13.359 | 0.626 | 0.746 | 0.026 | 0.331 | 3.916 | 0.656 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R1_bias | 19.753 | 0.507 | 0.663 | 0.005 | 0.436 | 4.564 | 0.756 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R2_ar0 | 23.741 | 0.501 | 0.636 | 0.012 | 0.444 | 4.796 | 0.803 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R3_ar1 | 17.742 | 0.471 | 0.644 | 0.005 | 0.465 | 4.673 | 0.766 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R4_iid | 15.863 | 0.497 | 0.640 | 0.008 | 0.448 | 4.714 | 0.724 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R5_realdem | 19.269 | 0.550 | 0.681 | 0.017 | 0.397 | 4.379 | 0.709 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R6_distbin | 15.298 | 0.526 | 0.668 | 0.010 | 0.413 | 4.374 | 0.695 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R7_tapbin | 17.523 | 0.492 | 0.663 | 0.006 | 0.463 | 4.587 | 0.762 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R8_real | 17.615 | 0.486 | 0.651 | 0.008 | 0.462 | 4.673 | 0.739 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S1_bias | 21.396 | 0.498 | 0.655 | 0.017 | 0.464 | 4.646 | 0.803 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S2_ar0 | 46.831 | 0.639 | 0.769 | 0.023 | 0.311 | 3.933 | 0.641 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S3_ar1 | 15.683 | 0.635 | 0.741 | 0.026 | 0.314 | 4.135 | 0.670 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S4_iid | 13.654 | 0.772 | 0.865 | 0.033 | 0.192 | 3.045 | 0.510 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S5_iid0 | 9.462 | 0.772 | 0.875 | 0.037 | 0.196 | 2.963 | 0.488 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S6_realdem | 55.380 | 0.509 | 0.448 | 0.021 | 0.455 | 5.433 | 0.625 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S7_block | 11.183 | 0.783 | 0.807 | 0.046 | 0.176 | 3.484 | 0.508 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S8_real | 29.045 | 0.523 | 0.463 | 0.025 | 0.444 | 5.830 | 0.653 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| W0_white_white | 16.703 | 0.525 | 0.650 | 0.020 | 0.426 | 4.632 | 0.770 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |

## F1

| arm | NEES mean | pose cov95 | heading cov95 | tail lo | tail hi | heading RMSE ° | pos RMSE m | band flags |
|---|---|---|---|---|---|---|---|---|
| A0_real_real | 125.526 | 0.250 | 0.481 | 0.008 | 0.717 | 7.090 | 0.846 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| J1_ar_indep | 72.243 | 0.168 | 0.589 | 0.001 | 0.794 | 5.213 | 0.909 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| J2_ar_corr | 89.598 | 0.129 | 0.517 | 0.001 | 0.841 | 6.366 | 1.109 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| J3_joint_block | 41.826 | 0.341 | 0.813 | 0.007 | 0.614 | 3.573 | 0.689 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| M0_Rmatched_Rmatched | 16.025 | 0.661 | 0.715 | 0.017 | 0.298 | 4.029 | 0.560 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R1_bias | 51.709 | 0.237 | 0.650 | 0.001 | 0.701 | 4.564 | 0.675 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R2_ar0 | 44.067 | 0.270 | 0.574 | 0.002 | 0.679 | 5.320 | 0.846 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R3_ar1 | 66.974 | 0.195 | 0.618 | 0.002 | 0.766 | 5.068 | 0.834 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R4_iid | 27.542 | 0.446 | 0.705 | 0.002 | 0.475 | 4.076 | 0.567 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R5_realdem | 40.401 | 0.230 | 0.571 | 0.001 | 0.713 | 5.356 | 0.855 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R6_distbin | 37.097 | 0.396 | 0.656 | 0.010 | 0.573 | 4.565 | 0.636 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R7_tapbin | 49.792 | 0.277 | 0.690 | 0.001 | 0.658 | 4.388 | 0.681 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R8_real | 39.965 | 0.413 | 0.673 | 0.009 | 0.543 | 4.433 | 0.584 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S1_bias | 30.462 | 0.529 | 0.634 | 0.008 | 0.414 | 4.672 | 0.649 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S2_ar0 | 18.964 | 0.645 | 0.748 | 0.010 | 0.305 | 3.836 | 0.553 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S3_ar1 | 23.450 | 0.595 | 0.705 | 0.010 | 0.355 | 4.288 | 0.620 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S4_iid | 24.807 | 0.716 | 0.854 | 0.016 | 0.242 | 3.054 | 0.478 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S5_iid0 | 11.063 | 0.747 | 0.874 | 0.017 | 0.207 | 2.939 | 0.436 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S6_realdem | 321.855 | 0.482 | 0.472 | 0.007 | 0.469 | 5.277 | 0.593 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S7_block | 38.466 | 0.731 | 0.803 | 0.016 | 0.222 | 3.480 | 0.481 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S8_real | 43.761 | 0.448 | 0.466 | 0.006 | 0.510 | 5.867 | 0.670 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| W0_white_white | 28.009 | 0.513 | 0.630 | 0.009 | 0.430 | 4.699 | 0.684 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |

## F3

| arm | NEES mean | pose cov95 | heading cov95 | tail lo | tail hi | heading RMSE ° | pos RMSE m | band flags |
|---|---|---|---|---|---|---|---|---|
| A0_real_real | 8139.583 | 0.643 | 0.734 | 0.007 | 0.303 | 3.459 | 0.412 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| J1_ar_indep | 307.000 | 0.223 | 0.520 | 0.001 | 0.744 | 6.058 | 0.994 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| J2_ar_corr | 86.223 | 0.230 | 0.559 | 0.002 | 0.729 | 5.582 | 0.965 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| J3_joint_block | 569.945 | 0.427 | 0.660 | 0.006 | 0.520 | 4.039 | 0.659 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| M0_Rmatched_Rmatched | 260.426 | 0.259 | 0.516 | 0.006 | 0.704 | 6.021 | 1.018 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R1_bias | 109.130 | 0.292 | 0.550 | 0.002 | 0.664 | 5.698 | 1.030 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R2_ar0 | 60.308 | 0.296 | 0.540 | 0.008 | 0.675 | 5.772 | 1.021 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R3_ar1 | 97.243 | 0.240 | 0.527 | 0.001 | 0.715 | 5.882 | 1.048 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R4_iid | 99.275 | 0.293 | 0.494 | 0.003 | 0.663 | 6.354 | 1.090 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R5_realdem | 76.047 | 0.307 | 0.531 | 0.005 | 0.654 | 6.116 | 0.974 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R6_distbin | 79.140 | 0.292 | 0.598 | 0.002 | 0.656 | 5.305 | 0.935 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R7_tapbin | 105.190 | 0.317 | 0.600 | 0.002 | 0.637 | 5.398 | 0.927 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R8_real | 90.366 | 0.253 | 0.531 | 0.001 | 0.710 | 5.868 | 1.048 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S1_bias | 120.734 | 0.292 | 0.505 | 0.008 | 0.671 | 6.450 | 1.058 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S2_ar0 | 80.079 | 0.289 | 0.556 | 0.006 | 0.675 | 5.678 | 0.908 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S3_ar1 | 61.987 | 0.306 | 0.529 | 0.009 | 0.652 | 6.314 | 1.006 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S4_iid | 185.589 | 0.531 | 0.784 | 0.018 | 0.424 | 3.495 | 0.593 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S5_iid0 | 127.390 | 0.513 | 0.744 | 0.015 | 0.449 | 3.894 | 0.635 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S6_realdem | 592.155 | 0.631 | 0.638 | 0.019 | 0.316 | 3.861 | 0.494 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S7_block | 142.979 | 0.519 | 0.653 | 0.014 | 0.433 | 4.426 | 0.635 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S8_real | 465.567 | 0.676 | 0.728 | 0.034 | 0.285 | 3.423 | 0.405 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| W0_white_white | 102.863 | 0.331 | 0.532 | 0.005 | 0.622 | 6.114 | 1.014 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |

## F2acf

| arm | NEES mean | pose cov95 | heading cov95 | tail lo | tail hi | heading RMSE ° | pos RMSE m | band flags |
|---|---|---|---|---|---|---|---|---|
| A0_real_real | 67.219 | 0.353 | 0.398 | 0.021 | 0.610 | 6.847 | 0.845 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| J1_ar_indep | 42.629 | 0.318 | 0.572 | 0.003 | 0.637 | 5.224 | 0.865 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| J2_ar_corr | 36.718 | 0.317 | 0.553 | 0.004 | 0.636 | 5.531 | 0.921 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| J3_joint_block | 19.044 | 0.630 | 0.841 | 0.014 | 0.314 | 2.941 | 0.523 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| M0_Rmatched_Rmatched | 11.863 | 0.719 | 0.796 | 0.032 | 0.243 | 3.145 | 0.535 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R1_bias | 16.095 | 0.625 | 0.759 | 0.003 | 0.312 | 3.286 | 0.565 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R2_ar0 | 15.236 | 0.608 | 0.724 | 0.018 | 0.336 | 3.578 | 0.628 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R3_ar1 | 16.612 | 0.521 | 0.723 | 0.007 | 0.414 | 3.525 | 0.630 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R4_iid | 17.953 | 0.584 | 0.724 | 0.008 | 0.367 | 3.429 | 0.588 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R5_realdem | 18.257 | 0.630 | 0.720 | 0.012 | 0.317 | 3.596 | 0.589 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R6_distbin | 17.312 | 0.562 | 0.737 | 0.012 | 0.381 | 3.511 | 0.609 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R7_tapbin | 44.917 | 0.615 | 0.734 | 0.004 | 0.332 | 3.403 | 0.572 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R8_real | 17.155 | 0.533 | 0.729 | 0.012 | 0.412 | 3.436 | 0.572 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S1_bias | 18.783 | 0.578 | 0.660 | 0.012 | 0.370 | 3.980 | 0.637 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S2_ar0 | 23.553 | 0.609 | 0.648 | 0.015 | 0.346 | 4.435 | 0.648 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S3_ar1 | 30.770 | 0.438 | 0.547 | 0.010 | 0.516 | 5.453 | 0.814 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S4_iid | 9.104 | 0.819 | 0.918 | 0.035 | 0.152 | 2.321 | 0.413 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': True, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S5_iid0 | 5.974 | 0.835 | 0.951 | 0.048 | 0.136 | 2.390 | 0.416 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': True, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S6_realdem | 10.464 | 0.544 | 0.505 | 0.008 | 0.401 | 4.200 | 0.641 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S7_block | 31.062 | 0.767 | 0.769 | 0.028 | 0.200 | 3.336 | 0.467 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S8_real | 29.747 | 0.561 | 0.526 | 0.025 | 0.412 | 5.243 | 0.649 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| W0_white_white | 15.655 | 0.625 | 0.717 | 0.024 | 0.327 | 3.556 | 0.634 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |

## F1acf

| arm | NEES mean | pose cov95 | heading cov95 | tail lo | tail hi | heading RMSE ° | pos RMSE m | band flags |
|---|---|---|---|---|---|---|---|---|
| A0_real_real | 41.648 | 0.222 | 0.349 | 0.007 | 0.747 | 6.502 | 0.802 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| J1_ar_indep | 79.907 | 0.125 | 0.525 | 0.001 | 0.844 | 5.540 | 0.951 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| J2_ar_corr | 93.906 | 0.124 | 0.532 | 0.001 | 0.848 | 5.697 | 0.989 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| J3_joint_block | 36.076 | 0.335 | 0.805 | 0.004 | 0.616 | 3.140 | 0.615 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| M0_Rmatched_Rmatched | 11.627 | 0.725 | 0.772 | 0.022 | 0.235 | 3.155 | 0.470 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R1_bias | 30.749 | 0.339 | 0.761 | 0.001 | 0.582 | 3.098 | 0.506 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R2_ar0 | 36.009 | 0.339 | 0.636 | 0.003 | 0.609 | 4.157 | 0.702 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R3_ar1 | 49.699 | 0.234 | 0.691 | 0.001 | 0.716 | 3.698 | 0.636 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R4_iid | 23.656 | 0.550 | 0.767 | 0.004 | 0.374 | 3.093 | 0.462 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R5_realdem | 26.616 | 0.277 | 0.620 | 0.001 | 0.651 | 4.239 | 0.735 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R6_distbin | 20.974 | 0.443 | 0.748 | 0.009 | 0.520 | 3.246 | 0.509 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R7_tapbin | 29.442 | 0.351 | 0.757 | 0.001 | 0.568 | 3.072 | 0.483 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| R8_real | 21.646 | 0.452 | 0.719 | 0.011 | 0.500 | 3.401 | 0.466 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S1_bias | 27.936 | 0.519 | 0.612 | 0.009 | 0.429 | 4.268 | 0.635 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S2_ar0 | 23.562 | 0.574 | 0.658 | 0.007 | 0.373 | 4.273 | 0.611 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S3_ar1 | 49.887 | 0.385 | 0.506 | 0.006 | 0.565 | 5.696 | 0.801 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S4_iid | 10.355 | 0.820 | 0.916 | 0.021 | 0.143 | 2.244 | 0.343 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': True, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S5_iid0 | 6.131 | 0.811 | 0.941 | 0.020 | 0.148 | 2.243 | 0.357 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': True, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S6_realdem | 12.142 | 0.526 | 0.532 | 0.006 | 0.415 | 4.040 | 0.567 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S7_block | 37.804 | 0.675 | 0.759 | 0.011 | 0.272 | 3.423 | 0.479 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| S8_real | 36.158 | 0.473 | 0.529 | 0.008 | 0.486 | 5.217 | 0.665 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |
| W0_white_white | 16.570 | 0.612 | 0.739 | 0.011 | 0.332 | 3.321 | 0.526 | {'nees_mean': False, 'nees_cov95': False, 'heading_cov95': False, 'nees_tail_lo': True, 'nees_tail_hi': False} |

## Paired contrast F2-F0 (mean [95% CI], seeds paired, mean over drifts)

| arm | ΔNEES | Δpose cov95 | Δheading cov95 | Δheading RMSE ° | Δpos RMSE m |
|---|---|---|---|---|---|
| A0_real_real | -66.224 [-76.984, -56.633] | +0.219 [+0.185, +0.259] | +0.249 [+0.203, +0.302] | -2.955 [-3.695, -2.222] | -0.008 [-0.079, +0.064] |
| J1_ar_indep | -223.969 [-254.556, -195.248] | +0.552 [+0.488, +0.608] | +0.478 [+0.424, +0.531] | -3.791 [-4.487, -3.112] | -0.550 [-0.641, -0.457] |
| J2_ar_corr | -232.973 [-278.637, -195.322] | +0.445 [+0.396, +0.491] | +0.480 [+0.434, +0.523] | -3.912 [-4.655, -3.211] | -0.456 [-0.566, -0.357] |
| J3_joint_block | -30.527 [-44.764, -11.331] | +0.519 [+0.462, +0.573] | +0.269 [+0.205, +0.327] | +0.125 [-0.283, +0.552] | -0.066 [-0.122, -0.008] |
| M0_Rmatched_Rmatched | +11.025 [+7.922, +15.263] | -0.341 [-0.403, -0.282] | -0.182 [-0.227, -0.137] | +2.353 [+2.061, +2.655] | +0.465 [+0.407, +0.527] |
| R1_bias | +10.901 [+6.706, +16.006] | -0.030 [-0.093, +0.031] | -0.241 [-0.304, -0.180] | +2.944 [+2.500, +3.432] | +0.524 [+0.442, +0.619] |
| R2_ar0 | +10.970 [+1.958, +24.121] | -0.053 [-0.131, +0.021] | -0.186 [-0.257, -0.118] | +2.692 [+2.250, +3.165] | +0.471 [+0.373, +0.577] |
| R3_ar1 | -3.794 [-11.692, +2.732] | +0.088 [+0.024, +0.147] | -0.208 [-0.264, -0.155] | +2.753 [+2.396, +3.140] | +0.448 [+0.385, +0.517] |
| R4_iid | +10.110 [+7.379, +13.192] | -0.274 [-0.342, -0.207] | -0.265 [-0.315, -0.216] | +3.089 [+2.743, +3.453] | +0.514 [+0.443, +0.593] |
| R5_realdem | +3.288 [-4.965, +15.936] | +0.096 [+0.033, +0.160] | -0.080 [-0.138, -0.019] | +1.808 [+1.460, +2.163] | +0.276 [+0.208, +0.345] |
| R6_distbin | +4.422 [+2.160, +7.091] | -0.079 [-0.139, -0.017] | -0.217 [-0.278, -0.159] | +2.570 [+2.190, +2.973] | +0.456 [+0.388, +0.526] |
| R7_tapbin | +8.866 [+5.915, +12.256] | -0.056 [-0.128, +0.017] | -0.243 [-0.304, -0.181] | +2.963 [+2.526, +3.402] | +0.532 [+0.456, +0.616] |
| R8_real | +5.848 [+2.573, +9.523] | -0.143 [-0.215, -0.074] | -0.225 [-0.291, -0.164] | +2.843 [+2.398, +3.316] | +0.497 [+0.414, +0.588] |
| S1_bias | -21.182 [-26.925, -14.772] | +0.360 [+0.291, +0.425] | +0.091 [+0.035, +0.146] | +1.081 [+0.677, +1.509] | -0.025 [-0.094, +0.048] |
| S2_ar0 | -73.077 [-115.355, -22.040] | +0.454 [+0.395, +0.511] | +0.459 [+0.411, +0.506] | -2.737 [-3.246, -2.240] | -0.326 [-0.411, -0.247] |
| S3_ar1 | -193.304 [-225.280, -163.707] | +0.527 [+0.466, +0.587] | +0.483 [+0.424, +0.541] | -4.190 [-5.019, -3.408] | -0.544 [-0.637, -0.451] |
| S4_iid | -19.731 [-39.259, -5.286] | +0.260 [+0.202, +0.318] | +0.052 [+0.011, +0.091] | +0.878 [+0.593, +1.168] | +0.049 [+0.000, +0.097] |
| S5_iid0 | +5.685 [+3.082, +9.104] | -0.132 [-0.179, -0.088] | -0.096 [-0.127, -0.067] | +1.330 [+1.135, +1.527] | +0.193 [+0.153, +0.235] |
| S6_realdem | +24.532 [-3.886, +60.208] | +0.321 [+0.279, +0.362] | -0.040 [-0.075, -0.004] | +1.091 [+0.800, +1.395] | -0.334 [-0.372, -0.295] |
| S7_block | -27.554 [-38.189, -18.695] | +0.469 [+0.408, +0.530] | +0.298 [+0.246, +0.352] | -0.233 [-0.643, +0.169] | -0.098 [-0.157, -0.038] |
| S8_real | -70.904 [-78.079, -61.956] | +0.315 [+0.265, +0.365] | +0.263 [+0.215, +0.313] | -5.410 [-6.074, -4.725] | -0.288 [-0.334, -0.242] |
| W0_white_white | +11.665 [+8.370, +15.290] | -0.342 [-0.412, -0.272] | -0.231 [-0.280, -0.182] | +2.844 [+2.499, +3.197] | +0.536 [+0.464, +0.607] |

## Paired contrast F1-F0 (mean [95% CI], seeds paired, mean over drifts)

| arm | ΔNEES | Δpose cov95 | Δheading cov95 | Δheading RMSE ° | Δpos RMSE m |
|---|---|---|---|---|---|
| A0_real_real | +19.006 [-22.884, +72.615] | +0.066 [+0.042, +0.092] | +0.277 [+0.226, +0.330] | -3.419 [-4.297, -2.546] | -0.080 [-0.140, -0.017] |
| J1_ar_indep | -167.829 [-198.866, -136.936] | +0.126 [+0.099, +0.156] | +0.327 [+0.281, +0.373] | -2.696 [-3.373, -2.025] | -0.308 [-0.403, -0.214] |
| J2_ar_corr | -160.155 [-206.345, -120.890] | +0.078 [+0.049, +0.106] | +0.271 [+0.211, +0.330] | -1.929 [-2.823, -1.056] | -0.101 [-0.219, +0.013] |
| J3_joint_block | -10.224 [-17.959, -2.834] | +0.139 [+0.107, +0.170] | +0.234 [+0.182, +0.285] | +0.284 [-0.011, +0.570] | +0.062 [+0.018, +0.108] |
| M0_Rmatched_Rmatched | +13.692 [+9.644, +18.585] | -0.305 [-0.360, -0.253] | -0.213 [-0.270, -0.160] | +2.466 [+2.119, +2.865] | +0.369 [+0.305, +0.440] |
| R1_bias | +42.857 [+26.397, +65.311] | -0.300 [-0.332, -0.266] | -0.255 [-0.309, -0.202] | +2.944 [+2.582, +3.314] | +0.442 [+0.373, +0.520] |
| R2_ar0 | +31.297 [+23.327, +40.130] | -0.283 [-0.325, -0.244] | -0.249 [-0.313, -0.188] | +3.216 [+2.786, +3.692] | +0.514 [+0.428, +0.612] |
| R3_ar1 | +45.438 [+33.596, +59.904] | -0.188 [-0.212, -0.164] | -0.233 [-0.282, -0.188] | +3.148 [+2.771, +3.556] | +0.515 [+0.446, +0.588] |
| R4_iid | +21.789 [+16.120, +28.499] | -0.325 [-0.369, -0.283] | -0.201 [-0.255, -0.150] | +2.451 [+2.109, +2.832] | +0.358 [+0.303, +0.421] |
| R5_realdem | +24.420 [+14.548, +37.515] | -0.224 [-0.269, -0.179] | -0.189 [-0.246, -0.131] | +2.786 [+2.380, +3.217] | +0.422 [+0.350, +0.493] |
| R6_distbin | +26.221 [+16.397, +37.772] | -0.209 [-0.245, -0.173] | -0.228 [-0.290, -0.168] | +2.761 [+2.331, +3.218] | +0.398 [+0.320, +0.479] |
| R7_tapbin | +41.134 [+28.848, +56.141] | -0.271 [-0.312, -0.231] | -0.216 [-0.273, -0.161] | +2.763 [+2.315, +3.238] | +0.450 [+0.379, +0.529] |
| R8_real | +28.197 [+12.675, +55.157] | -0.216 [-0.260, -0.175] | -0.203 [-0.265, -0.143] | +2.604 [+2.187, +3.069] | +0.342 [+0.285, +0.406] |
| S1_bias | -12.116 [-24.802, +9.545] | +0.391 [+0.337, +0.444] | +0.070 [+0.011, +0.129] | +1.107 [+0.720, +1.510] | -0.178 [-0.239, -0.115] |
| S2_ar0 | -100.944 [-124.310, -79.154] | +0.460 [+0.399, +0.520] | +0.438 [+0.388, +0.488] | -2.834 [-3.337, -2.323] | -0.415 [-0.499, -0.331] |
| S3_ar1 | -185.537 [-219.077, -154.943] | +0.486 [+0.434, +0.534] | +0.448 [+0.397, +0.498] | -4.036 [-4.825, -3.291] | -0.595 [-0.686, -0.504] |
| S4_iid | -8.579 [-30.347, +13.761] | +0.203 [+0.141, +0.264] | +0.041 [+0.002, +0.077] | +0.887 [+0.628, +1.166] | +0.017 [-0.032, +0.066] |
| S5_iid0 | +7.286 [+5.061, +9.817] | -0.157 [-0.198, -0.117] | -0.096 [-0.121, -0.073] | +1.306 [+1.104, +1.504] | +0.141 [+0.106, +0.180] |
| S6_realdem | +291.008 [+1.711, +850.861] | +0.293 [+0.249, +0.341] | -0.015 [-0.053, +0.024] | +0.935 [+0.591, +1.287] | -0.366 [-0.406, -0.326] |
| S7_block | -0.271 [-30.729, +51.333] | +0.417 [+0.359, +0.475] | +0.294 [+0.240, +0.349] | -0.236 [-0.599, +0.120] | -0.125 [-0.179, -0.070] |
| S8_real | -56.188 [-66.602, -43.271] | +0.239 [+0.197, +0.287] | +0.267 [+0.218, +0.316] | -5.373 [-6.069, -4.665] | -0.271 [-0.308, -0.233] |
| W0_white_white | +22.970 [+15.345, +32.539] | -0.354 [-0.410, -0.297] | -0.251 [-0.311, -0.193] | +2.911 [+2.488, +3.358] | +0.450 [+0.379, +0.526] |

## Paired contrast F3-F0 (mean [95% CI], seeds paired, mean over drifts)

| arm | ΔNEES | Δpose cov95 | Δheading cov95 | Δheading RMSE ° | Δpos RMSE m |
|---|---|---|---|---|---|
| A0_real_real | +8033.063 [+163.901, +23308.795] | +0.458 [+0.408, +0.504] | +0.530 [+0.474, +0.581] | -7.051 [-7.560, -6.474] | -0.515 [-0.548, -0.477] |
| J1_ar_indep | +66.928 [-156.409, +449.336] | +0.181 [+0.127, +0.236] | +0.258 [+0.191, +0.326] | -1.852 [-2.687, -0.993] | -0.223 [-0.341, -0.103] |
| J2_ar_corr | -163.530 [-228.533, -94.019] | +0.179 [+0.130, +0.230] | +0.313 [+0.255, +0.374] | -2.713 [-3.588, -1.878] | -0.245 [-0.365, -0.121] |
| J3_joint_block | +517.895 [+7.472, +1484.668] | +0.225 [+0.179, +0.276] | +0.081 [+0.015, +0.145] | +0.749 [+0.340, +1.188] | +0.032 [-0.033, +0.095] |
| M0_Rmatched_Rmatched | +258.092 [+50.985, +627.501] | -0.708 [-0.762, -0.650] | -0.413 [-0.472, -0.354] | +4.458 [+3.823, +5.121] | +0.827 [+0.717, +0.947] |
| R1_bias | +100.278 [+37.449, +216.090] | -0.244 [-0.302, -0.188] | -0.355 [-0.414, -0.295] | +4.078 [+3.486, +4.700] | +0.797 [+0.670, +0.949] |
| R2_ar0 | +47.538 [+31.599, +66.758] | -0.258 [-0.332, -0.176] | -0.282 [-0.334, -0.226] | +3.667 [+3.136, +4.226] | +0.689 [+0.558, +0.827] |
| R3_ar1 | +75.707 [+40.688, +119.668] | -0.143 [-0.198, -0.085] | -0.324 [-0.375, -0.272] | +3.962 [+3.417, +4.581] | +0.730 [+0.605, +0.863] |
| R4_iid | +93.522 [+62.679, +132.138] | -0.477 [-0.544, -0.417] | -0.411 [-0.471, -0.353] | +4.730 [+4.091, +5.399] | +0.881 [+0.758, +1.003] |
| R5_realdem | +60.066 [+33.672, +96.362] | -0.147 [-0.219, -0.077] | -0.230 [-0.298, -0.167] | +3.546 [+2.886, +4.227] | +0.541 [+0.396, +0.704] |
| R6_distbin | +68.264 [+40.710, +102.462] | -0.312 [-0.367, -0.252] | -0.286 [-0.345, -0.228] | +3.500 [+3.020, +3.995] | +0.697 [+0.598, +0.802] |
| R7_tapbin | +96.532 [+50.625, +156.392] | -0.232 [-0.301, -0.167] | -0.306 [-0.362, -0.252] | +3.774 [+3.194, +4.398] | +0.696 [+0.579, +0.824] |
| R8_real | +78.599 [+47.426, +114.460] | -0.376 [-0.430, -0.324] | -0.345 [-0.403, -0.289] | +4.038 [+3.487, +4.638] | +0.805 [+0.677, +0.956] |
| S1_bias | +78.156 [+40.812, +119.976] | +0.154 [+0.090, +0.216] | -0.059 [-0.122, +0.002] | +2.885 [+2.203, +3.620] | +0.231 [+0.108, +0.371] |
| S2_ar0 | -39.829 [-79.362, +5.378] | +0.104 [+0.041, +0.171] | +0.246 [+0.180, +0.314] | -0.992 [-1.790, -0.199] | -0.060 [-0.187, +0.072] |
| S3_ar1 | -147.001 [-180.968, -113.151] | +0.197 [+0.141, +0.257] | +0.271 [+0.199, +0.344] | -2.010 [-3.060, -0.898] | -0.209 [-0.351, -0.061] |
| S4_iid | +152.204 [-11.170, +422.614] | +0.018 [-0.045, +0.079] | -0.030 [-0.086, +0.024] | +1.328 [+0.927, +1.756] | +0.132 [+0.058, +0.211] |
| S5_iid0 | +123.613 [+18.043, +276.478] | -0.391 [-0.459, -0.326] | -0.227 [-0.285, -0.173] | +2.261 [+1.858, +2.704] | +0.340 [+0.264, +0.428] |
| S6_realdem | +561.308 [+48.588, +1310.282] | +0.442 [+0.394, +0.485] | +0.150 [+0.112, +0.188] | -0.481 [-0.670, -0.282] | -0.465 [-0.493, -0.433] |
| S7_block | +104.243 [+7.430, +248.528] | +0.205 [+0.146, +0.266] | +0.145 [+0.074, +0.213] | +0.709 [+0.151, +1.316] | +0.028 [-0.055, +0.118] |
| S8_real | +365.618 [+156.628, +635.974] | +0.467 [+0.420, +0.509] | +0.529 [+0.477, +0.576] | -7.817 [-8.352, -7.251] | -0.536 [-0.563, -0.505] |
| W0_white_white | +97.825 [+66.958, +134.666] | -0.536 [-0.592, -0.482] | -0.349 [-0.402, -0.296] | +4.326 [+3.697, +4.993] | +0.780 [+0.658, +0.915] |

## Paired contrast F2acf-F0 (mean [95% CI], seeds paired, mean over drifts)

| arm | ΔNEES | Δpose cov95 | Δheading cov95 | Δheading RMSE ° | Δpos RMSE m |
|---|---|---|---|---|---|
| A0_real_real | -39.301 [-74.915, +14.419] | +0.169 [+0.144, +0.194] | +0.193 [+0.150, +0.237] | -3.663 [-4.185, -3.129] | -0.081 [-0.119, -0.042] |
| J1_ar_indep | -197.443 [-227.159, -169.071] | +0.277 [+0.233, +0.321] | +0.311 [+0.265, +0.359] | -2.685 [-3.252, -2.119] | -0.352 [-0.424, -0.284] |
| J2_ar_corr | -213.035 [-257.615, -175.663] | +0.266 [+0.228, +0.304] | +0.307 [+0.262, +0.352] | -2.764 [-3.442, -2.133] | -0.288 [-0.373, -0.212] |
| J3_joint_block | -33.006 [-40.621, -25.398] | +0.429 [+0.381, +0.478] | +0.262 [+0.211, +0.312] | -0.349 [-0.610, -0.077] | -0.104 [-0.143, -0.064] |
| M0_Rmatched_Rmatched | +9.530 [+6.605, +12.837] | -0.248 [-0.306, -0.193] | -0.133 [-0.182, -0.084] | +1.582 [+1.311, +1.876] | +0.345 [+0.285, +0.411] |
| R1_bias | +7.244 [+4.143, +10.710] | +0.089 [+0.031, +0.148] | -0.146 [-0.196, -0.098] | +1.666 [+1.385, +1.950] | +0.333 [+0.268, +0.399] |
| R2_ar0 | +2.466 [-2.136, +7.541] | +0.054 [-0.013, +0.118] | -0.098 [-0.153, -0.044] | +1.473 [+1.147, +1.853] | +0.297 [+0.216, +0.387] |
| R3_ar1 | -4.925 [-14.415, +2.952] | +0.138 [+0.061, +0.210] | -0.128 [-0.183, -0.077] | +1.606 [+1.266, +1.966] | +0.312 [+0.228, +0.402] |
| R4_iid | +12.200 [+5.164, +22.844] | -0.187 [-0.256, -0.123] | -0.182 [-0.226, -0.140] | +1.805 [+1.555, +2.068] | +0.379 [+0.322, +0.442] |
| R5_realdem | +2.276 [-4.004, +10.232] | +0.176 [+0.121, +0.228] | -0.041 [-0.096, +0.013] | +1.025 [+0.726, +1.346] | +0.156 [+0.093, +0.221] |
| R6_distbin | +6.436 [+2.582, +11.182] | -0.042 [-0.094, +0.007] | -0.147 [-0.192, -0.104] | +1.707 [+1.427, +2.010] | +0.370 [+0.302, +0.443] |
| R7_tapbin | +36.259 [+3.659, +93.159] | +0.067 [+0.012, +0.120] | -0.173 [-0.224, -0.123] | +1.778 [+1.502, +2.061] | +0.341 [+0.289, +0.397] |
| R8_real | +5.387 [+2.125, +9.022] | -0.096 [-0.147, -0.047] | -0.147 [-0.195, -0.102] | +1.607 [+1.325, +1.924] | +0.330 [+0.268, +0.400] |
| S1_bias | -23.796 [-30.219, -16.077] | +0.440 [+0.379, +0.501] | +0.096 [+0.041, +0.151] | +0.416 [+0.088, +0.769] | -0.190 [-0.254, -0.125] |
| S2_ar0 | -96.355 [-120.173, -73.643] | +0.424 [+0.377, +0.471] | +0.338 [+0.290, +0.382] | -2.235 [-2.687, -1.789] | -0.320 [-0.407, -0.237] |
| S3_ar1 | -178.218 [-208.032, -150.806] | +0.329 [+0.281, +0.374] | +0.289 [+0.246, +0.331] | -2.871 [-3.501, -2.263] | -0.400 [-0.475, -0.329] |
| S4_iid | -24.281 [-42.550, -11.693] | +0.307 [+0.248, +0.365] | +0.104 [+0.071, +0.139] | +0.154 [-0.073, +0.381] | -0.048 [-0.090, -0.003] |
| S5_iid0 | +2.197 [+0.268, +4.953] | -0.068 [-0.124, -0.017] | -0.020 [-0.040, -0.002] | +0.757 [+0.603, +0.918] | +0.121 [+0.077, +0.167] |
| S6_realdem | -20.383 [-21.765, -19.084] | +0.355 [+0.309, +0.401] | +0.018 [-0.019, +0.054] | -0.142 [-0.343, +0.055] | -0.318 [-0.351, -0.285] |
| S7_block | -7.674 [-24.576, +10.984] | +0.453 [+0.402, +0.504] | +0.260 [+0.218, +0.302] | -0.381 [-0.651, -0.108] | -0.139 [-0.184, -0.092] |
| S8_real | -70.202 [-85.790, -43.496] | +0.352 [+0.290, +0.412] | +0.326 [+0.264, +0.387] | -5.997 [-6.604, -5.366] | -0.292 [-0.337, -0.243] |
| W0_white_white | +10.616 [+6.645, +15.654] | -0.242 [-0.304, -0.182] | -0.165 [-0.214, -0.119] | +1.767 [+1.473, +2.098] | +0.401 [+0.335, +0.473] |

## Paired contrast F1acf-F0 (mean [95% CI], seeds paired, mean over drifts)

| arm | ΔNEES | Δpose cov95 | Δheading cov95 | Δheading RMSE ° | Δpos RMSE m |
|---|---|---|---|---|---|
| A0_real_real | -64.872 [-74.598, -56.934] | +0.038 [+0.025, +0.051] | +0.145 [+0.118, +0.173] | -4.008 [-4.430, -3.562] | -0.125 [-0.151, -0.096] |
| J1_ar_indep | -160.165 [-191.824, -129.284] | +0.084 [+0.064, +0.104] | +0.263 [+0.228, +0.301] | -2.369 [-3.006, -1.755] | -0.266 [-0.346, -0.186] |
| J2_ar_corr | -155.847 [-201.900, -111.758] | +0.072 [+0.053, +0.092] | +0.285 [+0.240, +0.331] | -2.599 [-3.288, -1.915] | -0.221 [-0.326, -0.119] |
| J3_joint_block | -15.974 [-23.604, -8.506] | +0.133 [+0.104, +0.162] | +0.226 [+0.171, +0.278] | -0.149 [-0.399, +0.104] | -0.012 [-0.046, +0.025] |
| M0_Rmatched_Rmatched | +9.293 [+5.517, +14.493] | -0.241 [-0.293, -0.192] | -0.156 [-0.207, -0.105] | +1.592 [+1.302, +1.887] | +0.279 [+0.228, +0.337] |
| R1_bias | +21.898 [+11.883, +34.289] | -0.198 [-0.231, -0.165] | -0.144 [-0.197, -0.094] | +1.478 [+1.149, +1.850] | +0.273 [+0.202, +0.358] |
| R2_ar0 | +23.239 [+14.754, +32.920] | -0.215 [-0.255, -0.178] | -0.186 [-0.242, -0.134] | +2.052 [+1.756, +2.384] | +0.370 [+0.294, +0.458] |
| R3_ar1 | +28.163 [+16.849, +42.522] | -0.149 [-0.176, -0.122] | -0.160 [-0.209, -0.112] | +1.778 [+1.487, +2.115] | +0.318 [+0.254, +0.389] |
| R4_iid | +17.903 [+10.303, +27.730] | -0.220 [-0.268, -0.172] | -0.138 [-0.184, -0.094] | +1.468 [+1.186, +1.782] | +0.253 [+0.194, +0.318] |
| R5_realdem | +10.635 [+5.329, +15.822] | -0.177 [-0.217, -0.137] | -0.140 [-0.193, -0.090] | +1.668 [+1.355, +2.004] | +0.302 [+0.244, +0.362] |
| R6_distbin | +10.098 [+6.973, +13.449] | -0.162 [-0.194, -0.129] | -0.137 [-0.188, -0.085] | +1.442 [+1.177, +1.699] | +0.270 [+0.216, +0.326] |
| R7_tapbin | +20.784 [+12.865, +30.648] | -0.197 [-0.228, -0.167] | -0.149 [-0.197, -0.104] | +1.448 [+1.166, +1.766] | +0.253 [+0.198, +0.317] |
| R8_real | +9.879 [+6.883, +13.200] | -0.177 [-0.214, -0.142] | -0.156 [-0.210, -0.107] | +1.571 [+1.288, +1.880] | +0.224 [+0.183, +0.267] |
| S1_bias | -14.642 [-21.322, -7.577] | +0.381 [+0.324, +0.437] | +0.048 [-0.011, +0.107] | +0.703 [+0.325, +1.077] | -0.192 [-0.254, -0.130] |
| S2_ar0 | -96.345 [-117.393, -77.077] | +0.389 [+0.345, +0.432] | +0.348 [+0.308, +0.388] | -2.397 [-2.786, -2.016] | -0.356 [-0.421, -0.294] |
| S3_ar1 | -159.101 [-190.786, -128.284] | +0.276 [+0.230, +0.323] | +0.248 [+0.209, +0.291] | -2.628 [-3.262, -2.010] | -0.414 [-0.480, -0.348] |
| S4_iid | -23.030 [-41.862, -9.586] | +0.308 [+0.255, +0.361] | +0.102 [+0.067, +0.136] | +0.077 [-0.136, +0.302] | -0.118 [-0.157, -0.078] |
| S5_iid0 | +2.354 [+1.070, +3.847] | -0.092 [-0.136, -0.051] | -0.029 [-0.051, -0.010] | +0.610 [+0.462, +0.760] | +0.062 [+0.026, +0.102] |
| S6_realdem | -18.706 [-19.889, -17.593] | +0.338 [+0.296, +0.381] | +0.044 [+0.008, +0.080] | -0.302 [-0.508, -0.093] | -0.392 [-0.423, -0.362] |
| S7_block | -0.932 [-22.110, +25.126] | +0.361 [+0.305, +0.416] | +0.250 [+0.208, +0.292] | -0.293 [-0.572, -0.021] | -0.127 [-0.167, -0.086] |
| S8_real | -63.791 [-77.380, -45.916] | +0.264 [+0.218, +0.312] | +0.329 [+0.274, +0.384] | -6.023 [-6.534, -5.473] | -0.276 [-0.312, -0.238] |
| W0_white_white | +11.532 [+7.047, +16.920] | -0.256 [-0.307, -0.206] | -0.143 [-0.198, -0.092] | +1.533 [+1.230, +1.853] | +0.292 [+0.236, +0.353] |
