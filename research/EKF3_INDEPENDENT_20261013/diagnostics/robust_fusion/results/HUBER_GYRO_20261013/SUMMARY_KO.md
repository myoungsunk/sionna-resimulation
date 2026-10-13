# 고정 Huber-only: D5 gyro_bias 확장 실험

기준 커밋: `7a499d760bc645624ac3b1f8f844c657b767c300`. 원본 FP s·B_OLD/E1·3-state·R0·Huber 1.345·보정 전 NIS 99% gate를 고정했다. 학습·파라미터 탐색·새 ray tracing을 하지 않았다.

## 핵심 결과

Huber-only의 무편향 Full RF 이득은 정확히 재현됐으나, Gyro bias 전 수준으로 일반화되지 않았다. Level0(0.01°/s)에서는 Full RF의 평균 Heading/위치 RMSE가 B_OLD와 E1 모두 개선됐다. 다만 Heading은7조건 중2조건에서 악화됐고 B_OLD Pose 포함률은12.92%→12.69%로 조금 낮아져, 일관성이 함께 개선됐다고 단정할 수 없다.

Level1(0.05°/s)에서는 LoS/Full의 세 조합 모두 Joint C Heading/위치 RMSE가 증가했다. Full의 B_OLD/E1 각각 Heading 악화6/7조건, 위치 악화5/7조건이다. Level2(0.20°/s)에서는 세 조합 모두7/7조건에서 두 RMSE가 증가했고 Pose95%포함률은 양모델 모두0%이다. 수치 발산/공분산 오류가 없다는 것은 정확도·일관성의 성공을 뜻하지 않는다.

Full B_OLD Joint C의 Level2에서는 NIS 거부율이58.54%→60.73%, Heading p95가42.87°→43.67°로 증가했다. 이는 Bias가 있는 재귀 과정에서 관측 처리 효과가 달라진 결과이며, 원인을 Huber 또는 gate 하나로 확정하는 별도 ablation은 이번에 하지 않았다. 큰 Bias를 추정하지 않는3-state에서 Huber만 추가해 해결됐다는 주장은 지지되지 않는다.

판정: `reproducibility=PASS`, `execution=PASS`, `low_bias_full_RF_accuracy=EXPLORATORY_BENEFIT`, `general_adoption=NOT_ADOPTED`, `statistical_consistency=NOT_PASS`, `scientific_PASS=false`. 임계값을 변경하지 않았으며 이번 실패를 이유로 후속 모델을 자동 채택하지 않는다.

## 검증 상태

- 단위·회귀 테스트: 54 PASS. 네 조건의 smoke: 각24셀, 합계96셀 PASS.
- 무편향 전체504셀: 두모델 각각252셀의 기존 결과와 parity PASS. 최대 차이0; 허용치1e-8 유지.
- gyro_bias: Level당504셀, 총1512셀 실제 완료. 전체2016셀의 trace를 재집계했다.
- 각 실행마다 원본 D5 함수로12 M0셀을 독립 대조했다. 이는 전체 gyro 252 M0셀에 대한 독립 재실행이라고 주장하지 않는다.
- D0는 두모델의 매시점 pose/P가 완전히 일치한다. 공분산 양의 정부호, 유한값, 소스·입력 해시 검사를 통과했다.
- 평가 trace 총 1,785,888행; 집계 최대 절대오차 7.28e-12, Pose NEES 재계산 최대차이 7.64e-11. Heading NEES도 재계산했고, 두95%포함률의 시점별 판정은 정확히 일치한다.

## 조건 해석

D5 gyro_bias는 gyro bias만 활성화하며 Wheel/Gyro 백색잡음은 꺼진다. noise_pair에 bias를 더한 실험이 아니다. Bias 크기는 L0/L1/L2에서0.01/0.05/0.20°/s이며 부호는 동결 sensor seed stream이다. 두모델 모두 Bias 상태를 추정하지 않는다.

LoS는 원래 B_OLD, Full은 B_OLD/E1의 기존 세 조합을 유지했다. E1은 Full RF용 기존 route-LORO 보정으로 새로 학습하지 않았다. 평가 시작은30초이며 7 RF조건×3seed×4관측구성×3채널/보정조합×2모델이다.

### 실제 seed별 Bias

| 조건 | seed | 실제 bias (°/s) |
|---|---:|---:|
| Gyro L0 | 0 | 0.010 |
| Gyro L0 | 1 | -0.010 |
| Gyro L0 | 2 | 0.010 |
| Gyro L1 | 0 | 0.050 |
| Gyro L1 | 1 | -0.050 |
| Gyro L1 | 2 | 0.050 |
| Gyro L2 | 0 | 0.200 |
| Gyro L2 | 1 | -0.200 |
| Gyro L2 | 2 | 0.200 |
| 무편향 noise_pair | 0 | 0.000 |
| 무편향 noise_pair | 1 | 0.000 |
| 무편향 noise_pair | 2 | 0.000 |

## Joint C 결과

각 셀은 **M0 → Huber-only**. RMSE는 전체 평가표본의 오차제곱을 합산한 뒤 계산했다. 이는 독립 반복표본의 평균 또는 통계적 유의성 검정이 아니다.

| 조건 | RF / Range | Heading RMSE (°) | 위치 RMSE (m) | Pose NEES | Pose 95% 포함률 |
|---|---|---:|---:|---:|---:|
| Gyro L0 | full/B_OLD | 1.738 → 1.415 | 0.260 → 0.206 | 74.91 → 56.19 | 12.9% → 12.7% |
| Gyro L0 | full/E1_FULL_LORO | 1.332 → 1.195 | 0.176 → 0.150 | 68.01 → 65.95 | 15.9% → 18.3% |
| Gyro L0 | los/B_OLD | 0.637 → 0.638 | 0.083 → 0.083 | 28.67 → 28.60 | 31.4% → 31.3% |
| Gyro L1 | full/B_OLD | 4.383 → 4.508 | 0.434 → 0.441 | 578.39 → 526.32 | 2.0% → 1.9% |
| Gyro L1 | full/E1_FULL_LORO | 4.355 → 4.490 | 0.425 → 0.432 | 484.95 → 550.05 | 2.7% → 2.6% |
| Gyro L1 | los/B_OLD | 3.078 → 3.121 | 0.338 → 0.347 | 514.82 → 420.49 | 4.5% → 4.5% |
| Gyro L2 | full/B_OLD | 22.453 → 23.072 | 2.291 → 2.364 | 9709.37 → 9331.71 | 0.0% → 0.0% |
| Gyro L2 | full/E1_FULL_LORO | 22.704 → 23.241 | 2.298 → 2.364 | 9810.19 → 9594.96 | 0.0% → 0.0% |
| Gyro L2 | los/B_OLD | 20.324 → 21.365 | 2.181 → 2.268 | 9058.10 → 8356.93 | 0.0% → 0.0% |
| 무편향 noise_pair | full/B_OLD | 1.274 → 0.975 | 0.230 → 0.180 | 49.75 → 34.81 | 18.1% → 23.1% |
| 무편향 noise_pair | full/E1_FULL_LORO | 0.941 → 0.811 | 0.153 → 0.131 | 24.24 → 21.55 | 33.1% → 38.8% |
| 무편향 noise_pair | los/B_OLD | 0.259 → 0.259 | 0.054 → 0.054 | 16.06 → 17.22 | 74.7% → 74.9% |

## Joint C 경로조건별 악화

각 조건은3seed를 합산한다. 아래 수는7 RF조건 중 Huber가 악화된 수이다. 수치상 동률 허용치1e-8은 기존 재현 허용치이며 통계적 유의성 기준이 아니다.

| 조건 | RF / Range | Heading RMSE 증가 | 위치 RMSE 증가 | Pose NEES 증가 | Pose 포함률 감소 |
|---|---|---:|---:|---:|---:|
| Gyro L0 | full/B_OLD | 2/7 | 0/7 | 0/7 | 2/7 |
| Gyro L0 | full/E1_FULL_LORO | 2/7 | 0/7 | 1/7 | 0/7 |
| Gyro L0 | los/B_OLD | 2/7 | 3/7 | 3/7 | 3/7 |
| Gyro L1 | full/B_OLD | 6/7 | 5/7 | 4/7 | 1/7 |
| Gyro L1 | full/E1_FULL_LORO | 6/7 | 5/7 | 6/7 | 2/7 |
| Gyro L1 | los/B_OLD | 7/7 | 6/7 | 5/7 | 1/7 |
| Gyro L2 | full/B_OLD | 7/7 | 7/7 | 1/7 | 0/7 |
| Gyro L2 | full/E1_FULL_LORO | 7/7 | 7/7 | 1/7 | 0/7 |
| Gyro L2 | los/B_OLD | 7/7 | 7/7 | 2/7 | 0/7 |
| 무편향 noise_pair | full/B_OLD | 0/7 | 0/7 | 0/7 | 0/7 |
| 무편향 noise_pair | full/E1_FULL_LORO | 0/7 | 0/7 | 1/7 | 0/7 |
| 무편향 noise_pair | los/B_OLD | 2/7 | 3/7 | 2/7 | 0/7 |

## 관측 구성별 비교

D0/A/B/C 전체를 같은 방식으로 평가했다. `POOLED_METRICS.csv`에는 Heading/위치 RMSE와95%오차분위수, Pose/Heading NEES·포함률, NIS 거부율, 사후/사전 공분산 비율을 모두 저장했다. `VERIFIED_CELL_METRICS.csv`, `PAIRED_CELL_CONTRASTS.csv`, `CASE_METRICS.csv`에서 조건/seed별 차이를 확인할 수 있다.

| 조건 | RF / Range | 관측 | Heading RMSE (°) | 위치 RMSE (m) | NIS 거부율 |
|---|---|---|---:|---:|---:|---:|
| Gyro L0 | full/B_OLD | A | 1.444 → 1.377 | 0.262 → 0.246 | 8.9% → 8.9% |
| Gyro L0 | full/B_OLD | B | 5.451 → 5.267 | 0.968 → 0.933 | 3.8% → 3.8% |
| Gyro L0 | full/B_OLD | C | 1.738 → 1.415 | 0.260 → 0.206 | 9.1% → 9.2% |
| Gyro L0 | full/B_OLD | D0 | 2.836 → 2.836 | 0.459 → 0.459 | 0.0% → 0.0% |
| Gyro L0 | full/E1_FULL_LORO | A | 1.444 → 1.377 | 0.262 → 0.246 | 8.9% → 8.9% |
| Gyro L0 | full/E1_FULL_LORO | B | 2.293 → 2.335 | 0.353 → 0.355 | 3.3% → 3.3% |
| Gyro L0 | full/E1_FULL_LORO | C | 1.332 → 1.195 | 0.176 → 0.150 | 8.5% → 8.5% |
| Gyro L0 | full/E1_FULL_LORO | D0 | 2.836 → 2.836 | 0.459 → 0.459 | 0.0% → 0.0% |
| Gyro L0 | los/B_OLD | A | 0.644 → 0.644 | 0.111 → 0.111 | 0.0% → 0.0% |
| Gyro L0 | los/B_OLD | B | 1.894 → 1.892 | 0.242 → 0.242 | 0.0% → 0.0% |
| Gyro L0 | los/B_OLD | C | 0.637 → 0.638 | 0.083 → 0.083 | 0.0% → 0.0% |
| Gyro L0 | los/B_OLD | D0 | 2.836 → 2.836 | 0.459 → 0.459 | 0.0% → 0.0% |
| Gyro L1 | full/B_OLD | A | 4.811 → 4.800 | 0.564 → 0.559 | 10.3% → 10.5% |
| Gyro L1 | full/B_OLD | B | 7.586 → 7.523 | 1.088 → 1.074 | 3.9% → 4.1% |
| Gyro L1 | full/B_OLD | C | 4.383 → 4.508 | 0.434 → 0.441 | 10.4% → 11.7% |
| Gyro L1 | full/B_OLD | D0 | 7.599 → 7.599 | 0.851 → 0.851 | 0.0% → 0.0% |
| Gyro L1 | full/E1_FULL_LORO | A | 4.811 → 4.800 | 0.564 → 0.559 | 10.3% → 10.5% |
| Gyro L1 | full/E1_FULL_LORO | B | 7.187 → 7.275 | 0.756 → 0.761 | 3.2% → 3.2% |
| Gyro L1 | full/E1_FULL_LORO | C | 4.355 → 4.490 | 0.425 → 0.432 | 10.3% → 10.7% |
| Gyro L1 | full/E1_FULL_LORO | D0 | 7.599 → 7.599 | 0.851 → 0.851 | 0.0% → 0.0% |
| Gyro L1 | los/B_OLD | A | 3.186 → 3.200 | 0.460 → 0.461 | 0.1% → 0.1% |
| Gyro L1 | los/B_OLD | B | 7.299 → 7.346 | 0.716 → 0.721 | 0.0% → 0.1% |
| Gyro L1 | los/B_OLD | C | 3.078 → 3.121 | 0.338 → 0.347 | 0.1% → 0.8% |
| Gyro L1 | los/B_OLD | D0 | 7.599 → 7.599 | 0.851 → 0.851 | 0.0% → 0.0% |
| Gyro L2 | full/B_OLD | A | 23.101 → 23.355 | 2.491 → 2.501 | 49.4% → 50.2% |
| Gyro L2 | full/B_OLD | B | 25.386 → 25.149 | 2.696 → 2.690 | 31.6% → 33.4% |
| Gyro L2 | full/B_OLD | C | 22.453 → 23.072 | 2.291 → 2.364 | 58.5% → 60.7% |
| Gyro L2 | full/B_OLD | D0 | 28.492 → 28.492 | 2.877 → 2.877 | 0.0% → 0.0% |
| Gyro L2 | full/E1_FULL_LORO | A | 23.101 → 23.355 | 2.491 → 2.501 | 49.4% → 50.2% |
| Gyro L2 | full/E1_FULL_LORO | B | 26.068 → 26.159 | 2.605 → 2.637 | 35.3% → 36.3% |
| Gyro L2 | full/E1_FULL_LORO | C | 22.704 → 23.241 | 2.298 → 2.364 | 57.9% → 59.6% |
| Gyro L2 | full/E1_FULL_LORO | D0 | 28.492 → 28.492 | 2.877 → 2.877 | 0.0% → 0.0% |
| Gyro L2 | los/B_OLD | A | 20.924 → 21.489 | 2.399 → 2.414 | 46.6% → 48.5% |
| Gyro L2 | los/B_OLD | B | 26.521 → 26.525 | 2.653 → 2.662 | 30.4% → 31.4% |
| Gyro L2 | los/B_OLD | C | 20.324 → 21.365 | 2.181 → 2.268 | 52.7% → 57.0% |
| Gyro L2 | los/B_OLD | D0 | 28.492 → 28.492 | 2.877 → 2.877 | 0.0% → 0.0% |
| 무편향 noise_pair | full/B_OLD | A | 1.139 → 0.985 | 0.252 → 0.224 | 8.8% → 8.9% |
| 무편향 noise_pair | full/B_OLD | B | 5.671 → 4.946 | 1.013 → 0.896 | 3.8% → 3.9% |
| 무편향 noise_pair | full/B_OLD | C | 1.274 → 0.975 | 0.230 → 0.180 | 8.9% → 9.1% |
| 무편향 noise_pair | full/B_OLD | D0 | 2.406 → 2.406 | 0.429 → 0.429 | 0.0% → 0.0% |
| 무편향 noise_pair | full/E1_FULL_LORO | A | 1.139 → 0.985 | 0.252 → 0.224 | 8.8% → 8.9% |
| 무편향 noise_pair | full/E1_FULL_LORO | B | 1.993 → 2.061 | 0.327 → 0.329 | 3.2% → 3.3% |
| 무편향 noise_pair | full/E1_FULL_LORO | C | 0.941 → 0.811 | 0.153 → 0.131 | 8.4% → 8.4% |
| 무편향 noise_pair | full/E1_FULL_LORO | D0 | 2.406 → 2.406 | 0.429 → 0.429 | 0.0% → 0.0% |
| 무편향 noise_pair | los/B_OLD | A | 0.250 → 0.250 | 0.065 → 0.065 | 0.0% → 0.0% |
| 무편향 noise_pair | los/B_OLD | B | 1.293 → 1.290 | 0.187 → 0.186 | 0.0% → 0.0% |
| 무편향 noise_pair | los/B_OLD | C | 0.259 → 0.259 | 0.054 → 0.054 | 0.0% → 0.0% |
| 무편향 noise_pair | los/B_OLD | D0 | 2.406 → 2.406 | 0.429 → 0.429 | 0.0% → 0.0% |

## 판정 경계

재현성 PASS와 모델 채택은 별도이다. Accuracy와 NEES/coverage를 함께 읽어야 하며 RMSE 개선만으로 통계적 일관성 또는 Bias 보정 성공을 주장하지 않는다. Huber는 gate를 통과한 관측의 가중치만 바꾸지만 이후의 상태와 공분산이 달라져 이후 gate 통과율도 달라질 수 있다.

7조건은7개의 독립 RF scene이 아니다. 단일 장면, 동일 공간의 상관,3seed의 제한, E1 모델선택 및 공간중복 이력을 유지한다. 수치 방향만으로 독립환경 일반화·유의성·최종 채택을 확정하지 않는다. 파라미터 변경 없이 별도 seed와 독립 scene에서 확증해야 한다.

`scientific_PASS=false`. M2는 실행·수정하지 않았다. 원본 코드·RF 입력·기존 결과를 보존했으며 신규 코드와 결과만 추가한다.

## 증빙

`NOISE/L0/L1/L2_MANIFEST.json`, `*_PARITY.json`, `*_EXECUTION_CONTRACT.json`, `ANALYSIS_RECEIPT.json`, 테스트 로그 및 사전·최종 감사 기록을 함께 제공한다. 전체 원시 trace·입력 캐시·실행 소스·실행 로그는 분할 evidence ZIP에 보존한다. `RESTORE_EVIDENCE.py`는 SHA-256 확인 후 ZIP을 복원하며 기존 파일을 덮어쓰지 않는다.
