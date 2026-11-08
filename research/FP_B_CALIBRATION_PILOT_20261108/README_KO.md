# FP B-only 관측오차 보정 1차 파일럿 — 2026-11-08

## 질문
기존 native에 맞춰진 `muMB`, `muBASE`, `R`을 B 검출기에도 그대로 적용하는 것이 B 악화의 원인 중 하나인지, **B 전용 통계 보정을 적용하면 기존 B-only 대비 Heading/XY RMSE 및 NEES3가 얼마나 변화하는가** 검증한다.

## 범위 및 자료 분리
- **K1/K2/DR/관측선택 정책은 모두 사용하지 않는다.** B는 원래 정의(두 RX 각각 30% crossing, 유효한 더 이른 tap)를 유지한다.
- R2 979, R4 742, R5 1415표본의 B0 Full seed10 원본. 기존 SHA 검증된 `online.npz` 3개, evaluator 3개, FFD bank 2개를 Release에서 복원한다.
- **Leave-one-route-out**: 각 평가 경로를 제외한 나머지 2개 경로에서만 보정값을 학습한다. 각 fold 별도 Python 프로세스를 사용하여 평가 경로의 참값은 재귀 계산 완료 후에만 열람한다. 전체 동일 corridor/seed10이므로 독립 환경 일반화를 의미하지 않는다.
- 기존 native의 `muMB(t), muBASE(t), R(t)`, motion/Q/initial state/covariance, 원본 SourceFFD는 변경하지 않는다. 오직 B 전용 증분 평균 및 추가 PSD 공분산을 학습한다.

## 원리
`z_B-z_N`(관측 가능한 검출기 차이)의 훈련 경로별 평균을 2경로 균등 가중하여 `delta_mu`로 만든다. 이는 B와 native의 평균 오차 차이에 대한 상대 보정이며, *절대 LoS 정확도를 보증하지 않는다.* Main과 shadow gate의 `muMB`, `muBASE` 양쪽에 동일 `delta_mu`를 적용한다.

오프라인 **훈련 경로에서만** SourceFFD의 `h(x_true)`를 계산해 잔차 `r_N=z_N-h(x_true)-muMB`와 `r_B=z_B-h(x_true)-muMB`의 centered covariance를 구한다. 두 경로에서 동등 가중한 `Cov_B - Cov_N`의 양의 부분을 `R(t)`에 추가한다. Primary는 대각 성분의 양의 부분(분산만)이며, 전체 2x2 PSD 투영은 부가 민감도 평가다. 이는 covariance inflation이므로 기존 R을 인위적으로 축소하지 않는다.

## 사전 고정한 6군
`NATIVE_FROZEN`, `B_FROZEN`, `B_BIAS`(평균만), `B_COV`(대각 PSD 분산만), `B_BIAS_COV`(동시), `B_BIAS_FULLCOV`(전체 PSD cross-cov 민감도).

## 판정
- 먼저 과거 native/B 두 기준선의 W0 상태·공분산·게이트 1e-10 parity를 재확인한다.
- 평가 경로의 입력·참값은 보정 학습과 합쳐지지 않는다. `RESULTS.json`은 경로별/전체 Heading/XY RMSE, NEES3, XY95/Pose95, 게이트 수용 차이, 학습된 평균·공분산을 보존한다.
- RMSE 집계는 표본수 가중 MSE 후 제곱근이다. 한 번의 실험에서 결과를 보고 보정 파라미터를 튜닝하지 않는다.
- 개선이 없거나 경로 간 방향이 엇갈리면 `NOT_CONFIRMED`로 판정한다. 개선되더라도 별도 seed/environment 검증 전 운영 채택은 금지한다.

## 제한
기존 mu/R이 과거에 어떤 자료에서 적합됐는지 별도 이력 검증이 없어, 신규 delta만 경로 분리된 것이고 기존 보정의 독립성을 증명하지 못했다. 같은 복도의 독립 경로들에도 시간상관·공간 상관이 존재하므로 단순 표본수 3,136을 독립표본으로 해석하지 않는다. 학습 데이터의 LoS 참값과 결과 평가 참값은 온라인 필터에 절대 입력하지 않는다.