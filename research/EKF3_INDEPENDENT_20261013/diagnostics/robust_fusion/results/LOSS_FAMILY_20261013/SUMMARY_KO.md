# 3-state RF 손실 비교 결과

기준 커밋: 5b6549c964222d95d32b7307bd9c0b1d5594a6e4. 기존 FP s, B_OLD/E1 Range, 원본 SE(2) prediction, 초기 상태·공분산, R0 및 강건 가중 전 99% NIS gate를 유지했다. 새 ray tracing과 Gyro bias 상태 추가는 하지 않았다.

## 핵심 결과와 채택 판정

- 무편향 Full B_OLD Joint C: Cauchy가 네 모델 중 가장 낮은 Heading/위치 RMSE(0.5441deg/0.0837m)를 보였다. Pose NEES는 M0 49.75에서 9.31, 포함률은 18.06%에서 63.55%로 개선되지만 목표 95%에 미달한다.
- 무편향 Full B_OLD Joint C의 평균 개선에도 Cauchy는 7조건 중 Heading 2조건, 위치 1조건에서 M0보다 악화했다. Student-t도 Heading 3조건에서 악화했다. Huber는 해당 비교에서 Heading·위치 모두 7조건이 개선됐다.
- Student-t는 같은 조건에서 0.7868deg/0.1234m로 정확도가 개선되지만 Pose NEES 59.11 및 포함률 12.50%로 일관성이 M0보다 악화된다. 공통 관측 2차 모멘트 정합만으로 필터의 실제 포함률이 보장되지 않는다.
- Cauchy는 작은 bias L0 Full RF에서도 정확도 개선을 보였지만 L1/L2에서는 Heading·위치 오차가 M0보다 증가했다. L1 B_OLD Heading 4.3833→5.8922deg, L2 22.4532→25.4328deg이다.
- LoS noise_pair에서는 Cauchy의 Heading/위치 RMSE가 0.2586deg/0.0538m에서 0.3118deg/0.0647m로 증가했다. Full RF 개선을 전체 환경 개선으로 일반화할 수 없다.
- Full E1 noise_pair에서는 Cauchy의 Heading RMSE가 가장 낮고(0.6282deg), Student-t의 위치 RMSE가 근소하게 낮다(0.0965m). Cauchy의 포함률은 81.23%, Student-t는 17.30%로 정확도와 일관성의 순위가 다르다.
- 판정: Cauchy=EXPLORATORY_ONLY, Student-t=NOT_ADOPTED_AS_GENERAL_REPLACEMENT, Huber=EXPLORATORY_ONLY, M0=FROZEN_REFERENCE. 어느 손실도 모든 조건의 정확도·통계적 일관성을 함께 해결하지 않았다. 파라미터 사후 조정은 하지 않는다.

## 실행·검증

- 전체 4,032셀: noise_pair 및 gyro_bias Level 0/1/2 각각 1,008셀. 7 RF 조건 × 3 sensor seed × LoS B_OLD / Full B_OLD / Full E1 × D0/A/B/C × 4 모델.
- 원본 solver smoke 192셀 및 가속 solver smoke 192셀 통과. 단위·회귀 테스트 100 PASS.
- M0와 M-H는 각 조건의 기존 252셀 결과와 비교했다. 원본 D5 독립 재실행 검사는 조건당 12개 M0 셀이며, 이를 전체 D5 재실행으로 주장하지 않는다.
- 전체 trace의 NEES·95% 포함률·집계 지표를 재검산했다. 비교 허용치 1e-8 유지. 시점별 D0 pose/P는 네 모델이 동일하다.
- noise_pair에는 백색 센서 잡음이 있으며, 기존 D5 gyro_bias는 백색 Wheel/Gyro 잡음 없이 0.01/0.05/0.20 deg/s bias만 사용하는 서로 다른 조건이다.

## 학습 동결 및 해석

평가 route를 제외한 R2/R4/R5 홀드아웃 및 평가 XY 주변 0.25m buffer를 적용했다. case/pose별 한 번만 학습하며 seed를 독립 RF 표본처럼 복제하지 않았다. E1은 평가 route가 제외된 기존 outer-fold 계수로 학습 잔차를 구성했다. 평가 중 재학습이나 파라미터 재선택은 없다.

Huber delta=1.345는 기존 값이다. Cauchy scale은 학습 잔차의 zero-location Cauchy proxy 적합으로 고정했다. 필터에는 Cauchy M-estimator를 사용하며 R0는 정규화 척도이다. Cauchy에 유한 공분산이 있다고 주장하지 않는다. Student-t df는 학습 NLL로 사전 후보 중 선택하고 scale=(df-2)/df*R0로 공통 2차 모멘트를 맞췄다. C의 s/Range는 하나의 공동 블록이다.

M-C/M-T는 고정 prior와 한 번 선형화한 측정모델의 비볼록 MAP 해를 구한다. scalar solver는 원래 목적함수·gradient·Hessian 검사를 유지한다. 유한 정밀도 root 열거를 전역 최적성 증명으로 해석하지 않는다. 공분산은 effective R를 이용한 Joseph/IRLS 국소 Gaussian 근사이다.

## full / B_OLD — Joint C

| 조건 | 모델 | Heading RMSE (deg) | 위치 RMSE (m) | Pose NEES | Pose 95% (%) | Heading 95% (%) |
|---|---|---:|---:|---:|---:|---:|
| noise_pair | M0 Gaussian | 1.2744 | 0.2302 | 49.750 | 18.06 | 54.83 |
| noise_pair | M-H Huber | 0.9755 | 0.1799 | 34.807 | 23.06 | 61.65 |
| noise_pair | M-C Cauchy | 0.5441 | 0.0837 | 9.314 | 63.55 | 89.86 |
| noise_pair | M-T Student-t | 0.7868 | 0.1234 | 59.111 | 12.50 | 50.78 |
| gyro L0 | M0 Gaussian | 1.7380 | 0.2603 | 74.909 | 12.92 | 31.28 |
| gyro L0 | M-H Huber | 1.4149 | 0.2058 | 56.189 | 12.69 | 33.83 |
| gyro L0 | M-C Cauchy | 1.1815 | 0.1366 | 20.593 | 15.01 | 51.45 |
| gyro L0 | M-T Student-t | 1.1678 | 0.1419 | 106.107 | 6.27 | 21.86 |
| gyro L1 | M0 Gaussian | 4.3833 | 0.4336 | 578.387 | 2.01 | 6.07 |
| gyro L1 | M-H Huber | 4.5076 | 0.4411 | 526.324 | 1.93 | 5.32 |
| gyro L1 | M-C Cauchy | 5.8922 | 0.6010 | 310.929 | 2.52 | 6.72 |
| gyro L1 | M-T Student-t | 4.4086 | 0.4164 | 860.118 | 0.40 | 2.48 |
| gyro L2 | M0 Gaussian | 22.4532 | 2.2914 | 9709.367 | 0.00 | 0.00 |
| gyro L2 | M-H Huber | 23.0715 | 2.3639 | 9331.708 | 0.00 | 0.00 |
| gyro L2 | M-C Cauchy | 25.4328 | 2.5706 | 5871.372 | 0.00 | 0.03 |
| gyro L2 | M-T Student-t | 23.6925 | 2.4214 | 13409.573 | 0.00 | 0.00 |

## full / E1_FULL_LORO — Joint C

| 조건 | 모델 | Heading RMSE (deg) | 위치 RMSE (m) | Pose NEES | Pose 95% (%) | Heading 95% (%) |
|---|---|---:|---:|---:|---:|---:|
| noise_pair | M0 Gaussian | 0.9414 | 0.1531 | 24.238 | 33.14 | 55.13 |
| noise_pair | M-H Huber | 0.8114 | 0.1313 | 21.546 | 38.85 | 60.38 |
| noise_pair | M-C Cauchy | 0.6282 | 0.0990 | 19.715 | 81.23 | 91.55 |
| noise_pair | M-T Student-t | 0.7300 | 0.0965 | 44.225 | 17.30 | 45.33 |
| gyro L0 | M0 Gaussian | 1.3318 | 0.1759 | 68.007 | 15.94 | 29.58 |
| gyro L0 | M-H Huber | 1.1950 | 0.1498 | 65.952 | 18.29 | 32.19 |
| gyro L0 | M-C Cauchy | 1.1711 | 0.1355 | 18.210 | 32.62 | 52.24 |
| gyro L0 | M-T Student-t | 1.1466 | 0.1218 | 93.988 | 4.05 | 19.56 |
| gyro L1 | M0 Gaussian | 4.3552 | 0.4249 | 484.954 | 2.66 | 5.04 |
| gyro L1 | M-H Huber | 4.4903 | 0.4319 | 550.052 | 2.62 | 3.91 |
| gyro L1 | M-C Cauchy | 5.9833 | 0.6031 | 330.349 | 5.82 | 6.67 |
| gyro L1 | M-T Student-t | 4.4606 | 0.4191 | 1197.479 | 1.52 | 2.32 |
| gyro L2 | M0 Gaussian | 22.7039 | 2.2983 | 9810.185 | 0.00 | 0.00 |
| gyro L2 | M-H Huber | 23.2413 | 2.3639 | 9594.962 | 0.00 | 0.00 |
| gyro L2 | M-C Cauchy | 25.8753 | 2.6096 | 5569.445 | 0.00 | 0.06 |
| gyro L2 | M-T Student-t | 23.8729 | 2.4301 | 14987.622 | 0.00 | 0.00 |

## los / B_OLD — Joint C

| 조건 | 모델 | Heading RMSE (deg) | 위치 RMSE (m) | Pose NEES | Pose 95% (%) | Heading 95% (%) |
|---|---|---:|---:|---:|---:|---:|
| noise_pair | M0 Gaussian | 0.2586 | 0.0538 | 16.063 | 74.68 | 97.83 |
| noise_pair | M-H Huber | 0.2588 | 0.0538 | 17.216 | 74.86 | 97.83 |
| noise_pair | M-C Cauchy | 0.3118 | 0.0647 | 5.195 | 85.19 | 100.00 |
| noise_pair | M-T Student-t | 0.2617 | 0.0589 | 48.393 | 36.45 | 79.43 |
| gyro L0 | M0 Gaussian | 0.6373 | 0.0833 | 28.671 | 31.45 | 49.50 |
| gyro L0 | M-H Huber | 0.6376 | 0.0834 | 28.598 | 31.33 | 49.36 |
| gyro L0 | M-C Cauchy | 0.8861 | 0.1154 | 15.842 | 24.91 | 60.71 |
| gyro L0 | M-T Student-t | 0.5728 | 0.0812 | 116.395 | 13.19 | 33.62 |
| gyro L1 | M0 Gaussian | 3.0778 | 0.3380 | 514.822 | 4.55 | 4.97 |
| gyro L1 | M-H Huber | 3.1207 | 0.3470 | 420.493 | 4.55 | 4.97 |
| gyro L1 | M-C Cauchy | 5.4017 | 0.5836 | 265.284 | 3.90 | 8.83 |
| gyro L1 | M-T Student-t | 2.8549 | 0.3159 | 489.367 | 1.29 | 1.63 |
| gyro L2 | M0 Gaussian | 20.3237 | 2.1809 | 9058.096 | 0.00 | 0.00 |
| gyro L2 | M-H Huber | 21.3653 | 2.2678 | 8356.929 | 0.00 | 0.00 |
| gyro L2 | M-C Cauchy | 25.4200 | 2.5811 | 4597.999 | 0.10 | 0.15 |
| gyro L2 | M-T Student-t | 21.8939 | 2.2956 | 12357.415 | 0.00 | 0.00 |

## 경로별 악화 및 대조군

| 조건 | 채널/Range | 모델 | Joint Heading 악화 조건수 / 7 | Joint 위치 악화 조건수 / 7 |
|---|---|---|---:|---:|
| gyro_bias L0 | full/B_OLD | M-H Huber | 2 | 0 |
| gyro_bias L0 | full/B_OLD | M-C Cauchy | 5 | 3 |
| gyro_bias L0 | full/B_OLD | M-T Student-t | 4 | 1 |
| gyro_bias L0 | full/E1_FULL_LORO | M-H Huber | 2 | 0 |
| gyro_bias L0 | full/E1_FULL_LORO | M-C Cauchy | 3 | 3 |
| gyro_bias L0 | full/E1_FULL_LORO | M-T Student-t | 5 | 1 |
| gyro_bias L0 | los/B_OLD | M-H Huber | 2 | 3 |
| gyro_bias L0 | los/B_OLD | M-C Cauchy | 7 | 7 |
| gyro_bias L0 | los/B_OLD | M-T Student-t | 0 | 4 |
| gyro_bias L1 | full/B_OLD | M-H Huber | 6 | 5 |
| gyro_bias L1 | full/B_OLD | M-C Cauchy | 7 | 7 |
| gyro_bias L1 | full/B_OLD | M-T Student-t | 5 | 5 |
| gyro_bias L1 | full/E1_FULL_LORO | M-H Huber | 6 | 5 |
| gyro_bias L1 | full/E1_FULL_LORO | M-C Cauchy | 7 | 7 |
| gyro_bias L1 | full/E1_FULL_LORO | M-T Student-t | 5 | 4 |
| gyro_bias L1 | los/B_OLD | M-H Huber | 7 | 6 |
| gyro_bias L1 | los/B_OLD | M-C Cauchy | 7 | 7 |
| gyro_bias L1 | los/B_OLD | M-T Student-t | 1 | 2 |
| gyro_bias L2 | full/B_OLD | M-H Huber | 7 | 7 |
| gyro_bias L2 | full/B_OLD | M-C Cauchy | 7 | 7 |
| gyro_bias L2 | full/B_OLD | M-T Student-t | 7 | 7 |
| gyro_bias L2 | full/E1_FULL_LORO | M-H Huber | 7 | 7 |
| gyro_bias L2 | full/E1_FULL_LORO | M-C Cauchy | 7 | 7 |
| gyro_bias L2 | full/E1_FULL_LORO | M-T Student-t | 7 | 7 |
| gyro_bias L2 | los/B_OLD | M-H Huber | 7 | 7 |
| gyro_bias L2 | los/B_OLD | M-C Cauchy | 7 | 7 |
| gyro_bias L2 | los/B_OLD | M-T Student-t | 7 | 7 |
| noise_pair L1 | full/B_OLD | M-H Huber | 0 | 0 |
| noise_pair L1 | full/B_OLD | M-C Cauchy | 2 | 1 |
| noise_pair L1 | full/B_OLD | M-T Student-t | 3 | 0 |
| noise_pair L1 | full/E1_FULL_LORO | M-H Huber | 0 | 0 |
| noise_pair L1 | full/E1_FULL_LORO | M-C Cauchy | 1 | 1 |
| noise_pair L1 | full/E1_FULL_LORO | M-T Student-t | 3 | 1 |
| noise_pair L1 | los/B_OLD | M-H Huber | 2 | 3 |
| noise_pair L1 | los/B_OLD | M-C Cauchy | 5 | 6 |
| noise_pair L1 | los/B_OLD | M-T Student-t | 3 | 3 |

D0/A/B/C 전체 결과와 p95 오차는 POOLED_METRICS.csv, CASE_METRICS.csv, VERIFIED_CELL_METRICS.csv에 저장했다. PAIRED_CELL_CONTRASTS.csv는 같은 case/seed의 M0 대비 차이이며 시간 시점을 독립 표본으로 처리한 유의성 검정은 하지 않았다.

## 판정 범위

재현성·실행 완료와 정확도·통계적 일관성 및 독립 환경 일반화는 별개이다. 이 비교는 기존 단일 RF 장면의 탐색적 결과이며 기존 E1 모델군 선택 이력도 남아 있다. 독립 scene과 별도 seed 확증은 수행하지 않았다. Gaussian NIS gate를 공통 유지했지만 강건 posterior가 Gaussian이라는 뜻은 아니다. scientific_PASS=false를 유지한다.

원본 코드와 동결 입력·이전 결과는 수정하지 않았다. 원시 trace·소스·입력 캐시·실행 로그는 분할 EVIDENCE.zip과 RESTORE_EVIDENCE.py로 복원할 수 있다. RESULT_MANIFEST.json과 각 실행 MANIFEST.json에 SHA-256이 기록되어 있다.
