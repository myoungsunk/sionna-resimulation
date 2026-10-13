# M1 noise_pair 원인 분리 실행 계획

기준: be4de188302818eb420b57b9e069cf107dcad339. M1 현재 조합은 NOT_ADOPTED다. 이번 범위는 noise_pair 음성 대조군의 구성요소 분리이며 파라미터 재조정, 새 수신기, M2 실행은 포함하지 않는다.

| 모델 | Bias 상태 | RF 처리 |
|---|---|---|
| M0 | 없음 | 동결 R0 + 원본 NIS gate |
| M1-A | 있음 | 동결 R0 + 원본 NIS gate |
| M1-B | 없음 | 기존 outer-route 평균·ddof1 분산 + block Huber |
| M1-C | 있음 | 이전 M1 구현 그대로 |

기존 FP s, B_OLD/E1, RF·Wheel·IMU, 초기 pose·공분산, bias prior 0.1 deg/s, bias random walk 0, Huber delta 1.345를 유지한다. 학습 모델을 다시 맞추지 않는다. 범위는 기존 7조건 × seed 0/1/2 × level 1 × (LoS B_OLD, Full B_OLD, Full E1) × D0/A/B/C로 모델당 252셀이다. 먼저 R2_aA_m0·seed0의 모델당12셀 smoke를 통과한 뒤 전체를 실행한다.

M0와 M1-C의 이전 noise_pair 결과를 절대 허용치 1e-8로 대조한다. 입력 해시, 원본 회귀, 재현 중 하나라도 실패하면 전체 실행을 중단하고 원인을 확인한다. 기존 입력·코드·결과를 수정하거나 실패를 숨기기 위해 허용치를 바꾸지 않는다.

같은 셀에서 M1-A−M0와 M1-B−M0를 비교하고, M1-C−M1-B와 M1-C−M1-A를 함께 본다. Bias 효과는 RF 처리에 조건부이며 두 효과가 가산적이라고 가정하지 않는다. RF 처리에는 평균·분산·Huber·NIS gate 제거가 함께 포함되므로 M1-B의 결과만으로 Huber 자체가 원인이라고 단정하지 않는다. D0에서는 bias 평균이 0일 때 점추정이 같더라도 bias 불확실성으로 공분산이 달라질 수 있다.

Heading·위치 RMSE, pose/heading NEES, 95% 포함률, 관측 수용·거부율, Huber 가중치, 업데이트 전후 오차, 추정 bias를 기록한다. 시간 샘플을 독립 반복으로 간주하지 않고 경로별·seed별 대응 결과를 보존한다. 풀링은 기술 통계이며 독립 RF 장면 검증이 아니다. E1 전체 재귀 결과의 기존 공간 중복·모델 선택 이력 제한을 유지한다.

결과가 어느 쪽이든 임계값을 사후 조정하지 않는다. 이번 비교가 끝나면 근거와 다음 원인 분리 범위를 보고한다. M2-T0 NOT_READY, M2-T1 BLOCKED, scientific_PASS=false를 유지한다.
