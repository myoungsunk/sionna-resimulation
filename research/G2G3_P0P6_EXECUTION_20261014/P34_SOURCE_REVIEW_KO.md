# P3/P4 실제 One-step 사전 감사 — GitHub 물리 모델 원본 동결

## 연구 의도
사용자는 P3 대표 3-state 결합과 P4 여러 경로의 One-step 평가를 진행하라고 요청했다. 개별 오차 악화는 오차분포로 보고하고 전체 차단 금지. 수치 무효는 해당 추정 셀의 결과만 무효 처리한다. 기존 원본 H3 입력·LUT·DR prior 사용. B2는 original H3와 sensor observer가 서로 다른 것으로 확인돼 이번 버전에 직접 대입하지 않는다. 새로운 수치 개선을 사후 성능 PASS로 오인 금지.

## P3 source review
- P3 physical joint R0 G3: each 1440 discrete wrapped heading grid value, conditional Gaussian 2D position prior with full Pxyψ. Measurement likelihood exp[-0.5(es²/Rs + er²/Rr)] only once. Frozen Rs 0.0081 and Rr 0.0068578637; no Rsr in frozen R0.
- Likelihood-tilted proposal derived from range ONLY. Original 2026-10-14 numerical procedure and GH25/41 reused, importance correction log pprior-log q. Proposal does not turn into target; exact target still joint S+Range.
- P3 posterior joint mean/cov integrates XY conditional quadrature moments within heading and sums heading weights. Full 3x3 covariance including Pxy and Pxpsi, Pypsi. Wrapped yaw difference, circular mean. The posterior mean is not identical to heading marginal MAP. Store both and compare.
- G2 approximation: frozen original Range EKF (original gate). Then S-only likelihood, Gaussian conditional position integration GH9/17. Original G2X used full conditional S posterior and may have different angular strategy. Label algorithm G2_EKF_S and do not claim it is exact.
- P3 fixture selection includes original R2 aA m0 L2 195.6s, same low gyro bias L0, R4 Full/E1 low-bias. G2/G3 each same prior, independent evaluation truth only at score() after posterior function completes.
- Numeric thresholds: TV <=0.001, MAP <=0.1deg, HPD <=1deg and relative evidence <=0.005. These are pre-existing, not retrofitted. If P3 GH25/41 S/R does not converge, that estimator cell is CASE_RESULT_INVALID; others continue.
- Potential issue: near-anchor non-Gaussian multimodal heading approximated by circular mean may be misleading, so circular resultant/concentration saved. Covariance is a Gaussian moment, not a guarantee of 95% calibrated Gaussian posterior.
- Pre-run source hash and exact H3/P0/P3 model manifest before any numerical calculations. Same source H3 synthetic and G2 initial prior reused from prior verification. No independent external human reviewer; numerical cross order vs prior GH/RQMC data in scope.

## P4 source review
- P4 is FULL factorial **EKF approximation**, NOT a full nonlinear G3 exact benchmark. Uses 7 cases x 4 bias regimes x 3 seeds x 3 RF arms x all time >=30s, one-step DR prior without recursive RF feedback. Methods: DR, S_EKF, Range then S EKF, joint S+Range gated EKF, joint S+Range ungated EKF diagnostic.
- True gyro/drift bias and true position NEVER enter estimator, truth is used in score() only. All DR prior estimates regenerated with frozen D0 motion inputs, same seed and path across each arm.
- G2 Range EKF then S EKF uses original RR, RS, Rsr0, same Range once. Joint EKF update uses S/r in one vector and Joseph covariance. Ungated branch is explicit counterfactual and can diverge; recorded, not silently adopted.
- If one method fails numerically, others should still emit valid rows for same time; method denominator recorded. Repeated seeds do not count as independent RF scenes; report per-case and route block effects, not sample-level naive confidence.
- Precision vs accuracy: P4 G2-EKF-linear / G3-joint-EKF-linear are NOT the same as physical nonlinear P3 G3 joint-integral estimator. Separate label and scientific claim.
- Time and storage: 7 independent case jobs. Traces at 30s interval, summary all valid frames, per-method invalid cases/reasons, denominator complete. P4 no recursive feedback, no F-stage claims.
- Any P4 performance worsening is scientific observation not source failure. Numerical error in s LUT model/cov PSD is CASE_RESULT_INVALID for affected estimator time; unknown input/detector SHA is HARD_EXECUTION_BLOCK for the affected case.

## Audit classes
HARD_EXECUTION_BLOCK: original input hash or observer shape mismatch, posterior likelihood counted twice, truth leakage, changed normalized LUT, invalid covariance outside case-level numeric conditions.
CASE_RESULT_INVALID: independent GH TV failure, nonfinite/negative covariance, zero evidence per-method.
CLAIM_BLOCK: B2 independent calibration and external scene uncertainty, signed RF not fitted on H3 source, numerical approximations cannot be called full nonlinear exact, repeated RF scene/seed independence.
DIAGNOSTIC_DEFECT: optional plots/report format; repair only diagnostics and preserve tested model.
