# Goal 1 · G1-MODEL-002 tap 추출 진단 사양

**DRAFT · DIAGNOSTIC_ONLY. S2′ STOP (FULL_6), Step 3 HELD.** G1-MODEL-002의 관측 진단이다. 기준 문서는 연구 브랜치 커밋 44f30d6의 SPEC_DRAFT_KO.md, 관측 회귀는 G1-DIAG-002 K7/Q1이다. 역할은 IMPLEMENTER 및 진단 조건의 PROPOSER다. RESEARCH-GOVERNANCE-v1 COMMON SHA-256 a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb, IMPLEMENTER 2380fb1fe7302870a6c2d825cc2e65a73e91138677e095b4e51db43ab9ea90da, PROPOSER e7c4e6efa050448fc1624c9fe28c227b948631f189531ce75c7c6c0a695bc53e.

## 질문과 개입

같은 multipath를 관측할 때 tap 또는 분수 지연 읽기 위치만 바꾸면 heading 오차가 얼마나 달라지는가? 각 (case, seed)의 N30 full H에 동결 Q1과 동일한 복소 난수를 한 번 적용하고, 동일 배열에서 세 arm의 관측값을 산출한다.

| arm | 관측 추출 | 같은 규칙의 LoS 모형 예측 |
|---|---|---|
| DETECTED | 동결 30% leading-edge 검출기. 두 편파가 검출 tap을 공유한다. | 기존 M1-R의 거리 노드별 LoS 검출기. |
| ORACLE | 잡음 없는 LoS H에 동결 검출기를 적용한 yaw별 인덱스를 고정하고, **full H + 잡음**에서 그 tap의 s를 읽는다. | 거리 노드와 yaw 후보에서 **해당 관측 yaw의 고정 인덱스**로 읽는다. LoS H는 인덱스에만 사용한다. |
| PRIOR_FRAC | sweep 직전 위치 prior의 거리 중앙값을 중심으로 ±3σ_d 창에서 Hann 가중 복소 투영으로 공통 지연을 선택한다. 두 편파와 유효 yaw의 투영 전력을 합해 지연 점수를 만들고 거리 prior로 가중한다. 선택 지연에서 각각의 복소 진폭을 읽은 뒤 s를 계산한다. | 거리 노드와 yaw 후보에서 **관측에서 선택한 분수 지연**으로 읽는다. 선택 지연을 고정한 plug-in heading fit이다. |

prior는 S2′ Q1에 저장된 snap 평가 XY와 같은 난수 열로 재현한다. Σxy=(0.13 m)²I를 거리 방향으로 투영한다. 이 XY prior는 명목 좌표를 흔든 모의 사전 위치다. 운용에 필요한 입력은 현재 sweep 전의 위치·공분산, anchor·높이와 대역 내 보정된 절대 지연 원점이다. 같은 sweep의 range나 LoS H는 PRIOR_FRAC에 넣지 않는다.

## 분수 지연 정의

진폭은 CIR의 정확한 분수 표본 C(d)=Σ H_n w_n exp(2πi nΔf d/c)/4다. w_n은 기존 Hann이다. d는 경로 길이 단위다. d_geo 중심에서 검사할 창의 양 끝을 포함해, 간격이 기존 tap 간격의 1/8 이하가 되도록 균일 분할한다. 정수 CIR tap 기준은 검출기 선두 교차 위치이고, 분수 추출은 전파 지연 위치(템플릿 중심)를 쓰므로 지연 값 자체의 1:1 대응은 기대하지 않는다. 관측과 합성 LoS에는 해당 arm의 동일한 관측 위치와 수식을 적용한다.

창 내 d별 점수는 Σ_valid yaw,port |C(d)|² / v_C − (d−d_geo)²/(2σ_d²)다. v_C=σ_H² Σw_n²/16이며 지연 후보 간 잡음 상관을 독립 표본으로 세지 않는다. 이 점수는 평탄 복소 지연 템플릿에 대한 두 편파 에너지 점수다. 반사 성분을 분해하는 추정은 이 진단 범위에 없다. 최대 점수 위치를 택하며 동점은 prior 중심에 가까운 위치, 이후 이른 위치 순으로 처리한다. σ_d=0은 중앙값에서 읽는다. 경계 선택과 국소 신호 강도를 기록한다.

## 평가, 검사, 주장 경계

- BLOCK_C mount-0 여섯 case, 적격 90°/19점, 각 20 seed, TX +45°, k=0.0085, 동결 Q1 5점 Gauss–Hermite 공동 거리 적분과 공통 σ_s0²를 유지한다. 각 arm은 기존 RF 감지 여부를 공유하고, 3개 이상의 유효 yaw를 요구한다. 개별 추출값의 분모가 0·비유한이면 해당 yaw를 무효로 기록한다.
- 기준도 포함한 세 후보 계산은 동결 yaw 0.25° 격자, truth-centered ±10° 창 및 기존 우승 후보 선택을 사용한다. 곡률 계산 지원은 ±12°다. **이 창은 오프라인 공통 채점용**이다. 거리를 인과적 prior에서 읽는 효과를 시험하며 운용 heading 필터를 재검증하지 않는다. 오차는 wrap₁₈₀(추정−참값)이다. 새 분산 보정이나 필터 갱신은 적용하지 않는다.
- 진행 기준은 입력 SHA와 Q1 전체 sweep 기준선 오차·분산·XY·flat 일치(동결 1e−12), 실수 거리의 Fourier 표본과 IFFT 정수 표본 일치, 합성 단일 경로에서 공통 지연·편파비 재현이다. 기준선 검사는 개입 결과보다 먼저 독립적으로 완료한다.
- case별 sweep RMSE, 평균 signed 오차, |e| p95, |e|>5°, station별 평균 오차의 RMS, 공통 유효 분모와 무효·heading 창 경계·지연 창 경계 count를 낸다. 물리 station을 재표집하는 2,000회 짝 bootstrap으로 각 대조의 sweep RMSE 차이에 percentile 95% CI를 계산한다. R4_aB와 R2_aA는 별도 보고하고 R2_aA의 x≤6 m / x≥8 m 층을 별도 집계한다. x는 복도 좌표다.
- K8의 tap 불일치는 R4_aB에서 원인 후보지만, 개입의 효과 크기는 이 짝 대조로 추정한다. ORACLE은 같은 full 채널에서 읽기 위치만 바꾸는 비운용 개입이다. 올바른 읽기 위치에 겹치는 반사는 이 비교 이후에도 남을 수 있다. 결과는 기존 BLOCK_C의 구조 진단에 사용한다. S2′ 판정, Step 3, 확인 데이터 봉인 상태는 기존 결정대로 유지한다.
