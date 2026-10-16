# 실제 Odometry 위치 프로세스 Q 검증 — 결과 보고 (2026-10-16)

**결과: SOURCE / NUMERIC / INDEPENDENT REVIEW PASS. 하지만 실제로 검증된 Sensor-v2의 Q는 기존 필터에 이미 구현되어 있었음. 이동거리 잡음 Qd 확대를 Mount 45도의 조건부 XY 공분산 과신 해결책으로 채택하지 않음.**

## 증거 링크 및 원본 동결

- [메인 실행 Run 38846021652](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38846021652), [원시 artifact 12023177767](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38846021652/artifacts/12023177767), SHA256 78a1a13503846ae80ac19f16276f0c4a6c924452bd0e70e902c12119e718983a.
- [독립 재감사 Run 38846477218](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38846477218), [검증 artifact 12023925169](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38846477218/artifacts/12023925169), SHA256 2dafc59ca8cefb07764272777564e64a1124cc1cd8008634e05b496cb0a8a755.
- 기존 원 N4-C와 N4-B, 원 R2 Gyro+Wheel, Full/LoS RF 및 LoS 3D FFD LUT 완전 동결. POWER_JOINT의 보정평균, Range/s 측정 공분산, 측정 Gate 임계값은 수정하지 않음.
- 총 **160개 실제 Joint4/SR4 recursive arm** (2 mount × 4 gyro Bias × 2 solver × [Full 7 arms + LoS 3 arms]); 동일 seed0/trajectory/RF, 979 time frames, 초기 30초 제외 829 eval frames.
- N4-C와 원 R0의 x/P/Gate에 대해 48개 원본 정합 검증 통과. 별도의 소스 Git blob과 수치평가 zip SHA/CRC 독립 감사 통과.

## 현재 Q의 수학적 의미와 원 모델

Original core.py는 4-state transition x' = f(x, measured odom distance ds, measured gyro increment, dt)의 Jacobian F,G를 정확히 계산하며,

$$
P^-_{k+1}=F P^+F^T + GQ_{\mathrm{input}}G^T
$$

로 물리 입력 잡음을 위치/Heading으로 사상한다. Frozen original r2_bias_replay.py의 입력 잡음은 다음과 같다.

$$
Q_{\mathrm{input}}=
\mathrm{diag}\left(
2\cdot10^{-5}|\Delta s_{\mathrm{odom}}|,
\mathrm{rad}(0.015)^2\Delta t,
0
\right).
$$

Sensor-v2는 실제로 $2\cdot10^{-5}|\Delta s_{\mathrm{true}}|$인 Wheel distance 백색잡음을 생성하고, Gyro increment는 $\mathrm{rad}(0.015)^2\Delta t$를 사용한다. 즉, 원래 입력 Q와 생성기의 모델은 이미 정합되며, 원 x/y 공분산에는 $G$를 통해 세계좌표 방향성 상관까지 전파된다.

Sensor-v2의 Wheel yaw noise는 별도로 생성되지만, 현 4-state Heading predictor는 Wheel yaw가 아닌 Gyro를 사용하므로 Wheel yaw 노이즈를 Heading 측정잡음으로 중복 추가하는 것은 부당하다. 진짜 hardware encoder 바닥 잡음을 측정한 결과는 아님.

## 실제 생성 오차 Monte Carlo 감사

같은 원본 R2 주행의 독립 seed 1000–1031, B0/L0/L1/L2의 기준 노이즈 스트림(수준별 seed 스트림은 공유하므로 별도 128개 독립 RF 실험으로 주장 불가):

| 검증 | 결과 | 생성모델 정규화 기준 |
|---|---:|---:|
| Wheel normalized error variance | **0.985792** | 1 |
| Gyro normalized error variance | **0.992300** | 1 |
| measured-Qd / true-Qd median | **0.999867** | 1 |
| mean abs Qd relative difference | **1.773%** | 0 |
| Frozen seed0 Gyro/Wheel control parity | bit exact | exact |

Q는 원본 Sensor-v2 백색잡음과 일치. Full RF의 conditional XY NEES 원인을 임의의 빠진 Qxx/Qyy 항으로 단정할 수 없다.

## 실재 recursive Q 민감도: Full RF L2 Joint4

변경한 항은 input Wheel 거리분산 Qd뿐. 후보는 원래 1배와 거리분산 2/4/16/64배 및 legacy-Euler 대 SE2 lateral deterministic discrepancy를 별도 가설로 만든 covariance stress이다. **2–64배 후보는 실제로 측정된 Odometry uncertainty 값이 아니다.**

| Mount | Qd factor | Heading RMSE ° | XY RMSE m | Bias RMSE °/s | conditional XY NEES | narrow axis NEES | Pose NEES | Pose 95% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0° | 1× | 1.991 | .1917 | .03266 | 7.919 | 6.334 | 12.890 | 45.7% |
| 0° | 2× | 1.804 | .1680 | .03065 | 7.697 | 6.352 | 11.960 | 49.8% |
| 0° | 4× | 1.598 | .1468 | .02861 | 7.379 | 6.023 | 10.821 | 54.3% |
| 0° | 16× | 1.382 | .1308 | .02572 | 6.076 | 4.689 | 8.662 | 64.2% |
| 0° | 64× | 1.321 | .1289 | .02409 | 4.648 | 3.285 | 7.040 | 73.8% |
| 45° | 1× | **.727** | **.0786** | **.01231** | 16.058 | 13.774 | 18.580 | 12.3% |
| 45° | 2× | .763 | .0840 | .01276 | 16.168 | 13.066 | 18.810 | 11.9% |
| 45° | 4× | .761 | .0922 | .01283 | 15.690 | 11.737 | 18.294 | 16.5% |
| 45° | 16× | .731 | .1101 | .01237 | 14.471 | 10.029 | 16.883 | 29.7% |
| 45° | 64× | .792 | .1416 | .01297 | 14.190 | 9.156 | 17.009 | 32.3% |

마운트 45도에서 Qd×64는 XY RMSE .0786→.1416m 악화, conditional XY NEES 16.06→14.19로 여전히 2-DoF 명목 기준 ~2보다 훨씬 과신한다. 마운트 0도에서는 부분적으로 RMSE가 개선되나 원본 생성기의 물리적 Wheel 백색잡음 자체는 맞으므로 이를 새 진실 Q라고 주장하지 않음.

B0에서도 마운트 0도 1×→4× Heading 1.773→1.401°, XY .1621→.1410m이나 condXY 7.400→7.515로 약간 악화. 반면 마운트 45도 B0 1×→4× Heading .815→.829°, XY .0849→.1014m로 악화. 동일 Q 변경을 모든 mount에 적용하는 설명이 안 됨.

## 정상 LoS 보호 검사

Original R0 LoS J4에서 Qd×4 대비:

| Mount, bias | Heading RMSE 1×→4× | XY RMSE 1×→4× |
|---|---|---|
| 0°, B0 | .5217°→.6294° **악화** | .0367→.0382m **악화** |
| 0°, L2 | .2435°→.2843° **악화** | .0272→.0307m **악화** |
| 45°, B0 | .1122°→.0686° 개선 | .0400→.0330m 개선 |
| 45°, L2 | .1583°→.1440° 개선 | .0435→.0373m 개선 |

LoS에서도 geometry/cross-state coupling에 따라 Q 확대 효과가 다른 방향. 원래 깨끗한 LoS의 point accuracy와 covariance sharpness를 무시할 수 없다.

Original Legacy Euler truth vs SE2 transition lateral discrepancy magnitude을 순차 PSD 추가로 취급한 별도 모델은 L2 Full Mount45 J4 condXY 16.0579→16.0484, Heading .727425→.727331°, XY .078587→.078595m로 거의 변화 없음. 이는 deterministic motion approximation error를 실제 독립 랜덤 wheel noise라고 간주할 근거가 아니라 부정 대조이다.

## 최종 해석과 다음 실험

**CODE PASS, ORIGINAL PARITY PASS, SENSOR Q SOURCE MATCH PASS, TRUE RECURSIVE EXPLORATION PASS.**

**Scientific correction PASS: false.** Q distance 백색잡음 부재/계수 오지정이 주요 원인이라는 가설은 현 Sensor-v2 내부 모델과 맞지 않고, 이를 64배 늘려도 Mount45 위치 위치측정 과신이 남는다. Conditional XY의 좁은 고유축은 RF/위치 동역학/장기간 자기상관 등 다른 원인일 수 있으며 이번 결과로 하나를 확정하지 않는다. 독립 Scene 검증 없이 829시점을 독립 통계 표본으로 취급하지 않는다.

다음 추천: **원래 물리 Q는 고정한 상태에서 POWER_JOINT High-power Range V_r(q) floor만 변경**, signed μr/μs 및 s variance Vs 유지, correlated covariance SPD 및 NIS/Gate 통과변화 검사. 이어 Range/cross-XY/Heading 기하 등급별 오염을 측정한다. 이 후속 R-only 요인분해는 이번 실험에서 실행하지 않았다.

Main artifact contents: ODOM_Q_FINAL.json, ODOM_Q_ALL_RECURSIVE.csv (160 rows), ODOM_Q_SENSOR_MC.csv, ODOM_Q_SOURCE_PARITY.csv, all 32 per-case-level-solver QOD_*.npz for complete x-/P-/x+/P+, NIS, accepted/rejected, process Q_x/y. Independent artifact VERIFY_FINAL.json and PAIRED_FROM_ORIGINAL.csv (all revised Q candidates).
