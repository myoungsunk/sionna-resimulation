# P4 Full C0+ — 3앵커 정확도 향상과 EKF posterior overconfidence의 공존 원인

**원본 데이터 기반 분석 완료 · 2026-11-02 · 한 개 C0 Corridor 시뮬레이션**

P4 Full 원본 Actions 41435839892에 보존된 12개 full-time 4상태 EKF trace ZIP을 **물리적 byte SHA256 5ecf2a326ec17c8ce4ccc7a42fe76227ecf6ad7ec027df9cdfcd2304dcb0acfe**로 고정해 읽었다. 3 route×Full/NativeLoS×B0/L2×7 arm = 84 trajectory, 각 조건 2686개 t>=30s 평가 pose. GT는 offline 비교에만 사용했으며 원래 필터, covariance, R, gate, RT 데이터는 변경하지 않았다.

## 핵심 결과 — 3앵커는 평균값을 개선하지만 P를 그보다 더 빠르게 줄인다

| Full-L2 | 2앵커 AB | 3앵커 ABC |
|---|---:|---:|
| Heading RMSE (°) | 2.718 | **2.306** |
| XY RMSE (m) | 0.24316 | **0.17533** |
| 평균 Pxx+Pyy (m²) | 0.015507 | **0.003083** |
| XY RMSE / 예측 radial RMS σ | 1.953 | **3.158** |
| 평균 Pose NEES (3차원) | 56.15 | **102.41** |
| 명목 95% Pose Coverage | 27.66% | **8.23%** |

실제 XY RMSE는 AB→ABC 약 28% 감소했으나, 필터가 보고한 평균 XY covariance trace는 약 80% 감소했다. Full-B0에서도 ABC는 AB보다 XY/Heading 오차가 작지만 Coverage는 36.26%→8.97%로 악화한다. 정확도와 uncertainty calibration은 별개의 축이다.

## 1. Full first-path range 관측오차는 고정 Rr과 일치하지 않는다

실제 Native H→first-edge detector의 원시 z_r에서 참값 기반 연속 예측 h_r=||p_true−anchor||−0.5315983906250129m를 뺀 후, 원본 Full/LoS matched time과 세 앵커 모두를 집계했다. 원래 EKF 고정 분산은 Rr=0.0068578637 m² (σ=0.0828m)이다.

| 앵커 | Full residual 평균 (m) | Full RMSE (m) | sample-centered variance/Rr | lag-1 corr (R2/R4/R5) |
|---|---:|---:|---:|---|
| A | +0.06144 | **0.15518** | 2.96 | 0.804 / 0.501 / 0.836 |
| B | +0.02896 | **0.11114** | 1.68 | 0.513 / 0.513 / 0.440 |
| C | +0.08038 | **0.29372** | **11.64** | 0.827 / 0.784 / 0.657 |

C의 RMSE는 가정 σ의 3.55배. R5-C Full route RMSE는 0.3818m, 그 route의 95백분위 절대오차는 0.2421m이어서 드문 큰 오차의 기여가 존재할 수 있다. 여기서 표본 잔차는 실제 측정 회차별 IID 센서 잡음이 아니라 **위치와 시간에 종속된 동일 simulator channel errors**다. 오차 원인에 geometry-conditioned bias와 first-path detection 변화를 함께 고려해야 한다.

동시 앵커 간 Full sample correlation은 pooled AB +0.0585, AC −0.1211, BC −0.0026; 전 route도 절대값이 보통 0.24 이하이다. 따라서 **강한 동시 cross-anchor correlation이 핵심 원인이라고 단정할 근거는 약하다**. 오히려 앵커별 편향·분산·시간 구조가 고정 diagonal R과 불일치한다는 근거가 더 크다. Full residual covariance의 최대 eigenvalue는 0.08024m²로 고정 Rr의 11.70배다. 이 공분산을 데이터로 재학습해 독립 개선 성능을 주장한 것은 아니다.

## 2. 기하학적 가관측성 증가 자체는 실제로 존재한다

각 앵커의 순간 XY range Jacobian은 H_r,xy=[(x−a_x)/d,(y−a_y)/d]이고 H_r,yaw=H_r,bias=0이다. 참값에서 계산한 2D 정보 블록 Hxy.T * Rr^-1 * Hxy의 **최소 정보 고유값 median**은 다음처럼 증가한다.

| Route | AB | ABC |
|---|---:|---:|
| R2 | 1.206 | **5.393** |
| R4 | 0.269 | **5.239** |
| R5 | 0.118 | **3.508** |

C=(16,0.8,2.65)m가 기존 같은 y축의 A/B와 비공선 기하를 형성한다. 이 증가가 위치 오차 감소와 일관되지만, yaw/b_g는 순간 H에 직접 보이지 않으므로 시간 전이를 통해 간접 갱신된다.

필터가 사용한 Joseph covariance는

P_plus = (I−KH) P_minus (I−KH)^T + K R0 K^T

이다. 같은 P_minus, H, R0가 주어진 **수용 갱신에서는 innovation 편향의 크기에 관계없이** 같은 covariance를 축소한다. 반면 참값 기준 error e_est=(x_est−x_true)에는 일차적으로 K*b_multipath 성분과 model-linearization/process residual이 남을 수 있다. **상태 mean과 모델이 주장하는 uncertainty가 다른 속도로 개선되는 것이 가능한 이유다.**

## 3. 누적 갱신과 gate의 실효

Full L2 ABC는 원래 3136개 epoch 중 **2767 accepted / 369 rejected** (11.77% 거절). 3D 99% chi-square gate가 가정하는 calibration과 차이가 크지만, 원본 시계열이 IID가 아니므로 독립적인 유의확률 검정을 하지 않는다.

R5-L2 ABC의 **게이트 전 전체 NIS mean=25.74**이지만, accepted subset만의 NIS mean=**2.83**이다. 따라서 accepted innovation만 검토하면 모델 실패가 가려질 수 있다. LoS에서도 ABC pose95는 B0 71.71%, L2 73.27%로 명목 95%를 충족하지 못한다. Full multipath의 기여가 크지만 Q/선형화/모델 bridge/initial-state 불일치도 분리해서 검증할 필요가 있다.

기존 Full ABC prior, H, K, S를 고정하고 같은 time/pose의 Native LoS z_r로 바꾼 **단일시점 반사실**에서, 양쪽 모두 게이트를 통과하는 사건에 한하여 Full-B0의 XY RMSE는 R2 0.1217→0.1193m, R4 0.1796→0.1766m, R5 0.2039→0.2022m로 변했다. 이는 수 mm 수준의 즉시 차이를 보여준다. **Full trajectory를 새로 재귀한 인과 효과는 아니다**. R2-AB에서는 LoS 한 단계 치환이 오히려 악화되는 반례도 존재한다. 장기 bias 축적과 filter update 이력을 독립적으로 분해한 실험이 필요하다.

## 4. R scale을 키워 해결되는가? — 고정 사후 탐색 실험

GitHub Actions [41443144573](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41443144573)에서 동일 원본 AB/ABC Native z_r, 4state EKF4, P2 controls, chi2 gates로 gamma=1,4,16,64의 R_gamma=gamma*R0을 적용했다. 원본 gamma=1을 전체 24개 trace에서 먼저 직접 재현하여 **상태 최대차 3.05e-14, P 최대차 2.50e-15, gate mismatch 0**과 원본 pooled 수치 차이 ≤1.83e-14을 확인했다. γ는 사후에 선택된 탐색 수준이며, R을 학습하거나 새로운 holdout을 실험한 것이 아니다.

| Full-L2 ABC | gamma=1 | gamma=4 | gamma=16 | gamma=64 |
|---|---:|---:|---:|---:|
| Heading RMSE (°) | **2.306** | 2.413 | 4.720 | 6.119 |
| XY RMSE (m) | **0.175** | 0.204 | 0.397 | 0.489 |
| Pose95 Coverage | 8.23% | 10.24% | 12.70% | 36.60% |
| accepted/3136 | 2767 | 3003 | 3110 | 3127 |

R을 늘리면 gain과 covariance뿐 아니라 innovation gate의 수용 패턴도 크게 바뀐다. **원본 gamma=1의 수용/거절 마스크를 고정**한 연구용 gamma=16에서는 Full-L2 ABC Heading 4.461°, XY 0.341m, Coverage 27.22%, accepted 2767로, 새 self-gate gamma16의 4.720°, 0.397m, Coverage 12.70%, accepted 3110과 다르다. 이 fixed-mask 실험은 gate 의존성을 분해하기 위한 비실전적 진단일 뿐이다.

결론적으로 단순 R inflation은 covariance overconfidence를 완화할 수 있으나 원래 trajectory에서 mean accuracy를 손상시켰고, nominal 95% coverage도 확보하지 못했다. 따라서 무조건 R을 크게 키우는 것을 검증된 해결책이라 주장하면 안 된다.

## 5. 논문에서 가능한 논리 / 미해결 원인

**데이터로 지지되는 설명:** 비공선 ABC range geometry로 XY 정보가 추가되어 Heading/XY mean error가 감소한다. 동시에 Full 채널에서는 고정 R0보다 훨씬 큰 앵커/위치별 first-path range residual이 존재하며, 정규 수용 갱신마다 필터가 그 오차구조를 반영하지 않고 P를 반복 축소한다. NIS 거절/수용 선택과 시간상관된 오차는 이를 악화시킬 수 있다. 이에 실제 오차 감소율보다 covariance 축소율이 큰 상황이 발생한다.

**아직 판정하지 않은 것:** (1) 원본 Range first-edge tap-jump의 각 기여, (2) cross-anchor covariance와 temporally correlated bias의 순수 인과적 비율, (3) EKF nonlinear approximation 및 Q 불일치의 독립 기여, (4) 새로운 R/noise model의 route-heldout 개선 및 타 장면 generalization. 원본 Full-L2 R4-ABC의 pose95=0%도 반례로 그대로 유지한다.

이 결과는 일부 조건의 필터 정확도 향상을 증명하지만, calibrated covariance나 independent-scene model proof는 아니다.

## 검증 기록 및 원본 산출물

- [전수 진단 Github Actions 41442514650](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41442514650): 7/7 QA PASS, 12 원본 trace, 84 state/P consistency, 48 update groups, 12 fixed-prior Full↔LoS counterfactual, 25088 per-step AB/ABC rows.
- [Source SHA와 7개 QA](../audits/P4_FULL_COV_FORENSICS_20261102/runs/41442514650/P4_COVARIANCE_MECHANISM_QA.json)
- [Full/LoS 실제 Range residual 및 lag1](../audits/P4_FULL_COV_FORENSICS_20261102/runs/41442514650/P4_RANGE_RESIDUAL_DISTRIBUTIONS.csv)
- [3×3 empirical cross-anchor covariance](../audits/P4_FULL_COV_FORENSICS_20261102/runs/41442514650/P4_CROSS_ANCHOR_ERROR_COVARIANCE.csv)
- [AB/ABC geometric information](../audits/P4_FULL_COV_FORENSICS_20261102/runs/41442514650/P4_RANGE_GEOMETRY_INFORMATION.csv)
- [Posterior covariance vs true error by case/mode/bias](../audits/P4_FULL_COV_FORENSICS_20261102/runs/41442514650/P4_FILTER_POSTERIOR_CONSISTENCY.csv)
- [All accepted/rejected update group statistics](../audits/P4_FULL_COV_FORENSICS_20261102/runs/41442514650/P4_ACCEPTED_UPDATE_MECHANISM.csv)
- [All 25088 per-step AB/ABC source events](../audits/P4_FULL_COV_FORENSICS_20261102/runs/41442514650/P4_AB_ABC_PER_STEP_EVENT_LEDGER.csv)
- [Full vs LoS fixed-prior counterfactual](../audits/P4_FULL_COV_FORENSICS_20261102/runs/41442514650/P4_FULL_LOS_FIXED_PRIOR_COUNTERFACTUAL.csv)
- [R inflation replay QA 41443144573](../audits/P4_FULL_COV_FORENSICS_20261102/R_SENSITIVITY_RUN_41443144573/P4_R_SCALE_SENSITIVITY_QA.json) 및 [40 pooled R sensitivity outcomes](../audits/P4_FULL_COV_FORENSICS_20261102/R_SENSITIVITY_RUN_41443144573/P4_R_SCALE_40_POOLED_METRICS.csv)

**판정:** 원본 데이터를 보존한 기술적 진단 PASS, R sensitivity numerical replay PASS. 메커니즘은 C0 내에서 부분 지지되지만 각 원인의 독립적 causal attribution과 held-out calibration은 미검증. 같은 ChatGPT 대화에서 분석·테스트를 작성했으며 별도 GitHub Actions runner는 독립적인 인간 peer reviewer 서명이 아니다.
