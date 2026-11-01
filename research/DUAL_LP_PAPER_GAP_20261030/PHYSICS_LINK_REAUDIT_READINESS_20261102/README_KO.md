# Dual-LP 보완본 독립 감사 준비·데이터 유효성·물리 결과 연결

기준일: 2026-11-02 (Asia/Seoul).
검토 대상: `research/dual-lp-physics-link-r1-r5-repair-20261102`, SHA `ca8cb43777100a0f5fae53978c0e4096d49701ff`.

**결론:** R1/R2/R3/R5는 범위를 명시한 보완을 확인했다. 현재 수치자료는 검사한 범위에서 유효하나 R4 음성시험 코드의 미해결 결함이 있어 'R1–R5 완전 종료'나 새 독립 감사 최종 승인을 선언하지 않는다.

`DATA_ACCEPT_WITH_BOUNDARIES / R4_QA_REVISION_REQUIRED / INDEPENDENT_REAUDIT_PENDING`.

## 문서

1. [사전 유효성 평가·R4 잔여 결함](01_PREAUDIT_VALIDITY_AND_OPEN_R4_KO.md)
2. [독립 감사자 입력·임무·수용 기준](02_INDEPENDENT_REAUDIT_HANDOFF_KO.md)
3. [유효 데이터의 물리 관측–EKF 갱신–성능 연결](03_PHYSICS_TO_RESULTS_USE_KO.md)

이 브랜치는 문서4개만 추가한다. 기존 코드·model·mean/variance 설정·raw RF·trace·score·계약을 변경하지 않았다. Workflow를 추가하거나 RT/새 필터를 실행하지 않았다.

## 사전점검에서 실제 수행한 것

- 원격 HEAD와 비교범위 확인: 이전 감사 SHA에 비해 원 제출은 신규27파일, 기존변경0/삭제0.
- 보완ZIP inventory42파일 SHA·크기, RERUN 입력108개 SHA 확인. 별도 FFD 은행을 지정해시로 보충.
- 제출 보완코드 무수정 재실행 PASS를 확인하되, 이 결과 자체가 검사의 의미를 증명하지 않음을 구분.
- 핵심 계산은 제출 validation helper를 부르지 않는 별도 산술: 144행의5량 재산출, mean null24배치/25,088, 첫 분기 스냅샷144개.
- 원132 trace와 score파일은 이전 감사 원자료와 byte-identical. physics/shadow/FD의 해제된 내용도 동일.
- R4 negative harness의 pose/time 검출을 의도적으로 무력화해도 두 시험이 PASS하는 반례를 재현. 실제 제출 코드의 `got`이 직전 dt검사 결과를 재사용하는 것이 원인.
- 동일 timestamp와 평가분모 항등검사도 별도 반례 확인. 실제 저장 데이터의 오염을 발견했다는 의미는 아님.
- 물리3136 packet과 shadow50176 후보를 연결하고, 같은 표본의 signed 갱신과 loss를 비교할384개 구간을 새로 집계. 기존R6 원표는 보존.

## 독립성과 현재 결과 사용

현재는 제안자 문맥의 사전점검·문서 준비이며 새로운 별도 감사자의 최종 서명이 아니다. 제출 helper는 결함을 재현하는 시험대상일 때에만 사용했다. 원 SourceFFD 물리 미분의 전수 재실행은 이번 범위가 아니며 이전 동일입력 검사와 저장기록을 상속한다. 모든 동일성을 독립 물리 진실이나 하드웨어 보정으로 확대하지 않는다.

기존 Heading12/12, XY8/12, R2/R5 lookup 우세와 R4 constant 우세, R4 반례는 계속 사용할 수 있다. R4의 제한 QA를 고치는 데 새 모델·모든case개선·새RT를 요구하지 않는다. V4와 missing ML fresh inference는 현재 회고적 범위의 수치수용과 별도다.

## 입력·부속 산출물

공개GitHub에 보완코드와 부분표27개가 게시됐지만, 원132 trace와 FFD 전체는 별도 ZIP/은행 입력이다. 독립 감사자는 `02`의 해시·접근목록을 통해 확보해야 한다.

이번 대화에서 제공한 `DualLP_Repair_V2_Reaudit_Readiness_20261102.zip`에는 상세문서, `preaudit.py`, `physics_result_bridge.py`, 재계산 CSV/JSON, 결함 반례와 로그, SHA manifest가 있다. 큰 원자료와 FFD 은행은 중복하지 않았다. ZIP 자체를 이 Git 트리에 게시했다고 주장하지 않는다.

최소 다음 조치: 구현자가 R4의 현재반환값 참조·strict timestamp·독립 분모 검사를 별도 커밋으로 보완하고, 감사자는 그 수정에 대한 음성시험·반음성시험을 독립 실행한다. 모델과 기존 성능은 그대로 유지한다.
