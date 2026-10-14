# G2/G3 B2 → C2 → D0 검증 최종 브리핑 (2026-10-14)

## 1. 실제 실행 증빙
- 결과 실행: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38561262164
- 원시 아티팩트: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38561262164/artifacts/11891769888
- 검증 소스 commit: 410fe26661bba7ed3e67266d05ac962d58803691
- 참조한 원래 RF scene commit: b05af070a87981f8712fdd41eac4c1bbb882e9c7
- 감사 규칙: 9beb061f354edef18e1f977f5d462d7e0d8b1f2e
- source-bound pre-run source+input 감사 영수증: PRE_RUN_BOOTSTRAP, PRE_RUN_B2, PRE_RUN_C2, PRE_RUN_D0
- RF 장면: office 35 distinct locations, corridor A2 15, A2B 14. A2/A2B are correlated variants of the SAME corridor, not two independent scenes.
- No original RF or original H3/G2/G3 numerical result was modified. No new full-pose physical G2/G3 or recursive estimator was deployed.

## 2. 단계별 네 가지 판정
| 실험 | 실행 | 계산 유효 | 가설 | 과학적 주장 |
|---|---|---|---|---|
| B2 signed RF conditional model | PASS | PASS for normalized likelihood and data | A2/A2B 95% empirical tail coverage supported | CLAIM_BLOCK for independently calibrated online probability |
| C2 guarded distance action | PASS | Quad vs independent Simpson PASS | C1–C4 guarded actions supported, C4 97.38% confidence CONTRADICTS reliability hypothesis | CLAIM_BLOCK for universal safe RF selection and full pose |
| D0 exact Bayes sequential/joint | PASS | 1D radial + toy angular identity PASS | G2 exact = G3 exact on identical toy factors | CLAIM_BLOCK for actual H3 S/R and full 3state posterior |
| E full one-step | NOT_RUN | NOT_RUN | NOT_EVALUATED | depends on real B and D |
| F recursive | NOT_RUN | NOT_RUN | NOT_EVALUATED | depends on E, pose cov calibration |

## 3. B2 수식과 외부 RF 검증
B2 candidate: signed e=z_RF-r_true.
Clean Office LoS 25개로 fitting한 Gaussian을 측정 tap spacing 0.149552m의 uniform half-bin jitter와 convolution하여 의도적으로 error uncertainty를 넓힘. 이것은 30% leading-edge detector의 exact law가 아니고, 이미 관측된 오차의 quantization variance와 일부 중복될 수 있어 반드시 sharpness/coverage를 함께 평가.
Blocked 10개 Office에서 Student-t(df=3) positive multipath tail fitting.
기존 synthetic C3 과소보정 component Student-t(df3,loc=-0.5m,scale0.25m,weight0.035)는 이전 모델에서 상속; 별도 독립 calibration 아님. CIR first-to-peak, FP energy, FP/peak ratio만 logistic Q features로 사용하고 Office blocked label로 정규화한 weight를 50% global shrinkage. A2/A2B truth, XY, actual gyro fault label not used in candidate prediction.

| 검증/metric | A2 15 positions | A2B 14 positions |
|---|---:|---:|
| 이전 B1 95% one-sided coverage | 80.0% | 85.7% |
| B2 95% empirical coverage | 100.0% | 100.0% |
| B2 99% empirical coverage | 100.0% | 100.0% |
| 이전 B1 mean NLL | -0.4532 | -0.8198 |
| B2 mean NLL (lower better) | -0.9064 | -1.0650 |
| B2 PIT KS | 0.2726 | 0.1374 |
| B2 median predicted 95% lower-bound signed residual | -0.1146m | -0.1136m |
| B2 actually smallest signed residual | -0.0794m | -0.0558m |

Office leave-one-location-out 95% and 99% coverage both 100%; this is CONSERVATIVE, not verified probabilistic calibration. All data are positional yaw means, NOT 19 independent RF transactions; two synthetic scene families do not prove 95%/99% real deployment accuracy. Model NLL improvement on this particular corridor family is meaningful descriptive scoring, but does not fix low scene diversity, time correlation, source mapping or DR calibration.

## 4. C2 four frozen controls, no prior retuning
Same C1–C4 truth/DR/RF from earlier frozen contract. DR pFault=0.05 + extra std=2m is still synthetic, not independently trained on gyro/wheel sequences.

Given delta=DR_RF_distance_difference=d-z, probability P_RFbetter=P(|eRF|<|eDR| | delta,Q,U) is computed using signed B2 e_RF model and synthetic DR mixture. Numerics checked by adaptive quad versus separate fixed Simpson integration.
Guarded action: only if delta>0 AND NIS>6.634896601 AND pRFbetter>=0.95 => update radial to z-mu_clean, otherwise keep d. This is NOT a 3-state Bayesian G2/G3 filter.

| Case | DR error | Guarded radial error | Model P_RFbetter | Interpretation |
|---|---:|---:|---:|---|
| C1 DR exact | 0m | 0m | 46.52% | DR retained |
| C2 large DR bias | 2.8059m | 0.0524m | 97.55% | large radial improvement |
| C3 RF too short | 0.0300m | 0.0300m | 15.96% | DR retained; this C3 was known when inherited negative component devised |
| C4 RF too long | 0.0300m | 0.0300m | 97.38% | DR retained ONLY because delta<0 |

Major contradiction: in C4 the RF measurement 7m is 2m wrong while DR=5.03m has only 0.03m error; **posterior direct RF distance-superiority probability is 97.38% (incorrectly confident)**. Thus the guarded action passing C4 does not validate its inferred probability. The longer-RF sign constraint is performing the protection, and a full G2/G3 estimator accepting long RF could be badly biased. This is a scientific claim block, not a numerical quadrature failure.

## 5. D0 and full physical G2/G3 limitations
D0 used the B2 signed likelihood in toy scalar range r and angle psi, and compared one-step normalized joint multiplication with sequential Range-then-conditional-S factorization. Max density absolute difference 7.105427e-15, Heading marginal TV 1.040668e-16. This is an algebraic/finite-grid check with the SAME integrand, NOT an independent solution of physical H3 nonlinear 3state pose.

Original R0 G3 independent tilted GH one-cell numerical test already verified via Actions 38531405523 with max TV .0003356. But physical 195.6s sample G3 heading error 52.58° vs original G2X 24.56° (Actions 38532581455): numerical convergence is not estimation correctness. B2 RF feature/calibration schema (Office TX0) is not automatically the original H3/E1 sensor schema. Replacing original H3 RF likelihood without source consistency checks would be a HARD_EXECUTION_BLOCK.
DR Fault prior from independent time-series gyro/wheel/odometry data is still missing: office and anchor static sweeps have no such data. Therefore full 3state G2/G3, E and F cannot scientifically proceed as validated claims on this model.

## 6. Next hypothesis / confirmation boundary
The user required contradiction diagnosis before hypothesis changes. C4 false high-confidence persists, B2 probability calibration is not independently certified. Do NOT retune 95% threshold or synthetic pFault after looking at C4 or A2/A2B test labels.

Recommended next hypothesis: independently calibrate asymmetric positive/negative RF outlier risk using additional distinct RF scene and online CIR Q; calibrate DR radial and pose fault prior from independent dynamic gyro/odom data; investigate the C4 positive RF conflict WITHOUT a blind one-sided sign gate as the only protection. Then establish physical same-observer signed RF model matching H3, solve nonlinear joint S+Range reference posterior with independent TV<=0.001, run real G2/G3 paired one-step, and recursive position/Heading RMSE, NEES and coverage.

## 7. QA and evidence
- Evidence ZIP B2_REPORT.json; B2_TRANSFER.csv; B2_VS_B1_EXTERNAL_NLL.csv; B2_OFFICE_LOOCV.csv; C2_REPORT.json; D0_REPORT.json; PRE_RUN_*.json.
- CONTRACT.json / PRE_RUN_REVIEW_KO.md / APPROVAL.json / run.py / gate.py.
- Executed result machine summary EXECUTED_RESULT_SUMMARY.json.
- Four statuses: EXECUTABLE PASSED, NUMERICAL CALCULATION PASSED IN TESTED LIMITED SCOPE, HYPOTHESIS B2 CONSERVATIVE TAIL & C GUARD SUPPORTED BUT C4 PROBABILITY CONTRADICTED, SCIENTIFIC CALIBRATION/FULL G2G3 CLAIM_BLOCK.
- scientific_PASS=false. No stage/accuracy/safety claim beyond this boundary.
