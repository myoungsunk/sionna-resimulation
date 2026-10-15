# G2/G3 P3–P4 실행 결과 종합 브리핑 (2026-10-15 확인)

## 실제 실행과 출처
- 브랜치: research/g2g3-p0-p6-execution-20261014
- P3 물리적 비선형 G3 및 G2-EKF-S 대표 시점: [Run 38580298879](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38580298879), [artifact 11902209334](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38580298879/artifacts/11902209334)
- P4 전체 One-step Jacobian 기반 G2/G3 EKF 근사 factorial: [Run 38580884160](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38580884160), 7개 성공 job/artifact.
- 사전 감사: P34_SOURCE_REVIEW_KO.md, APPROVAL_P3.json, APPROVAL_P4.json, p34_gate.py 및 7개 P4 per-case PRE_RUN.
- P3와 P4 수치 비교에서 **P3 G3 Joint nonlinear integral**과 **P4 G3 Joint EKF linearized**의 서로 다른 추정 알고리즘을 혼동 금지.
- P3/P4 계산의 RF는 원본 동결 R0이다. B2 office-signed likelihood나 DR fault mixture의 신규 3state joint filter는 사용하지 않았다.
- 추정과 점수 계산 구분: 원본 일치 검사와 계산은 정답 누수 없이 진행, 실제 오류/NEES 계산 때만 Ground Truth 사용.

## 1. 네 가지 판정
| 검증 | 실행 | 계산 유효성 | 가설 결과 | 과학적 주장 |
|---|---|---|---|---|
| P3 물리 3state posterior | PASS | 대표 세 조건 x 두 방법, **6/6 수치 PASS**, covariance 저장 | 큰 gyro bias에서 G3 위치 개선과 Heading 악화 공존 | 오직 세 조건만; full nonlinear G2-exact vs G3-exact 비교 아님 |
| P4 full-factorial EKF | 7/7 job PASS | **각 방법 223,236건, 5개 방법 총 1,116,180 성공, 0 기록상 계산 실패** | gated G2/G3 EKF 위치 RMSE 소폭 개선, ungated G3 악화 | R0 기하/조건에서만 one-step EKF 성능 주장 가능, 독립 RF scene/generalization 아님 |
| B2 signed RF + DR fault | NOT_INTEGRATED | NOT_EVALUATED | 이후 별도 실험 필요 | 해당 model의 full 3state 우월성 주장 금지 |
| P5 recursive/P6 final | NOT_RUN | NOT_RUN | NOT_EVALUATED | scientific_PASS=false |

## 2. P3 실제 대표 시점
| Case / DR | method | xy error m | heading abs error deg | status |
|---|---|---:|---:|---|
| R2_aA_m0 gyro_bias L2 seed0 sample978 195.6s LoS B_OLD | G2_EKF_S | 6.2386 | 24.5895 | numerical PASS |
| same | G3_JOINT | 5.0878 | 52.6284 | numerical PASS |
| R2_aA_m0 gyro_bias L0 seed0 sample978 195.6s | G2_EKF_S | .2270 | .5185 | numerical PASS |
| same | G3_JOINT | .2267 | .5302 | numerical PASS |
| R4_aA_m0 gyro_bias L0 seed0 sample550 110s Full E1 | G2_EKF_S | .2870 | 1.4037 | numerical PASS |
| same | G3_JOINT | .3394 | 1.6265 | numerical PASS |

P3 includes full 3x3 Gaussian posterior moment/cross-cov fields mean_x/y/psi, Pxx/Pxy/Pyy/Pxpsi/Pypsi/Ppsipsi, Heading MAP and posterior TV. These are **posterior moments**, not independently calibrated normal 95% coverage.
R2 L2 demonstrates numerical convergence does NOT imply accuracy; G3 improves XY vs G2 but worsens Heading. An individual worsening is an expected result to count, not an execution failure.

## 3. P4 Full factorial pooled summary (2026-10-15 offline independent recomputation of 7 archived per-case condition_summary)
7 cases x 4 DR condition x 3 sensor seed x 3 RF arm yields all evaluation instants with time >= 30s.
Per-method matched N=223,236. Five methods total attempts 1,116,180, valid 1,116,180, recorded invalid 0.
RMSE pooled as sqrt(sum(n_group * RMSE_group²)/sum(n_group)); metric uses equal weight per time/sample row, not independent-scene confidence.

| Method | xy RMSE m | heading RMSE deg | pooled pose 95% empirical coverage |
|---|---:|---:|---:|
| DR | 1.5325 | 14.8607 | .501 |
| G0_S_EKF | 1.5212 | 14.3130 | .492 |
| G2_RANGE_S_EKF | 1.5150 | 14.5316 | .482 |
| G3_JOINT_EKF_GATE | 1.5122 | 14.5285 | .484 |
| G3_JOINT_EKF_NOGATE | 1.5638 | 15.4284 | .470 |

L2 condition-only N=55,809 matched rows per method:
| method | xy RMSE m | heading RMSE deg | pose95 |
|---|---:|---:|---:|
| DR | 2.8766 | 28.4917 | .0181 |
| G0_S_EKF | 2.8134 | 27.6381 | .0208 |
| G2_RANGE_S_EKF | 2.7876 | 27.8205 | .0201 |
| G3_JOINT_EKF_GATE | 2.7888 | 27.9010 | .0205 |
| G3_JOINT_EKF_NOGATE | 2.7153 | 29.5089 | .0206 |

Low bias L0 condition-only N=55,809:
| method | xy RMSE m | heading RMSE deg |
|---|---:|---:|
| DR | .4587 | 2.8363 |
| G2_RANGE_S_EKF | .5908 | 2.9628 |
| G3_JOINT_EKF_GATE | .5784 | 2.9229 |
| G3_JOINT_EKF_NOGATE | .8165 | 3.6538 |

P4 shows mild pooled gated EKF xy improvement (~1.3%, non-independent block pooled); L0 worsening, L2 slight gains, and some ungated L2 XY benefits at the cost of Heading error. All exceptions remain in outputs.
**Crucial scientific caveat:** P4 covariance is substantially overconfident in large gyro bias. DR L2 pose NEES average 1785.2 and pose95 1.81%; G3 gated L2 average NEES 1807.0 and pose95 2.05%. Improved xy RMSE alone does not establish coherent covariance or filter scientific PASS. P4 sensor seeds share RF scenes; blocked independent scene confidence not established.

## 4. Objective next stage
P3 physical numerical testing and full P4 EKF analysis are accomplished; important next gap is a **full nonlinear G2-exact/G3-exact across the complete factorial**, incorporating consistent signed RF likelihood, actual DR bias propagation, and full covariance vs posthoc truth. P4 EKF results must never be presented as full nonlinear exact G3. P5 recursive not run. No retroactive scientific pass.
