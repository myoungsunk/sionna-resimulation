# CTRL-TRAJ-06 — 폐루프 EKF: ceiling 탐지 후 s 관측 제거·가중 하향의 효과 (EXPLORATORY)

## 실행 기록

| run | 내용 | 상태 |
|---|---|---|
| [41006198836](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41006198836) | 첫 실행 | **무효.** NULL에서도 mount 0 heading이 10–17° drift했다. |
| [41013436584](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41013436584) | `diag/`: s_fp range ripple 진단 | 참고 |
| [41014212025](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41014212025) | `variants/`: 원인 분리 진단 | 원인 확정 |
| 41014211980 | 첫 실행 설정으로 의도치 않게 다시 돌아간 run | 사용 안 함 |
| [**41015711136**](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41015711136) | **본 결과** `results_run_41015711136/` | 유효 |

무효 run의 원인: LUT 오차가 아니다(LUT와 정확 계산의 차이 < 0.1°). **tap 잡음이 s_fp power ratio에 남기는 편향**이다.
- mount 0에서 편향 중앙값은 0.026(σ_s 0.03)과 0.088(σ_s 0.09)이다.
- 원거리 heading 감도는 0.003/°에 불과해, 이 편향이 heading 수 도로 바뀐다.
- Stokes 방향(J11−J22, J12)은 이 편향을 받지 않는다. 영향을 받는 것은 s_fp의 분모다.

## 구성

- **EKF:** 저장소의 4-state EKF [x, y, ψ, b_g].
  - 예측: `core.transition`과 `r2_bias_replay.predict_one`의 Q. 벡터화 구현이 `core.predict`와 오차 0으로 일치한다.
  - 갱신: [r, s] 결합 갱신, R0 = diag(RR, σ_s²), χ²(2, 0.99) gate. s를 버리면 r만 χ²(1, 0.99)로 갱신한다. 회전 중에는 s를 쓰지 않는다.
  - 입력 잡음: `build_positive_bias_controls`(sensor-v2 잡음, B0 / L2 = 0.2°/s gyro bias). 초기 pose 오차는 0.1 m, 5°다.
- **경로:** y = 0.3에서 x 4.2 → 19.8 m(yaw 0°), 제자리 180° 회전 10 s, 19.8 → 4.2 m(yaw 180°). 총 166 s다.
- **채널:** CTRL-TRAJ-02 구성(실제 FFD bank, slab Fresnel, 1회 반사).
  - 시나리오: NULL(LoS만), LOS+C(ceiling), ALL(ceiling + floor + wall 2면).
  - range 관측은 참값 + N(0, RR)이다. 반사에 의한 range bias는 넣지 않았다.
- **관측 잡음:** 주파수 bin별 복소 백색 잡음을 Hann 창과 4× IFFT를 거쳐 FP 7-tap에 정확한 공분산으로 전파한다. 원거리 LoS의 std(s_fp)가 σ_s ∈ {0.03, 0.09}가 되도록 잡음 수준을 맞췄다.
  - `taps_debiased`: tap 잡음에 noise floor 차감을 더한 방식(운용형). mount 0에서 잔여 편향이 0.012–0.041 남는다.
  - `additive`: s와 Stokes에 Gaussian 잡음을 직접 더하는 방식. 편향이 없는 기준이다.
- **필터의 s 모델:** LoS 모델 LUT (x, y, ψ). QA로 정확 계산과 비교했다.
- **탐지기(causal):** EKF prior만 쓴다.
  - 직전 25 sample(1 m)의 Dperp와 σ_w = rms √P_ψψ를 계산한다.
  - flag 조건: Dperp > thr(leg, x̂ bin)이고 σ_w ≤ thr_σ(leg).
  - 임계값: 평가와 다른 seed의 NULL·BASE 실행 60회에서 NULL p95(coverage 0.82)로 정했다.
- **정책**

| 정책 | 내용 |
|---|---|
| BASE | 항상 s 사용 |
| DROP_DPERP | 탐지되면 s 버림 |
| INFL10_DPERP | 탐지되면 R_s를 10배 |
| DROP_DPERP_NOGATE | DROP_DPERP와 같되 σ gating 없음 |
| DROP_D0 | 전력만 쓰는 d0 탐지기, 같은 gating |
| ORACLE_DROP | 참값으로 원거리 반사 구간을 알고 s 버림 |
| R_ONLY | s를 쓰지 않음 |

- **불확실성:** seed 200개로 정책 간 쌍을 맞췄다.
  - bootstrap 95% CI(2,000회)로 RMSE와 BASE 대비 ΔRMSE를 냈다.
  - heading NEES와 95% coverage(χ²₁), XY NEES와 95% coverage(χ²₂)를 계산했다.
  - 평가 구간: 원거리 ρ > 6 m, t ≥ 30 s, 회전 제외.

## 결과 1 — ceiling이 폐루프 EKF를 얼마나 망가뜨리나 (BASE)

additive 잡음, σ_s 0.03, B0:

| | mount 0 heading | mount 0 XY | mount 45 heading | mount 45 XY |
|---|---|---|---|---|
| NULL | 1.17° | 0.09 m | 0.24° | 0.10 m |
| LOS+C | **7.14°** | 0.43 m | **3.49°** | 0.30 m |

- heading NEES는 NULL에서 1.2–3.4이고, LOS+C에서 20–370이다. 95% coverage는 2–22%로 떨어져 **심하게 과신**한다.
- heading 편향은 LOS+C에서 +1.8 – +6.4°다. 오염이 heading에 흡수된다.

## 결과 2 — 탐지 후 s 제거·가중 하향의 효과 (LOS+C, ΔRMSE vs BASE [95% CI], 음수가 개선)

additive 잡음:

| σ_s, bias, mount | DROP_DPERP | INFL10_DPERP | DROP_DPERP_NOGATE | DROP_D0 | ORACLE_DROP |
|---|---|---|---|---|---|
| 0.03 B0 m0 | +0.05 [−0.57, +0.46] | +0.13 [−0.47, +0.49] | −1.09 [−1.69, −0.62] | −0.32 [−0.59, −0.09] | **−2.93** [−3.38, −2.56] |
| 0.03 L2 m0 | +0.54 [+0.45, +0.64] | +0.58 | +1.73 | +0.71 | **−3.48** [−3.80, −3.14] |
| 0.03 B0 m45 | +0.73 [+0.52, +0.96] | +0.76 | +2.78 | **−0.88** [−1.05, −0.70] | +1.65 [+1.31, +1.98] |
| 0.09 B0 m0 | +0.04 [−0.17, +0.28] | −0.17 | −1.00 | −0.50 | **−2.34** |
| 0.09 B0 m45 | +0.06 [−0.00, +0.13] | −0.02 | −0.27 | **−1.20** [−1.28, −1.12] | +1.39 |

XY ΔRMSE:
- DROP_DPERP: +2 – +14 cm (악화).
- ORACLE_DROP: mount 0에서 −10 – −20 cm, mount 45에서 −2 – +21 cm.

taps_debiased 잡음에서도 방향은 같다.
- DROP_DPERP: mount 0에서 −0.09 – −0.34°, mount 45에서 +0.08 – +2.76°.
- ORACLE_DROP: mount 0에서 −2.3 – −4.8°, mount 45에서 +0.7 – +4.8°.

**NULL 오탐 비용:**
- DROP_DPERP의 원거리 flag 비율은 4–8%다.
- heading 손실은 additive mount 0에서 +0.15 – +0.70°, mount 45에서 +0.01 – +0.03°다.

## 해석

1. **ceiling 오염은 폐루프에서 heading과 XY를 크게 나쁘게 만든다.** heading이 NULL 대비 3–15배, XY가 2–5배 나빠지고 공분산이 심하게 과신한다. 문제는 실재한다.
2. **Dperp + P_ψψ gating으로 탐지해 s를 버리거나 가중을 낮추는 방식은 heading도 XY도 개선하지 않는다.** CI가 0을 포함하거나 악화 쪽이다. CTRL-TRAJ-04/05의 개루프 판별력(TPR 0.8–0.9)이 폐루프 이득으로 옮겨지지 않았다.
3. **원인 1: 참값으로 구간을 아는 ORACLE도 이득이 제한적이다.**
   - mount 0: 2.3–3.5° 개선되지만 3.3–4.2°가 남는다.
   - mount 45: 오히려 0.7–1.7° 나빠진다.
   - s를 버리면 heading 정보가 없어진다. 원거리 이전(< 6 m)에 쌓인 오염 편향을 되돌릴 수단도 없다. R_ONLY가 5.2°다.
4. **원인 2: 폐루프에서는 탐지율이 떨어진다.** 원거리 flag 비율이 34–44%다(NOGATE 77–88%).
   - EKF가 오염을 heading 편향으로 흡수해 예측 상태가 관측에 가까워진다.
   - gating을 빼면 탐지는 늘지만, bias가 있는 조건(L2)이나 mount 45에서 크게 악화한다.
5. **d0로 s를 버리는 방식은 mount 45에서만 일관되게 개선한다**(−0.9 – −1.2°, CI가 0 제외). mount 0에서는 섞여 있다. 개루프 순위(Dperp > d0)와 폐루프 순위가 다르다.
6. **결론: "탐지하고 버린다"는 맞는 대응이 아니다.** 오염을 모델링하는 방향이 필요하다. 예를 들어 다음과 같은 방식이다.
   - 천천히 변하는 ceiling-induced Stokes/s offset을 state로 추가하고, Dperp를 그 innovation으로 쓴다.
   - Stokes S2/S3를 heading-robust 관측으로 직접 넣는다.

## 불확실성 요약

| 항목 | 내용 |
|---|---|
| 통계 | seed 200개, 쌍 bootstrap CI 폭은 대개 ±0.1–0.5°. 결론의 부호는 CI 밖에 있다. |
| 잡음 모델 | mount 0 NULL 성능이 잡음 모델에 민감하다: additive 1.0–1.8°, debiased 3.3–7.8°(잔여 편향). 정책 결론(DROP_DPERP 무효, ORACLE의 mount별 부호)은 두 모델에서 같다. |
| s 모델 | LUT와 정확 계산의 차이 < 0.1°(variants run). |
| 필터 일관성 | NULL heading NEES 1.0–3.4, coverage 0.85–0.95. 오염 시 NEES 20–370으로, 공분산이 오염을 반영하지 못한다. |
| 구조적 한계 | 직선 경로 1개, 1회 반사, range bias 없음, 두 포트 위상 이상적. 학습된 μ/R(9 arm)이 아닌 R0형 EKF다. 임계값은 NULL 모델 시뮬레이션으로 정했다. |
