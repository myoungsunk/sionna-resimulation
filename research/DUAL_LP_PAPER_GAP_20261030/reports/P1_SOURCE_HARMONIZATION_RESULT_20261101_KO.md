# DLP-EKF-GAPS-001 / P1 SourceFFD C0 관측모델 정합 — FROZEN 실행 결과

**실행일:** 2026-11-01 KST  
**상태:** `FROZEN RATIFICATION VALID` → `P1 COMPUTATION PASS` → `RETROSPECTIVE_DESCRIPTIVE_ONLY`  
**계약:** `DLP-EKF-GAPS-001/P1-V1`, SHA-256 `373781e0a2395032faa49ff0228d84ebf8d93bb9c880e0504105bc5e12e82594`  
**원본 제안자 HEAD:** `340877f3537b4cc65cdaa9d687423cba92e0b28b`  
**P1 runner:** [GitHub Actions 41300302082](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41300302082) — SUCCESS  
**계산 코드 SHA-256:** `76c24e282f9f8ad1156aafd6cbf70e041ce74b69c5a698228d9510f212e377fc`

## 1. 이 결과로 정확히 무엇이 검증됐는가

원본 하나의 C0 Corridor에서 **동일한 복소 RF H와 동일한 pose/time, 동일한 TX +45° / RX ±45°의 signed-s 및 raw range 추출**을 사용했다. 오래된 2° LUT의 `h_s`와 원본 SourceFFD의 `h_s`만 교체했으며, range 예측 `h_r=d-0.5315983906250129m`는 두 arm 모두 유지했다. 그 결과를 GT pose **오프라인 특성화**에만 사용하여 signed 잔차와 ddof=1 공분산을 계산했다.

- **원본 C0 자산 39/39, FFD 실제 .npz bank 2/2**: 새 GitHub runner에서 물리적 전체바이트 SHA-256 일치.
- 7 case의 Full 9519개와 Native LoS 9519개, 총 **19038 paired-observer rows**. 원본 frozen RF trace 14502개 timeline row와 전수 대조; archived r/s 최대차 각각 `1.78e-15 m / 7.96e-16`, tap 불일치 0건.
- 타임라인 채널당 7251개 및 `t>=30s` 채널당 6201개; pose 누락·중복·부적합 signed packet 0건.
- 16개 잠금 기준 `T00–T15 = 16/16 PASS`. Signed 잔차 항등식 최대 오차 `2.22e-16`; 공분산 독립 공식 차이 `2.78e-17`.
- SourceFFD 직접-H vs NativeLoS 복소 H: 최대 상대오차 `3.25405e-4`, RMS `7.31143e-5`. NativeLoS (s) RMSE `6.592045e-7`, max `1.082114e-5`, first-path switch 0.
- SourceFFD 전체 C0 안정셀 Jacobian 중앙차분축 **28,520개**: 실패 0, 최대절대차 `2.54980e-8`; 비매끄러운 FFD cell switching 37 axis records (32 unique pose keys), 전부 ledger에 보존. First-path 전환과 invalid packet은 0.
- 사용하지 않는 사후 파라미터 보정, RF 재생성, 새 EKF, R 학습, P2/P3/P4, Office/3D/M2 수행하지 않음.

## 2. 핵심 실험값: 같은 raw H의 old LUT 대 SourceFFD

`RMSE(e_s)`의 단위는 signed dual-port power ratio의 **무차원 값**. 각 모드별 n=9519, 독립 RF scene은 1개다.

| 채널 | old LUT RMSE | SourceFFD RMSE | old signed 평균 | SourceFFD signed 평균 |
|---|---:|---:|---:|---:|
| Native LoS | 0.014184009 | **0.000000659205** | -0.002821432 | ~-0.000000072762 |
| Full (reflection 포함) | **0.169678245** | 0.170112850 | 0.020805978 | 0.023627338 |

**해석 1 — 물리적 direct-only predictor QA:** SourceFFD는 이미 사용한 동일한 bank 계열 Native LoS를 소수점 6자리 수준의 작은 오차로 정합했다. 이것은 *retrospective engineering parity*이며 독립 EM solver나 새로운 장면에서의 전파 정확성 증명이 아니다.

**해석 2 — Full 다중경로에서는 범용 개선 없음:** Full의 old→Source 변화는 `+0.000434605` RMSE (악화)로 매우 작다. Full 소스 잔차의 RMSE `0.170112850`는 Full−NativeLoS signed 관측 대비의 RMSE `0.170112816`와 거의 같다. 실제 matched pair마다 `e_s^FULL,src = (z_s^FULL-z_s^LOS) + e_s^LOS,src` 성립하고, LoS source 잔차가 매우 작기 때문이다. Full 잔차를 모두 독립 확률 잡음이라고 주장하지 않는다.

**해석 3 — Range는 그대로:** `RMSE(e_r)`은 old/Source 양측에서 동일하다. LoS `0.0459452m`, Full `0.1335843m`. Range bridge가 tap 기반 raw ranging likelihood로 바뀐 것은 아니다.

## 3. Full 채널을 case별로 전수 표시

| case | n | old LUT (s) RMSE | SourceFFD (s) RMSE | Source−Old |
|---|---:|---:|---:|---:|
| R2_aA_m0 | 1303 | 0.204219 | 0.206237 | +0.002018 |
| R2_aA_m45 | 1303 | 0.228879 | 0.229336 | +0.000457 |
| R2_aB_m0 | 1303 | 0.107234 | 0.107675 | +0.000441 |
| R4_aA_m0 | 922 | 0.201631 | 0.201823 | +0.000192 |
| R4_aB_m0 | 922 | 0.126340 | **0.126293** | -0.000047 |
| R5_aA_m0 | 1883 | 0.186697 | 0.187480 | +0.000783 |
| R5_aB_m0 | 1883 | 0.099496 | **0.097659** | -0.001837 |

**7개 중 2개 개선, 5개 악화.** 전체에서는 약간 악화이며, 단일 Corridor의 강하게 상관된 time/pose 표본이므로 여기서 IID 신뢰구간이나 일반화 성능 우수성을 만들지 않는다. SourceFFD의 가치는 여기서는 **직접경로 관측모델의 일관된 물리적 정의 및 Native LoS 정합**, Full multipath 오차 자체의 저감은 아니다.

## 4. Source–old 극단 차이: 반드시 보존할 제한

`|h_s^old-h_s^src|`의 전체 Full 9519개 pose 분포: 중앙값 0.00302066, P90 0.01676896, P95 0.02254170, P99 0.03405875, **최대 0.87761570**.

최대값은 `R5_aB_m0 / pose_id=706`, GT `(x,y)=(10.010199,0.037008)m`, anchor B `(10,0,2.65)m`, 3D거리 2.200335m. 거의 앵커 바로 아래에 위치한다. 같은 pose에서 old LUT `h_s=-0.06920457`, SourceFFD `h_s=-0.94682028`. 원본 2° LUT의 근극점 방향 보간과 관계될 **가능성**이 있으나, 이것만으로 원인을 확정하지 않는다. 원본 `hs_lut_meta.json`의 과거 interpolation gate `passed=false`도 그대로 제한으로 인용한다.

이상치를 삭제하지 않았으며, 기존 Full/LoS 전체 통계에도 포함했다. 해당 pose들은 이후 필요하면 별도 **탐색적** 국소 기하/보간 재조사를 수행해야 한다. `source_near_boundary=False`는 SourceFFD FFD interpolation cell 경계 진단이지 **legacy LUT가 극점에서 안정적이라는 보증은 아니다.**

## 5. Signed covariance와 해석 제한

| 조건 | (C_{rr}) (m²) | (C_{rs}) (m) | (C_{ss}) |
|---|---:|---:|---:|
| Full + old LUT | 0.015565651 | +0.005107446 | 0.028360797 |
| Full + SourceFFD | 0.015565651 | +0.005083367 | 0.028383112 |
| LoS + old LUT | 0.002106258 | -0.000110973 | 0.000193246 |
| LoS + SourceFFD | 0.002106258 | ~-1.822e-9 | ~4.293e-13 |

이 행렬은 `e_r=z_r-h_r(x_GT)`, `e_s=z_s-h_s(x_GT)`의 **오프라인 표본 공분산**이고, 각 stratum에서 평균을 뺀 `ddof=1` 공식이다. `Full C_rs≠0`이라고 곧바로 상호 독립성이 어떤 장면에서도 부정된다는 인과 주장을 하거나, LoS `C_ss~0`을 runtime RF 측정 잡음이 실제 0이라는 뜻으로 해석하지 않는다.

기존 `R0=diag(0.0068578637,0.0081)`은 **계속 변경 없는 conventional 비교 기준**이다. 이번 P1에서는 이 통계로 `R`을 다시 추정하거나 필터에 주입하지 않았다.

## 6. 감사·재현·파일 근거

- [APPEND-ONLY FROZEN ratification](../contracts/DLP-EKF-GAPS-001/P1_20261101/P1_FROZEN_RATIFICATION_20261101.md).
- [원본 P1 실행 로그 (Actions)](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41300302082).
- [P1 기계 판독 QA (16개 T00-T15)](../runs/P1_SOURCE_HARMONIZATION_41300302082/P1_SCIENCE_QA.json).
- [raw H/timeline 14,502 행 parity](../runs/P1_SOURCE_HARMONIZATION_41300302082/P1_RAW_OBSERVER_PARITY.csv).
- [모든 19,038 signed residual 행](../runs/P1_SOURCE_HARMONIZATION_41300302082/P1_MATCHED_SIGNED_ERRORS.csv).
- [152 stratum moments](../runs/P1_SOURCE_HARMONIZATION_41300302082/P1_STRATIFIED_MOMENTS.csv).
- [invalid + 37 boundary records](../runs/P1_SOURCE_HARMONIZATION_41300302082/P1_INVALID_AND_BOUNDARY_LEDGER.csv).
- [전체 run manifest 및 출력 SHA-256](../runs/P1_SOURCE_HARMONIZATION_41300302082/P1_MANIFEST.json).
- [추가 분리 수학 코드 실행](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41300720787): 11/11 PASS; **동일 ChatGPT 세션에서 구현/후속 확인을 작성했으므로 `SELF_REVIEW_ONLY`이며 별도 감사자 서명이 아니다**.

후속 독립 사람이 실제 raw artifact와 run별 실패·경계 장부를 확인하려면 위 자료로 완전 재계산 가능하다. P1은 성공적으로 **실행 및 기계 검증**되었지만, 학술적 **외부 일반화나 EKF 성능 향상은 검증하지 않았다**. P2 이상으로 자동 승격하지 않는다.
