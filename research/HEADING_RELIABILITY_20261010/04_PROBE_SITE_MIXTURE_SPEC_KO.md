# 04 — Multi-angle weighted posterior + site multipath risk (pre-execution, 2026-10-10)

This is a NEW exploratory follow-up to 00/01, not a silent replacement of the 2026-10-10 preregistration. Analyze only the existing frozen sensor-v2 and same-XY yaw-probe data. No change to production EKF, original LUT, routes or RF.

## Research question and distinction

User intention: do **not** select only the smallest LUT residual. Measure 2–3 yaw angles, infer (a) whether multipath degrades the **site** as a whole, (b) posterior corruption probability **at each angle**, then (c) jointly estimate heading and its uncertainty while still retaining low-quality points with less influence.

This is latent-variable measurement weighting. The point's contribution is integrated over both clean/contaminated hypotheses; no observation is silently dropped. Output q_site_bad, q_point_bad[i], psi_est, sigma_psi, and estimated heading error for evaluation only.

## Fixed data and operational limitations

- Input: results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/PROBES/07_PROBE_STATIONS.csv.gz for 3-angle rows, filtered status; 01_FEATURES.csv per pose measured s; 02_LABELS_EVAL_ONLY.csv truth and e_s/e_MP; frozen 2° FFD LUT hs_lut_2deg.npy, meta and frozen case geometry.
- This public probe table includes pre_rf_state[6] and heading Pψψ, but NOT the original full pre_rf_cov[6,6]. Therefore the tested study conditions on **fixed estimated x,y** and uses only Pψψ; online pose-heading covariance effects cannot be validated. The full NPZ is preserved on Snowball, not published here.
- δ angles are recorded true yaw offsets in SAMPLES (ideal actuator). Physical noisy yaw control and time overhead are NOT modeled. Only 34 case-specific station groups / 16 distinct physical sites have v2 evaluation prior; 169 station-case groups is larger but lacks operational prior for most.
- No actual independent physical environments. Same RF repeated across drift/seed, so use physical station coordinates as uncertainty cluster and avoid interpreting 5100 repeated rows as 5100 independent RF locations.
- Sensor use of first-path powers, two-port magnitude CIR amplitude assumed only where hardware available. No oracle e_s/e_MP or true heading for inference.

## Likelihood and mathematical model

Let prior heading ψ0, variance Pψψ and relative recorded yaw angles δ_i; z_i is measured dual-polarization s, h_i(ψ)=fixed LUT predicted s at estimated xy, heading ψ+δ_i. Unknown correction u=ψ−ψ0. Grid u ∈ [−90°,90°] at 0.5°. Nonlinear LUT evaluated on each grid point; prior u~N(0,Pψψ).

Site latent M∈{0 clean,1 multipath} and each angle latent c_i∈{0 good,1 contaminated}. Conditional likelihood:

r_i(u)=z_i−h_i(ψ0+u)
r(u)~N(0, diag(σ_{c_i}²)+τ_const,M² 11ᵀ+τ_yaw,M² ggᵀ)

where g_i=∂h_i/∂ψ evaluated at prior ψ0+δ_i. Common site nuisance both offset in s and equivalent heading-like bias is integrated into the covariance, *not* estimated as true heading. This only approximates non-Gaussian correlated RF; its probabilities are nominal.

Frozen **illustrative** constants before experiment:
P(M=dirty)=0.35; P(point_bad|M=clean)=0.06; P(point_bad|M=dirty)=0.55;
σ_good_s=0.06, σ_bad_s=0.30;
τ_const_clean=0.01, τ_const_dirty=0.15 (s units);
τ_yaw_clean=1°, τ_yaw_dirty=15°.
These are **not trained or experimentally calibrated noise parameters**, and cannot be treated as sensor-level confidence. Do not tune after reading results; changing them requires separately named sensitivity runs.

Enumerate 2×2^M site/angle hypotheses (M=1,2,3). For each, marginalize u on the fixed grid. Posterior mode masses produce q_site_bad, q_point_bad[i]. The mixture over u yields ψ_est and σψ; no lowest-residual point selection. The posterior can be multimodal: mean/std are descriptive; monitor high posterior mass near grid boundaries and 95% posterior quantiles, posterior ambiguity.

Comparators (same site/drift/seed; same angle subsets [0], [0,2], [0,2,4]):
- PRIOR only (no RF)
- BASE_N Gaussian white R=.09²I with exact nonlinear LUT grid
- MIX_N latent site + point corruption mixture above, exact nonlinear LUT grid.

## Labels and validation

Site true_bad: max_i |s_RF,i − h_LUT(p_true,psi_true+δ_i)| > 0.1; point true_bad_i: corresponding absolute error >0.1. **These oracle labels are forbidden in inference.**
Heading error: circular abs difference between ψ_est and true first pose yaw. Also evaluate nominal 95% posterior interval coverage (warning: ignores xy uncertainties and unvalidated temporal/probe cross-covariance).
Metrics: mean / median / 90th percentile heading absolute error; site/point Brier+AUROC of nominal q_bad; site flag rate at q_site_bad≥0.5; negative log likelihood of actual error under Gaussian moment approx; 95% coverage; per-point posterior contamination probabilities and worst error by route/anchor; paired MIX_3−BASE_3 and MIX_3−MIX_1; compare use of RF to PRIOR.
Uncertainty: paired physical-station-cluster (route,x,y) bootstrap; 1000 resamples, seed=20261010. Do not treat 5,100 seed/drift observations as independent locations.

## Stop/failure conditions

Missing any input, mismatch of stored fixed LUT hash, duplicate feature key, invalid probe offsets, missing prior or invalid covariance -> record and stop/skip transparently. No offline truth feature in inference. No claim of calibrated probability, hardware success, changed EKF performance, or new-geometry generalization. Existing scientific_PASS=false, F01/F02 OPEN unchanged. Workflow may report model failure if RMSE worsens, probability uncalibrated or confidence coverage poor; do not optimize constants after results.
