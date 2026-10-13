# M1 noise_pair 구성요소 분리 결과

## 결론

현재 무편향 조건에서는 Bias 상태만 추가한 M1-A에서 이미 큰 정확도 악화가 재현됐다. Full RF Joint C의 B_OLD와 E1 모두, seed별 결과를 합친 7개 RF 조건 전부에서 M1-A와 M1-C의 Heading RMSE가 M0보다 컸다. 따라서 이전 M1 실패를 강건 RF 모델 단독 실패로 해석할 수 없다.

RF 처리만 바꾼 M1-B는 Full RF Joint C의 풀링 RMSE를 개선했지만, 7조건 중 4조건에서는 Heading RMSE가 악화됐다. LoS에서는 일관성이 심하게 악화됐다. M1-B 역시 일반 개선안으로 승인하지 않는다. 이번 결과는 평가 조건 내 구성요소 대비이며 Bias 추정 자체가 항상 해롭다는 결론이 아니다.

## 실행과 재현

- 기준 commit: be4de188302818eb420b57b9e069cf107dcad339.
- 원본 FP s, B_OLD/E1, RF·Wheel·IMU, 초기 pose/P0, Bias prior 0.1deg/s 및 RW0, Huber1.345, R0/NIS gate와 모든 허용치 유지. 학습 모델 재적합 없음.
- noise_pair, level1, 7조건, seed0/1/2, LoS B_OLD 및 Full B_OLD/E1, D0/A/B/C. 모델당252셀, 총1008셀.
- 신규9 + 기존49 = 58 tests PASS. smoke48셀 완료 후 전체1008셀 실행, 종료코드0. 전체 실행 약753.45초.
- M0 252셀, M1-C 252셀의 기존 지표 재현 최대 절대차이0. 허용치1e-8 불변. M0의 수용/거부 횟수도 일치.
- 1008셀의 원시 trace에서 위치·Heading RMSE를 재집계해 저장 지표와 절대차이1e-10 이내임을 확인.
- 독립 코드 감사 ACCEPT. 소스·입력·참조 결과 해시, 실행 명령 및 종료 증빙 보존.

| 모델 | Bias 상태 | RF 처리 |
|---|---|---|
| M0 | 없음 | 동결 R0 + NIS gate |
| M1-A | 있음 | 동결 R0 + NIS gate |
| M1-B | 없음, 실제3state | 학습 평균·분산 + block Huber |
| M1-C | 있음 | 기존 RobustBiasEKF 그대로 |

## Full RF / B_OLD / Joint C

| 모델 | Heading RMSE (deg) | 위치 RMSE (m) | Mean pose NEES | Pose95 포함률 |
|---|---:|---:|---:|---:|
| M0 | 1.2744 | 0.2302 | 49.750 | 18.06% |
| M1-A | 3.7833 | 0.4380 | 282.077 | 16.20% |
| M1-B | 0.9628 | 0.1603 | 64.434 | 31.50% |
| M1-C | 4.4082 | 0.4513 | 310.133 | 23.95% |

## Full RF / E1 / Joint C (탐색 전용)

| 모델 | Heading RMSE (deg) | 위치 RMSE (m) | Mean pose NEES | Pose95 포함률 |
|---|---:|---:|---:|---:|
| M0 | 0.9414 | 0.1531 | 24.238 | 33.14% |
| M1-A | 3.6528 | 0.3727 | 54.893 | 23.17% |
| M1-B | 0.8179 | 0.1388 | 23.695 | 37.70% |
| M1-C | 4.0158 | 0.4065 | 82.196 | 24.88% |

## LoS / B_OLD / Joint C

| 모델 | Heading RMSE (deg) | 위치 RMSE (m) | Mean pose NEES | Pose95 포함률 |
|---|---:|---:|---:|---:|
| M0 | 0.2586 | 0.0538 | 16.063 | 74.68% |
| M1-A | 0.4858 | 0.0609 | 26.474 | 68.47% |
| M1-B | 0.2868 | 0.0605 | 1195.727 | 20.70% |
| M1-C | 0.3999 | 0.0632 | 2211.206 | 14.70% |

각 표의 각 행은 7조건×3seed, 평가 표본18603개를 합친 기술 통계다. 시간 샘플·sensor seed가 독립 RF 장면을 만드는 것은 아니다. 경로별·seed별 원본 지표는 ABLATION_METRICS.csv, seed를 합친 조건별 결과는 CASE_METRICS.csv에 있다.

## 관측 조합별 원인 분리

Full RF B_OLD의 Heading RMSE는 다음과 같다. 행의 A/B/C는 관측 조합이며 모델명 M1-A/B/C와 구별한다.

| 관측 조합 | M0 | M1-A Bias만 | M1-B RF만 | M1-C 둘 다 |
|---|---:|---:|---:|---:|
| D0 | 2.4064 | 2.4064 | 2.4064 | 2.4064 |
| A | 1.1385 | 6.1952 | 1.0670 | 7.8948 |
| B | 5.6713 | 11.0686 | 6.6073 | 7.6575 |
| C | 1.2744 | 3.7833 | 0.9628 | 4.4082 |

- D0 점추정은 네 모델에서 동일하다. Bias 상태의 추가 불확실성은 공분산을 바꿀 수 있으므로 D0 covariance까지 같다고 주장하지 않는다.
- Bias만 추가한 M1-A의 악화는 Joint에 국한되지 않는다. Heading-only와 Range-only에서도 풀링 Heading 오차가 커졌다.
- M1-B는 Joint와 Heading-only의 풀링 정확도를 개선했지만 Range-only에서는 악화됐다. 모든 관측 조합에 유익한 RF 처리라고 할 수 없다.
- Full B_OLD Joint에서 M1-C는 M1-A보다도 악화됐다. RF 효과는 Bias 상태 유무에 따라 달라진다. PAIRED_FACTORIAL_CONTRASTS.csv는 각 셀에서 MSE 단위의 조건부 차이와 상호작용 C−A−B+M0를 보존한다. 이를 독립 인과 추정이나 유의성 검정으로 해석하지 않는다.

## 추정 Bias와 공분산

동결 sensor_v2의 noise_pair는 wheel_noise/gyro_noise만 활성화하며 실제 gyro bias는0이다. Full B_OLD Joint에서 조건별 M1-A bias RMSE는 약0.0140–0.0898deg/s, M1-C는0.0172–0.0930deg/s였다. 무편향 자료에서 0이 아닌 Bias 추정과 정확도 악화가 함께 나타났다. RF 잔차나 운동모델 불일치가 Bias로 흡수되는 해석과 부합하지만, 어느 오차가 얼마만큼 흡수됐는지는 이번 비교만으로 확정하지 않는다.

M1-B의 LoS 평균 pose NEES는16.06→1195.73, 포함률은74.68%→20.70%로 악화됐다. 기존 학습 LoS s 분산은 경로별 R0의 약0.00141–0.10869배였으며, 이 값은 이번 실행에서 변경하지 않았다. 작은 학습 RF 척도와 covariance 불일치의 관계는 후속 분리 대상이며 Huber 단독 원인으로 결론 내리지 않는다. RF_MODEL_CONTRAST.csv에 모든 fold의 평균·분산 대비를 기록했다.

## 다음 검증 범위

파라미터 재조정 없이 먼저 (1) M1-A의 정확한 관측/운동모델 합성 대조군에서 Bias 추정·공분산을 확인하고, (2) 동결 자료에서 RF 평균, RF 척도, Huber, hard gate 제거를 하나씩 분리하는 후속 계약을 정한다. Bias posterior와 innovation의 지속성, 모델 불일치를 함께 검토한다. 이는 다음 계획이며 이번에 실행하지 않았다.

M2-T0는 별도로 정확한 운동 factor의 fixed-lag 주변화 오류부터 해결해야 한다. 이번 M1 결과로 M2 성공을 예상하지 않는다. M2-T0 NOT_READY, M2-T1 BLOCKED(시간 상관 구조 미확정), 독립 RF 환경 확증 NOT_RUN, scientific_PASS=false 유지.

## 보존 및 재현

원본 및 이전 결과를 수정하지 않았다. 추가 코드만 ablation 영역에 두고 실험 결과는 별도 영역에 게시한다. 기존 E1의 공간 중복·모델군 선택 이력 및 전체 재귀 상태의 오염 가능성은 그대로 남아 있으므로 탐색 결과로만 해석한다.

EXECUTION_CONTRACT.json에 실행 명령·입력/참조/소스 해시가 있다. 재실행은 run_ablation.py의 --inputs, --structure, --reference, --out 인자를 사용하며 출력 폴더는 새로 지정한다. 먼저 --smoke를 통과한 후 같은 인자로 전체를 실행한다.

전체 trace와 로그는 용량 때문에 EVIDENCE.zip.partNNN으로 분할했다. 모든 part와 EVIDENCE_ARCHIVE.json, RESTORE_EVIDENCE.py를 같은 폴더에 받은 뒤 `python RESTORE_EVIDENCE.py`로 연결·SHA256 검증한다. 기존 EVIDENCE.zip은 덮어쓰지 않는다. ZIP에는 실행 소스 snapshot, 입력 cache, 학습 모델, 참조 지표, 소규모/전체 trace, 감사·시험·종료 증빙을 보존했다. 관리 실행은 정상 종료하고 소유 참조를 해제했다.
