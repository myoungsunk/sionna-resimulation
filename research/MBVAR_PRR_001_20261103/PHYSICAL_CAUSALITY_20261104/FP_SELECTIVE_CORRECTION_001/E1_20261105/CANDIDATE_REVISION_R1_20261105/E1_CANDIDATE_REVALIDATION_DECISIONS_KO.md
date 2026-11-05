# E1 후보 개정 재검증 — 사용자 결정 반영

2026-11-05 / PROPOSER / 설계 반영, NOT_RUN. 질문 ID FP-SC-001-E1-R1. E1-02로 명명하지 않는다.

## 사용자 요청과 첨부의 권한 구분

이번 사용자 본문이 지정한 네 대조, 주안 VAB, 전체 데이터 수, 통과 조건, 기존 실패 보존과 주장 경계를 적용한다. 첨부 FP_SC_candidate_revision_followup_decisions_20261105.zip은 제안 근거다. 자체 NOT_FROZEN/NO_EXECUTION_AUTHORIZATION 표기를 유지한다. D01–D07의 후속 준비·실행·seed·모델·승인 제안은 이번 요청으로 일괄 승인되지 않는다. 이 문서도 실행 토큰이 아니다.

기준 로컬 저장소 HEAD: 0679b3b615ce99639f5bba4e2515eff209375db7. 후속 연결을 확인한 소스: 486f0b6c008e7a953ada75a03a941ffa46994985의 src/qclean_uwb/fp_sc/followup/{selection,contracts,engine}.py. 해당 커밋에 대한 확인이며 최신 브랜치 상태라는 주장은 하지 않는다. 연구 지침은 앞선 CANDIDATE_REVISION_PROPOSAL_KO.md에 기록한 로컬 공통/PROPOSER 해시를 유지한다.

## 실험 범위와 판정

|대조|후보 구간|봉우리 지지|
|---|---|---|
|V0|기존 에지±1|기존 양측 prominence|
|VA|기존 + 에지부터 peak까지|기존 양측 prominence|
|VB|기존 에지±1|기존 + 왼쪽 상승 지지|
|VAB — 사전 주안|기존 + 상승 구간|기존 + 왼쪽 상승 지지|

정확한 수식과 경계는 기존 CANDIDATE_REVISION_PROPOSAL_KO.md를 유지한다. 30%/15%/6%, raw fallback, noise/numeric floor, cap64, plateau 첫 peak, tap 중복 제거와 두 후보 모드를 유지한다. 새 RF 생성은 없다. 동일 6,320파형 × 2모드 × 4대조 = 50,560 packet-mode-arm 행이다. 각 대조의 12,640행 receipt를 별도 보존하고 종합 비교표로 연결한다. 원래 단일 대조 receipt를 50,560행으로 바꿔 사용하지 않는다.

- V0: 기존 12,640행의 후보·ID·분모·상태·판정을 재현한다. 불일치 시 재검증 결과를 채택하지 않고 원인을 해결한다.
- 참조 포함: dynamic Full TWO_PORT_UNION 큰 오류의 supported AND usable exact-tap recall이 전체 및 비어 있지 않은 각 route에서 >=95%. 분모 0은 NOT_TESTED.
- 기존 성공 보호: 기존 usable-reference 성공을 신규 실패로 바꾸지 않는다. 기존 후보와 유효 raw fallback도 보존한다.
- 후보 예산: 기존 usable 파형에서 신규 overflow 0. 상한 64 유지; 조용한 절단 또는 cap 증가는 금지한다.
- 후보 부담: 전체/정상/오류별 후보 수 median/p95/max, group 수·병합, episode 누락, 처리시간·메모리를 공개한다. 이미 본 결과에 맞춘 추가 합격선을 만들지 않는다.
- VAB가 실패하면 같은 결과에서 VA/VB를 골라 자동 채택하지 않는다. 대조는 원인 분리 근거로만 남긴다.
- 기존 E1 실패와 모든 증거는 보존한다. 개정 사양·출력·판정은 별도 버전이다.

## 후보 생성에서 후속 선택기로 넘기는 계약

후보에 존재함 → 실제 CIR 지지가 있음 → pool 사용 가능 → 선택 가능 → 최종 선택 → 정정/필터 효과는 서로 다른 상태다. E1 재검증의 주 지표는 앞의 세 단계이며 후속 선택 성공을 대신하지 않는다.

확인된 기존 연결:

1. selection.from_pool의 support = max_lobe[min(1,prominence/G) * exp(-abs(tap-edge))].
2. select는 supported와 support>=Policy.min_support를 함께 요구하며 기본 min_support=0.15다.
3. 모든 지지 봉우리에서 에지 거리 >=2이면 support<=exp(-2)=0.1353352832<0.15다. 따라서 A 확장 후보가 다시 탈락할 수 있다. 다른 포트의 가까운 지지가 있으면 이 상한의 전제는 성립하지 않는다.
4. B로 허용한 낮은 양측 prominence 봉우리만 지지하는 후보 역시 기존 점수에서는 낮게 남는다. 다른 지지 봉우리/포트의 점수도 확인해야 하므로 모든 B 후보가 무조건 탈락한다고 일반화하지 않는다.
5. OriginalAdapter는 기존 CandidateConfig/generator를 사용한다. 그림에서 A/B를 계산한 것이 운영 adapter 반영을 의미하지 않는다.

후속 인계에서 candidate_revision, candidate_config_sha256, support_semantics_version, mapping_recipe_sha256을 명시적으로 결속해야 한다. 지원 기록에는 RX, lobe/group, 기존 prominence, 왼쪽 상승량, edge/peak/valley, support 근거 종류를 보존한다. 지원의 참/거짓(supported), 필수 선택 자격(selection_eligible), 연속 순위 점수(rf_score)를 분리하는 새 계약이 필요하다. 정확한 점수식·가중치·보류 기준은 아직 미확정이며 이번 문서에서 임의로 정하지 않는다. 전역 0.15 임계값만 낮춰 연결 문제를 감추지 않는다.

후속 연결 검증은 별도 버전으로 강한 e+2 후보, 낮은 bilateral/high-left-rise 후보, 같은 lobe의 다수 후보, noise-only, 한 RX null을 포함해야 한다. 생성→adapter→eligible까지 후보와 근거가 보존되는지 검사하되 참조를 써서 최종 선택을 강제하지 않는다. 같은 lobe의 촘촘한 후보를 독립 물리 가설로 세지 않고 lobe 내부 margin과 group 사이 margin을 구분한다.

## 결과와 진행 경계

수용 가능 주장은 '노출 개발 데이터에서 제한된 후보 가용성 개선'까지다. FP 정정 성공, 선택 안전성, 거리/편파 개선, EKF 개선, 미지 환경 일반화는 별도 검증 전 NOT_TESTED다.

이번 작업은 사용자 결정과 소스 기반 연결 문제를 문서에 반영한 것이다. 후보 전체 재계산·운영 코드 변경·선택기 실행·E1-02·E2 이상 실행·새 RF/노이즈 생성·독립 감사는 수행하지 않았다. E2_GO=false를 유지한다.
