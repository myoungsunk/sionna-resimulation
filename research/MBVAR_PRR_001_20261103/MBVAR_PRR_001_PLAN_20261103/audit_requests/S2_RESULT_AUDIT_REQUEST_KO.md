# S2-R — 실제 상태 복구와 단순 P 확대의 구별: 독립 결과·주장 감사 요청

**역할:** INDEPENDENT RESULT AUDITOR S2  
**상태:** REQUEST TEMPLATE / NOT ASSIGNED / NOT RUN

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

## 핵심 임무

‘코드가 실행되었는가’가 아니라 **실행 결과가 미리 정한 과학적 주장을 지지하는가**를 독립적으로 판단하십시오. 구현자 결론을 답습하지 말고 사전 계약과 원시 trace로부터 재계산하십시오.

## 단계별 확인

- snapshot 시작 state/P 및 이후 입력 동일성부터 재확인. 예방으로 애초에 덜 틀린 결과를 복구라고 부르지 않음.
- A/B/C_P/D_P에서 mean error, 10/20s 오류 적분, 정확도 회복시간, false recovery, σ/coverage를 각각 재계산.
- P만 커졌고 mean error가 줄지 않으면 UNCERTAINTY_RELAXED_ONLY. 상태복구 주장은 NOT_SUPPORTED.
- trigger가 발생하지 않은 case, 보류, 미복구, 말미 censoring을 삭제하지 않음.
- D−B로 예방 위 복구 추가가치, D−C로 복구 위 예방 추가가치, interaction은 각 손실에서 별도 계산.
- 실제로 오염된 관측에 P 확대가 gain을 키워 악화시킨 반례와 정상 LoS 불필요복구를 공개.
- C4(복구), C6(결합)를 판정. 새 bg 평균/동역학을 같이 바꿨다면 순수 P 효과 주장을 차단.

## 전체 필수 검사

- 등록한 모든 route/bias/channel/seed/arm이 있는지 확인. 누락·실패·censoring을 NA와 구분.
- 원본 input/code/contract SHA, 실제 run SHA, artifact digest가 일치하는지 확인.
- 전체 t≥30s 점수와 초기·회복·말미 구간을 분리. packet을 독립 표본으로 bootstrap하지 않음.
- 정확도와 calibration을 동시에 보고, P를 크게 만들거나 bad samples를 제외해 얻은 겉보기 성공을 차단.
- 기준 대비 쌍대 차이, R5-B/LoS 보호, 최악 seed와 오복구를 포함.
- 추가 sensor seeds의 의미를 같은 RF에서의 안정성으로 제한. 경로/환경 일반화를 승인하지 않음.

## 출력

`RESULT_AUDIT_S2.json`, `RESULT_FINDINGS_S2.md`, `CLAIM_SUPPORT_S2.csv`를 제출하십시오.

각 claim에 필요한 근거, 관측 결과, 반례, 미확인 조건, 허용 문장을 기록하십시오. 기술 판정은 별도 열, 과학 판정은 SUPPORTED/PARTIAL/NOT_SUPPORTED/NOT_TESTED로 구분하십시오. 다음 단계 승인 필요성과 사유를 제안하되 책임자 승인으로 대신하지 마십시오.
