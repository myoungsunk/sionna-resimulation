# Goal 1 · G1-MODEL-002 위치 prior의 LoS tap 직접 읽기

**DRAFT · DIAGNOSTIC_ONLY · S2′ STOP (FULL_6) · Step 3 HELD**

## 질문과 고정 입력

동일 full H와 복소 잡음에 대해 위치 prior로 예측한 LoS leading-edge tap을 직접 읽으면 기존 검출 tap 대비 오프라인 heading 오차가 얼마나 달라지는가? DETECTED, ORACLE, PRIOR_FRAC의 [동결 사양](../TAP_DIAG_20261114/SPEC_KO.md), [해석 정정](../TAP_DIAG_20261114/REPORT_KO.md) 및 원래 실행을 보존한다. 새 arm은 PRIOR_DIRECT다. 연구 브랜치는 `research/g1-sweep-heading-floor-spec-20261113`, 사양의 근거는 해석 정정 커밋 `94bcc0814d80edf07fba40bf4536004b5ac5a079`다. 기준 실행의 입력·코드·복소 잡음 및 결과 행을 SHA-256과 수치 대조로 고정한다.

- DETECTED는 동결 30% leading edge이고 ORACLE은 잡음 없는 BLOCK_C LoS H에서 같은 검출기로 구한 각 yaw의 고정 인덱스다. 둘 다 이전과 동일한 noisy full H를 읽는다.
- PRIOR_FRAC는 동결된 거리 창 내 에너지 기반 분수 지연 비교 arm이다.
- PRIOR_DIRECT는 사전 위치·anchor 위치·높이로 구한 거리에서 아래 규칙으로 sweep 공통 정수 tap 하나를 예측한다. 동일 noisy full H의 동일 CIR 배열에서 이 인덱스의 두 편파 전력을 읽는다.

## PRIOR_DIRECT의 leading-edge 정의

사전 위치는 Q1의 고정 seed 및 snap 규칙으로 재현한 모의 XY prior이며, 높이와 anchor 좌표는 고정한다. d_geo = ‖(x_prior, y_prior, z) − anchor‖이다. 고정 주파수 격자와 절대 지연 원점에서 이상적인 단일 LoS 템플릿 `H_geo(f) = c/(4π f d_geo) exp(−2πi f d_geo/c)`를 만든다. 템플릿 양 편파는 동일하며 경로 전파와 1/f 응답을 쓴다. 기존과 동일한 Hann, 4N IFFT, 가장 강한 편파의 peak 대비 30% 이상인 첫 정수 tap을 적용한다. 따라서 기준은 CIR의 leading edge이며 tap 간격은 c/(4NΔf)다. 실제 full H와 LoS H, 복소 잡음, 측정 에너지, RF의 추정 지연 및 참 heading은 이 인덱스 선택에 입력하지 않는다. 동일한 절대 지연 원점에 대한 사전 보정을 가정한다. 거리 모호 범위를 벗어나거나 유효하지 않은 템플릿은 오류로 중단한다.

ORACLE은 실제 noiseless LoS 채널의 편파·yaw별 주파수 응답을 포함한다. PRIOR_DIRECT는 거리 전파 템플릿을 사용하므로 두 arm은 leading-edge **규칙과 정수 CIR 원점**을 공유하며, 안테나 응답으로 인한 인덱스 차이는 있을 수 있다. 인덱스 일치·이른 쪽·늦은 쪽을 유효 yaw별로 집계한다. 해석용으로 명목 위치에서 같은 기하 템플릿이 고르는 인덱스도 기록한다. 명목 위치의 인덱스는 오차 분해용이며 PRIOR_DIRECT의 읽기와 heading 계산에 사용하지 않는다.

관측 yaw에 쓴 인덱스를 heading 모형의 모든 yaw·거리 적분 노드에 고정한다. 관측과 FFD LoS 예측의 읽기 위치를 맞춘다. 기존 RF 감지 mask를 네 arm이 공유하며 참 heading ±10° 오프라인 창, Q1의 0.25° 격자, 공통 열 분산 및 5점 Gauss–Hermite 적분을 유지한다. prior 불확도는 적분에 쓰며 인덱스를 다시 고르는 탐색은 수행하지 않는다.

## 검사 및 보고

- BLOCK_C 여섯 mount-0 case, 물리 station 122개, N30 20 seed, 총 2,440 sweep. 동일 full H·LoS H·pose·입력 해시와 새 실행의 복소 잡음이 포함된 full H 배열 해시를 최초 실행과 대조한다. Q1의 오차·분산·XY·flat 일치(동결 허용오차 1e−12)가 개입 계산보다 먼저 성립해야 한다. DETECTED·ORACLE·PRIOR_FRAC 원시 행도 최초 실행과 대조하며 범주값 불일치 또는 허용오차 1e−12를 넘으면 중단한다.
- 합성 단일 경로에서 정수 표본 및 30% 첫 교차점을 직접 DFT로 확인한다. 합성 LoS를 고정 PRIOR_DIRECT 인덱스에서 IFFT로 읽은 편파비와 heading 코드의 예측 편파비를 여섯 case에서 대조한다. 두 편파 분모가 0 또는 비유한이면 해당 yaw를 무효 처리하고 유효 yaw가 3개 미만인 sweep을 기록한다.
- 네 arm의 공통 유효 sweep에서 case별 RMSE, signed bias, |e| p95, |e|>5°, station 평균 오차 RMS와 heading 창 경계를 집계한다. 주 비교는 PRIOR_DIRECT−DETECTED ΔRMSE이며 PRIOR_DIRECT−ORACLE을 함께 보고한다. 95% 구간은 동일한 물리 station 단위 짝 bootstrap 2,000회 percentile로 계산한다. R4_aB를 별도 보고한다. R2_aA는 전체 및 x≤6 m / x≥8 m 층을 별도 보고한다. case별 구간에는 다중비교 보정을 적용하지 않는다.
- 적용 범위는 기존 BLOCK_C, 모의 사전 위치, 참 heading 중심 오프라인 창이다. S2′ STOP과 Step 3 보류를 유지하며 새 모델 모수를 이 결과에서 채택하지 않는다.

역할은 PROPOSER 및 IMPLEMENTER다. RESEARCH-GOVERNANCE-v1 로컬 COMMON SHA-256 `a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb`, PROPOSER `e7c4e6efa050448fc1624c9fe28c227b948631f189531ce75c7c6c0a695bc53e`, IMPLEMENTER `2380fb1fe7302870a6c2d825cc2e65a73e91138677e095b4e51db43ab9ea90da`를 적용했다.
