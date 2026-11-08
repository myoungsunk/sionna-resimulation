# PALO A/B results

A/B ONLY; stored-prior counterfactuals; NOT closed-loop policy performance

Raw sources: 16450dc14366ba4ed2cb4e151952493f0efc944f

Validated 16 trajectories, 15664 priors, 93984 action rows.

Fit 40–100 s; calibration 100–120 s; gap 120–140 s; diagnostic test >=140 s. Same physical frames grouped. No oracle donor used for training/calibration. R2 is already exposed.

## Add vs remove
Same prior, candidate and decision imply identical X/P. Prior histories, not the verbal default, change the problem. Omitting a new factor does not undo old RF updates.

## Same-frame benefit disagreements
|level|n|S4 beneficial|DR beneficial|disagreements|both gate|disagreements both gate|
|---|---:|---:|---:|---:|---:|---:|
|B0|779|464|174|420|751|406|
|L0|779|467|413|370|751|356|
|L1|779|455|593|368|751|354|
|L2|779|437|746|359|751|343|

## Locked thresholds
```json
{
  "M0": {
    "feature": "dr_innov_mean5",
    "direction": "le",
    "threshold": 0.0013173491110675948,
    "objective": 2608.1976097061156
  },
  "M1": {
    "features": [
      "nis",
      "innovation_abs",
      "Hpsi_abs",
      "Hxy_norm",
      "Pxy_trace",
      "Ppsi",
      "Pxypsi_norm",
      "correction_abs",
      "dr_innov_std5",
      "dr_heading_diff",
      "dr_xy_diff",
      "dr_innov_mean5_abs"
    ],
    "threshold": 0.01,
    "abstain": false,
    "calibration_best_gain": 4.18367254152919
  },
  "M2": {
    "features": [
      "nis",
      "innovation_abs",
      "Hpsi_abs",
      "Hxy_norm",
      "Pxy_trace",
      "Ppsi",
      "Pxypsi_norm",
      "correction_abs",
      "dr_innov_std5",
      "dr_heading_diff",
      "dr_xy_diff",
      "dr_innov_mean5_abs",
      "delta_x",
      "dr_offset_x",
      "delta_y",
      "dr_offset_y",
      "delta_psi",
      "dr_offset_psi",
      "delta_bg",
      "dr_offset_bg",
      "delta_forward",
      "delta_lateral",
      "dr_offset_forward",
      "dr_offset_lateral",
      "dr_heading_alignment",
      "dr_xy_alignment",
      "dr_heading_distance_gain",
      "dr_xy_distance_gain"
    ],
    "threshold": 0.75,
    "abstain": false,
    "calibration_best_gain": 9442.676917377994
  },
  "M3": {
    "features": [
      "nis",
      "innovation_abs",
      "Hpsi_abs",
      "Hxy_norm",
      "Pxy_trace",
      "Ppsi",
      "Pxypsi_norm",
      "correction_abs",
      "dr_innov_std5",
      "dr_heading_diff",
      "dr_xy_diff",
      "dr_innov_mean5_abs",
      "delta_x",
      "dr_offset_x",
      "delta_y",
      "dr_offset_y",
      "delta_psi",
      "dr_offset_psi",
      "delta_bg",
      "dr_offset_bg",
      "delta_forward",
      "delta_lateral",
      "dr_offset_forward",
      "dr_offset_lateral",
      "dr_heading_alignment",
      "dr_xy_alignment",
      "dr_heading_distance_gain",
      "dr_xy_distance_gain",
      "P_xpsi",
      "P_ypsi",
      "bg_est",
      "bg_sigma",
      "P_psibg",
      "normalized_step",
      "heading_fraction",
      "xy_fraction",
      "lag5_delta_psi",
      "lag5_delta_bg",
      "lag5_innovation_abs",
      "dr_motion_distance",
      "dr_turn",
      "lag5_dr_turn",
      "dr_innov_mean5"
    ],
    "threshold": 0.1,
    "abstain": false,
    "calibration_best_gain": 3089.8659011916707
  }
}
```

## Limitations
B evaluates same-prior counterfactual risk, NOT recursively executed policy RMSE. Oracle-prior tests are privileged-state diagnostics. Classifier scores are not certified probabilities. Scaling is modeled information weakening, not calibrated uncertainty. No C/D or new RF simulations were run.

See A_summary.csv, B_test_metrics.csv, B_test_risk_sweep.csv, online_features.csv.gz and offline_labels.csv.gz.
