# 07 — Existing-sensor-v2 ratio/CIR versus multi-yaw-probe reliability: exploratory overlap

Date: 2026-10-10. Report status EXPLORATORY / NOT CALIBRATED / NO NEW RF. This report cross-links two completed but independently developed experiments. It is NOT the full-P6 noisy probe run specified in 06.

## Existing records

Probe: 2026-10-10 GitHub Actions run 38047959200, frozen data and nominal site/point mixture. 5100 run-level MIX3 records, grouped to 34 case-station units from 16 physical XY sites; no actual noisy rotation, no pose cross covariance. Original posterior input: RF-off sensor-v2 heading prior and true yaw offsets from frozen SAMPLES.

Passive: GitHub Actions run 38049158399, same original sensor-v2 RF-off prior + fixed LUT. Leave-one-ROUTE-out logistic models; source output RATIO_MODELS_PREDICTIONS.csv.gz. For each probe case-station, matched the first available pose_id for the same case and route_x_y station_group. 34/34 matched; q_good trained to predict *single-angle inverse heading error<=5deg*, NOT site multipath probability and NOT MIX3 heading accuracy. No ground truth fed to any classifier or mixture inference; ground truth labels only evaluate results.

Fusion at case-station: q_site = mean of nominal MIX3 q_site_bad across sensor seeds; q_passive_good = held-out route probability at the first probe observation. Exploratory risk score (not a probability) r_fused = 0.5 q_site + 0.5(1-q_passive_good). Evaluate against the **fraction of MIX3 headings with absolute error >5deg** across the same repeated seeds (p_bad5). The 0.5 weights are illustrative, not learned or calibrated.

## Observed Pearson association with station heading failure fraction

34 case-station units, only 16 distinct physical coordinates:

| Predictor | Pearson with p_bad5 |
| --- | ---: |
| q_site_bad from three-angle likelihood | +0.322 |
| 1-q_passive_good (range+total power+signed s+|s|) | +0.414 |
| 1-q_passive_good (+CIR shape features) | +0.377 |
| 0.5q_site+0.5(1-q_passive_good WITH CIR) | +0.505 |
| 0.5q_site+0.5(1-q_passive_good NO CIR) | +0.510 |

Cluster bootstrap over 16 distinct physical sites, 3000 replicates (seed 20261010):
- fused WITH CIR Pearson r=+0.505, 95% CI [+0.242,+0.683].
- additional correlation from fused versus passive risk WITH CIR: Δr=+0.128, 95% CI [−0.102,+0.359] **contains zero**.
- change when adding CIR in fused versus fused NO CIR: Δr=−0.005, 95% CI [−0.043,+0.031] **contains zero**.
These intervals are conditional on ONE corridor and few physical sites, not generalized statistical inference.

For site-multipath truth label based on any of 3 oracle e_s values >0.1:
q_site alone had descriptive AUC 0.692 across 34 units, passive ratio/power 0.740, passive ratio/power+CIR 0.723, illustrative fused +CIR 0.689. This means the fixed fusion score does NOT improve site-multipath identification in this dataset. Fused site risk must not be described as validated.

## Conclusions and correct next test

1. First-path normalized dual-LP ratio s contains information relevant to operational RF-heading correctness beyond distance+total power for the old within-corridor held-out routes (see RATIO_MODELS_HELDOUT.csv). Not physical depolarization detection.
2. Three-angle nominal site posterior itself is poorly calibrated and missed many true corrupted sites. Fusion's higher descriptive correlation with **post-MIX3 heading errors** is a plausible research lead, not an established gain.
3. Adding CIR shape to the already ratio/power-based site fusion did not show incremental improvement in 16 physical sites; additional thermal noise, correlated probe motion and new geometry may change this.
4. Full-P6, actual noisy body yaw, 2/3-angle observation covariance and cross-geometry validation are still missing. Execute 06 data contract before claiming no-harm filter behavior, NEES improvements, meaningful probability calibration or generalization.

Never conflate q_site_bad (risk of polarimetric mismatch), q_passive_good (single-angle heading correctness), q_fused heuristic (uncalibrated score), and the actual corrected heading error from MIX3. They are different targets.

Source scripts and artifacts:
- run_dual_lp_ratio_association.py and workflow dual-lp-ratio-heading-20261010.yml on codex/probe-mixture-reliability-20261010.
- 06_SENSOR_V2_NOISY_PROBE_FULL_COV_DATA_SPEC_KO.md on same branch.
- Existing 7 case full RF H and paired LoS H unchanged, source frozen as old.
- All 7 cases share one corridor; F01/F02 remain OPEN.
