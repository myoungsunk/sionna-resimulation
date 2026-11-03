# MBVAR-PRR-001 실행 계획 패키지

**작성:** 2026-11-03 / **상태:** DRAFT, 실행 전

이 패키지는 **1. 오염 관측 가중치 조정 → 2. 선택적 P 복구 → 3. 체크포인트 재처리**를 단계별로 검증하기 위한 계획과 독립 감사 요청 문안이다. 구현 코드나 새로운 실험 결과를 포함하지 않는다.

## 먼저 읽을 파일

1. [`01_EXECUTION_PLAN_KO.md`](01_EXECUTION_PLAN_KO.md): 전체 계약·실험·단계별 검증·중단 기준.
2. [`02_EXPERIMENT_MATRIX_KO.md`](02_EXPERIMENT_MATRIX_KO.md): 예방×복구 네 실험, 현재성능/복구만의 효과 분리.
3. [`audit_requests/`](audit_requests/): 구현 전 사전감사 1종, 단계별 코드감사 3종, 단계별 결과감사 3종.
4. [`templates/EXECUTION_CONTRACT_DRAFT.json`](templates/EXECUTION_CONTRACT_DRAFT.json): 제안 설정과 동결/승인 차단 필드.
5. [`templates/AUDIT_RESULT_TEMPLATE.json`](templates/AUDIT_RESULT_TEMPLATE.json): 기술 판정과 주장 지원 판정을 분리한 보고 틀.
6. [`SOURCE_REGISTRY.json`](SOURCE_REGISTRY.json): 조회한 source reference, 기존 자료 hash, 미확보 입력.
7. [`evidence/`](evidence/): 이전 대화에서 생성한 **진단용 표** 사본. 새 성능 검증이나 독립 감사 결과가 아님.

## 단계 공통 흐름

PROPOSER 계약 확정 → 독립 설계 사전감사 → 격리 구현·합성/회귀 QA → 코드 SHA 동결 → 독립 코드감사 → 승인된 실행 → 독립 결과·주장 감사 → 다음 단계 승인.

- 구현자의 자체검산은 독립감사를 대체하지 않는다.
- 독립 감사자는 별도 세션·별도 runner와 자체 검산 코드를 사용한다.
- 이 문서에 적힌 계수·성과 목표는 **v0.1 제안값**이다. 실행 전에 승인·동결해야 하며 결과를 본 뒤 변경하면 새 실험 버전이다.
- 현재 독립 에이전트가 배정되거나 감사가 실행된 상태가 아니다. 요청서를 전달 가능한 형태로 준비한 것이다.
- GitHub 저장소에는 이 패키지를 푸시하지 않았으며, 기존 RF·필터·계약·결과를 변경하지 않았다.

## 네 실험의 의미

| Arm | 예방 | 복구 |
|---|---|---|
| A | OFF | OFF |
| B | ON | OFF |
| C | OFF | ON |
| D | ON | ON |

2단계는 복구=P, 3단계는 복구=checkpoint로 각각 수행한다. 두 복구를 처음부터 합쳐 하나의 효과로 제시하지 않는다. `C_CP`에서는 현재 관측에 상시 예방을 하지 않지만, 복구 시 과거 의심 구간을 다시 가중하는 것이 checkpoint 처치에 포함된다.

## 현재 상태

| 항목 | 상태 |
|---|---|
| 계획·실험·감사 요청서 작성 | COMPLETE |
| 독립 설계 감사 | NOT_REQUESTED / NOT_RUN |
| 구현·합성시험·원본 parity 재실행 | NOT_RUN |
| 과학적 성능 시험 | NOT_RUN |
| 동결·실행 승인 | NOT_GRANTED |

패키지 파일의 `MANIFEST.sha256`은 문서 사본의 무결성 확인용이다. 과학 실험 입력 전체의 INPUT_LOCK이나 실행 승인을 대체하지 않는다.
