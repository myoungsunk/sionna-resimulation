# Delta-s usage map (machine summary)

```json
{
  "A_R2_pose_median": {
    "d_mp_r": {
      "DS": 0.154,
      "EXIST": 0.481,
      "EXIST_DS": 0.521,
      "HGB_EXIST_DS": 0.578,
      "POWER1_MU": NaN
    },
    "d_mp_s": {
      "DS": 0.407,
      "EXIST": 0.009,
      "EXIST_DS": 0.265,
      "HGB_EXIST_DS": 0.518,
      "POWER1_MU": NaN
    },
    "e_r": {
      "DS": 0.151,
      "EXIST": 0.559,
      "EXIST_DS": 0.604,
      "HGB_EXIST_DS": 0.66,
      "POWER1_MU": 0.197
    },
    "e_s": {
      "DS": 0.407,
      "EXIST": 0.009,
      "EXIST_DS": 0.265,
      "HGB_EXIST_DS": 0.518,
      "POWER1_MU": 0.019
    }
  },
  "A_R2_LF_median": {
    "e_r": {
      "DS": 0.296,
      "EXIST": 0.59,
      "EXIST_DS": 0.643,
      "HGB_EXIST_DS": 0.736,
      "POWER1_MU": 0.368
    },
    "e_s": {
      "DS": 0.304,
      "EXIST": 0.127,
      "EXIST_DS": 0.335,
      "HGB_EXIST_DS": 0.583,
      "POWER1_MU": 0.028
    }
  },
  "B_spearman_median": {
    "|e_r|": {
      "DSA": 0.378,
      "EXIST": 0.382,
      "EXIST_DSA": 0.431,
      "POWER1_V": 0.24
    },
    "|e_s|": {
      "DSA": 0.574,
      "EXIST": 0.734,
      "EXIST_DSA": 0.735,
      "POWER1_V": 0.546
    }
  },
  "C_auc_median": {
    "contam": {
      "DS": NaN,
      "DSA": 0.769,
      "EXIST": 0.871,
      "EXIST_DS": NaN,
      "EXIST_DSA": 0.877,
      "RAW_|ds+1|_no_training": 0.754
    },
    "outlier_s": {
      "DS": NaN,
      "DSA": 0.815,
      "EXIST": 0.872,
      "EXIST_DS": NaN,
      "EXIST_DSA": 0.876,
      "RAW_|ds+1|_no_training": 0.809
    },
    "rs_same_sign": {
      "DS": 0.642,
      "DSA": NaN,
      "EXIST": 0.538,
      "EXIST_DS": 0.649,
      "EXIST_DSA": NaN,
      "RAW_|ds+1|_no_training": NaN
    }
  },
  "D_median": {
    "R2_ds1_on_hs_g": 0.028,
    "corr_ds1_g": -0.106,
    "corr_ds1_hs": -0.086,
    "corr_e_s_g": -0.061
  },
  "E_tau_median": {
    "ds_+1": 1.65,
    "ds_+4": 1.37,
    "e_r": 14.73,
    "e_s": 2.97
  },
  "F": [
    {
      "case": "R2_aA_m0",
      "median_abs_ds1_full": 0.0174,
      "median_abs_ds1_los": 0.0072,
      "frac_abs_ds1_gt_0.01_full": 0.6562,
      "frac_abs_ds1_gt_0.01_los": 0.4589
    },
    {
      "case": "R2_aA_m45",
      "median_abs_ds1_full": 0.0274,
      "median_abs_ds1_los": 0.0107,
      "frac_abs_ds1_gt_0.01_full": 0.8089,
      "frac_abs_ds1_gt_0.01_los": 0.5019
    },
    {
      "case": "R2_aB_m0",
      "median_abs_ds1_full": 0.0155,
      "median_abs_ds1_los": 0.0082,
      "frac_abs_ds1_gt_0.01_full": 0.6255,
      "frac_abs_ds1_gt_0.01_los": 0.4651
    },
    {
      "case": "R4_aA_m0",
      "median_abs_ds1_full": 0.0214,
      "median_abs_ds1_los": 0.0064,
      "frac_abs_ds1_gt_0.01_full": 0.6909,
      "frac_abs_ds1_gt_0.01_los": 0.4132
    },
    {
      "case": "R4_aB_m0",
      "median_abs_ds1_full": 0.0255,
      "median_abs_ds1_los": 0.0129,
      "frac_abs_ds1_gt_0.01_full": 0.7484,
      "frac_abs_ds1_gt_0.01_los": 0.5846
    },
    {
      "case": "R5_aA_m0",
      "median_abs_ds1_full": 0.0164,
      "median_abs_ds1_los": 0.0047,
      "frac_abs_ds1_gt_0.01_full": 0.6426,
      "frac_abs_ds1_gt_0.01_los": 0.3691
    },
    {
      "case": "R5_aB_m0",
      "median_abs_ds1_full": 0.0149,
      "median_abs_ds1_los": 0.0052,
      "frac_abs_ds1_gt_0.01_full": 0.6006,
      "frac_abs_ds1_gt_0.01_los": 0.3882
    }
  ]
}
```

## A
| case      | target   | model        |   R2_nc_pose |   R2_nc_LF |
|:----------|:---------|:-------------|-------------:|-----------:|
| R2_aA_m0  | e_s      | EXIST        |        0.197 |      0.245 |
| R2_aA_m45 | e_s      | EXIST        |        0.093 |      0.127 |
| R2_aB_m0  | e_s      | EXIST        |        0.009 |      0.127 |
| R2_aA_m0  | e_s      | DS           |        0.333 |      0.409 |
| R2_aA_m45 | e_s      | DS           |        0.407 |      0.459 |
| R2_aB_m0  | e_s      | DS           |        0.291 |      0.304 |
| R2_aA_m0  | e_s      | EXIST_DS     |        0.501 |      0.542 |
| R2_aA_m45 | e_s      | EXIST_DS     |        0.482 |      0.523 |
| R2_aB_m0  | e_s      | EXIST_DS     |        0.256 |      0.261 |
| R2_aA_m0  | e_s      | HGB_EXIST_DS |        0.66  |      0.709 |
| R2_aA_m45 | e_s      | HGB_EXIST_DS |        0.589 |      0.661 |
| R2_aB_m0  | e_s      | HGB_EXIST_DS |        0.495 |      0.583 |
| R2_aA_m0  | e_s      | POWER1_MU    |        0.073 |      0.127 |
| R2_aA_m45 | e_s      | POWER1_MU    |       -0.008 |     -0.003 |
| R2_aB_m0  | e_s      | POWER1_MU    |        0.088 |      0.135 |
| R2_aA_m0  | d_mp_s   | EXIST        |        0.197 |    nan     |
| R2_aA_m45 | d_mp_s   | EXIST        |        0.093 |    nan     |
| R2_aB_m0  | d_mp_s   | EXIST        |        0.009 |    nan     |
| R2_aA_m0  | d_mp_s   | DS           |        0.333 |    nan     |
| R2_aA_m45 | d_mp_s   | DS           |        0.407 |    nan     |
| R2_aB_m0  | d_mp_s   | DS           |        0.291 |    nan     |
| R2_aA_m0  | d_mp_s   | EXIST_DS     |        0.501 |    nan     |
| R2_aA_m45 | d_mp_s   | EXIST_DS     |        0.482 |    nan     |
| R2_aB_m0  | d_mp_s   | EXIST_DS     |        0.256 |    nan     |
| R2_aA_m0  | d_mp_s   | HGB_EXIST_DS |        0.66  |    nan     |
| R2_aA_m45 | d_mp_s   | HGB_EXIST_DS |        0.589 |    nan     |
| R2_aB_m0  | d_mp_s   | HGB_EXIST_DS |        0.495 |    nan     |
| R2_aA_m0  | e_r      | EXIST        |        0.596 |      0.514 |
| R2_aA_m45 | e_r      | EXIST        |        0.559 |      0.59  |
| R2_aB_m0  | e_r      | EXIST        |        0.535 |      0.55  |
| R2_aA_m0  | e_r      | DS           |        0.146 |      0.242 |
| R2_aA_m45 | e_r      | DS           |       -0.004 |      0.296 |
| R2_aB_m0  | e_r      | DS           |        0.3   |      0.383 |
| R2_aA_m0  | e_r      | EXIST_DS     |        0.678 |      0.643 |
| R2_aA_m45 | e_r      | EXIST_DS     |        0.522 |      0.535 |
| R2_aB_m0  | e_r      | EXIST_DS     |        0.613 |      0.634 |
| R2_aA_m0  | e_r      | HGB_EXIST_DS |        0.706 |      0.647 |
| R2_aA_m45 | e_r      | HGB_EXIST_DS |        0.628 |      0.673 |
| R2_aB_m0  | e_r      | HGB_EXIST_DS |        0.719 |      0.677 |
| R2_aA_m0  | e_r      | POWER1_MU    |        0.218 |      0.368 |
| R2_aA_m45 | e_r      | POWER1_MU    |        0.285 |      0.425 |
| R2_aB_m0  | e_r      | POWER1_MU    |        0.103 |      0.179 |
| R2_aA_m0  | d_mp_r   | EXIST        |        0.544 |    nan     |
| R2_aA_m45 | d_mp_r   | EXIST        |        0.551 |    nan     |
| R2_aB_m0  | d_mp_r   | EXIST        |        0.337 |    nan     |
| R2_aA_m0  | d_mp_r   | DS           |        0.151 |    nan     |
| R2_aA_m45 | d_mp_r   | DS           |        0.069 |    nan     |
| R2_aB_m0  | d_mp_r   | DS           |        0.273 |    nan     |
| R2_aA_m0  | d_mp_r   | EXIST_DS     |        0.617 |    nan     |
| R2_aA_m45 | d_mp_r   | EXIST_DS     |        0.521 |    nan     |
| R2_aB_m0  | d_mp_r   | EXIST_DS     |        0.436 |    nan     |
| R2_aA_m0  | d_mp_r   | HGB_EXIST_DS |        0.656 |    nan     |
| R2_aA_m45 | d_mp_r   | HGB_EXIST_DS |        0.614 |    nan     |
| R2_aB_m0  | d_mp_r   | HGB_EXIST_DS |        0.578 |    nan     |
| R4_aA_m0  | e_s      | EXIST        |       -0.288 |     -0.518 |
| R4_aB_m0  | e_s      | EXIST        |       -0.509 |     -0.382 |
| R4_aA_m0  | e_s      | DS           |        0.42  |      0.262 |
| R4_aB_m0  | e_s      | DS           |        0.457 |      0.322 |
| R4_aA_m0  | e_s      | EXIST_DS     |        0.256 |      0.037 |
| R4_aB_m0  | e_s      | EXIST_DS     |        0.265 |      0.335 |
| R4_aA_m0  | e_s      | HGB_EXIST_DS |        0.266 |      0.319 |
| R4_aB_m0  | e_s      | HGB_EXIST_DS |        0.514 |      0.523 |
| R4_aA_m0  | e_s      | POWER1_MU    |       -0.152 |     -0.429 |
| R4_aB_m0  | e_s      | POWER1_MU    |       -0.05  |     -0.06  |
| R4_aA_m0  | d_mp_s   | EXIST        |       -0.288 |    nan     |
| R4_aB_m0  | d_mp_s   | EXIST        |       -0.509 |    nan     |
| R4_aA_m0  | d_mp_s   | DS           |        0.42  |    nan     |
| R4_aB_m0  | d_mp_s   | DS           |        0.457 |    nan     |
| R4_aA_m0  | d_mp_s   | EXIST_DS     |        0.256 |    nan     |
| R4_aB_m0  | d_mp_s   | EXIST_DS     |        0.265 |    nan     |
| R4_aA_m0  | d_mp_s   | HGB_EXIST_DS |        0.266 |    nan     |
| R4_aB_m0  | d_mp_s   | HGB_EXIST_DS |        0.514 |    nan     |
| R4_aA_m0  | e_r      | EXIST        |        0.499 |      0.722 |
| R4_aB_m0  | e_r      | EXIST        |        0.459 |      0.846 |
| R4_aA_m0  | e_r      | DS           |        0.17  |      0.434 |
| R4_aB_m0  | e_r      | DS           |        0.134 |      0.344 |
| R4_aA_m0  | e_r      | EXIST_DS     |        0.555 |      0.758 |
| R4_aB_m0  | e_r      | EXIST_DS     |        0.422 |      0.827 |
| R4_aA_m0  | e_r      | HGB_EXIST_DS |        0.538 |      0.834 |
| R4_aB_m0  | e_r      | HGB_EXIST_DS |        0.638 |      0.898 |
| R4_aA_m0  | e_r      | POWER1_MU    |        0.259 |      0.599 |
| R4_aB_m0  | e_r      | POWER1_MU    |        0.197 |      0.62  |
| R4_aA_m0  | d_mp_r   | EXIST        |        0.387 |    nan     |
| R4_aB_m0  | d_mp_r   | EXIST        |        0.326 |    nan     |
| R4_aA_m0  | d_mp_r   | DS           |        0.152 |    nan     |
| R4_aB_m0  | d_mp_r   | DS           |        0.155 |    nan     |
| R4_aA_m0  | d_mp_r   | EXIST_DS     |        0.449 |    nan     |
| R4_aB_m0  | d_mp_r   | EXIST_DS     |        0.309 |    nan     |
| R4_aA_m0  | d_mp_r   | HGB_EXIST_DS |        0.453 |    nan     |
| R4_aB_m0  | d_mp_r   | HGB_EXIST_DS |        0.517 |    nan     |
| R5_aA_m0  | e_s      | EXIST        |        0.249 |      0.299 |
| R5_aB_m0  | e_s      | EXIST        |       -0.384 |      0.092 |
| R5_aA_m0  | e_s      | DS           |        0.269 |      0.267 |
| R5_aB_m0  | e_s      | DS           |        0.416 |      0.274 |
| R5_aA_m0  | e_s      | EXIST_DS     |        0.446 |      0.494 |
| R5_aB_m0  | e_s      | EXIST_DS     |        0.197 |      0.234 |
| R5_aA_m0  | e_s      | HGB_EXIST_DS |        0.586 |      0.611 |
| R5_aB_m0  | e_s      | HGB_EXIST_DS |        0.518 |      0.463 |
| R5_aA_m0  | e_s      | POWER1_MU    |        0.019 |      0.028 |
| R5_aB_m0  | e_s      | POWER1_MU    |        0.035 |      0.063 |
| R5_aA_m0  | d_mp_s   | EXIST        |        0.249 |    nan     |
| R5_aB_m0  | d_mp_s   | EXIST        |       -0.384 |    nan     |
| R5_aA_m0  | d_mp_s   | DS           |        0.269 |    nan     |
| R5_aB_m0  | d_mp_s   | DS           |        0.416 |    nan     |
| R5_aA_m0  | d_mp_s   | EXIST_DS     |        0.446 |    nan     |
| R5_aB_m0  | d_mp_s   | EXIST_DS     |        0.197 |    nan     |
| R5_aA_m0  | d_mp_s   | HGB_EXIST_DS |        0.586 |    nan     |
| R5_aB_m0  | d_mp_s   | HGB_EXIST_DS |        0.518 |    nan     |
| R5_aA_m0  | e_r      | EXIST        |        0.588 |      0.638 |
| R5_aB_m0  | e_r      | EXIST        |        0.574 |      0.549 |
| R5_aA_m0  | e_r      | DS           |        0.183 |      0.234 |
| R5_aB_m0  | e_r      | DS           |        0.151 |      0.24  |
| R5_aA_m0  | e_r      | EXIST_DS     |        0.604 |      0.678 |
| R5_aB_m0  | e_r      | EXIST_DS     |        0.634 |      0.622 |
| R5_aA_m0  | e_r      | HGB_EXIST_DS |        0.715 |      0.764 |
| R5_aB_m0  | e_r      | HGB_EXIST_DS |        0.66  |      0.736 |
| R5_aA_m0  | e_r      | POWER1_MU    |        0.163 |      0.297 |
| R5_aB_m0  | e_r      | POWER1_MU    |        0.093 |      0.253 |
| R5_aA_m0  | d_mp_r   | EXIST        |        0.527 |    nan     |
| R5_aB_m0  | d_mp_r   | EXIST        |        0.481 |    nan     |
| R5_aA_m0  | d_mp_r   | DS           |        0.199 |    nan     |
| R5_aB_m0  | d_mp_r   | DS           |        0.154 |    nan     |
| R5_aA_m0  | d_mp_r   | EXIST_DS     |        0.543 |    nan     |
| R5_aB_m0  | d_mp_r   | EXIST_DS     |        0.538 |    nan     |
| R5_aA_m0  | d_mp_r   | HGB_EXIST_DS |        0.674 |    nan     |
| R5_aB_m0  | d_mp_r   | HGB_EXIST_DS |        0.558 |    nan     |

## B
| case      | target   | model     |   spearman |
|:----------|:---------|:----------|-----------:|
| R2_aA_m0  | |e_s|    | EXIST     |      0.748 |
| R2_aA_m45 | |e_s|    | EXIST     |      0.734 |
| R2_aB_m0  | |e_s|    | EXIST     |      0.676 |
| R2_aA_m0  | |e_s|    | DSA       |      0.527 |
| R2_aA_m45 | |e_s|    | DSA       |      0.47  |
| R2_aB_m0  | |e_s|    | DSA       |      0.418 |
| R2_aA_m0  | |e_s|    | EXIST_DSA |      0.752 |
| R2_aA_m45 | |e_s|    | EXIST_DSA |      0.728 |
| R2_aB_m0  | |e_s|    | EXIST_DSA |      0.685 |
| R2_aA_m0  | |e_s|    | POWER1_V  |      0.546 |
| R2_aA_m45 | |e_s|    | POWER1_V  |      0.603 |
| R2_aB_m0  | |e_s|    | POWER1_V  |      0.451 |
| R2_aA_m0  | |e_r|    | EXIST     |      0.29  |
| R2_aA_m45 | |e_r|    | EXIST     |      0.464 |
| R2_aB_m0  | |e_r|    | EXIST     |      0.358 |
| R2_aA_m0  | |e_r|    | DSA       |      0.341 |
| R2_aA_m45 | |e_r|    | DSA       |      0.396 |
| R2_aB_m0  | |e_r|    | DSA       |      0.321 |
| R2_aA_m0  | |e_r|    | EXIST_DSA |      0.373 |
| R2_aA_m45 | |e_r|    | EXIST_DSA |      0.501 |
| R2_aB_m0  | |e_r|    | EXIST_DSA |      0.412 |
| R2_aA_m0  | |e_r|    | POWER1_V  |      0.24  |
| R2_aA_m45 | |e_r|    | POWER1_V  |      0.335 |
| R2_aB_m0  | |e_r|    | POWER1_V  |      0.162 |
| R4_aA_m0  | |e_s|    | EXIST     |      0.734 |
| R4_aB_m0  | |e_s|    | EXIST     |      0.689 |
| R4_aA_m0  | |e_s|    | DSA       |      0.632 |
| R4_aB_m0  | |e_s|    | DSA       |      0.593 |
| R4_aA_m0  | |e_s|    | EXIST_DSA |      0.735 |
| R4_aB_m0  | |e_s|    | EXIST_DSA |      0.706 |
| R4_aA_m0  | |e_s|    | POWER1_V  |      0.631 |
| R4_aB_m0  | |e_s|    | POWER1_V  |      0.486 |
| R4_aA_m0  | |e_r|    | EXIST     |      0.433 |
| R4_aB_m0  | |e_r|    | EXIST     |      0.382 |
| R4_aA_m0  | |e_r|    | DSA       |      0.424 |
| R4_aB_m0  | |e_r|    | DSA       |      0.378 |
| R4_aA_m0  | |e_r|    | EXIST_DSA |      0.525 |
| R4_aB_m0  | |e_r|    | EXIST_DSA |      0.409 |
| R4_aA_m0  | |e_r|    | POWER1_V  |      0.431 |
| R4_aB_m0  | |e_r|    | POWER1_V  |      0.162 |
| R5_aA_m0  | |e_s|    | EXIST     |      0.794 |
| R5_aB_m0  | |e_s|    | EXIST     |      0.734 |
| R5_aA_m0  | |e_s|    | DSA       |      0.58  |
| R5_aB_m0  | |e_s|    | DSA       |      0.574 |
| R5_aA_m0  | |e_s|    | EXIST_DSA |      0.805 |
| R5_aB_m0  | |e_s|    | EXIST_DSA |      0.737 |
| R5_aA_m0  | |e_s|    | POWER1_V  |      0.604 |
| R5_aB_m0  | |e_s|    | POWER1_V  |      0.465 |
| R5_aA_m0  | |e_r|    | EXIST     |      0.435 |
| R5_aB_m0  | |e_r|    | EXIST     |      0.377 |
| R5_aA_m0  | |e_r|    | DSA       |      0.387 |
| R5_aB_m0  | |e_r|    | DSA       |      0.377 |
| R5_aA_m0  | |e_r|    | EXIST_DSA |      0.499 |
| R5_aB_m0  | |e_r|    | EXIST_DSA |      0.431 |
| R5_aA_m0  | |e_r|    | POWER1_V  |      0.293 |
| R5_aB_m0  | |e_r|    | POWER1_V  |      0.216 |

## C
| case      | label        | model                  |   auc |   prevalence |
|:----------|:-------------|:-----------------------|------:|-------------:|
| R2_aA_m0  | contam       | EXIST                  | 0.885 |        0.421 |
| R2_aA_m45 | contam       | EXIST                  | 0.859 |        0.553 |
| R2_aB_m0  | contam       | EXIST                  | 0.867 |        0.354 |
| R2_aA_m0  | contam       | DSA                    | 0.769 |        0.421 |
| R2_aA_m45 | contam       | DSA                    | 0.71  |        0.553 |
| R2_aB_m0  | contam       | DSA                    | 0.75  |        0.354 |
| R2_aA_m0  | contam       | EXIST_DSA              | 0.888 |        0.421 |
| R2_aA_m45 | contam       | EXIST_DSA              | 0.855 |        0.553 |
| R2_aB_m0  | contam       | EXIST_DSA              | 0.877 |        0.354 |
| R2_aA_m0  | contam       | RAW_|ds+1|_no_training | 0.783 |        0.421 |
| R2_aA_m45 | contam       | RAW_|ds+1|_no_training | 0.715 |        0.553 |
| R2_aB_m0  | contam       | RAW_|ds+1|_no_training | 0.737 |        0.354 |
| R2_aA_m0  | outlier_s    | EXIST                  | 0.933 |        0.047 |
| R2_aA_m45 | outlier_s    | EXIST                  | 0.79  |        0.107 |
| R2_aB_m0  | outlier_s    | EXIST                  | 0.872 |        0.031 |
| R2_aA_m0  | outlier_s    | DSA                    | 0.915 |        0.047 |
| R2_aA_m45 | outlier_s    | DSA                    | 0.786 |        0.107 |
| R2_aB_m0  | outlier_s    | DSA                    | 0.731 |        0.031 |
| R2_aA_m0  | outlier_s    | EXIST_DSA              | 0.939 |        0.047 |
| R2_aA_m45 | outlier_s    | EXIST_DSA              | 0.799 |        0.107 |
| R2_aB_m0  | outlier_s    | EXIST_DSA              | 0.876 |        0.031 |
| R2_aA_m0  | outlier_s    | RAW_|ds+1|_no_training | 0.926 |        0.047 |
| R2_aA_m45 | outlier_s    | RAW_|ds+1|_no_training | 0.806 |        0.107 |
| R2_aB_m0  | outlier_s    | RAW_|ds+1|_no_training | 0.794 |        0.031 |
| R2_aA_m0  | rs_same_sign | EXIST                  | 0.585 |        0.583 |
| R2_aA_m45 | rs_same_sign | EXIST                  | 0.559 |        0.493 |
| R2_aB_m0  | rs_same_sign | EXIST                  | 0.516 |        0.53  |
| R2_aA_m0  | rs_same_sign | DS                     | 0.657 |        0.583 |
| R2_aA_m45 | rs_same_sign | DS                     | 0.714 |        0.493 |
| R2_aB_m0  | rs_same_sign | DS                     | 0.621 |        0.53  |
| R2_aA_m0  | rs_same_sign | EXIST_DS               | 0.667 |        0.583 |
| R2_aA_m45 | rs_same_sign | EXIST_DS               | 0.706 |        0.493 |
| R2_aB_m0  | rs_same_sign | EXIST_DS               | 0.626 |        0.53  |
| R4_aA_m0  | contam       | EXIST                  | 0.871 |        0.514 |
| R4_aB_m0  | contam       | EXIST                  | 0.82  |        0.475 |
| R4_aA_m0  | contam       | DSA                    | 0.776 |        0.514 |
| R4_aB_m0  | contam       | DSA                    | 0.76  |        0.475 |
| R4_aA_m0  | contam       | EXIST_DSA              | 0.868 |        0.514 |
| R4_aB_m0  | contam       | EXIST_DSA              | 0.826 |        0.475 |
| R4_aA_m0  | contam       | RAW_|ds+1|_no_training | 0.743 |        0.514 |
| R4_aB_m0  | contam       | RAW_|ds+1|_no_training | 0.754 |        0.475 |
| R4_aA_m0  | outlier_s    | EXIST                  | 0.823 |        0.085 |
| R4_aB_m0  | outlier_s    | EXIST                  | 0.792 |        0.077 |
| R4_aA_m0  | outlier_s    | DSA                    | 0.815 |        0.085 |
| R4_aB_m0  | outlier_s    | DSA                    | 0.813 |        0.077 |
| R4_aA_m0  | outlier_s    | EXIST_DSA              | 0.847 |        0.085 |
| R4_aB_m0  | outlier_s    | EXIST_DSA              | 0.81  |        0.077 |
| R4_aA_m0  | outlier_s    | RAW_|ds+1|_no_training | 0.776 |        0.085 |
| R4_aB_m0  | outlier_s    | RAW_|ds+1|_no_training | 0.809 |        0.077 |
| R4_aA_m0  | rs_same_sign | EXIST                  | 0.528 |        0.465 |
| R4_aB_m0  | rs_same_sign | EXIST                  | 0.522 |        0.452 |
| R4_aA_m0  | rs_same_sign | DS                     | 0.679 |        0.465 |
| R4_aB_m0  | rs_same_sign | DS                     | 0.632 |        0.452 |
| R4_aA_m0  | rs_same_sign | EXIST_DS               | 0.686 |        0.465 |
| R4_aB_m0  | rs_same_sign | EXIST_DS               | 0.636 |        0.452 |
| R5_aA_m0  | contam       | EXIST                  | 0.915 |        0.391 |
| R5_aB_m0  | contam       | EXIST                  | 0.887 |        0.297 |
| R5_aA_m0  | contam       | DSA                    | 0.821 |        0.391 |
| R5_aB_m0  | contam       | DSA                    | 0.818 |        0.297 |
| R5_aA_m0  | contam       | EXIST_DSA              | 0.922 |        0.391 |
| R5_aB_m0  | contam       | EXIST_DSA              | 0.891 |        0.297 |
| R5_aA_m0  | contam       | RAW_|ds+1|_no_training | 0.786 |        0.391 |
| R5_aB_m0  | contam       | RAW_|ds+1|_no_training | 0.811 |        0.297 |
| R5_aA_m0  | outlier_s    | EXIST                  | 0.968 |        0.044 |
| R5_aB_m0  | outlier_s    | EXIST                  | 0.991 |        0.024 |
| R5_aA_m0  | outlier_s    | DSA                    | 0.96  |        0.044 |
| R5_aB_m0  | outlier_s    | DSA                    | 0.965 |        0.024 |
| R5_aA_m0  | outlier_s    | EXIST_DSA              | 0.97  |        0.044 |
| R5_aB_m0  | outlier_s    | EXIST_DSA              | 0.986 |        0.024 |
| R5_aA_m0  | outlier_s    | RAW_|ds+1|_no_training | 0.933 |        0.044 |
| R5_aB_m0  | outlier_s    | RAW_|ds+1|_no_training | 0.981 |        0.024 |
| R5_aA_m0  | rs_same_sign | EXIST                  | 0.583 |        0.583 |
| R5_aB_m0  | rs_same_sign | EXIST                  | 0.538 |        0.563 |
| R5_aA_m0  | rs_same_sign | DS                     | 0.586 |        0.583 |
| R5_aB_m0  | rs_same_sign | DS                     | 0.642 |        0.563 |
| R5_aA_m0  | rs_same_sign | EXIST_DS               | 0.615 |        0.583 |
| R5_aB_m0  | rs_same_sign | EXIST_DS               | 0.649 |        0.563 |

## D
| case      |   R2_ds1_on_hs_g |   corr_ds1_g |   corr_ds1_hs |   corr_e_s_g |
|:----------|-----------------:|-------------:|--------------:|-------------:|
| R2_aA_m0  |            0.019 |       -0.123 |         0.003 |       -0.131 |
| R2_aA_m45 |            0.075 |       -0.116 |        -0.258 |       -0.061 |
| R2_aB_m0  |            0.028 |       -0.106 |        -0.125 |       -0.084 |
| R4_aA_m0  |            0.117 |       -0.021 |        -0.308 |        0.161 |
| R4_aB_m0  |            0.018 |       -0.086 |        -0.086 |       -0.03  |
| R5_aA_m0  |            0.007 |        0.01  |        -0.079 |        0.008 |
| R5_aB_m0  |            0.041 |       -0.188 |        -0.058 |       -0.235 |

## E
| case      | series   |   tau_int_s |   lag1 |   acf_2s |
|:----------|:---------|------------:|-------:|---------:|
| R2_aA_m0  | ds_+1    |       3.469 |  0.913 |    0.347 |
| R2_aA_m0  | ds_+4    |       6.046 |  0.91  |    0.216 |
| R2_aA_m0  | e_s      |       2.157 |  0.932 |    0.06  |
| R2_aA_m0  | e_r      |      23.842 |  0.819 |    0.482 |
| R2_aA_m45 | ds_+1    |       1.65  |  0.911 |   -0.003 |
| R2_aA_m45 | ds_+4    |       1.371 |  0.865 |   -0.009 |
| R2_aA_m45 | e_s      |       2.967 |  0.953 |    0.268 |
| R2_aA_m45 | e_r      |      31.107 |  0.885 |    0.606 |
| R2_aB_m0  | ds_+1    |       1.296 |  0.813 |   -0.059 |
| R2_aB_m0  | ds_+4    |       1.292 |  0.836 |   -0.009 |
| R2_aB_m0  | e_s      |       6.825 |  0.875 |    0.305 |
| R2_aB_m0  | e_r      |       5.086 |  0.553 |    0.148 |
| R4_aA_m0  | ds_+1    |       0.802 |  0.509 |    0.025 |
| R4_aA_m0  | ds_+4    |       1.138 |  0.557 |    0.079 |
| R4_aA_m0  | e_s      |       0.767 |  0.782 |    0.266 |
| R4_aA_m0  | e_r      |      21.576 |  0.642 |    0.446 |
| R4_aB_m0  | ds_+1    |       0.678 |  0.559 |   -0.032 |
| R4_aB_m0  | ds_+4    |       0.722 |  0.541 |   -0.039 |
| R4_aB_m0  | e_s      |       1.289 |  0.739 |    0.043 |
| R4_aB_m0  | e_r      |      13.875 |  0.586 |    0.309 |
| R5_aA_m0  | ds_+1    |       1.902 |  0.866 |    0.134 |
| R5_aA_m0  | ds_+4    |       2.57  |  0.859 |    0.239 |
| R5_aA_m0  | e_s      |       6.42  |  0.953 |    0.575 |
| R5_aA_m0  | e_r      |      14.733 |  0.851 |    0.293 |
| R5_aB_m0  | ds_+1    |       2.001 |  0.835 |    0.112 |
| R5_aB_m0  | ds_+4    |       2.277 |  0.838 |    0.127 |
| R5_aB_m0  | e_s      |       4.419 |  0.772 |    0.212 |
| R5_aB_m0  | e_r      |       6.443 |  0.489 |    0.182 |

## F
| case      |   median_abs_ds1_full |   median_abs_ds1_los |   frac_abs_ds1_gt_0.01_full |   frac_abs_ds1_gt_0.01_los |
|:----------|----------------------:|---------------------:|----------------------------:|---------------------------:|
| R2_aA_m0  |                0.0174 |               0.0072 |                      0.6562 |                     0.4589 |
| R2_aA_m45 |                0.0274 |               0.0107 |                      0.8089 |                     0.5019 |
| R2_aB_m0  |                0.0155 |               0.0082 |                      0.6255 |                     0.4651 |
| R4_aA_m0  |                0.0214 |               0.0064 |                      0.6909 |                     0.4132 |
| R4_aB_m0  |                0.0255 |               0.0129 |                      0.7484 |                     0.5846 |
| R5_aA_m0  |                0.0164 |               0.0047 |                      0.6426 |                     0.3691 |
| R5_aB_m0  |                0.0149 |               0.0052 |                      0.6006 |                     0.3882 |
