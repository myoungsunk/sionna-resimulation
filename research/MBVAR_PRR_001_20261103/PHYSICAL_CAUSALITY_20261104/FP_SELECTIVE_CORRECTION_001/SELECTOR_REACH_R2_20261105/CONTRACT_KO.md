# FP-SC-SELECTOR-REACH-R2 — 세 검사 실행 계약

사용자 승인: 실제 선택기 합성 검사, 기존50,560행 실제 후보 집합 대조, 완료 관문 확인. E1-02/E2 시작 금지. VAB 주안·기존 실패·E1 및 bridge R1 결과 보존.

역할 IMPLEMENTER 및 동일 작업자 자체 검산. 기준 HEAD ce4ae9c5a5bf6841fc2059f6bf0fcf0dad4e40fe, 브랜치 implement/fp-sc-001-e1-run-20261105. 로컬 RESEARCH-GOVERNANCE-v1 COMMON_CONTRACT/ROLE_IMPLEMENTER 적용, 실제 해시는 부속 기록. 질문: 진단 전용 자격 표시가 아니라 실제 select의 집합 구성 경로에 VAB 후보가 도달하는가?

## 수정 경계

- selection.prepare_candidate_set를 실제 select와 전체 진단의 공통 경로로 사용한다. legacy는 원래 supported AND support>=min_support, 개정 Evidence는 검증된 selection_eligible을 사용한다.
- SelectionBinding은 arm/mode/candidate config/bridge recipe/selector recipe/Policy SHA를 대조한다. 개정 flag와 valid/overflow/polarization/supported의 불일치는 중단한다.
- R1 생성 규칙·순위 초안·Policy 기본 수치·margin·wrongness·history 수치는 변경하지 않는다. 새 순위 점수를0.15 문턱으로 재사용하지 않는다.
- 실제 select 호출은 합성 시험의 명시적 SyntheticSelectionProbe와 Evidence digest 결속으로만 허용한다. 단계 실행기는 이 인자를 전달하지 않는다. selector_ready=True만으로 개정 select/history를 활성화할 수 없다. PM-FORCE/NN-HARD는 도달 검사에 사용하지 않는다.
- 후보 집합 구성 전 prior/history hold는 NOT_REACHED와 사유로 기록하며 후보 제외와 구분한다. 단계 실행·실제 corpus 선택·이력 갱신·EKF·새 RF는0이다.

## 세 검사와 통과 조건

1. 실제 select 합성 검사: edge+2와 LEFT_RISE가 실제 eligible에 포함되고 정상 PM에서 REPLACE_SUPPORTED 가능함을 확인. RF score<0.15 후보도 자격 유지. 지원 없음/분모 invalid/overflow 제외, prior/history hold 및 동일·상이 group 동점 보류, 버전 불일치 차단. 공통 함수 호출을 spy로 확인. legacy는 고정486f0b6 select와200개 합성 Evidence×5모드=1,000개 Decision 전체 필드 exact 일치. 기존 bridge 합성 및 legacy ReceiverSelectionTest도 회귀 검사.
2. 기존 전체50,560행: 원래 R1 POOLS/CSV 해시·pool hash·키/분모를 검증하고 실제 prepare_candidate_set의 C 경로를 호출한다. C는 temporal 항이 없는 순위·집합 구성으로 결정은 내리지 않는다. P/M/PM의 준비된 context에서 집합 동일성과 context 부재 hold는 합성 검사로 확인한다. 실제50,560행에서 P/M/PM을 실행했다고 주장하지 않는다.
   - 기대 집합은 원본 pool의 raw.valid,overflow,polarization_valid,supported로 직접 계산; bridge flag 또는 공통 helper를 기대값으로 재사용하지 않는다.
   - 실제 집합과 기대 집합의 누락·추가·중복0. 원본 usable reference와 실제 집합 참조 포함이 일치해야 함. 참조는 집합 생성 후 evaluator에만 join.
   - 순위 점수도 별도 scalar q 및 -log(q) 계산과 절대오차2e-14 이내 비교. 후보 순위의 score/tap 정렬과 전체 후보의 eligible/excluded 분할을 확인.
   - 원래6,320파형×2모드×4arm, 큰 오류87/R2 19/R4 14/R5 54 유지. VAB87/87 및 원래 누락8건 모두 actual set에 포함해야 함. VAB 주안 변경 금지.
3. 완료 관문: 위 시험·행/원본 보존·저장 출력 재집계·수치 검사 통과 시 PASS_ACTUAL_SELECTOR_SET_REACH. 실패 시 기존 기록 보존 후 별도 run으로 수정 검증. 실제 선택 안전성 및 단계 권한은 계속 HOLD.

## 주장 경계

도달 완료는 실제 선택기 내부의 집합 구성까지 검증했다는 뜻이며, 실제 corpus 선택 성공·FP 정정·이력 안정성·EKF·일반화가 아니다. mapping/model/권한 준비와 E1-02는 별도 다음 단계다. 이전 결과를 덮어쓰거나 E1-02/E2를 시작하지 않는다.
