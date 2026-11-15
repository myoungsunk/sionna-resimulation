# G1-MODEL-003 v3 개발 결과

mount 0의 G-T1 A/B/C에서 거리 모델을 개발한 결과, S3-R은 `DEV_FAIL_RANGE`였다. 거리 모델의 통과가 S3-J 진입 조건이므로 G-T2·G-V의 봉인을 유지했다. 확인 실행은 0회다.

## S0–S2′

- 동결된 0.2 s 타임라인의 165,933 packet을 SHA-256으로 재확인했다. v2 R4·J4의 B0 기준값을 추가 회귀 36개에서 재현했다. [S0 회귀 기록](S0/REGRESSION_V3.json)
- 두 SNR의 거리 RMS를 기준으로 O10을 골랐다. O10은 0.09018 m, O30은 0.12960 m였다. 차이는 39.42 mm로 5 mm 동률 기준을 넘었다. 동결 지연 원점은 6,012/6,012 pose에서 재확인했다. 선택 체인의 LoS parity는 최대 pooled p90 |Δs|가 6.41×10⁻⁷로 기준 0.005 이하였다. [거리 규칙](S1/RANGING_RULE_SELECTION_V3.json) · [parity](S1/PARITY_V3.json)
- 계획과 합성 검산을 `e6a9b09`에 먼저 커밋했다. G-T1의 특성화와 경로별 영점 RMS 검사를 실행했다. S2-T의 값은 필터 실행 전 `e993969`에 커밋했다. S2-F상 TB3 r2.1.0은 C3에서만 정확도 범위에 들었다. S3-R 결과로 인해 정확도 판정에는 진입하지 않았다. [계획](S2/CHARACTERIZATION_PLAN_003_V3.json) · [특성화](S2/CHARACTERIZATION_003_V3.json) · [S2-T](S2/TRANSFER_PRECHECK.json) · [S2-F](S2/FUTILITY_V3.json)

## S3-R

1차 체인 O10, 30 dB, G-T1 A/B/C, 6개 경로, 40 seed의 B0 집계다.

| arm | heading 포함률 | heading CI 상한 | XY 포함률 | heading NEES | heading RMSE | XY RMSE |
|---|---:|---:|---:|---:|---:|---:|
| DR | 99.8% | 100.0% | 95.7% | 0.14 | 4.34° | 0.614 m |
| R4 | 35.8% | 40.7% | 21.0% | 152.79 | 23.16° | 2.408 m |
| R-M | 38.4% | 43.4% | 25.9% | 360.88 | 32.00° | 3.045 m |
| R-MC | 60.3% | 65.6% | 49.4% | 46.06 | 16.31° | 1.488 m |

- 거리 arm 세 개가 B0/L0/L1/L2와 TB3 두 점에서 모두 실패했다. R-MC는 R4보다 B0 포함률과 NEES가 개선됐지만 세 NEES 모두 허용 범위 [0.5, 2.0]을 벗어났다. B0 초기 heading 오차를 0으로 둔 R-MC의 heading·XY 포함률도 63.3%·53.3%였다. [1차 판정과 전 수준 집계](S3/RANGE_STAGE.json)
- R-MC의 B0 heading 포함률은 A/B/C의 TEACH→REPEAT에서 각각 9.5%·28.8%·49.9%였고, 직진 대조 P-B에서는 99.5%·97.5%·99.5%였다. R-MC는 TEACH→REPEAT에서 R4 대비 수용된 정지 packet당 절대 heading 갱신량을 0.0696°에서 0.00775°로 줄였다. 두 arm의 포함률과 갱신량이 보여 주는 차이는 경로별 개발 결과다. [경로별 집계](S3/RANGE_STAGE.json)
- C6 보정용 O10/30 dB 관측 중 45,544/1,261,200개(3.61%)가 두 학습 앵커의 거리 지원 구간 밖이었다. 기존 갱신 집계의 `range_mean_outside_support`는 실제로 바깥쪽 두 절점 사이를 벗어나 상수값이 적용된 packet을 세며, 이 경우는 318,090개(25.22%)다. 두 수치를 분리해 보고한다. [C6 지원 구간과 절점 집계](S3/RANGE_C6_SUPPORT_COUNTS.json)
- A/TEACH→REPEAT의 S2-T 거리 |Z|는 정의된 세 구간에서 최대 5.48이었고 R-MC의 B0 heading 포함률은 9.5%였다. B/TEACH→REPEAT는 정의된 두 구간에서 최대 1.93이었고 B0 heading 포함률은 28.8%였다. 비교는 희소한 거리 구간의 사전 지표와 전체 경로의 사후 포함률을 함께 기술한 것이다. [S2-T](S2/TRANSFER_PRECHECK.json) · [S3-R](S3/RANGE_STAGE.json)
- O30 30 dB와 O10 20 dB는 보고용 대조로 보존했다. [O30](S3/RANGE_REPORT_O30_30.json) · [20 dB](S3/RANGE_REPORT_OR_20.json)

## S-V·S-C 진단

`DEV_FAIL_RANGE` 뒤 G-T1에서 `DIAGNOSTIC_ONLY` 실행을 시작했다. 진행 중인 S-V·S-C 진단은 개발 판정과 분리한다.

- 기존 RT의 P-B 직진 구간에서 스윕 없이 실행한 패킷 편파 진단을 추가했다. DR 짝 비교, 감도가 낮은 구간, 오차가 증가한 구간과 재현 기록을 포함한다. **DIAGNOSTIC_ONLY · S2′ STOP (FULL_6) · Step 3 보류.** [P-B 진단 보고서](PB_STRAIGHT_DIAG/REPORT_KO.md)
