# G1-DIAG-003 · S0 입력 상태와 실행 전 보완 계획

**SPEC_DRAFT · DIAGNOSTIC_ONLY · S0 INPUT_MISSING / NOT_RUN · S2′ STOP (FULL_6) · Step 3 보류**

[기존 데이터 사양](SPEC_A_BLOCKC_KO.md)의 선행 조건과 판정 보완안을 기록한다. 대상은 BLOCK_C 연속 주행의 원래 packet 단위 4-state EKF다. 작성 기준은 `research/g1-sweep-heading-floor-spec-20261113`의 `8f7fdd75ea3ac5ffa9e3284cd1f5470977cf41d1`이다. 아래 D1–D6 보완안은 실행 전 검토용이며, 사양의 동결 기준이나 기존 실행 결과를 바꾸지 않는다.

## 1. S0 입력 상태와 원본 기준

2026-11-14 KST 확인에서 R2의 지정 artifact 두 건은 GitHub API에서 404였고 해당 Actions run의 artifact 목록은 비어 있었다. 확인한 로컬 작업 폴더와 Snowball 경로에서 동일 보관본을 찾지 못했다. 아래 SHA-256은 원본 워크플로와 보고서에 기록된 값이다. 파일 바이트의 재검증은 미완료다.

| 용도 | 원본 | 고정 ZIP SHA-256 및 확인 상태 |
|---|---|---|
| R2_aA 연속 주행 RF | [run 38331588521 · artifact 11782748118](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38331588521/artifacts/11782748118) | `88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63` · `INPUT_MISSING` |
| R2 기준 결과·재현 증거 | [run 38664617622 · artifact 11940333419](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38664617622/artifacts/11940333419) | `ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399` · `INPUT_MISSING` |
| Anchor B JOINT4 기준 결과 | [run 39376076166 · artifact 12243278686](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39376076166/artifacts/12243278686) | `265b586283cbd3e50333530463ad1578a41bd0f7932b94b3728dfd87355dd4c1` · 목록에서 `expired=false` 확인. R4-B와 R5-B case별 artifact는 각각 `12243228864`, `12243741168`이다. |

R2 기준 보고서가 명시한 실제 실행 소스는 `81cdffbdedf43b318ebf8eddb4fcbac1fd30d878`이다. 앞선 run `38664174582`에는 SR 분기 오류가 기록돼 있다. Anchor B의 실제 실행 소스는 `5dd61292538c3e95858c9050a60c4d4ddb03a214`이며, 원본 입력 매니페스트의 case별 RF로 따로 재현한다. `analysis/b-mcg-v1-20261109`의 `a4a0b60af00757f1f02817ea59c0362fb6d4d961`은 두 원본 보고서를 열람한 커밋이다. [R2 원본 워크플로](https://github.com/myoungsunk/sionna-resimulation/blob/a4a0b60af00757f1f02817ea59c0362fb6d4d961/.github/workflows/ekf4-r2-bias-l012.yml) · [R2 원본 보고서](https://github.com/myoungsunk/sionna-resimulation/blob/a4a0b60af00757f1f02817ea59c0362fb6d4d961/research/EKF4_RANGE_S_STAGED_20261014/R2_MOUNT0_45_GYRO_BIAS_B0_L0_L1_L2_RESULTS_20261015_KO.md) · [Anchor B 원본 보고서](https://github.com/myoungsunk/sionna-resimulation/blob/a4a0b60af00757f1f02817ea59c0362fb6d4d961/research/PJ_SEPARATE_RS_20261020/01_EXECUTED_RESULTS_KO.md#L29)

| S0 항목 | 원본 조건과 기대값 |
|---|---|
| R2_aA B0 DR-only | 동결 참조와 상태 x·공분산 P의 최대 차이 0. 원본은 mount 0°/45° 및 Full/LoS에서 이를 기록했다. |
| R2_aA mount 0° DR, L0/L1/L2 | heading RMSE 1.69° / 6.59° / 24.97° |
| R2_aA mount 0° J4 LoS, L0/L1/L2 | heading RMSE 0.50° / 0.40° / 0.24° |
| R2_aA mount 0° J4 Full, L0/L1/L2 | heading RMSE 7.50° / 7.54° / 7.52°. 별도 B0 대조의 J4 Full RMSE는 7.49°다. |
| R2_aA mount 0° J4 Full, L2 | heading RMSE 7.521°, 포함률 16.3%, 평균 heading NEES 86.37 |
| R2_aA L2 최종 gyro bias | 원본 표는 4개 mount×RF 조합의 S4·J4 `b̂ ± σ_b`를 별도 기재한다. S0 비교 목록에서 각 값에 모델·mount·RF·단위(°/s)를 명시한다. 예를 들어 mount 0° Full은 S4 +0.1041 ± 0.0050, J4 +0.2087 ± 0.0026이다. |
| Anchor B JOINT4, B0 Full, mount 0° | R4-B RMSE 1.323° / 포함률 40.0%, R5-B 2.541° / 22.1% |

## 2. 재현 재개 순서

1. 원본 R2 보관본을 확보하면 ZIP SHA-256을 대조한다. Anchor B는 별도 실행의 원본 입력 매니페스트와 case별 RF·코드 식별자를 확인한다. 입력 해시와 평가 기준 자료가 확보되기 전에는 S0를 `INPUT_MISSING / NOT_RUN`으로 기록한다.
2. 원래 Sensor-v2 seed 0, B0와 양의 L 수준, `t ≥ 30 s`를 고정한다. R2의 979개 전체 프레임과 829개 평가 프레임, 원본 x·P, 보고 자릿수 기준을 대조한다. mount 45°는 회귀 대조에만 사용한다. 기준과 하나라도 다르면 불일치한 case·조건·지표와 근거를 기록하고 중단한다.
3. S0 전체가 통과하면 [사양의 순서](SPEC_A_BLOCKC_KO.md#7-실행-순서)에 따라 **D4 → D5 → D1 → D2 → D6 → D3**를 진행한다. D1–D3의 원인 판정과 교차 대조의 상세 규칙은 진단 결과를 보기 전에 확정한다. 실행 증거는 사양에 지정된 `DIAG_A/` 아래에 남긴다.

## 3. D1–D6 실행 전 보완안

| 항목 | 확인할 점과 비교 방법 |
|---|---|
| **D1 · 혁신 자기상관** | $F=1+2\sum_{\tau\ge1}\rho(\tau)$는 정상 시계열 표본평균의 분산 팽창 지표로 보고한다. heading NEES에 비교할 때는 J4의 상태 전이, 이득, gate를 통과한 range·s 갱신이 heading에 전달되는 가중치를 사용한다. 고정한 선형화에서 중심화한 관측 오차의 시간 교차공분산을 포함한 결과와 시간 간 교차항을 제거한 결과를 비교한다. 관측 오차의 평균에 의한 heading 편차와 분산 항을 각각 기록한다. 고정 선형화는 실제 재귀 결과와 별도로 해석하며, 현 초안의 `2F`·`5F` 판정은 heading 원인 귀속에 적용할 근거를 실행 전에 검토한다. |
| **D2 · s 갱신 솎기** | 동일 RF·센서 난수·초기값과 range 갱신 기회를 공유한다. s를 솎은 packet은 range-only 갱신으로 처리할 때의 gate와 공분산을 사전에 명시한다. m별 솎기 위상, 실제 수용 갱신 수, RMSE·포함률·NEES를 함께 보고한다. 포함률 회복은 상관된 반복 사용 가설에 부합하는지 평가한다. 낮은 포함률이 지속되면 s 정보량 감소와 gate 변화를 함께 확인한다. |
| **D3 · oracle 평균 제거** | 동일한 `m`과 솎기 위상에서 제거 전후를 짝 비교한다. D2의 원래 J4와 솎기 기준선을 재사용한다. 이동거리 창의 끝 처리, 같은 위치의 반복 packet 가중치, 유효 표본 기준을 사전에 고정한다. 모든 대조에서 진단용 참 pose 기반 성분만 제거하며, 큰 W에서 남은 효과와 RMSE·포함률·NEES를 함께 기록한다. |
| **D4 · 공간 구조** | 같은 RF를 재사용한 sensor seed와 인접 1 m 구간의 상관을 집계에 반영한다. 이동거리·회전각별 유효 표본쌍 수와 경로별 signed 평균을 함께 낸다. 장거리 성분은 중심화 분산과 0 기준 제곱평균을 구분한다. heading으로 환산한 값은 기울기가 작은 구간의 영향을 받는 진단 지표다. DR과 비교할 때 경로·평가 시점·오차 정의를 맞춘다. |
| **D5 · R4 대조** | 같은 4-state·센서 난수·초기값, range 관측과 range 갱신 기회를 사용한다. 동일 checkpoint에서 J4−R4의 heading·XY 오차 차이를 짝 비교하고, 각 arm의 gate 수용 수도 기록한다. |
| **D6 · 거리 의존 분산** | 사양의 기존 `σ_b²` 표를 사용하는 in-sample 진단이다. 편파 평균과 range 모델은 원래 J4 조건을 유지한다. 포함률·NEES와 RMSE·수용 갱신 수를 함께 봐 분산 증가가 정확도와 편파 갱신에 미친 영향을 확인한다. |

D1–D3의 결과가 일치하지 않거나 감쇠·gate 변화로 설명이 겹치면 기전 판정을 유보한다. 이 진단의 RF는 고정된 기존 경로이므로 반복 sensor seed는 같은 RF에 대한 조건부 반복이다. G1-MODEL-003에는 **arm 우선순위와 S2 특성화 항목**만 전달한다. 진단의 수치 모수와 oracle 평균 제거를 후속 모델에 적용하는 근거는 이 계획의 범위 밖이다. [NIST의 자기상관과 표본평균 분산](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=152041)

검토·계획 기록은 RESEARCH-GOVERNANCE-v1 로컬 COMMON SHA-256 `a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb`, AUDITOR `e1bdc2f231c71cdc27201c688e041b078576a6adf6c0290acc16ce4d8218291a`, PROPOSER `e7c4e6efa050448fc1624c9fe28c227b948631f189531ce75c7c6c0a695bc53e`를 따른다.
