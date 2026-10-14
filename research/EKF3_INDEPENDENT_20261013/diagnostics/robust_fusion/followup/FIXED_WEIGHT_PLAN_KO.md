# 고정 1/3 가중치 대조: 실행 전 계약

기준 커밋 e157c99c12377c69fc407514cb0337060e7b4e14. 기존 파일과 결과를 수정하지 않는다.

- 비교: M0, RF_HUBER_ONLY (1.345), RF_CAUCHY (동결 경로 홀드아웃 계수), RF_FIXED_THIRD.
- Joint C의 원본 FP s 및 B_OLD/E1 range, 원본 3-state 예측·초기조건·R0를 유지한다.
- gate는 원본 R0 기반 prior NIS 99% 판정을 보정 전에 한 번 수행한다. 고정 대조군만 허용된 관측의 R_eff=3R0를 사용한다.
- noise_pair Level 1, gyro_bias Level 1 및 2, 기존 7개 조건 × seed 0/1/2 × LoS B_OLD / Full B_OLD / Full E1. 총 189개 입력 셀, 모델별 189개 재귀 셀.
- 동일 prior 실험: 각 입력 셀의 M0 및 Cauchy 재귀 경로에서 얻은 모든 평가 시점(t>=30 s)의 실제 prior를 각각 복제한다. 각 prior에서 네 보정을 수행하며 이후 상태로 전파하지 않는다. 동일 prior의 gate 판정은 네 모델이 일치해야 한다.
- 재귀 실험: 네 모델 각각의 posterior를 다음 시점으로 전파한다. 이전 세 모델의 모든 요청 셀 결과가 기존 공개 결과와 절대 오차 1e-8 이내로 일치해야 한다. 표본 수와 gate count는 정확히 일치해야 한다.
- H, innovation, S, K, R_eff, P-/P+, RF 정답 잔차와 prior 상태 오차 기여, 가중치, 보정 전후 제곱오차, NEES 및 포함률을 압축 수치 trace로 기록한다. 정답 정보는 평가용으로만 사용한다.
- 고정 1/3은 2D Cauchy 학습 score의 평균 가중치 항등식에서 정하며 평가 결과에 맞추지 않는다. 실제 평가 평균 정보량이나 likelihood가 Cauchy와 동일하다는 주장은 하지 않는다.
- 소규모 실행 및 parity/gate 검사 후 전체 실행. 불일치 시 중단하며 허용치를 완화하지 않는다. 독립 감사 후 코드와 결과를 기존 연구 브랜치에 추가한다.
- gate OFF, covariance replay, oracle bias 대조는 이번 범위 밖이다. 시점을 독립 반복으로 취급하지 않고 경로/seed별 결과를 함께 보고한다. 단일 RF 장면 탐색 결과이며 scientific_PASS=false를 유지한다.
