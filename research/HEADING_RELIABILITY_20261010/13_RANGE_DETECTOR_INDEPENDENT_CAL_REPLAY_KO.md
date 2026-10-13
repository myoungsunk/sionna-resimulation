# 13. 독립 FFD LoS first-arrival 보정 및 3점 RF/6D EKF 재검증

상태: **FFD 독립 학습/검증 완료, 저장 Native RF paired replay 완료, 추가 Native RF 재생성 및 LoS PathSolver parity 별도 진행 중. scientific_PASS=false.**

## 1. 실제 범위 / 결과의 출처

- 원본 Native Sionna 3점: GitHub Actions [38111818466](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38111818466), 실행 commit `02597aab94756e58dd958c5b15c6b785b3188c28`.
- 독립 LoS 보정(원본 +45/−45 FFD NPZ SHA 검증): GitHub Actions [38115071695](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38115071695), artifact `independent-los-range-calibration-replay`. 원래 workflow의 독립 FFD 직접식 vs native LoS parity는 `ModuleNotFoundError: scripts` 때문에 실행 전에 차단됐고, import 수정 후 다른 workflow에서 재검증한다. 보정 자체는 정상 완료.
- 원본 RF packet을 바꾸지 않은 6차원 EKF paired replay: GitHub Actions [38115705305](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38115705305), artifact `los-calibrated-real-three-point-ekf-replay`.
- 추가 actual Sionna PathSolver rerun: [Calibrated Native Sionna 3pt Re-execution](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38115656127). 종료 증거가 확인되기 전까지 NOT_VERIFIED.
- 이전 수치와 비교할 때: 이번 재생은 **원래의 완전히 같은 물리 궤적·센서/RF 입력**을 사용하며 실제 RF 채널을 새로 계산하지 않았다. 최종 native rerun은 별도 결과와 분리한다.

## 2. 안테나 delay인가, 검출 편향인가?

동결된 first-arrival 관측 함수는 257-bin Hann FFT / 4N zero-pad / strongest-RX 30% leading-edge이다. 이는 peak보다 이전 tap을 검출하므로 평탄 진폭·위상의 이상적 LoS에서도 *음의* 거리 오차가 존재한다.

순수 flat spectrum LoS(2–16m)에서 검출편향 평균 약 −0.694m, 표준편차 약 0.043m. 실제 평가 위치(7.0,0.1), 3개 실제 FFD LoS의 잡음 없는 clean range는 약 3.140597m, 기하학적 거리는 3.72156m → **−0.581m**.

그러므로 −0.581m를 전부 하드웨어 안테나 지연이라고 부르면 안 된다. 안테나·RF chain의 group delay와 signal shape, magnitude bandshape, window/leading-edge timing 오차는 따로 구별해야 한다. 기존 `range_offset_m=0`을 무작정 게이트/R 확대 없이, **독립 기하에서 학습된 음의 forward-prediction offset**으로만 바꾸었다.

`h_r(x)=||p(x)-a|| + b_{LoS}`, `b_{LoS}=mathrm{median}_{TRAIN sites}[mathrm{detector}(H_{LoS,FFD}) - ||p-a||]`.

여기서 `b_{LoS}`에 들어간 학습 위치는 평가물리 pose에서 0.70m 이상 떨어진 서로 다른 XY이며, 이번 평가물리 H·range·true pose는 보정기에 전달하지 않았다. 실제 디바이스 송수신 안테나 지연 보정까지 수행했다고 주장하지 않는다.

## 3. 사전 등록한 다른 XY에서 calibration 및 holdout

Training 15 XY × 3 yaw = 45 관측 / mount. Holdout 7 XY × 3 yaw = 21 관측 / mount. Mount 0°와 45°를 독립적으로 처리. 총 132 LoS FFD synthetic observation. Training 값으로만 median offset 결정, holdout RMSE≤0.15m 및 P95 절대 오차≤0.25m 기준 고정.

| 항목 | Mount 0° | Mount 45° |
|---|---:|---:|
| TRAIN median offset(m) | −0.5124272934 | −0.5327236346 |
| TRAIN bias mean(m) | −0.5250167294 | −0.5383102635 |
| HOLDOUT bias mean(m) | −0.5524490105 | −0.5595705466 |
| HOLDOUT residual mean(m) | −0.0400217171 | −0.0268469120 |
| HOLDOUT RMSE(m) | 0.0563378386 | 0.0479470768 |
| HOLDOUT absolute residual P95(m) | 0.0863561441 | 0.0660598028 |
| HOLDOUT 독립 위치 기준 통과 | true | true |
| TRAIN flat-spectrum-only mean bias(m) | −0.6845391388 | −0.6845391388 |
| TRAIN FFD minus flat mean shift(m) | +0.1595224094 | +0.1462288753 |

별도 FFD angular+frequency response가 flat DSP bias와 차이나는 것은 관찰되나 이를 별도로 검증된 group delay로 인과 규정하지 않는다. 실제 Sionna LoS parity와 디바이스 실측 calibration까지 요구한다.

## 4. 원래 평가 RF가 세 번 모두 반영되는가?

동일 원본 input를 사용, **전체 6x6 P 상태와 숫자가 원래 결과를 완벽 재현**한 후(`max_state_abs_diff=0`, `max_P6_abs_diff=0`) 사전등록된 0° offset `−0.5124272934m`만 적용한다. Q/R/gate, P0, drift, noise, RF packet, timestamp, 입력 및 control trajectory는 동일하게 유지한다. 평가 true pose는 모든 추정기 replay가 끝난 뒤 성능 계산에만 읽는다.

| 지표(동일 40 ticks, 1 seed) | RF-off | 기존 range_offset=0 | flat detector offset 진단 | 독립 FFD-LoS offset |
|---|---:|---:|---:|---:|
| Range 갱신 수용 | 0 | 0/3 | 3/3 | 3/3 |
| Position RMSE(m) | 0.000090041 | 0.000090041 | 0.0478156 | 0.0843013 |
| Heading RMSE(deg) | 0.0232113 | 0.0232113 | 0.0232091 | 0.0232119 |
| Pose NEES (df3 mean) | 0.00002235 | 0.00002235 | 0.685613 | 2.33857 |
| 최종 위치 오차(m) | 0.00008066 | 0.00008066 | 0.0535848 | 0.1043085 |
| Pose 95% coverage (기술통계) | 1.0 | 1.0 | 1.0 | 1.0 |

독립 FFD 보정의 RF NIS는 `0.5199 / 1.3157 / 0.0597`, status는 3개 모두 `applied`. 수정 전 NIS `26.56 / 33.44 / 28.17`, status 3개 `rejected`. 즉 **RF 갱신 미수용이라는 소프트웨어 문제는 해결되었지만, 정확도 개선은 관찰되지 않았고 위치 RMSE는 악화**되었다.

초기 상태가 truth와 매우 가깝고 slip=neutral, 1 seed, 차체 제자리 회전이어서 RF-off 위치 오차가 약 0.09mm에 불과하다. 약 0.069m에 해당하는 잔여 평가-site LoS detector bias 및 range thermal noise가 관측 correction으로 유입됐다. `NEES≈2.34`가 표면적으로 3에 가까워진 것은 **위치 오차가 커졌기 때문**이며 공분산 calibration 또는 정확도 향상으로 주장할 수 없다. 평가결과를 보고 flat offset을 최종 모델로 선택하거나 R을 임의 튜닝하지 않는다.

## 5. 우선 남은 검증 단계

1. 실제 native PathSolver LoS vs FFD analytic h의 **257 주파수 bin 복소 norm·동일 first arrival tap parity**를 검사(실행 스크립트의 import 수정 포함). 평가 oracle은 오직 사후 parity 진단에 사용한다.
2. calibration SHA로 봉인된 동일 FFD offset을 실제 native forward 3점 시뮬레이션에 적용하여 *새로운 true pose/channel*을 다시 생성하고, 기존 RF-off와 같은 물리 trajectory 내 기술통계 비교.
3. `s`는 이번 팔에서 `use_s=false`. 독립된 LoS LUT 및 site×angle joint `Sigma_sr` 공분산, q_site/q_point 실험 없이 2/3점 heading 개선 또는 일관성 PASS를 선언하지 않는다.
4. 개발된 물리 `slip_mode=hypothesis` + 최소 `drive → measured stop → probe → resume` 스케줄 구간은 실물 식별 계수가 아니며, R2/R4/R5 위험 감지 기반 full-route 성능을 대체하지 않는다. 여러 독립 seed와 mount 0/45 실험, 실제 slip calibration은 별도 다음 실행이 필요.

최종 과학 판정: **F01/F02 OPEN, scientific_PASS=false, L1/L2 미완료**. 실험 숫자를 넘는 주장은 하지 않는다.

## 6. 실제 다른-site calibration에서 확인한 cross-angle quantization 상관

`OTHER_SITE_LOS_CALIBRATION.csv`의 training physical XY 15개에 대해 각 0°, 10°, 20°의 동일-site `first_arrival_tap`을 직접 묶어 확인했다.

- Mount 0°: 15/15 XY에서 3개 yaw 모두 **동일한 first-arrival tap**이었다. 같은 XY의 잡음 없는 FFD-LoS `detector_range - geometric_range`도 세 angle 사이에 정확히 같은 값이다.
- Mount 45°: 14/15 XY에서 동일한 tap이었다. 나머지 1개 XY에서 yaw에 따른 tap이 달라져 detector range/bias가 약 0.1495522588 m 변했다.
- 따라서 잡음 없는 같은-site 거리 quantization/FFD mismatch를 3개 독립 난수처럼 세면 잘못된 공분산이다. `R_{r_i r_j}`의 site-shared term은 일반적으로 0이 아니다. 신뢰할 수 있는 thermal noise covariance만 반복 측정 독립 가정과 연결해야 한다.
- 이 검사는 순수 LoS의 detector staircase 상관 증거다. Full multipath RF range/s와의 임의 cross covariance 또는 calibration 적합 값까지 입증하지는 않는다. `q_site/q_point` joint likelihood 및 `Σ_sr[2M,2M]` 추정은 여전히 NOT_IMPLEMENTED.
- 독립 holdout 21 rows/mount는 실제 독립 XY **7개**에 대한 3회 correlated angle sampling이므로 유효 독립 site N을 21이라고 부르면 안 된다.
