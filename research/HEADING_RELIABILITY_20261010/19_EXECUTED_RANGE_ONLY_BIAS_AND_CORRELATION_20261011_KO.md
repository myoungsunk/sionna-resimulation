# 19 — 기존 RF 데이터만 사용한 Range-only EKF 편향·분산·시간상관 보정 실제 실행

일자 2026-10-11 | 연구 브랜치 codex/range-only-bias-consistency-20261011 | **실제 시뮬레이션 실행 완료, 과학적 PASS는 아님**.

실행: [GitHub Actions 38114255647](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38114255647). 소스: run_range_bias_consistency_ablation.py. 기존 H 재사용, raytracing 신규 실행 없음. 7케이스 × 3drift × 8seed = 168 matched trials per arm, 각 run별 원래 Tnone 진행시간 t>=30s의 full-route RMSE/NEES 계산. 총 1008 Sensor-v2 필터 실행, 원 소스/채널 변경 없음. 0/45는 옛 7케이스 mount 배치만 사용.

## 1. 필터 구성

- A_ODOM: IMU+wheel, range 없음.
- B_RANGE_FIXED: 원본 Sensor-v2 range offset=−0.531598390625m 및 R=0.0068578637m².
- C_BIAS_BIN: train-only 거리 구간 [0,5),[5,10),≥10m의 mean error bias를 예측 range에 적용, R 고정.
- D_BIAS_VAR_BIN: C + train-only centered residual variance, 원본 R floor.
- E_BIAS_VAR_TIME: D + train-only empirical lag1 correlation ρ의 정보중복 보정 α=(1+ρ)/(1−ρ), α capped [1,12]; 이는 exploratory observation variance inflation이며 **정확한 시간상관 Kalman filter가 아님**.
- F_VAR_TIME_NO_BIAS: E에서 mean bias만 제거하여 편향보정 필요성을 검사.

학습/평가 분리는 **leave-one-ROUTE-out**: R2 평가 모델은 R4/R5에서만 fit; R4은 R2/R5, R5는 R2/R4. 학습에서는 동일 anchor/mount 중복을 피하기 위해 R2A mount45를 제외; 평가에서는 보존한다. 실제 현장 환경은 전부 같은 corridor라서 독립 geometry 검증이 아님. 참 위치는 offline training labels/evaluation에만 사용하며, filter 입력에는 예상 거리에서 산출한 bin만 사용.

## 2. 수치 결과 — 정확도와 일관성 모두 비교

| Arm | heading run-RMSE mean ° | position run-RMSE mean m | pose NEES mean | pose95coverage | median min conditional XY sigma m |
|---|---:|---:|---:|---:|---:|
| A_ODOM | 8.9347 | 1.0074 | 8.87 | 0.8338 | .10219 |
| B_RANGE_FIXED | 9.7922 | 1.2854 | **1285.37** | .1497 | **.00906** |
| C_BIAS_BIN | 6.7991 | .8583 | 342.23 | .2097 | .00904 |
| D_BIAS_VAR_BIN | 7.4006 | .8931 | 395.48 | .2785 | .01060 |
| **E_BIAS_VAR_TIME** | **6.9517** | **.8042** | **146.52** | **.5132** | **.01677** |
| F_VAR_TIME_NO_BIAS | 12.5056 | 1.5258 | 672.93 | .2596 | .01673 |

E−B differences: heading -2.84057°, position -.481205m, NEES -1138.86, coverage +.36348. NEES 88.6% 감소 및 위치 RMSE 37.4% 감소. 단, E도 df3 theoretical NEES expectation=3, coverage nominal=.95를 **크게 위반**하므로 scientific_PASS=false.

Case-wise E NEES:
R2A mount0 19.26; R2A mount45 41.01; R2B mount0 **399.51**;
R4A 6.38; R4B 8.45; R5A 59.46; R5B **491.56**. 여전히 거리 기하/편향 조건에 크게 의존한다.

## 3. 학습에서 얻은 구간별 실제 편향·분산과 시간 중복

3 heldout models의 binned mean meter:
- 0–5m: −.003 to +.004, centered std .053~.059m;
- 5–10m: +.055 to +.067, centered std .103~.135m;
- ≥10m: +.128 to +.132, centered std .136~.204m.

Train-only lag1 Pearson after bin mean correction: ρ(R2 heldout)=.60484, R4=.64115, R5=.52554; independent-equivalent variance inflation α=4.061/4.573/3.215. 물리 autocorrelation을 AR1 스칼라 R의 단순 확대에 투영한 proxy일 뿐 완전한 colored-noise state model 아님.

**중요한 결과:** 평균 편향 미보정 arm F의 성능은 오히려 B보다 나쁠 수 있다. R inflation만으로 해결했다고 해석하면 안 된다. B의 0.9cm는 6상태 P에서 heading 조건부 XY 고유축의 최소 표준편차로, 5Hz의 반복적 scalar range 갱신이 radial 근처 위치 방향을 초정밀로 오인한 결과다. Range 한 샘플 R std=.082812m이면 iid 수학 모델에서 ~82개 독립 반복만으로 예측 std=.00914m에 도달할 수 있다; 실제 RF bias 지속성 때문에 이 iid 환산은 부적합하다.

## 4. 과학적 의미와 다음 검증

1. 하나의 절대 UWB range는 2D 위치 ground truth 전체가 아니다: 고정거리 원 형태 constraint와 motion prior를 조합한다. b_hardware와 b_multipath를 한 시점 한 앵커만으로 완전히 식별할 수 없으므로 known-distance / heldout route의 독립 교정 필요.
2. RF first-path timestamp chain의 constant offset(-.5316m)은 이미 B에서 보정된 값이고, 이번 모델은 그 **이후 추가 편향**을 다뤘다. 실제 장치 antenna delay랑 같은 기호/원인으로 단정하면 안 된다.
3. 완전한 통계적 일관성을 위해 persistent b_r(t) nuisance-state / colored innovation, s-range correlated covariance, sensor geometry observability 및 background Q 상관을 함께 모델링해야 한다. 단순히 R 확대만으로 NEES~3를 맞추는 것은 채택 조건 불충분.
4. 외부 geometry, TX RX mount0/45 동일 native source, 독립 RF/gyro seeds에서 95% pose coverage/NIS whiteness와 RMSE의 동시 개선을 최종 판단한다.

실행물은 GitHub Actions artifact(sensor-v2-range-only-trust-ablation-20261011)에 전체 1008 run CSV, training models, per-case metrics, full P6 snapshot, NIS/status가 있다. 원본 소스와 데이터 변경 없음.
