# P5 confirmatory criteria (frozen BEFORE the 128-seed confirmatory run; development seeds 5000-5031 have been looked at)

Confirmatory seeds 5100-5227 (128), 12 conditions x 3 drift levels x 8 arms = 36,864 runs. Same harness, arms and priors as the development run (pose-SMALL prior, calibration prior as configured, range-only, no `s`).
What the development run already showed (disclosed): B_OLD is worse than the IMU+wheel-only arm A; E_COND and BEST_PLUS_R_IAT were the most accurate; BEST_PLUS_R_IAT was an arm added after P3 (R multiplied by a constant IAT_COND=5.8 taken from the V05 timestamp analysis of the same simulated corridor -> mild information leak into R, listed as a limitation).

Primary questions (relative change of the condition-cluster mean, bootstrap over the 12 conditions, 95 % CI -> 'LIMITED' because one scene / 3 routes):
 Q1 E_COND vs B_OLD: position RMSE and heading RMSE both decrease with CI upper bound < 0.
 Q2 BEST_PLUS_R_IAT vs B_OLD: same.
 Q3 best arm vs A (IMU+wheel only): position RMSE decreases with CI upper < 0 (is the RF range worth using at all?).
Consistency (secondary, NOT a pass criterion for accuracy): mean pose NEES, median NEES, pose95 coverage, range-innovation lag-1 autocorrelation, range reject rate. An arm is called 'not worse than A in consistency' only if its coverage CI contains or exceeds A's. No arm is declared consistent unless mean pose NEES is inside the chi2 reference interval; with A itself far outside that interval (development: NEES 48.7, coverage 64 %), consistency cannot be certified in this setting.
Interpretation limits: V02 LARGE FAIL stays; this is a diagnostic of range-bias handling, not scientific_PASS; P4 was within-scene only (GENERALIZATION_NOT_VERIFIED), so P5 cannot upgrade it.
