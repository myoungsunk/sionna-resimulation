# G1-DIAG-003 · S0 입력 상태와 실행 전 보완 계획

**SPEC_DRAFT · DIAGNOSTIC_ONLY · R2 RF 입력 확보(보고) · S0 NOT_RUN · S2′ STOP (FULL_6) · Step 3 보류**

[기존 데이터 사양](SPEC_A_BLOCKC_KO.md)의 선행 조건과 판정 보완안을 기록한다. 대상은 BLOCK_C 연속 주행의 원래 packet 단위 4-state EKF다. 작성 기준은 `research/g1-sweep-heading-floor-spec-20261113`의 `8f7fdd75ea3ac5ffa9e3284cd1f5470977cf41d1`이다. 실행 전 결정은 `cd5282446dab789b0dfac8d520cc64f04f4f7b1a`의 계획을 검토한 후 [기존 데이터 사양](SPEC_A_BLOCKC_KO.md)에 반영했다.

## 1. S0 입력 상태와 원본 기준

2026-11-14 KST 조회에서 R2의 지정 artifact 두 건은 GitHub API에서 404였다. 이후 연구자가 PC와 Snowball에 원본 RF ZIP의 해시 일치 사본을 확보했다고 확인했다. 실제 실행에 사용할 ZIP 경로와 SHA-256은 재생 전에 매니페스트에 기록한다. 만료된 기준 결과 ZIP은 원본 보고서로 대조하고, 프레임별 산출물은 원본 코드 재실행으로 생성한다.

| 용도 | 원본 | 고정 ZIP SHA-256 및 확인 상태 |
|---|---|---|
| R2_aA 연속 주행 RF | [run 38331588521 · artifact 11782748118](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38331588521/artifacts/11782748118) | `88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63` · PC·Snowball 보관본 확보(연구자 확인) |
| R2 기준 결과·재현 증거 | [run 38664617622 · artifact 11940333419](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38664617622/artifacts/11940333419) | `ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399` · 결과 ZIP 만료. 보고서 수준 대조 |
| Anchor B JOINT4 기준 결과 | [run 39376076166 · artifact 12243278686](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39376076166/artifacts/12243278686) | `265b586283cbd3e50333530463ad1578a41bd0f7932b94b3728dfd87355dd4c1` · 목록에서 `expired=false` 확인. R4-B와 R5-B case별 artifact는 각각 `12243228864`, `12243741168`이다. |

R2 기준 보고서가 명시한 실제 실행 소스는 `81cdffbdedf43b318ebf8eddb4fcbac1fd30d878`이다. 앞선 run `38664174582`에는 SR 분기 오류가 기록돼 있다. Anchor B의 실제 실행 소스는 `5dd61292538c3e95858c9050a60c4d4ddb03a214`이며, 원본 입력 매니페스트의 case별 RF로 따로 재현한다. `analysis/b-mcg-v1-20261109`의 `a4a0b60af00757f1f02817ea59c0362fb6d4d961`은 두 원본 보고서를 열람한 커밋이다. [R2 원본 워크플로](https://github.com/myoungsunk/sionna-resimulation/blob/a4a0b60af00757f1f02817ea59c0362fb6d4d961/.github/workflows/ekf4-r2-bias-l012.yml) · [R2 원본 보고서](https://github.com/myoungsunk/sionna-resimulation/blob/a4a0b60af00757f1f02817ea59c0362fb6d4d961/research/EKF4_RANGE_S_STAGED_20261014/R2_MOUNT0_45_GYRO_BIAS_B0_L0_L1_L2_RESULTS_20261015_KO.md) · [Anchor B 원본 보고서](https://github.com/myoungsunk/sionna-resimulation/blob/a4a0b60af00757f1f02817ea59c0362fb6d4d961/research/PJ_SEPARATE_RS_20261020/01_EXECUTED_RESULTS_KO.md#L29)

| S0 항목 | 원본 조건과 기대값 |
|---|---|
| R2_aA B0 DR-only | RF ZIP에 기준 x·P가 있으면 최대 차이 0을 요구한다. 기준이 없으면 해당 없음으로 기록한다. |
| R2_aA mount 0° DR, L0/L1/L2 | heading RMSE 1.69° / 6.59° / 24.97° |
| R2_aA mount 0° J4 LoS, L0/L1/L2 | heading RMSE 0.50° / 0.40° / 0.24° |
| R2_aA mount 0° J4 Full, L0/L1/L2 | heading RMSE 7.50° / 7.54° / 7.52°. 별도 B0 대조의 J4 Full RMSE는 7.49°다. |
| R2_aA mount 0° J4 Full, L2 | heading RMSE 7.521°, 포함률 16.3%, 평균 heading NEES 86.37 |
| R2_aA L2 최종 gyro bias | 원본 표는 4개 mount×RF 조합의 S4·J4 `b̂ ± σ_b`를 별도 기재한다. S0 비교값과 단위(°/s)는 갱신 사양 §4에 명시했다. 예를 들어 mount 0° Full은 S4 +0.1041 ± 0.0050, J4 +0.2087 ± 0.0026이다. |
| Anchor B JOINT4, B0 Full, mount 0° | R4-B RMSE 1.323° / 포함률 40.0%, R5-B 2.541° / 22.1% |

## 2. 재현 재개 순서

1. 확보한 R2 RF ZIP을 원본 SHA-256과 대조한다. Anchor B는 별도 실행의 입력 매니페스트와 case별 RF·코드를 확인한다.
2. 커밋 `81cdffb`의 R2 원본 조건으로 두 번 실행해 새 프레임별 수치 출력과 지표 파일의 비트 일치를 확인한다. S0 표의 RMSE·포함률·NEES와 네 L2 gyro bias 조건을 보고 자릿수까지 대조한다. 기준 x·P는 RF ZIP에 있을 때 0 차이를 요구한다. R2의 판정은 `REPORT_LEVEL_PASS`로 표시하며 과거 결과 ZIP과의 프레임 단위 일치는 미검증이다. Anchor B R4-B·R5-B 기준까지 일치해야 S0 전체를 통과한다. 적용 기준에서 하나라도 불일치하면 중단한다.
3. S0 전체가 통과하면 **D4 → D5 → D1 → D2 → D6 → D3** 순서로 진행한다. D4 시작 전에 새 창 정의와 0 기준 RMS를 구현한다. 실행 증거는 사양에 지정된 `DIAG_A/` 아래에 남긴다.

## 3. 결과 확인 전 확정한 항목

| 항목 | 실행 규칙 |
|---|---|
| D1 | 편향², 고정 EKF 선형화에서의 시간 교차항, 나머지 분산으로 실측 heading MSE를 분해한다. 한 항이 60% 이상이면 주원인 후보이고, 어느 항도 도달하지 않으면 혼합이다. 세부 유보 조건은 사양을 따른다. |
| D2 | s를 건너뛴 packet은 range-only χ²₁ 99% gate를 쓴다. m개의 모든 위상을 실행하고 위상별 지표를 같은 가중치로 평균한다. |
| D3 | 이동거리 중심 창을 사용한다. 끝에서 줄어든 창은 최소 2 m를 보장하고 같은 pose의 반복 packet은 한 번만 센다. 유효 창 폭은 2, 5, 10 m다. 같은 m·위상의 D2와 짝 비교한다. |
| D4 | 장거리 성분의 중심화 분산과 0 기준 제곱평균을 모두 보고한다. heading 환산 바닥에는 0 기준 RMS를 쓴다. |
| D5·D6 | 같은 체크포인트에서 R4 대조와 분산 증가 대조를 각각 평가하고, 정확도·포함률·수용 갱신 수를 함께 보고한다. |
| 종합 | D1–D3이 어긋나면 원인 귀속을 유보한다. 결과는 G1-MODEL-003의 arm 우선순위와 특성화 항목에만 사용한다. |

검토·계획 기록은 RESEARCH-GOVERNANCE-v1 로컬 COMMON SHA-256 `a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb`, AUDITOR `e1bdc2f231c71cdc27201c688e041b078576a6adf6c0290acc16ce4d8218291a`, PROPOSER `e7c4e6efa050448fc1624c9fe28c227b948631f189531ce75c7c6c0a695bc53e`를 따른다.
