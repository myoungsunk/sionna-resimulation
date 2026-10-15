# N4-Q4-R 실행 결과 — Full RF Prior Covariance Calibration (2026-10-15)

**최종 판정: Q4-R0 / R1 / R2 / R3 코드·수치 실행 PASS, 과학적 Prior calibration FAIL.** 이후 Q5/6 투입 금지. 원본 Joint4/SR4·POWER_JOINT·LoS LUT·Sensor-v2 gyro/wheel·원 RF 데이터 변경 없음.

## 1. 원본·결과 증거

- [Q4-R0/R1 PASS Run 38743107112](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38743107112), [원시 결과 artifact 11976975584](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38743107112/artifacts/11976975584), archive SHA256 **86dc05d64ddb2ddf5a688665f387b6d12346162491fa9435ecaecf6c8f1aefe9**. 448개 후처리 P 정책 평가.
- [Q4-R2 PASS Run 38743984546](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38743984546), [원시 x-/P- 및 x+/P+ artifact 11976841890](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38743984546/artifacts/11976841890), SHA256 **4f979b13f32c0a269d10dd0d7d1dc39d6f8b82dca425fb2e9aacf3cfda22e510**. 240개 실제 재귀 실험·원본 Joint4/SR4/POWER_JOINT **48개** 출력/게이트 parity 검사.
- [Q4-R3 PASS Run 38744726747](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38744726747), [원시 신뢰도/기하 평가 artifact 11977017861](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38744726747/artifacts/11977017861), SHA256 **6cf473eb82b867e6b45c01500cdadaf088e8bdbf0f2f9ab616477c3080a5ff8d**. 56개 실제 재귀 prior FFD sigma-point 평가.
- [독립 아카이브·정합 재감사 PASS Run 38745641140](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38745641140), [stage-gate artifact 11978476397](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38745641140/artifacts/11978476397), SHA256 **a55097fcb2cfee94a026fe3bc662f55ac7710abfa2e21c27bb12eed25c4321c0**.
- 새 저장소 branch: \`research/n4q-q4r-prior-calibration-20261015\`. 원본 R2, N4-Q4, N4-C, N4-B의 각 기존 source·artifact는 별도 연구 브랜치에 동결 보존.
- 모든 stage를 감사→원본 ZIP SHA/CRC→수학 유닛테스트→실제 수치→원본 baseline parity 순서로 검증. 초기 Q4-R0 실패는 기존 N4-C 소스가 해당 별도 브랜치에 없어 source blob 감사를 통과하지 못했던 문제: 원본 N4-C 파일을 **동일 Git blob SHA**로 복사해 재감사한 뒤 최종 실행함. 최초 실패 run 결과는 채택하지 않음.

## 2. Q4-R0: 과학적 학습 데이터 가용성

동결 R4/R5 파일 \`SAMPLES.json\`은 위치·Yaw 순서(정지 중 yaw-sweep 포함)를 포함하나 **원 original source manifest에 검증된 시간별 \`t_s,ds_odom,dtheta_gyro,dt_s\` 제어열이 없음**. 따라서 1303 samples 자체를 실제 독립 Gyro/Odom 순차 주행 트레이스로 해석해 공분산 모델을 학습하지 않았다.

현재 R2는 원본 979 time-steps와 오리지널 Gyro/Odom controls가 있는 진정한 sequential stream이지만 같은 corridor, 같은 Full RF channel realization, sensor seed 0이며 수차례 성능을 이미 확인한 데이터이다. **독립 final holdout으로 재사용 불가**.

결론: \`R4/R5_GYRO_WHEEL_TIME_TRAIN_AVAILABLE=false\`, \`Q4R_FULL_SCIENTIFIC_TRAIN_PASS=false\`. R1~R3는 **사전 고정된 하이퍼파라미터/오프라인 파일럿 검증**이지만 **독립 학습 데이터로 추정된 확률적 보정모델**은 아니다. R2 정책 비교 목록도 이전 R1을 이미 본 상태에서 고정되었으므로, 최종 hidden-test 성능이라고 주장하지 않는다.

## 3. Q4-R1: 사후 P 보정 대조 (상태/게이트 변경 없음)

Q4-R1의 모든 후보는 기존 필터의 실제 \`x^-\`를 유지하고 PSD covariance만 변환. Raw, scalar ×4/16/64, congruence D, conditional XY narrow-eigen-axis PSD addition 및 combined PSD. 실제 point RMSE는 모든 후보에서 원본과 **동일**이라는 독립 재검증 PASS.

### L2 Full mount0 원본 Frozen Joint4/POWER_JOINT

| 후처리 후보 | Pose NEES | Pose95 포함률 | median heading sigma |
|---|---:|---:|---:|
| J4 RAW | 296.61 | 16.89% | 0.805° |
| J4 4×P | 74.15 | 21.11% | 1.609° |
| J4 64×P | 4.635 | 82.51% | 6.436° |
| POWER_J4 RAW | 12.854 | 45.96% | 1.145° |
| POWER_J4 4×P | **3.214** | **93.37%** | 2.291° |
| POWER_J4 16×P | 0.803 | 100% | 4.582° |

**해석:** Scalar inflation으로 사후 평균 NEES/coverage만 맞추는 것은 가능하나 원래 Headings·Bias를 전혀 수정하지 못하고 16×P는 과도한 확장이다. 독립 validation에서 보정 배율을 추정한 결과가 아니므로 4×P를 과학적으로 선택하지 않는다.

## 4. Q4-R2: 수정된 P를 실제 RF 갱신 전에 삽입한 Recursive EKF

- 본 stage는 R1의 '기존 x 고정'과 달리 \`Pcal^-=P^- + Q_PSD\`를 각 RF 업데이트 직전에 적용하며 변경된 \`K\`, Gate, posterior \`x^+,P^+\`, 미래 예측 \`x^-,P^-\`가 모두 재귀적으로 변한다.
- 진짜 bias 0,+0.01,+0.05,+0.20°/s, Full/LoS mount0/45, Joint4/SR4, 원 R0/POWER_JOINT, Q_SMALL/Q_MEDIUM/Q_LARGE 및 conditional XY 작은 eigen-axis PSD 보정. 원본 Gyro/Odom·관측·LoS LUT·R0 고정.
- 사후 보정에서 쓰인 \`64×P\` 등은 **매 업데이트 증폭 시 방향미관측 bias covariance가 폭발**할 위험이 있어 실제 재귀군에서 반복 적용하지 않음. 따라서 R1과 R2는 한 모델을 동일 적용한 결과가 아니라 **서로 목적이 다른 대조**.
- **240** 재귀 policy arms 수행, 원본 raw **48개** baseline state/cov Gate parity (state/cov ≤1e−6, gate mismatch 0) 통과.

### Full RF L2 J4

| 모델 | Mount0 Heading RMSE | Mount45 Heading RMSE | Mount0 Bias RMSE | Mount0 Pose NEES | Mount0 Pose95 |
|---|---:|---:|---:|---:|---:|
| 원 J4 | 7.521° | 0.848° | 0.09608°/s | 297.85 | 16.77% |
| J4 + Q_MEDIUM | **11.449°** | **15.227°** | 0.14970°/s | 26.49 | 46.20% |
| 원 POWER_J4 | **1.991°** | **0.727°** | **0.03266°/s** | 12.89 | 45.72% |
| POWER_J4 + Q_SMALL | 3.596° | 2.464° | 0.06198°/s | 6.76 | 81.91% |
| POWER_J4 + Q_MEDIUM | 8.729° | **11.902°** | 0.14066°/s | 7.58 | 80.34% |
| POWER_J4 + EIG_NARROW_10CM | 2.628° | 1.926° | 0.04544°/s | 4.81 | 84.92% |

**핵심 반례:** 공분산 NEES와 포함률이 개선되는 경우에도 **실제 재귀 Heading 및 Bias 성능이 크게 악화**했다. 특히 원 Full m45의 강력한 baseline 0.727°를 보존하지 못했다. Causal uncertainty management는 단순한 P amplification/floor가 아님.

## 5. Q4-R3: 수정된 실제 Recursive Prior의 LoS FFD 예측불확실도

실제 \`x^-,P^-\`에 6개 cubature points (x,y,ψ) → 원 FFD/LUT → \`s_LoS\` geometric prediction interval; 원 GT LoS expected s 및 \`I_geom\` oracle label은 offline score only. 포함률과 info-Brier 및 sharpness를 모두 계산.

### Full RF L2 Joint4 (829 timepoints)

| 모델 | LoS geometric95 coverage | information Brier |
|---|---:|---:|
| J4 RAW | 32.21% | 0.1835 |
| J4 Q_MEDIUM | 64.05% | 0.2347 |
| POWER_J4 RAW | 72.86% | **0.0474** |
| POWER_J4 Q_MEDIUM | 86.01% | 0.1588 |
| POWER_J4 EIG_PLUS_YAW1 | 86.25% | 0.1702 |

### Full RF L2 Mount45 (829 timepoints)

| 모델 | LoS geometric95 coverage | information Brier |
|---|---:|---:|
| J4 RAW | 53.80% | **0.0175** |
| J4 Q_MEDIUM | 59.59% | 0.1692 |
| POWER_J4 RAW | 69.12% | **0.0173** |
| POWER_J4 Q_MEDIUM | 71.17% | 0.1871 |
| POWER_J4 EIG_PLUS_YAW1 | 70.08% | 0.1909 |

**Q4-R3 내부 파일럿 통과조건(Full mount0/45 B0/L2, Joint4/SR4 각 geo95 ≥90% 및 point accuracy/LoS guard) 미달**. 모든 Full R3 policy에서 두 Mount 조건을 동시에 만족한 arm **0개**. 실제 LoS의 기하 응답 포함률은 RAW ~100%인데 Q_MEDIUM 또한 100%이지만, LoS 예측구간 폭은 m45 median σs 약 0.0073 → 0.0627로 약 8.6배 확대, 정보량 분류 Brier 악화 (L2 0.00985 → 0.08719). LoS의 의미 있는 sharpness도 보존하지 못했다.

## 6. 독립 재감사 및 결과 판정

[Run 38745641140](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38745641140) 독립 프로그램은 각 원 결과 archive ZIP SHA/CRC, source blob, 실행군 completeness **R1 448 / R2 240 / R3 56**, R2 original 48 baseline gate/source parity, R1 P-only는 Heading/XY/Bias point estimates 변함 없다는 negative test, R3 original Q4 cubature coverage의 수치 parity 모두 재확인 PASS.

\`STAGE_GATES.json\`:
- \`Q4R_SCOPED_TECHNICAL_PASS=true\`
- \`Q4R_CALIBRATION_SCIENTIFIC_PASS=false\`
- \`any_R3_full_geometry_90pct_pilot=false\`
- \`R4R5_sequential_prior_train_verified=false\`
- \`Q5_GO=false\`, \`Q6_GO=false\`.

**최종:** Q4-R은 계획한 0/1/2/3단계 *실제 실행 완료*. 단순 Cov-only calibration을 N4-Q4 Full RF 원인 해결책으로 채택할 수 없음. \`POWER_JOINT\` 기준선을 보존하며, 새 센서 관측오차의 signed mean/cov/time correlation과 추정기 Prior consistency를 함께 모델링할 필요. 현재 동결 R4/R5 raw pose samples를 임의의 timed control stream으로 해석해 train/test 경계를 어기는 실험은 하지 않는다.

## 7. 재진입을 위한 실제 필요한 자료

1. R4/R5 또는 신규 scene의 **진짜 시간·wheel/gyro controls·pose ID·ground truth**와 거기에 맞춘 Full/native LoS RF packet; 원본 source SHA/boot/FP tap, unit, mount angle.
2. 별도 실험 scene/gyro+RF noise seed와 independent evaluation split. 현 R2는 이미 반복 사용했으므로 final hidden test 불가.
3. 과신된 Prior를 단순히 크게 만드는 대신 **관측 편향과 필터 상태 편향**을 완화할 수 있는 model, temporal persistence/occlusion/FP 전환과 online lagged quality, normalizable measurement likelihood 또는 명확한 heuristic guard.
4. LoS에서 공분산의 sharpness·Heading·Bias 성능을 보존하는 모델. Mount45 근처 유리한 FFD \`Hψ\` 동작점에 대한 신뢰 정보 소실 금지.

현재는 Q5–Q7에 false PASS를 부여하지 않는다. Q7 original Full multipath distinct scenes 입력은 \`BLOCKED_INPUT\`로 유지.
