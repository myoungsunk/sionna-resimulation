# 두 Heading과 UWB Range 공동 EKF — 1차 실행 요약

## 1. 목적 및 범위
GitHub 복도 수치 기하(20 × 2.4 × 2.7 m, anchor (4,0,2.65) m, tag z=0.45 m)와 동일한 10 m 직선/네모/ㄹ자/지그재그 경로를 사용합니다. 모든 값은 합성 데이터입니다.
- Heading 1: IMU/Odom에서 얻은 상대 회전 증가량(각 step의 gyro error 및 누적 편향), Prediction Q.
- Heading 2: **별도 RF가 제공한다고 가정한 절대 world heading**(각 시점의 RF Heading 오차 및 편향), Update R. RF로 실제 구현한 센서 데이터가 아닙니다.
- RF range와 RF heading은 별도의 관측으로 공동 융합하며, 두 RF 오차 사이의 상관계수와 IMU/RF 노이즈 공유 가능성까지 별도로 검사합니다.
- 총 1,000개 독립 궤적을 경로별로 사용했습니다. 코어 348조건 + 관측 주기 및 동시 교차상관 보조 56조건 = 404개의 필터 조건.

## 2. 기본 Sensor ablation (표준편차: gyro 0.23°/step, RF Heading 1°, range 0.08 m)
| 경로 | DR RMSE | DR+Range RMSE | DR+RF Heading RMSE | DR+Range+RF Heading RMSE | Final 95% Coverage |
|---|---:|---:|---:|---:|---:|
| 직선 | 0.363 | 0.346 | 0.153 | **0.106** | 95.3% |
| 네모 | 0.171 | 0.115 | 0.154 | **0.091** | 95.2% |
| ㄹ자 | 0.191 | 0.145 | 0.156 | **0.101** | 94.2% |
| 지그재그 | 0.326 | 0.307 | 0.152 | **0.097** | 95.9% |

## 3. Heading 1 (IMU/Odom) vs Heading 2 (RF) bias/variance sweep
- gyro per-step random sigma: 0.08, 0.15, 0.23, 0.40, 0.60°; gyro bias: across the full 100 steps ±5°, ±2°, 0°.
- RF Heading per-sample sigma: 0.5, 1, 2, 3, 5, 10°; RF fixed bias: ±5°, ±2°, 0°.
- Fixed RF absolute Heading sigma=1° at every 0.5s: changing gyro sigma altered Heading RMSE but scarcely changed XY RMSE. This is the *high-rate good RF heading* regime, NOT an indication that gyro is redundant.
- Fixed gyro sigma=0.23°/step, RF heading sigma=1°: +2° **unmodeled RF heading bias** degrades straight 2D RMSE 0.106→0.232 m and final 95% coverage 95.3→10.1%.
- +5° cumulative gyro bias with RF heading unbiased and every 0.5s: nearly no deterioration. When RF Heading becomes sparse this changes (section 5).

## 4. Cross covariance: three errors, not one
Define independent or correlated per-epoch sensor errors $n_1$ (gyro increment), $n_r$ (range) and $n_2$ (RF heading). A nonzero Pearson correlation among observed *heading estimates* is not the same as a correlation among the *sensor noises*.
$$R_{RF}=\begin{bmatrix}\sigma_r^2&\rho_{r2}\sigma_r\sigma_2\\\rho_{r2}\sigma_r\sigma_2&\sigma_2^2\end{bmatrix}.$$
$$C_k=\operatorname{Cov}(e_k^-,n_{RF,k})=-G_k\begin{bmatrix}0&0\\0&\rho_{12}\sigma_1\sigma_2\end{bmatrix}.$$
$$S_k=H_kP_k^-H_k^T+R_{RF}+H_kC_k+C_k^TH_k^T.$$
$$K_k=(P_k^-H_k^T+C_k)S_k^{-1}.$$
With both $\rho_{r2}$ and $\rho_{12}$ nonzero, the full normalized noise correlation matrix must be positive semidefinite. For independent gyro and range errors we generate samples only when $\rho_{r2}^2+\rho_{12}^2<1$.

### RF Range–RF Heading correlation, straight route, rho=0.8
| Joint covariance | 2D RMSE (m) | Mean NEES | Final 95% coverage |
|---|---:|---:|---:|
| cov_correct | 0.1052 | 1.987 | 95.1% |
| cov_ignored | 0.1056 | 1.987 | 95.2% |

### RF Range+Gyro to RF Heading, each rho=0.5
| 공동 공분산 | 직선 RMSE (m) | 평균 Joint NIS (2DOF expectation=2) | Final 95% |
|---|---:|---:|---:|
| correct_full | 0.1055 | 1.999 | 95.0% |
| ignored_all | 0.1057 | 1.892 | 95.2% |

현재의 Gaussian·LoS·중앙 앵커·RF Heading 1° 구성에서는 동시점 상관을 무시해도 위치 RMSE 차이가 작았습니다. 이것이 모든 환경이나 다중경로에서 상관을 무시해도 된다는 뜻은 아닙니다. AR(1) 시간적 상관은 별도의 현상이며 이 1차 실험에 포함하지 않았습니다.

## 5. Heading 1이 의미 있는 조건: RF Heading 저주기/저정밀
직선, RF Heading sigma 5°, RF 업데이트 10초마다, bias1 = 0:
| Gyro sigma/step | 2D 위치 RMSE | 최종 95% 포함률 |
|---|---:|---:|
| 0.08° | 0.230 m | 93.8% |
| 0.60° | 0.252 m | 92.2% |

즉 RF Heading을 0.5초마다 얻을 때 보이지 않던 Heading 1 품질의 영향이, RF Heading이 느리고 부정확해지면 나타납니다.

## 6. 센서 오차와 궤적 오차의 상관(실제 Monte Carlo 표본에서 계산)
| 경로 | 최종 DR 누적 Heading RMSE | Raw RF Heading RMSE | 융합 Heading RMSE | corr(Heading1 error, DR y-error) | corr(fused-heading error, fused y-error) |
|---|---:|---:|---:|---:|---:|
| straight | 3.79° | 0.98° | 0.45° | 0.928 | 0.076 |
| rectangle | 3.66° | 0.97° | 0.45° | -0.164 | 0.008 |
| rieul | 3.86° | 0.96° | 0.45° | 0.824 | -0.016 |
| zigzag | 3.66° | 1.01° | 0.46° | 0.921 | 0.060 |

이 상관계수는 **실제 오차 간의 통계적 연관성**이며, 필터 측정오차 공분산 $R$의 비대각 원소와 동일한 뜻이 아닙니다.

## 7. 물리적 관측 가능성: RF Heading이 절대 Heading인가 상대 방위각인가
이번 주 실험의 Heading 2는 독립 world-yaw를 제공한다는 합성 상한 시나리오입니다. 단일 앵커 상대 방위각 $\alpha=\operatorname{atan2}(a_y-y,a_x-x)-\psi$만 제공한다면 전역 yaw 회전 게이지는 제거되지 않습니다.
| RF 모델 | 직선 2D RMSE | 최종 95% 포함률 |
|---|---:|---:|
| 절대 Heading 가정 | 0.106 m | 95.3% |
| 앵커 상대 Bearing | 0.342 m | 84.7% |

**RF에서 absolute heading을 실제로 추정할 수 있음이 검증되기 전까지 0.106 m 수치를 실험 달성 성능으로 주장하면 안 됩니다.** RF가 본질적으로 relative bearing인지, 독립 절대 yaw 관측인지 확인하는 것이 다음 연구 단계의 필수 Gate입니다.

## 8. Bootstrap 신뢰구간 (대응 Monte Carlo 주행 재표본)
| 경로 | DR+Range 대비 RMSE 개선율 | 95% Bootstrap CI |
|---|---:|---:|
| straight | 69.4% | 67.7–70.9% |
| rectangle | 20.8% | 18.8–22.8% |
| rieul | 30.5% | 27.8–33.0% |
| zigzag | 68.3% | 66.5–69.8% |

## 9. 파일 및 재현
- `dual_heading_sim.py` + `relationship_audit.py` + `cadence_and_jointcov.py` + `paired_bootstrap.py` — 독립 실행 가능한 전체 소스.
- `01_sensor_ablation.csv`부터 `13_paired_bootstrap.csv`까지 — 상세 결과.
- `01_...png`부터 `08_...png`까지 — 경로 그림·2차원 sweep·상관관계·궤적 오차.
- `QA_REPORT.json`과 `QA_INDEPENDENT.json` — 모델 수치 검증.
- 모든 로그는 synthetic이며 RF 수신 신호 시뮬레이션 및 실제 기기 주행 자료가 아닙니다.
