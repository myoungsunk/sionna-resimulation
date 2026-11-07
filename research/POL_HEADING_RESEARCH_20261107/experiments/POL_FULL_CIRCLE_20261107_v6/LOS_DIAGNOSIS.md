# LOS failure diagnosis

Question: POL-FULL-CIRCLE-v6-LOS. Role: same-author read-only diagnosis/self-check, not independent audit. No estimator edits or recursive reruns. Inputs: frozen v6 model/CALIBRATION and existing LOS B0 outputs. Governance: COMMON_CONTRACT.md and ROLE_AUDITOR.md local v1; source/model hashes are in INPUT_HASHES.json and PROVENANCE.json. Existing results preserved.

## Confirmed observations

- Calibration t<30: heading RMSE S4 0.3739 deg, v6 2.0794 deg, refined 2.0869 deg. Failure already occurs inside calibration; evaluation split alone cannot explain it.
- v6 fits residual second moment on LOS but angular sigma and outlier probability on Full, then shares both across LOS and Full. Angular sigma=8.101593 deg; it is an independent per-observation latent displacement, not a persistent error state.
- Exact per-LUT-cell Gaussian integration of E_delta[h(x,psi+delta)] at true LOS poses: RMS difference from h(x,psi) is 0.04289416 in calibration, 0.03876564 in evaluation. Actual LOS residual RMS around h is 0.00475401 and 0.01356170 respectively. The convolved inlier mean therefore changes, rather than merely expanding a symmetric uncertainty interval. This establishes a model consequence, not its isolated causal contribution to trajectory RMSE. Uniform-outlier component excluded from this diagnostic mean.
- Residual floor R_s=2.26006484e-5 versus S4 0.0081, a factor 358.40 lower. Total local linear variance additionally contains H_psi^2 sigma_angle^2, so the total observation weight is NOT uniformly 358 times larger. Across all LOS truth poses its local linear approximation has quantiles [min,p10,p50,p90,max]=[2.26027e-5,2.15914e-4,0.00418644,0.02459188,0.16126278]. Nonlinear angular variation remains near extrema; the floor alone is not the exact effective variance there.
- LOS residual calibration: mean -0.00304819, RMS 0.00475401, raw adjacent-sample correlation 0.75776. Evaluation: mean -0.00506954, RMS 0.01356170, adjacent correlation 0.65414. These residuals contain model/geometry effects; correlation is not proof of a stationary noise process or of multipath in LOS.
- v6 updates conditional XY and gyro bias through CH/V and inherited cross-covariances, so this is not a heading-only correction. LOS B0 XY sigma RMS falls from S4 0.1206 m to v6 0.0573 m while XY RMSE rises from 0.0981 to 0.1896 m.
- All retained actual posterior branch counts are one. Maximum absolute LOS B0 heading error over all frames: S4 1.5481 deg, v6 3.0740 deg. This failure is not an observed 180-degree flip. Previous circular-mean defect cannot affect a single Gaussian component's mean.
- Refined LOS B0 heading RMSE=1.29484 versus nominal 1.26435; XY=0.19503 versus 0.18956. Numerical convergence is unresolved, but refinement does not remove the degradation against S4.

## Interpretation and claim boundary

Leading model mismatch: Full-derived angular smearing is applied to LOS, changing the nonlinear observation distribution; meanwhile a much smaller residual floor and independent repeated observations allow concentrated state posteriors. Structured residuals can be absorbed into coupled position/heading states rather than represented as persistent model discrepancy. This is a supported mechanism and design concern, not an ablation-established attribution of all error.

REDIRECT: do not attribute LOS degradation simply to multipath, evaluation split, or 180-degree ambiguity. Separate fixes to likelihood support from changes to noise/calibration assumptions. A future matched ablation should retain the S4 residual scale first, isolate angular smearing and time correlation, and resolve conditional-integration convergence before claiming a validated replacement. No such ablations were executed in this diagnosis.
