# Single-anchor DR + RF range + two Heading channels — synthetic EKF study

## Scope and caution
- Environment: github `myoungsunk/sionna-resimulation`, `src/qclean_uwb/scenarios/corridor.py`, 20×2.4×2.7 m corridor, anchor (4,0,2.65)m, tag z=0.45m; GitHub values explicitly preliminary placeholders.
- Four 10m routes preserve 2026-10-12 planned segment headings. Corners use idealized instantaneous yaw changes; no collision dynamics; no dual-LP or actual RF heading estimator.
- Heading 1 is measured **relative** IMU/Odom yaw increment used once in EKF prediction; Heading 2 is an **independent world-yaw measurement** in the main study (synthetic upper-bound assumption).
- `rf_relative_bearing` is a distinct **anchor-relative** observation model, not an absolute-heading performance claim.
- Ground truth, range noise and initial pose samples are matched across bias-variance sweeps. Independent drive and RF error streams unless explicitly correlated.

## Model (heading 1, heading 2, range)
$$u_{1,k}=\Delta\psi_k^{GT}+b_{1,step}+n_{1,k},\quad n_1\sim\mathcal N(0,\sigma_1^2).$$
$$z_{2,k}=\psi_k^{GT}+b_2+n_{2,k},\qquad z_{r,k}=r(\mathbf p_k)+n_{r,k},$$
$$r(\mathbf p)=\sqrt{(x-4)^2+y^2+(2.2)^2}.$$
$$Q_u=\operatorname{diag}(\sigma_{\Delta s}^2,\sigma_1^2),\quad R_{RF}=\begin{bmatrix}\sigma_r^2&\rho_{r2}\sigma_r\sigma_2\\\rho_{r2}\sigma_r\sigma_2&\sigma_2^2\end{bmatrix}.$$
If RF heading and the current gyro input share instantaneous noise, let $D_{u,z}=\operatorname{Cov}(n_u,n_z)$. The prediction-to-observation noise cross covariance is $C=\operatorname{Cov}(e_k^-,n_z)=-G_kD_{u,z}$ with $e_k^-=x_k^{GT}-\hat x_k^-$.
$$S=HP^-H^T+R+HC+C^TH^T,\quad K=(P^-H^T+C)S^{-1}.$$
$$P^+=(I-KH)P^-(I-KH)^T+KRK^T-(I-KH)CK^T-KC^T(I-KH)^T.$$
When $C=0$, recover standard correlated-R joint EKF update and Joseph form.
Important: the gyro-related correlation here is between sensor noise streams *within a step*, not merely between two estimated headings (which already share state P). The two RF observation noises are correlated using $\rho_{r2}$; their covariance must not be double counted.

## Baseline sensor ablation: matched 1000-run Monte Carlo
| 경로 | 센서 | 2D RMSE (m) | Y RMSE (m) | Final RMSE (m) | Heading RMSE (deg) | Mean NEES | Final 95% (%) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 직선 | dr | 0.363 | 0.344 | 0.599 | 3.433 | 2.020 | 94.600 |
| 직선 | range | 0.346 | 0.343 | 0.586 | 3.437 | 2.440 | 86.700 |
| 직선 | heading | 0.153 | 0.101 | 0.164 | 0.471 | 1.996 | 95.300 |
| 직선 | both | 0.106 | 0.098 | 0.102 | 0.471 | 1.995 | 95.300 |
| 네모 | dr | 0.171 | 0.127 | 0.172 | 3.403 | 2.042 | 95.400 |
| 네모 | range | 0.115 | 0.103 | 0.082 | 3.366 | 2.038 | 95.100 |
| 네모 | heading | 0.154 | 0.106 | 0.164 | 0.470 | 2.028 | 95.300 |
| 네모 | both | 0.091 | 0.078 | 0.076 | 0.470 | 1.996 | 95.200 |
| ㄹ자 | dr | 0.191 | 0.149 | 0.254 | 3.508 | 2.087 | 93.700 |
| ㄹ자 | range | 0.145 | 0.136 | 0.206 | 3.459 | 2.121 | 93.600 |
| ㄹ자 | heading | 0.156 | 0.103 | 0.166 | 0.463 | 2.084 | 94.400 |
| ㄹ자 | both | 0.101 | 0.089 | 0.084 | 0.463 | 2.105 | 94.200 |
| 지그재그 | dr | 0.326 | 0.304 | 0.534 | 3.294 | 1.943 | 95.200 |
| 지그재그 | range | 0.307 | 0.304 | 0.521 | 3.290 | 2.231 | 88.400 |
| 지그재그 | heading | 0.152 | 0.099 | 0.161 | 0.467 | 1.969 | 95.700 |
| 지그재그 | both | 0.097 | 0.088 | 0.090 | 0.467 | 1.953 | 95.900 |

## Heading 1 (IMU/Odom) bias-variance sweep: straight path, RF sigma 1deg, RF bias zero
Cumulative gyro bias is distributed evenly over 100 increments and is unmodeled by EKF.
| gyro_accumulated_bias_deg | rmse_2d_m | rmse_heading_deg | mean_nees_xy | final_coverage_pct |
| --- | --- | --- | --- | --- |
| -5.000 | 0.106 | 0.502 | 1.995 | 95.300 |
| -2.000 | 0.106 | 0.475 | 1.995 | 95.300 |
| 0.000 | 0.106 | 0.471 | 1.995 | 95.300 |
| 2.000 | 0.106 | 0.479 | 1.994 | 95.300 |
| 5.000 | 0.106 | 0.510 | 1.994 | 95.300 |

## Heading 2 (RF) bias-variance sweep: straight path, gyro sigma 0.23deg/step, zero gyro bias
RF bias is a fixed offset in every observation, whereas RF Gaussian sigma is per-observation random scatter.
| rf_heading_bias_deg | rmse_2d_m | rmse_heading_deg | mean_nees_xy | final_coverage_pct |
| --- | --- | --- | --- | --- |
| -5.000 | 0.514 | 4.997 | 28.074 | 0.000 |
| -2.000 | 0.225 | 2.038 | 5.978 | 12.100 |
| 0.000 | 0.106 | 0.471 | 1.995 | 95.300 |
| 2.000 | 0.232 | 2.060 | 6.320 | 10.100 |
| 5.000 | 0.521 | 5.020 | 28.965 | 0.000 |

## Joint biases (selected combinations; straight)
| gyro_accumulated_bias_deg | rf_heading_bias_deg | rmse_2d_m | final_rmse_2d_m | mean_nees_xy | final_coverage_pct |
| --- | --- | --- | --- | --- | --- |
| -5.000 | -5.000 | 0.513 | 0.872 | 28.040 | 0.000 |
| -5.000 | 0.000 | 0.106 | 0.102 | 1.995 | 95.300 |
| -5.000 | 5.000 | 0.521 | 0.882 | 29.000 | 0.000 |
| 0.000 | -5.000 | 0.514 | 0.872 | 28.074 | 0.000 |
| 0.000 | 0.000 | 0.106 | 0.102 | 1.995 | 95.300 |
| 0.000 | 5.000 | 0.521 | 0.882 | 28.965 | 0.000 |
| 5.000 | -5.000 | 0.514 | 0.873 | 28.108 | 0.000 |
| 5.000 | 0.000 | 0.106 | 0.102 | 1.994 | 95.300 |
| 5.000 | 5.000 | 0.521 | 0.881 | 28.930 | 0.000 |

## Same-epoch RF range-heading error correlation (same true trajectory)
R is modeled with offdiagonal covariance in `cov_correct`, forced diagonal in `cov_ignored`.
| corr_range_rf | model | rmse_2d_m | mean_nees_xy | final_coverage_pct |
| --- | --- | --- | --- | --- |
| -0.800 | cov_correct | 0.106 | 2.006 | 95.000 |
| -0.800 | cov_ignored | 0.106 | 1.996 | 94.800 |
| -0.500 | cov_correct | 0.106 | 2.001 | 95.100 |
| -0.500 | cov_ignored | 0.106 | 1.996 | 94.900 |
| 0.000 | cov_correct | 0.106 | 1.995 | 95.300 |
| 0.000 | cov_ignored | 0.106 | 1.995 | 95.300 |
| 0.500 | cov_correct | 0.106 | 1.989 | 95.100 |
| 0.500 | cov_ignored | 0.106 | 1.991 | 95.200 |
| 0.800 | cov_correct | 0.105 | 1.987 | 95.100 |
| 0.800 | cov_ignored | 0.106 | 1.987 | 95.200 |

## Same-epoch gyro error–RF heading error correlation
Physical coupling (e.g. RF heading algorithm reusing gyro information) is hypothetically synthesized. Joint update must use prediction-observation cross covariance C, not only offdiagonal R.
| corr_gyro_rf | model | rmse_2d_m | mean_nees_xy | final_coverage_pct |
| --- | --- | --- | --- | --- |
| -0.600 | cov_correct | 0.106 | 1.991 | 95.000 |
| -0.600 | cov_ignored | 0.106 | 1.992 | 95.200 |
| 0.000 | cov_correct | 0.106 | 1.995 | 95.300 |
| 0.000 | cov_ignored | 0.106 | 1.995 | 95.300 |
| 0.600 | cov_correct | 0.106 | 1.995 | 95.000 |
| 0.600 | cov_ignored | 0.106 | 1.994 | 94.900 |

## Interpretation boundaries
1. These are simulated measurement observations, not Sionna-generated range or polarization-derived RF Heading. No causal claim that RF actually provides absolute yaw.
2. Two reported headings can disagree for reasons of bias, noise, or misaligned coordinates; a small disagreement is not proof they are both correct (common-mode bias).
3. A gyro bias is an *increment* bias, RF yaw bias a *pose* bias. Their degree units should never be equated without specifying 100-step cumulative convention.
4. RF bearing = azimuth(anchor - robot) minus robot yaw retains rotation-gauge ambiguity with one anchor; it is not equivalent to world yaw.
5. The simulation does not add corridor-wall measurements, collision response, path replanning, lever arm, outage, AR(1) time memory, or true RF multipath.
6. Q and R are set to actual *random* variances in the sweep; biases remain deliberately unmodeled unless listed as `external_calibration` (diagnostic oracle using known biases).

## Files
- `dual_heading_sim.py`: complete generator, filter, plots, QA.
- `all_cases.csv`: all hypotheses and results.
- `01` to `08` CSV files: factorized sweeps, RF correlation and interpretation checks.
- `01` to `06` PNG plots: individual trajectory/heatmap/correlation/accuracy.
- `CONFIG_SNAPSHOT.json`, `QA_REPORT.json`, `SHA256SUMS.txt`: provenance.
