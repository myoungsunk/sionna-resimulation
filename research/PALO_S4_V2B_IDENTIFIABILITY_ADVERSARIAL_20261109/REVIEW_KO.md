# PALO 적대적 재검토: S4 필터 성능과 RF·헤딩·자이로 바이어스 구별

**지위:** 과거 Actions 계산의 원시 CSV/NPZ를 별도 산술 코드로 재분석한 과학적 리뷰. 신규 RF·필터 실행 및 제3자 독립 감사가 아님. 원본 V2-B [Actions #42563563313](https://github.com/myoungsunk/sionna-resimulation/actions/runs/42563563313), 불변 [raw data](https://github.com/myoungsunk/sionna-resimulation/tree/2b1fa6f2e4bce1ca95c11ca79f25a3ce51a4ce8c/research/PALO_IMM_V2_20261109/runs/42563563313).

## 1. 심사 판정

기존의 “V2-B의 Full 16/16 Heading RMSE가 S4보다 악화되어 대체 주필터 채택 불가”는 수치적으로 옳다. 하지만 “오염·헤딩·바이어스 구별 불가능”은 순간 스칼라 편파식의 rank 부족을 시계열 전체로 부당하게 일반화한 주장이다. “S4보다 나빠 모든 기능이 무가치하다”도 틀리다. **S4 자체가 상당한 overconfidence이고 V2-B에는 제한된 XY/불확실성 이득이 있었다.** 따라서 정확도·동적 상태추정·분포 정합성과 오염 원인의 식별성을 분리해 평가해야 한다.

## 2. 필터 정확도 이외의 측정

S4는 4상태 x,y,psi,bias, s-only EKF. frozen predict_one의 4상태 Q에서 bias 과정잡음은 0이다. 단, simulated true bias 역시 조건별 상수이므로 이 한 항이 부정확하다거나 모든 문제의 원인이라고 선언할 수 없다.

**Full L2, t≥40초:**

| 장소 | 방법 | H RMSE° | XY RMSE m | bias RMSE °/s | H NEES (기준 1) | H95 | XY NEES (기준 2) | XY95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| R2-B | S4 | 1.292 | .308 | .0351 | 3.729 | 75.0% | 22.855 | 36.5% |
| R2-B | V2-B | 1.364 | .241 | .0436 | 2.189 | 80.2% | 9.491 | 40.7% |
| R4-A | S4 | 1.037 | .113 | .0161 | 10.189 | 44.8% | 1.744 | 90.0% |
| R4-A | V2-B | 2.188 | .272 | .0255 | 20.998 | 15.7% | 8.083 | 30.6% |
| R5-A | S4 | 5.297 | .551 | .0787 | 43.146 | 3.9% | 48.868 | 7.3% |
| R5-A | V2-B | 14.919 | 1.628 | .1161 | 143.603 | 3.9% | 88.543 | 10.9% |
| R5-B | S4 | 1.611 | .262 | .0387 | 9.260 | 47.2% | 23.149 | 36.3% |
| R5-B | V2-B | 1.711 | .226 | .0347 | 11.703 | 47.3% | 16.543 | 43.1% |

**Full 16 case×bias 비교, 전체 t≥40초 / 후반 t≥140초:**

| 신규 필터가 S4보다 나은 경우 | 전체 | 후반 |
|---|---:|---:|
| H RMSE 개선 | 0/16 | 0/16 |
| XY RMSE 개선 | 8/16 | 5/16 |
| bias RMSE 개선 | 4/16 | 8/16 |
| H NEES가 1에 더 가까움 | 4/16 | **0/16** |
| H95 명목 95%에 더 가까움 | 6/16 | **0/16** |
| XY NEES가 2에 더 가까움 | 10/16 | 10/16 |
| XY95 명목 95%에 더 가까움 | 12/16 | 4/16 |
| Heading q99 감소 | 6/16 | **0/16** |

극심 사례는 R5-A L2 후반의 V2-B H 17.534°, XY 2.052m, H95/XY95=0/0, Heading NEES 194.61. **V2-B가 주 추정기 채택 미달임은 유지한다.** 그러나 S4 역시 LoS에서 R2-B B0 H95 64.18%, bias95 72.4%, R5-A LoS L2 XY NEES 약 91.7로 consistency 미달이다. S4는 대조군이지 calibrated gold standard가 아니다. V2-B의 혼합분포를 정규분포로 축약한 NEES는 혼합분포 posterior의 모든 품질을 평가하지 않으므로 혼합 CDF·log score·whiteness도 함께 보아야 한다.

## 3. '구별 불가능'은 현재 데이터로 증명되지 않았다

순간 스칼라 식 r≈H_p δp+g δpsi+c+ε 하나에서 여러 잠재오차를 유일하게 복원할 수 없음은 자명하다. 하지만 알려진 운동 전이·회전·위치·추가 관측의 시계열 식별성은 다른 문제다.

위치를 알고 c가 짧은 창에서 상수이고 bias가 시간에 따른 heading 예측에만 작용한다고 단순화하면, 관측 행은
\[
J_i=[g_i,-(t_i-t_0)g_i,1],\quad g_i=H_{\psi,i}.
\]
이는 heading 초기오차, gyro bias 오차, c를 구별하는 최소한의 한계 진단이다. **전체 5상태 Fisher/CRLB 결과가 아니며** 위치/동적 공분산·RF 시간상관·모드 불확실성을 누락했다.

저장된 V2-B 정상모드 Hpsi를 이용해 2/5/10초 비중첩창 총 594개를 새로 산술 집계했다.

| Full/B0 경로 | 2초 창 수 | 2초 heading vs constant c 구별 정보 잔존 중앙값 | 2초 heading과 c의 cos>.95 비율 | 10초 정보 잔존 중앙값 |
|---|---:|---:|---:|---:|
| R2-B | 77 | 1.88% | 72.7% | 20.2% |
| R4-A | 54 | 0.56% | 77.8% | **77.4%** |
| R5-A | 121 | 0.39% | 83.5% | 5.9% |
| R5-B | 121 | 2.51% | 68.6% | 44.0% |

따라서 짧은 창에서 불리하더라도 회전·기하학적 기울기 변화가 큰 창은 분리 가능성이 증가한다. L2 bias .2°/s가 2초간 만드는 편파 관측 신호의 표준 관측잡음 σs=.09 대비 **시점당 RMS 중앙값**은 R2-B .017σ, R4-A .068σ, R5-A .020σ, R5-B .016σ이다. gyro bias를 짧은 편파 창만으로 정밀 추정할 능력이 충분하다고 주장하기도 어렵다. 이 수치는 실제 누적 검출 SNR이 아니다.

**필수 남은 검정:** 실제 F,Q,P 및 x,y,psi,b,c와 시간상관을 포함한 조건부 observability Fisher 정보에서 위치·c를 Schur complement하고 ψ·b의 최소 고유값/CRLB, 물리적인 단위당 sensitivity를 route·회전량별로 평가.

## 4. 이미 존재하는 각 오차별 추가 단서

- **RF multipath:** 두 RX 포트 복소 CIR, 첫 경로 에너지·전력·선행탭·tap 전후의 복소 간섭 항, 포트별 편파 변화. 별도 [paired B FP study](https://github.com/myoungsunk/sionna-resimulation/blob/ac4b85fadd8c285d29432bbe6c5cb261f12845f3/research/FP_DISTORTION_RESULTS_20261109/REPORT_KO.md)에서 3,136 frame 중 1,855개 FP tap 같음, 그중 442개에서 |s_F−s_L|>.05. FP 검출점 일치만으로 s가 깨끗함을 보장하지 않음. s와 CIR은 같은 RF이므로 독립 증거처럼 합산하면 안 됨; LoS는 사후 label만 가능.
- **Heading:** 고정 위치 회전시 g(ψ)와 수신 s의 변화, 독립적인 wheel encoder yaw·LiDAR scan matching. 위 FP 데이터 R4 k40–54, x/y 고정, 66.64° 회전, Full/LoS FP 검출 tap 15시점 동일인데 Δs가 +.420→−.309로 반전. c를 시간만의 stationary AR(1)로 모델링하는 것이 불충분할 수 있음을 보여주는 구체적인 기하학적 반례.
- **Gyro bias:** 장시간 gyro 회전 적분과 **독립적인** wheel/LiDAR 상대 yaw의 기울기 차이, stationary zero-angular-rate, 온도/시간 안정성, 회전·직진 구간 간 일관성. frozen scalar EKF의 motion 입력에는 ds_odom과 dtheta_gyro만 있고 독립 raw left/right encoder yaw·LaserScan이 없다. Hardware sensing 자료를 이 데이터에 몰래 추가하지 않음.
- **필터 과신:** LoS/Full paired, RF-off DR, NIS·NEES 및 temporal autocorr, 위치–헤딩–bias 교차공분산, 원래 Q/R/P 모델의 가정과 게이트 손실.

## 5. 오염 c의 높은 상관: 절반만 성공한 실험

같은 원본 R2-B Full B0에서 오프라인 s_F−s_L와 C모드 조건부 c의 상관은 전체(t≥40) **0.9797**, 후반(t≥140) **0.9719**이다. 그러나 실제 출력에 기여하는 π_C·c의 상관은 전체 **0.8977**, 후반 **0.8175**다. 이 결과는 RF 왜곡 특성 정보가 전혀 없다는 주장을 반박하지만, mode probability 또는 c 추정이 heading utility를 안다는 증거는 아니다. V2-A/B 모델은 GT reference-state residual을 이용해 R2에서 calibration돼 실제 online 검증 조건과 다름. R2 후반도 동일 route이다.

## 6. 최종 적대적 권고 — 필터 모듈을 붙이기 전에 두 과학 질문을 분리

**E1. RF/heading/bias의 조건부 구별 가능성:** 기존 C/D, FP 실험을 단순 재반복하지 않는다. R4 고정위치 yaw-sweep, R2/R5 직진/회전, 2/5/10초 구간에서 full dynamic Fisher/Schur/CRLB를 산출하고, 가급적 원본 complex CIR의 단일 물리특징이 **RF 오염 label과 실제 heading correction loss label 각각에 추가 판별력**이 있는지 leave-one-route-out로 평가. 독립적 원인식별과 개별 업데이트 이득을 등치하지 않는다.
 
**E2. S4 기준선의 필터 설계 감사:** 아직 불확실한 S4 covariance를 확정된 기준으로 쓰지 않는다. 기존 LoS·Full 4bias의 Q_b/P0 및 관측 R_s·correlation, gate와 gyro bias cross-cov를 **한 번에 하나의 요인만** 교환해 교정 가능성과 정확도/NEES/coverage 기전 분리. Synthetic true bias는 조건별 상수이므로 임의 Q_b 확대를 정답처럼 채택하지 말 것. RF→bias를 막으면 L2 회복을 잃을 수 있으므로 독립 gyro–wheel/LiDAR yaw 정보 없이 bias 고정은 금지.

E1/E2 결과가 확인된 후 **하나의 최소 구조**만 사전 동결해 개발. 정확도 + covariance calibration + worst-block q99 + L2 recovery + LoS 보호가 채택 기준. 이미 여러 번 본 R2/R4/R5 동일 corridor 자료만으로 일반화 선언 불가. V2-B는 수치감사 통과/현재 헤딩 주필터 채택 보류, RF 물리 오프셋 추정 능력의 부분효과는 별도 보존.

## 출처

- [V2B 실행 원본](https://github.com/myoungsunk/sionna-resimulation/tree/2b1fa6f2e4bce1ca95c11ca79f25a3ce51a4ce8c/research/PALO_IMM_V2_20261109/runs/42563563313).
- [FP paired RF 연구](https://github.com/myoungsunk/sionna-resimulation/blob/ac4b85fadd8c285d29432bbe6c5cb261f12845f3/research/FP_DISTORTION_RESULTS_20261109/REPORT_KO.md).
- [C/D 반사실·원인 분해](https://github.com/myoungsunk/sionna-resimulation/blob/1a30b1f44d875d0d5b105584b78d2fb91460c088/research/PALO_MECHANISM_CD_EXEC_20261108/POSTRUN_REVIEW_42453921978_KO.md).
- 본 리뷰의 독립 산술 스크립트 및 594개 window CSV는 현재 대화의 별도 검산 패키지에 포함. 새로운 모델 실행이나 제3자 감사는 아님.
