# Dual-LP: Direct LoS → 다중경로 오염 → 관측 신뢰도 보정 — 그림·표·원장

**자료 정리일:** 2026-11-02. **성격:** 기존 R2-B/R4-B/R5-B × 4 gyro 조건 12개의 Full RF 결과 + 새 **탐색적 Direct LoS replay**. 새 Sionna RT 없음, 기존 EKF·RF·학습 회귀·평가 기준 미변경.

## 0. 가장 중요한 메시지

물리적 안테나의 편파 Heading 민감도는 보정 후 더 커진 것이 아니다. **Direct LoS에서는 Heading 정보가 존재하지만 Full multipath에 의해 공통 first-path 포트별 복소 신호와 선택 tap이 바뀌고, 그 signed 잔차가 EKF의 상태 갱신을 왜곡할 수 있다.** 기존 MB_VAR는 채널 물리현상을 취소하지 않고 저장된 Range 평균 보정과 편파 관측의 재귀 갱신 가중치를 바꾼다. R2/R5에서는 일부 회복하지만 R4에서는 효과가 제한되고 XY는 오히려 악화한다.

## 1. 본문 권장 그림 4개 + 보조 그림 9개

| 사용 | Figure | 그림의 정확한 질문 | 반드시 설명할 제한 |
|---|---|---|---|
| **Main 1: 관측 전후** | `F03_RAW_MULTIPATH_POLARIZATION_TIME.png` | 같은 pose의 LoS signed s가 Full에서 어떻게 달라지고 tap이 바뀌는가? | 원 채널 비교이지 EKF 인과효과가 아님 |
| **Main 2: 물리 원인** | `F04_RANGE_CONDITIONED_PHYSICS.png` | 거리별 편파차·first tap 선택 변화·원래 Heading 민감도는 어떻게 변하는가? | 거리 구간이 시간·방위와 결합됨, 독립 공간 인과 분리 아님 |
| **Main 3: 결과 서사** | `F01_THREE_STAGE_B0_PERFORMANCE.png` | LoS 탐색 기준선, 기존 Full BB, 보정 MB의 실제 성능은? | LoS μ=0, Full은 기존 μ이므로 단일변수 인과 비교가 아님 |
| **Main 4: 조건부 성능** | `F12_DISTANCE_CONDITIONED_3_STAGE_PERFORMANCE.png` | 같은 거리 구간에서 관측 왜곡과 실제 추정 오차가 어떤 양상인가? | 구간별 시간표본 재집계, 이질적 n·상관 보유 |
| Extended 5 | `F11_PHYSICAL_SENSITIVITY_VS_FILTER_GAIN.png` | 물리 Hsψ와 동일 prior의 실제 가중치 Kψs는 어떻게 다른가? | 서로 다른 분석 population, 직접 비율 인과 주장 금지 |
| Extended 6 | `F06_LOCAL_VS_RECURSIVE_EFFECT.png` | 같은 prior의 즉시 손실 변화가 왜 최종 재귀 RMSE와 다른 방향일 수 있는가? | MSE와 RMSE 각각의 동일 기준 대비 변화율 |
| Extended 7 | `F02_THREE_STAGE_12_CONDITIONS.png` | 4 gyro 수준까지 선택 12조건 모두에 같은 서사가 유지되는가? | 12개 독립 장면이 아니라 하나의 Corridor 반복 |
| Extended 8 | `F07_TIME_ALIGNED_PHYSICS_AND_HEADING.png` | 편파오염·Heading 오차·거리 조건이 시간축에서 어떻게 대응하는가? | 시각화용 이동평균이며 성능 평가는 원 시점 RMSE |
| Extended 9 | `F08_TEMPORAL_CORRELATION_AND_TRAVEL.png` | 시간상관과 같은 lag의 주행거리는 얼마나 되는가? | 거리변환은 독립 공간 field kernel이 아님 |
| Extended 10 | `F05_RANGE_MEAN_ERROR_DECOMPOSITION.png` | 평균 교체는 Full RF Range 잔차의 어떤 부분을 바꾸는가? | B0 fixed BASE accepted 동일 집합, posterior XY가 아님 |
| Extended 11 | `F13_YAW_DEPENDENT_DUAL_LP_PHYSICS.png` | 두 편파 응답의 상대각·Heading 기하 민감도는? | true-pose SourceFFD, Full multipath는 별도 채널 |
| Supplement S1 | `F09_LOS_MEAN_CONTROL_AND_CAUSAL_BOUNDARY.png` | LoS에 Full RF용 μ를 잘못 적용하면 어떻게 달라지는가? | 보고서 인과 과장 방지용 필수 통제군 |
| Supplement S2 | `F10_MAX_DISTORTION_PORT_POWER_EXAMPLES.png` | 큰 Full–LoS 편파 왜곡 구간에서 두 포트 power는 어떻게 달라지는가? | 극단 사례는 각 case의 t≥30 최대 절대 차이로 선택한 *예시*, 평균적 사례 아님 |

모든 PNG에는 같은 이름의 **SVG 벡터 원본**이 존재한다. 정량 데이터는 `tables/` 안의 CSV로, 실행 코드는 `source/`에 보존하였다.

## 2. 성능 3단계 — B0

| Case | Direct LoS clean-mean Heading / XY | Full BB_ORIG Heading / XY | Full MB_VAR Heading / XY |
|---|---:|---:|---:|
| R2-B | 0.4348° / 3.7436 cm | 1.2047° / 6.8269 cm | 1.0847° / 5.3303 cm |
| R4-B | 0.3033° / 5.9080 cm | 1.4418° / 8.5363 cm | 1.4312° / 9.4325 cm |
| R5-B | 0.2147° / 2.1000 cm | 1.0731° / 8.6882 cm | 0.6434° / 4.4551 cm |

위 Direct LoS 수치는 기존 논문 원본 점수가 **아니라 이번에 새로 계산한 탐색적 반사실**이다. 보존 `H_LoS`에서 같은 first-path 관측 체인으로 `z_los`를 재생했고, 같은 4상태 SourceFFD·운동·초기 `x,P`·BB 기준 `R`·NIS를 사용하되 **LoS에는 평균 μ=0**을 적용했다. 원본 Full BB/MB는 기존에 저장된 회귀 평균 μ_B/μ_M을 유지한다. 따라서 LoS→Full 점수 차이에는 RF 채널 변화와 **평균모형 적합성 변화가 함께 들어 있으므로** 그 전체를 순수 다중경로 효과로 표현하지 않는다.

이를 확인하기 위해 LoS에 **Full BB μ를 그대로 적용**하는 추가 통제군도 실행하여 `tables/THREE_STAGE_COMPARISON_12_BIASES.csv` 및 `F09...png`에 함께 보존했다. 이 경우 R5-B B0는 1.3517° / 13.2892cm가 되며, RF가 LoS여도 잘못 이전된 평균 보정만으로 성능이 악화할 수 있음을 확인한다. 따라서 논문의 주 문장은 **원시 H 수준의 Full–LoS 물리 왜곡**과 **LoS 기준 → Full 이전 → 보정 후의 기술적 성능 간격**을 나눠 기술한다.

## 3. 직접관측 물리 지표 — t≥30초, gate 비선택

| Case | n | RMS(Full−LoS s) | RMS(Full−LoS 거리) | Full·LoS first tap 불일치 | strong RX port 불일치 | median abs(Hsψ) |
|---|---:|---:|---:|---:|---:|---:|
| R2-B | 829 | 0.1129 | 9.36 cm | 26.30% | 5.07% | 0.461/rad |
| R4-B | 592 | 0.1174 | 9.36 cm | 34.63% | 15.71% | 1.775/rad |
| R5-B | 1,265 | 0.0949 | 13.38 cm | 29.33% | 4.19% | 0.405/rad |

모든 물리 지표는 같은 pose에서 원 `H`·`H_LoS`와 `SourceFFD`를 비교한 것으로, 추가분산 적용 후 물리적 편파 민감도가 변한다고 주장하지 않는다. Heading 관측 민감도 `H_{sψ}`는 직접경로 SourceFFD의 **true-pose·active branch** 기준이고, 실제 필터의 posterior information·성능과 다르다.

## 4. 표 데이터 안내

- `PHYSICAL_LOS_FULL_PACKET_3136.csv`: 같은 시각·pose의 Full/LoS/SourceFFD signed ratio, 두 포트 power, `J_sψ`, 거리, tap/port, margin, signed 차이.
- `DISTANCE_BINS_PHYSICAL.csv`, `YAW_BIN_PHYSICAL_SIGNATURES.csv`: 거리·상대방위 구간별 물리 특성과 표본 수.
- `POLARIZATION_ACF_TIME_AND_TRAVEL.csv`: 편파잔차 ACF와 해당 시간 lag의 누적 이동거리 중앙값.
- `TIME_RESOLVED_<case>_<bias>.csv`: 모든 12조건의 시각별 `Heading_error`, XY 오차, predicted std, 수용, NIS, 필터 gain, 물리 잔차, rho.
- `DISTANCE_BIN_PERFORMANCE_B0.csv`: B0 세 단계의 동일 거리 구간에서 Heading/XY 조건부 RMSE와 n.
- `THREE_STAGE_COMPARISON_12_BIASES.csv`: 각 route×gyro에 Direct LoS clean-mean/LoS frozen Full μ/Full BB/Full MB를 구분해 기록한 48행.
- `LOS_COUNTERFACTUAL_24.csv`: 새 두 가지 LoS 기준선, 3경로 ×4gyro×2mean.
- `RANGE_ERROR_SAME_FIXED_MASK_B0.csv`: B0의 동일한 원 BASE accepted mask에서 거리 관측 평균 교체의 직접 효과. 원고 표 1 재현.
- `LOCAL_VS_RECURSIVE_HEADING_12.csv`: 동일 BB prior의 국소 Heading MSE와 전체 재귀 RMSE의 별도 변화.
- `MATCHED_PRIOR_POLARIZATION_GAIN_12.csv`: 물리 `Hsψ`가 아닌 동일-prior `Kψs`의 절댓값·signed 결과.
- `FULL_REPLAY_PARITY_6.csv`: 원 3 case B0 × BB/MB 재귀를 동일 코드로 새로 실행해 기존 trace의 X/P/mask와 일치하는지 검사.
- `ILLUSTRATIVE_WINDOWS_SELECTION.csv`: 극적 사례의 **선정 규칙·case별 시간**, 결과 기반 선택임을 공개.

## 5. 해석 제한과 필수 주의사항

1. **Direct LoS 단계의 점수는 탐색적 신규 비교다.** SourceFFD, LoS H, gyro/wheel 입력은 보존 자산이지만, LoS 평균모형(μ=0)과 원 BB 평균은 다르다. 필터 기준선을 동결한 단일개입 과학 실험으로 소급하지 않는다.
2. **물리 민감도는 관측 자체의 특징**이며 MB_VAR를 적용한다고 직접 증가하지 않는다. MB_VAR가 변경하는 것은 평균과 `R_ss`, 이후 `K`, `NIS`, state/P 및 수용이력이다.
3. Raw Full−LoS 차이는 다중경로가 포함된 **채널 차이**지만 detector/surrogate 불일치까지 영향받는다. 특정 ray·반사면의 원인 비율을 산출하지 않았다.
4. 시간 ACF/거리 변환은 **공간과 시간의 독립 확률모델 추정이 아니다**. 본 자료는 한 Corridor/동일 seed 반복.
5. R4의 XY 악화와 95% 신뢰도 보정 실패를 숨기지 않는다. 동일 경로에서 `BB_VAR`와 `MB_CONST`가 더 좋다는 기존 반례도 별도 종합 자료에 유지한다.
6. 독립 외부 물리 환경에 대한 실증은 없으며, R4 V3 별도 AI 감사 `ACCEPT_WITH_BOUNDARIES`는 이번 탐색적 LoS 비교의 제3자 승인을 의미하지 않는다.
7. 같은 시간/거리 구간은 자기상관된 packet을 포함한다. 구간이 많아도 독립 표본 다수가 아니다. 최대 왜곡 예시는 논문 본문에서 대표값으로 이용하면 안 된다.

## 6. 재현과 검산

원입력: `DualLP_Physics_Link_Validation_20261101.zip` (기존 219MB 재구현 자료), 이전 GitHub RF source commit `9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13`. LoS 안테나 응답 구현은 기존 `diag_mbvar` 및 검증된 SourceFFD를 재사용했다. FFD 은행은 원 SHA `b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b` (+45)와 `39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9` (-45)이다.

1. `source/los_counterfactual.py`: 원본 `H_LoS`에 대해 source 관측 parity 확인, 24개 새 LoS 조건 재귀 계산, trace·score 저장.
2. `source/verify_original_replay.py`: Full BB/MB B0 6개 재실행이 기존 보존 `X/P/mask`와 정확 일치하는지 검사.
3. `source/make_paper_figures.py`, `source/make_angle_figure.py`: 표와 PNG/SVG 그림 생성.
4. `tables/VALIDATION_SUMMARY.json`, `MANIFEST.json`: 실제 행수·SHA·정량 비교 결과 기록.

**새 RT 호출: 0. 원래 원고·코드·학습 결과 변경: 0.**
