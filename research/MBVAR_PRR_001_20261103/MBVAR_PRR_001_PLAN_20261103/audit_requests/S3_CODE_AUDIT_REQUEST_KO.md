# S3-C — 체크포인트 재처리: 독립 코드 구현 감사 요청

**역할:** INDEPENDENT CODE AUDITOR S3  
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

## 실행 전 확인

해당 단계의 사전 설계 승인이 있고, 구현 SHA가 실제로 동결되어 있는지 확인하십시오. 구현자의 CI 통과와 본 실험 승인 여부를 구분하십시오. 승인된 합성·parity 범위를 넘어 평가 데이터로 모델을 조정하지 마십시오.

## 단계별 필수 검산

1. IDENTITY_REPLAY: x/P뿐 아니라 risk detector·cooldown·shadow state를 복원하고 완전히 같은 결과가 나와야 함.
2. 현재 posterior에서 과거 측정을 다시 넣지 않음. 첫 재적용 관측 이전 checkpoint 선택을 확인.
3. REWEIGHTED_REPLAY를 독립 cold replay와 비교. 같은 원관측·controls·고정 mean/R·σb·새 prior에서 d0/H/K 재계산.
4. 역사 reweight가 바뀐 sample 목록·사유·결정시각을 검사. 단순 재실행인데 성능이 바뀌면 원인을 찾아야 함.
5. online_emitted와 retrospective_smoothed 분리. 이미 내보낸 과거 출력을 조용히 덮어쓰지 않음.
6. current time t의 후보가 t 이후 입력을 읽지 않는지 prefix/suffix 인과성시험. 과거시점의 재가중에는 current까지만 허용.
7. 최종 추론 체인 packet ledger: 같은 likelihood 이중 사용·독립 fusion 없음. 재계산 횟수와 정보 사용 횟수를 구분.
8. x/P/history/risk 상태의 원자적 교체, 지연 중 출력, 실패 시 rollback이 완전한지 확인. 후보 채택은 사전 고정한 finite/PSD/packet·변화량 guard만 사용하고 GT·최소 NIS로 선택하지 않음. 현재와 후보의 last sample id가 다를 때 stale 상태 교체를 차단.
9. buffer miss, episode 이전 checkpoint 부재, 오래된 손상checkpoint, duplicate/misordered/missing packet, 중첩 replay를 음성시험.
10. C_CP와 D_CP 모두 P injection OFF. C_CP는 상시 예방 OFF이지만 등록된 역사 재가중 ON. identity와 구분.
11. primary 60s와 10/30s 민감도, episode당 처리횟수 cap, memory/latency에 shadow 및 replay 전체 비용 포함.
12. 예상하지 못한 Rrs≠0, float precision 변경, timestamp drift를 자동 보정하지 않고 중단하는지 확인.

## 감사자가 만들어야 할 근거

양성시험뿐 아니라 각 오류를 의도적으로 만든 음성시험이 FAIL하는지 제출하십시오. 서로 다른 runner에서 동일 입력의 결정론·gate·출력 hash를 확인하고, 비교가 저장 정밀도 차이에 불과한지 구분하십시오.

## 승인 조건과 출력

모든 P0/P1 문제가 해소되고 필수 시험이 충족돼야 `GO_S3_DEV` 또는 별도 동결 평가 승인 토큰을 발급할 수 있습니다. 미해결 항목이 있으면 HOLD/FAIL. 

제출물: `CODE_AUDIT_S3.json`, `CODE_FINDINGS_S3.md`, 독립 테스트 코드·입출력·runner 로그. 이 승인은 성능 개선이나 다음 단계 승인 자체가 아닙니다.
