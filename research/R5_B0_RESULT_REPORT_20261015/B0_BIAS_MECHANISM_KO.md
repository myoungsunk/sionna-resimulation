# B0 Full RF: 3/4-state, Gyro Bias prior, Range-only versus s-only 진단 결과

2026-10-15 · `research/r5-b0-hard-soft-physics-20261015`

## 검증 출처
- 기존 보관된 R2 3/4-state 재귀 동결 비교: [Actions Run 38689513593](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38689513593), [artifact 11951221174](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38689513593/artifacts/11951221174), artifact ZIP SHA256 `a6ad6fd2ed19dbed91db69c838d1a628a13f11db47f98e8e3315ca3c94a1c327`, 32개 원 성능 행/16 paired 비교.
- 추가 4-state Bias prior sensitivity 및 Range-only/s-only/Joint, 공통 Gate 조건: [Actions Run 38689772383](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38689772383), [artifact 11951427487](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38689772383/artifacts/11951427487), artifact ZIP SHA256 `1089a8a713e0b4e8099d76102b9edc6384a4811826a71573d79a0459f3dd75e6`.
- 두 실행 모두 Pre-execution source/blob audit GO, original RF/R2 ZIP SHA/CRC verified, 이전 코드/LUT/R0/source 수정 없음. 4-state sigma0.1 기존 재귀와 3/4조건 strict1e-9, B0 Full Mount0 1조건 max state ~7.58e−8 (기존 다른 재실행에서도 재현된 수치 미세차), gate diff 0.
- 진짜 자이로 Bias `B0=0°/s`; 4-state bias state는 별도로 학습 가능. 결과는 하나의 corridor/noise seed0, independence/generalization 미검증.

## A. 기존 3state vs 4state 재귀 결과, B0 Full RF (Heading RMSE °)

| Mount | S3 | S4 | J3 | J4 | SR3 | SR4 |
|---|---:|---:|---:|---:|---:|---:|
| 0° | 0.59555 | 15.35646 | 0.70137 | 7.48996 | 0.69765 | 7.51566 |
| 45° | 0.38006 | 1.70829 | 0.24998 | 0.84496 | 0.24976 | 0.84616 |

- 원래 B0 DR4 Heading RMSE 0.483996°. RF Full 데이터가 깨끗한 노바이어스 DR보다 조금/크게 악화할 수 있지만, 4state의 큰 악화는 3state에선 거의 나타나지 않는다.
- Mount0 S4 최종 b `−0.09304°/s` (진짜 0), J4 최종 b `+0.01432°/s`. 단일 최종값으로 축적 경로 전체를 설명하지 않으므로 bias RMSE와 trajectory를 함께 검사.

## B. 동일 4state의 Gyro Bias prior 표준편차 변화 (B0, Full)

**4-state Joint Range+s, 동일 원본 R0 gate threshold; Gyro Bias prior mean=0, Q_bias=0**

| b prior σ (°/s) | Mount0 Heading RMSE ° | Mount45 Heading RMSE ° | Mount0 Pose NEES |
|---:|---:|---:|---:|
| 0.001 | **0.70055** | **0.27934** | 54.60 |
| 0.010 | 2.45356 | 0.74367 | 85.88 |
| 0.030 | 6.46919 | 0.87559 | 1479.17 |
| 0.100 (원래 기준선) | 7.48996 | 0.84496 | 2591.15 |

**해석:** B0에서는 b prior를 매우 좁게 설정할수록 틀린 RF 정보가 Gyro Bias로 흡수되는 폭이 작아지면서 Heading 악화가 크게 줄어든다. 그러나 이것은 참 Bias=0을 알고 있는 경우의 연구 통제에 해당하며, 실제 Bias L2=+0.20°/s에서는 오히려 심각한 underadaptation이 될 수 있다. **범용 배포 방안으로 b prior σ=0.001°/s를 채택하지 않는다.**

## C. Common gate와 Range/s의 효과 분리

Mount0 Full, B0:
- Original Joint4 b prior `0.1°/s`: **7.48996°**.
- Joint4 b prior `0.001°/s`, dynamic gate: **0.70055°** (829평가시점 중 776회 joint accepted).
- **동일 원래 J4 수용 마스크를 강제**하고 b prior `0.001°/s`: **1.62393°** (768회 accepted). 원본 J4가 7.48996°이므로 gate differences만으로 악화 전부를 설명할 수 없다.
- S-only4 b prior `0.001°/s`: Heading RMSE **0.60268°**, Pose NEES **3.416** / Pose95 **100%**.
- Range-only4 b prior `0.001°/s`: Heading RMSE **5.41650°**, Pose NEES **291.996**.
- Range-only4 b prior `0.1°/s`: Heading RMSE **9.11614°**.

Mount45 Full, B0:
- Joint4 b prior `0.001°/s`: Heading **0.27934°** vs original `0.1°/s` **0.84496°**.
- Range-only4 b prior `0.001°/s`: Heading **9.73754°**.
- S-only4 b prior `0.001°/s`: Heading **0.37849°**.
- Pose NEES는 Mount45 Joint sigma0.001에서도 **83.37**, Pose95 **4.95%**이므로 b prior만 조정해 모든 covariance 문제가 해결되는 것은 아니다.

**중요:** Range-only에서도 위치 수정과 pose–heading 공분산을 통해 Heading이 크게 오염될 수 있다. 따라서 "편파 s 오염만 제거하면 Full RF가 정확해진다"는 것은 B0 Full에서 성립하지 않는다. `R_r(q)`, `R_{rs}(q)`, first-path detector bias, 시간상관, XY conditional covariance 검증이 필요하다.

## D. 남은 인과 해석 한계
3state vs 4state 및 prior sensitivity는 b prior variance, 교차공분산, predict dynamics, gate acceptance을 함께 변화시킨다. Fixed-gate ablation은 gate만이 단독 원인이 아님을 지지하지만, 전체 악화분을 전부 b의 point estimate 하나에 귀속시킬 수는 없다. Numeric covariance parameterization과 과신, estimator model mismatch는 별도 감사·검증 대상이다.

## E. 연구 결정
- **B0 Full MP 오염 + gyro-bias 추정 자유도/공분산의 결합이 Heading 실패를 증폭한다**는 것이 추가 수치 evidence로 강하게 지지됨.
- **더 복잡한 물리 피처 Hard Gate는 우선 배제**. G5 MP-proxy가 true Heading harm을 식별하지 못하는 이유 및 LoS false rejection 확인.
- **Signed s mean+Rs**는 Mount0 B0 3.362°지만 Mount45 1.350°, DR4 0.484° 대비 악화. Mean/variance의 조건부 교정 및 Rr, Rrs, time-correlation, bias confounding diagnostics가 다음 대상.
- 다음: B0 prior/innovation/conditional-heading information 기반 **harm-aligned quality score** 연구, 기존 169 yaw-sweep에서 physics+gradient shape likelihood 검증, L2에 대한 real bias correction retention guard.

`technical_execution_PASS=true`; `scientific_generalization_PASS=false`.
