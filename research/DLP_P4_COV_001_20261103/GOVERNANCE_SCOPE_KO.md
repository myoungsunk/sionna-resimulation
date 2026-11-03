# DLP-P4-COV-001 — 거버넌스 적용과 역할 분리 (PROPOSER, FROZEN SPEC)

기준 소스·거버넌스 Git commit: e365b2f79eb86a3fd53d0d350f8e2d9364f285fe.

기존 docs/research-governance/COMMON_CONTRACT.md 및 ROLE_* 규정의 직접 적용 대상은 MBVAR-INFO다. 이 계약은 기존 규약을 자동 확장했다고 주장하지 않고 다음 원칙을 별도 과학 계약의 구속 조건으로 채택한다.

- APPLY: 원본 불변, 모든 입력 해시와 코드 SHA, append-only 증거, 탐색/동결 구분, 사용 전 independent auditor verdict, 과장 없는 주장 범위.
- ADAPT: MBVAR의 GP/RT/holdout 규약 대신 기존 P4 12개 EKF trace와 R2/R4/R5 GT의 읽기 전용 D1 분석을 수행한다.
- NOT_APPLICABLE: 새로운 RF RT, MBVAR S0/S1 covariance simulator, 신규 독립 장면/seed 생성, 보정 R 학습 및 D2–D4 필터 개입.
- D0 구현자 자체 점검과 과거 Actions의 독립 계산 runner는 새로운 D1에 대한 독립 사전 감사가 아니다.
- 독립 AUDITOR는 구현자·제안자와 다른 검증 주체/세션에서 실제 입력·식·해시를 확인하고 identity/verification method를 기록한다. 같은 세션의 자체 점검은 SELF_REVIEW_ONLY로 표시하고 GO를 발행할 수 없다.
- 이전에 본 C0+ 탐색적 수치와 R4 0% 현상은 설계 동기다. 재분석 D1은 새로운 holdout이나 미관측 검증이 아니다.
- 프로포저는 과학적 estimand와 단계 규칙을 동결한다. 구현자는 실행하되 AUDITOR 역할을 자임하지 않는다. 감사자는 독립한 수학 계산으로 확인한다.
- 상태 전이: D0_PASS → PROPOSER_FROZEN_SPEC → AUDITOR_PRE_RUN_GO_D1 → IMPLEMENTER_D1_RUN → INDEPENDENT_POSTRUN_REVIEW. GO_D1 서명 없으면 실행 보류.
- 사후 변경: 원계약 수정 금지. 사유·기존 결과 조회 여부·영향 범위를 기록한 AMENDMENT-XXX 및 새로운 독립 사전 감사 필요.

원본 P1–P4, main, MBVAR, POL-XCORR, 기 연구 본문은 변경하지 않는다.
