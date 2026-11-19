# BLOCK_C 중앙선 기준점 주변 4 cm 간격 sweep 실행 계획

- 질문 ID `BLOCK-C-M7-NEAR-STATION-SWEEP-001`. 상태는 계획, 역할은 PROPOSER.
- 기준 저장소 `myoungsunk/sionna-resimulation`, 브랜치 `research/blockc-centerline-sweep-20261117`, 로컬 참조 커밋 `1a0f3c1b15be8e07c1884dbd1e42a1bb6c9b74f4`.
- 기존 중앙선 데이터 실행 ID `BLOCK_C_CENTERLINE_M7_20261118_dhdj70s5`, 생성 코드 `e9b4a76a8ce85d15de0f2be94900487c9b7b52bf`, 동결 Method B `047cce2acb244ec2d7badc563345ccdd1f48613f`.
- 기존 실행 계약에 기록된 공통 지침 해시 `a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb`와 로컬 공통 지침이 일치한다. 제안 역할 지침 SHA-256은 `e7c4e6efa050448fc1624c9fe28c227b948631f189531ce75c7c6c0a695bc53e`다.

## 좌표와 표본

세 거리대에서 중심 yaw sweep이 중앙선을 따라 이동할 때 얼마나 달라지는지 비교할 수 있도록 RF 데이터를 확보한다. station 간격은 4 cm다. 중심에서 Δx = −16, −12, −8, −4, +4, +8, +12, +16 cm에 추가한다. +x를 앞, −x를 뒤로 정의한다. 세 중심은 모두 앵커보다 x가 작아 +x가 앵커에 가까워지는 방향이다. ρ는 수평 거리다.

| 거리대 | 기존 중심 x (m) | 중심 ρ (m) | 뒤 4개 x (m) | 앞 4개 x (m) |
|---|---:|---:|---|---|
| 단거리 P016 | 7.95 | 2.05 | 7.79, 7.83, 7.87, 7.91 | 7.99, 8.03, 8.07, 8.11 |
| 중거리 P010 | 5.25 | 4.75 | 5.09, 5.13, 5.17, 5.21 | 5.29, 5.33, 5.37, 5.41 |
| 원거리 P003 | 2.10 | 7.90 | 1.94, 1.98, 2.02, 2.06 | 2.14, 2.18, 2.22, 2.26 |

y=0 m, 수신 안테나 z=0.45 m, mount 0°를 유지한다. world yaw −180°부터 +170°까지 10° 간격으로 36개 RF pose를 만든다. +180° 관측은 −180°와 같은 RF pose를 참조하므로 station당 관측 행은 37개다. 신규 24 station은 864 RF pose와 888 관측 행이다. 중심 3곳의 108 RF pose는 원본 실행 ID와 pose ID로 참조한다. 비교용 표는 27 station, 972 RF pose, 999 관측 행이다. 새 station ID에는 중심 ID와 부호 있는 오프셋을 기록한다. 예를 들어 `P016_DX_M04CM`은 x=7.91 m다.

## 생성 순서와 통과 기준

1. **입력 동결.** [기존 station 표](../../artifacts/BLOCK_C_CENTERLINE_M7_20261118_dhdj70s5/inputs/STATIONS.json)와 신규 좌표를 대조한다. 세 중심 좌표, 각 중심을 포함한 9개 위치의 4 cm 간격, 24개 신규 위치의 유일성, station별 36개 yaw, ±180°의 공통 pose ID를 검사한다. 중심 H의 파일 해시와 원본 pose ID를 기록한다.
2. **Snowball 원본 대조.** 기존 M7 실행과 같은 BLOCK_C 형상, 6개 PLY, 재질, 앵커 B=(10, 0, 2.65) m, FFD, 런타임과 [solver 계약](../../artifacts/BLOCK_C_CENTERLINE_M7_20261118_dhdj70s5/inputs/M7_RT_CONFIG.json)을 사용한다. 투과·LoS·정반사 ON, 광선 100,000개, 깊이 3, seed 20260924를 유지한다. 기본 17 node와 원본 경계 적응형 추가 추적, 원본 Jones 보간·지연 위상 합성으로 최종 257 bin을 계산한다. 유한 반사면 검사·직접파 대체·후처리 필터는 원본과 같이 OFF다. R2/R4/R5 기준 9 pose가 원본 H와 비트 일치할 때 본 생성으로 넘어간다.
3. **신규 위치별 RT 및 export.** 기존 [M7 sweep 생성기](../../scripts/drive_sim/run_blockc_m7_sweep.py)를 사용해 24개 위치를 직접 추적하고, 각 위치의 공용 경로로 36개 yaw의 H를 합성한다. `H_full`, `H_LoS`, `PATHS_NEAR`, 전체 raw trace 및 실제 node 목록을 같은 추적 결과에서 저장한다. 중심 데이터와 신규 데이터를 참조하는 비교용 pose·관측 표를 함께 보관한다.
4. **완전성 및 G4·G8.** 신규 864개 pose의 축·순서·누락·중복과 파일 해시를 확인한다. 전체 `H_full`이 원본 합성 함수 `h_for_antenna_yaws`의 결과와 `array_equal`이어야 한다. 기존 G4 직접파 검증은 p90 `|Δs| ≤ 0.005`, G8 직렬화 검증은 상대오차 `< 1e-6`과 0 참조 불일치 0건을 적용한다. 실패가 발생하면 해당 기록과 원인을 보고한다. 완료 보고에는 통과 여부, 신규 위치·pose 수, 실제 trace 호출 수, 소요 시간과 저장량을 포함한다.

기존 40위치 실행의 본 생성 69.47초와 결과 128.20 MB를 위치 수로 환산하면, 신규 trace·합성 약 42초와 결과 약 77 MB다. 원본 대조와 최종 검사 시간은 별도이며, 실제 시간은 Snowball 부하와 위치별 추가 node 수에 따라 달라진다. 데이터 검증까지가 범위다. 이 표본은 세 중심의 국소 공간 변화를 비교하는 데 사용한다.
