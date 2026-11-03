# A0 — 구현 전 독립 설계·입력 사전감사 요청

**역할:** INDEPENDENT PRE-AUDITOR  
**현재 상태:** REQUEST TEMPLATE / NOT ASSIGNED / NOT RUN

## 공통 전제와 독립성

- 이 파일은 **독립 에이전트에게 전달할 요청서 템플릿**이다. 현재 배정·실행·승인을 의미하지 않는다.
- 대상: MBVAR-PRR-001, 단일 앵커 B, R4-B/R5-B, Mount0, 기존 4상태 MB_VAR.
- 새 경로·RF·관측평균 재학습·FGO 전환 금지. truth/LoS label은 평가용이며 runtime 입력 금지.
- 구현자와 다른 세션 및 **별도 runner**에서, 직접 작성한 독립 검산 경로를 사용한다. 구현자의 점수표·서술만으로 승인하지 않는다.
- production update/score helper를 그대로 import해 얻은 일치는 단독 독립 증거가 아니다. 원본 RF/관측모델을 공유할 때는 공유한 부분과 별도 계산한 부분을 명시한다.
- 원본 계약·데이터·성공 기준을 수정하지 않는다. 발견한 문제는 최소 재현 사례와 수정 요구사항으로 보고한다.
- 기술 실행 성공, 과학적 주장 지원, 다음 단계 책임자 승인을 분리한다.
- 요구된 권한·입력·SHA·runner가 없으면 `BLOCKED` 또는 `SELF_REVIEW_ONLY`; 독립 PASS를 발급하지 않는다.

## 먼저 읽을 자료

1. `../01_EXECUTION_PLAN_KO.md`와 `../02_EXPERIMENT_MATRIX_KO.md`.
2. `../templates/EXECUTION_CONTRACT_DRAFT.json`에서 파생되어 실제로 승인된 `CONTRACT_LOCK.json`.
3. `SOURCE_REGISTRY.json`, 원본 `INPUT_LOCK.json`, 실제 실행 코드 SHA와 환경 lock.
4. 구현자 실행 요약은 마지막에 읽는다. 먼저 원시 코드·로그·artifact의 사실을 확인한다.

## 반드시 제출할 공통 기록

- auditor_id/session_id/runner_id, 검토한 코드·계약·입력·출력 SHA.
- 감사자가 직접 작성한 검산 코드 SHA, 실행 명령·환경·음성시험 결과.
- issue_id, severity(P0/P1/P2), 실제 근거 파일/line/array key/sample id, 기대값/관측값, 판정에 미치는 영향.
- 미검증 항목·실패·NA·실행 안 됨을 각각 분리.
- 수정 후에는 새 SHA를 대상으로 재감사하고 기존 실패 기록을 보존.
- 최종 판정은 `AUDIT_RESULT_TEMPLATE.json` 구조를 사용하되 모든 값은 실제 증거로 채운다.

## 질문

이 계획이 ‘오염 예방’과 ‘이미 손상된 상태 복구’를 과학적으로 구별하며, 구현자가 결과를 보고 임의로 조건을 바꾸지 않고 실행할 수 있을 만큼 정의됐는지 감사하십시오.

## 필수 검토

1. MB_VAR의 실제 μr/μs/R/σb·BASE gate 정의를 source 및 배열로 확인. POWER_DIAG와 혼용하지 않음.
2. 참조 SHA와 향후 실행 SHA를 구별. 모든 raw RF·bank·controls·μ/R·timeline의 immutable hash를 확인.
3. 개발 자료와 추가 seed의 출처·이미 사용된 데이터 여부. 같은 RF를 독립 환경이라고 부르지 않는지 확인.
4. 후보 목록·τd/τD/wmin·P 하한·trigger·cooldown·history 길이·선정 규칙·평가 기준의 미확정 항목을 열거. 평가를 보고 선택할 자유도가 남으면 HOLD.
5. 4-arm A/B/C/D의 의미가 S2(P)와 S3(CP)에서 일관되는지 확인. C_CP는 역사 재가중이 있어야 하며 단순 replay와 구별.
6. 동일-prior/동일 손상 snapshot/전체 causal replay/수정된 과거곡선 점수가 분리되는지 확인.
7. F32 로그를 F64 precision 인증에 쓰지 않는지, 단위·PSD 허용오차가 선고정됐는지 확인.
8. risk가 현재 상태오차와 상쇄될 수 있는 조건, 고가중 정상관측 오기각, Q와 P 복구의 차이, 버퍼부족·이미 손상된 checkpoint의 실패 정책.
9. 기술·과학·운영 gate가 분리되며, 과학적 NULL을 PASS로 바꾸는 경로가 없는지 확인.
10. 별도 auditor/runner 및 결과검산 역할을 실제로 배정했는지 확인. 미배정은 아직 독립감사 완료가 아님.

## 허용 활동

읽기·hash 확인·설계 검토 및 승인된 최소 수치 단위시험만. 본 과학 실험·신규 RF·평가용 tuning·원본 수정 금지.

## 출력

`PREAUDIT_FINDINGS.md`, `SPEC_AUDIT.json`에 각 항목 PASS/FAIL/BLOCKED를 기록하십시오. 전체 전제가 충족돼야 `SPEC_APPROVED`를 제안할 수 있습니다. 책임자 승인과 실제 계약 SHA 동결이 없는 상태에서는 실행을 승인하지 마십시오.
