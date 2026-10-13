# 고정 3-state 강건 손실 비교: 사전 계약

기준 commit: 5b6549c964222d95d32b7307bd9c0b1d5594a6e4. M0, M-H, M-C, M-T만 비교한다. 기존 FP s, B_OLD/E1, R0, 초기 pose/P, 모션 입력, 99% NIS gate 및 모든 기존 파일을 보존한다. 새 RF 생성, 평균 보정, Bias state, 분산 학습 또는 평가 후 파라미터 재선택은 하지 않는다.

## 범위 및 순서

기존7조건×3seed×LoS/B_OLD 및 Full/B_OLD/E1×D0/A/B/C×4모델: 조건당1008셀. noise_pair level1 및 gyro_bias level0/1/2, 총4032셀. gyro_bias는 백색잡음 없이0.01/0.05/0.20deg/s만 활성화하는 기존 D5 정의를 유지한다.

학습 파라미터 동결 → 단위/계약 테스트 → 네 조건 각48셀 smoke → M0/M-H 기존 결과 재현 → 전체 실행 → 원시 trace 검산 → 독립 감사 → GitHub 게시. 비교 재현 허용치1e-8을 유지한다. 코드/입력 drift, 비유한 상태, 비양의 공분산, 보정 최적화 실패는 중단한다. 유한 성능 악화는 숨기거나 튜닝하지 않고 보고한다.

## 학습·평가 분리

R2/R4/R5 route holdout을 사용한다. 해당 평가 route는 shape 학습에서 제외하며, 평가 경로XY의0.25m 이내 학습 위치도 제외한다. 학습은 기존 RF 캐시의30초 이후 case/pose별1회만 사용하고 sensor seed를 복제하지 않는다. 학습 최소100개 고유 case/pose를 요구한다. 온라인 입력에 GT를 넣지 않으며 GT는 학습 잔차·분리·평가 label에만 사용한다.

각 heldout route/channel/range/arm별 shape를 학습한다. C는2차원[s,r] 블록1개, A/B는1차원이다. 이27개 설정은 모든seed와noise_pair/gyro_bias 수준에 동일하게 적용한다. E1 학습 잔차는 평가 route를 제외한 기존 E1_outer_route 계수로 구성한다. 기존 E1모델군 선택 및 공간중복 이력 때문에 독립 과학적 확증으로 주장하지 않는다.

## 손실 및 scale

- M0: 기존 Gaussian, R0 및 NIS gate.
- M-H: 기존 Huber delta1.345, R0 및 NIS gate. 기존 구현을 직접 사용한다.
- M-C: q=e'R0^-1 e, loss=c²/2 log(1+q/c²), weight=1/(1+q/c²). c는 R0로 정규화한 학습 잔차에 zero-location 다변량 Cauchy proxy를 최대우도로 적합해 고정한다. 필터에는 통상적인 Cauchy M-estimator로 사용하며, 이 손실이 유한공분산 Cauchy likelihood라고 주장하지 않는다. c의 score equation d-(d+1)mean[q/(c²+q)]=0을 사용한다. 임의 floor 또는 평가성능 기준을 쓰지 않는다.
- M-T: df 후보[3,4,6,10,20,50,100] 중 학습 NLL 최소값 선택, 동률은 앞 후보. T=(df-2)/df R0로 설정하여 Student-t 관측분포의 공분산=R0. loss=(df+d)/2 log(1+q_T/df), weight=(df+d)/(df+q_T). 1을 초과하는 weight를 임의 clipping하지 않는다.

모든 모델의 NIS는 강건 가중 전, HP^-H'+R0에서1회 계산한다. Student-t gate에 scale T를 대신 넣지 않는다. C는 관측별 독립 weight를 적용하지 않는다. 결측은 유효 subblock을 취하며 shape는 동결된 해당 arm 값을 유지한다.

M-C/M-T는 원본 prediction과 고정 prior에서 한 번 선형화한 MAP update를 사용한다. 비볼록 손실의 해법·시작점·수렴 규칙을 소스에 고정하고 사후 임계값 조정이나 Gaussian fallback을 하지 않는다. 공분산은 effective scale/weight를 사용한 Joseph의 국소 IRLS Gaussian 근사이며 정확한 robust posterior covariance가 아니다.

## 검증·해석

도함수, 공동 블록, Student-t 공분산 정합, Gaussian 극한, 결측, gate-before-weight, 양의 정부호, M0/M-H parity, D0 중립성을 검증한다. 정확도, p95오차, NEES,95%포함률, gate 거부율, 경로/seed별 악화를 함께 보고한다. 7조건은7개의 독립scene이 아니며 시점을 독립반복으로 세지 않는다. scientific_PASS=false를 유지한다.

손실 정의 참고: [SciPy Cauchy loss](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html), [SciPy multivariate Student-t shape parameter](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.multivariate_t.html). 설치 버전 및 실제 호출 테스트를 실행 증빙에 기록한다.

## 전체 실행 전 수치해법 가속 기록

최초 trust-exact 두시작점 smoke192셀은 모두 정상종료했다. 전체 실행 비용을 줄이기 위해 동일한 목적함수의 방사형 stationary equation을 다항식으로 풀고 원래 gradient/Hessian으로 검사하는 scalar solver를 채택한다. gradient<=1e-7 및 Hessian최소고유값>=-1e-10 등 기존 수렴 검사는 유지한다. 목적함수 값은 기존 solver와 별도 비교하며, 유한 정밀도의 root 탐색이므로 global optimum이라고 주장하지 않는다. 파라미터·학습 결과·관측·gate는 변경하지 않는다. 원래 solver 코드와 최초 smoke 증빙을 별도 보존하고, 가속 solver로 네 smoke를 재검증한 뒤 전체 실행한다. M0/M-H 재현 허용치는1e-8 그대로이다.
