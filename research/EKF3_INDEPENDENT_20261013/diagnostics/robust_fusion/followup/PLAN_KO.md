# M1 후속 원인 분리 실행 계약

기준 commit 7d65f387a2e4c461cbca65014f3975d452e00f93. 원본 코드·입력·기존 결과를 보존한다. 파라미터를 평가 결과에 맞춰 조정하지 않는다. 이번 범위는 아래 두 실험이며 M2 구현·실행은 포함하지 않는다.

## 1. M1-A 합성 대조

정확히 알려진 SE(2) 운동과 명시적인 합성 RF 관측함수를 사용한다. 실제 FFD/RF를 재현했다고 주장하지 않는다. 실제 gyro bias 0과 알려진 +0.05deg/s, 직진·회전·왕복을 비교한다. 초기 pose가 정확하고 잡음이 없는 명목 조건에서 불필요한 Bias 보정이 생기는지 확인한다. 잡음 및 초기오차가 있는 조건은 시나리오당100개의 독립 seed로 반복하고 편향·RMSE·95% 포함률을 기록한다. 먼저 소규모 검사를 통과한다.

M0와 M1-A는 동일한 관측·입력·초기 pose를 받는다. Bias prior std0.1deg/s, RW0, 기존 R0·NIS 임계값을 유지한다. D0/A/B/C 모두 비교한다. D0에 관측 불가능한 Bias 수렴을 요구하지 않는다. 비영 Bias 한 번의 추정만으로 구현 실패를 판정하지 않는다. 고정 true bias 조건의 반복 포함률은 unconditional prior-predictive calibration과 구별한다.

같은 관측에 대해 각 모델의 prior innovation·S·NIS·gate 판정·Bias 방향 gain과 Bias 보정량을 기록한다. 운동/관측 Jacobian 및 보정식을 독립 수치 검사한다. 무잡음 불변성이나 코드 검사 실패 시 해당 결과를 일반화하지 않고 원인을 확인한다.

## 2. M1-B RF 요소 분리

모든 대조군은 동일한 초기조건의 실제3state에서 출발한다. 변경을 순서대로 누적하지 않는다.

| 이름 | 평균 | 분산 | 손실 | NIS gate |
|---|---|---|---|---|
| M0 | 0 | R0 | Gaussian | 원본 ON |
| RF_MEAN_ONLY | 기존 학습 평균 | R0 | Gaussian | 원본 ON |
| RF_VAR_ONLY | 0 | 기존 학습 분산 | Gaussian | 원본 ON |
| RF_HUBER_ONLY | 0 | R0 | Huber1.345 | 원본 ON |
| RF_GATE_OFF | 0 | R0 | Gaussian | OFF |
| M1B_REPRO | 기존 학습 평균 | 기존 학습 분산 | Huber1.345 | OFF |

Huber-only의 gate는 보정 전 동일 prior와 원본 R0로 계산하고 통과 관측에만 Huber를 적용한다. 공동 s·Range는 하나의 강건 블록이다. gate 임계값은 바꾸지 않는다. Gate 설정이 같아도 궤적·공분산 변화에 따라 이후 실제 수용 결과는 달라질 수 있다.

noise_pair, level1, 기존7조건, seed0/1/2, LoS B_OLD 및 Full B_OLD/E1, D0/A/B/C: 모델당252셀, 6모델1512셀. R2_aA_m0·seed0의 모델당12셀 smoke 후 전체 실행한다. M0와 M1B_REPRO는 이전 ablation의 M0/M1-B와 절대 허용치1e-8로 재현 대조하며 M0 수용·거부 횟수도 검사한다. 학습 모델은 다시 맞추지 않는다.

## 3. 판정과 보존

RMSE, NEES, 포함률, 수용·거부, Huber 가중치, 공분산 변화, 조건별 결과를 함께 보고한다. 단일 요소의 효과는 기준선에 조건부이며 전체 조합의 효과를 단순 합으로 가정하지 않는다. E1 전체 재귀 결과의 기존 공간 중복·모델 선택 이력 제한을 유지한다. 독립 장면 또는 새로운 수신기 증빙으로 해석하지 않는다.

소스·입력·출력 해시, 실행 명령, 종료코드, smoke/full 게이트, 감사 기록을 별도 신규 결과 폴더에 보존하고 연구 브랜치에 게시한다. scientific_PASS=false를 유지한다.
