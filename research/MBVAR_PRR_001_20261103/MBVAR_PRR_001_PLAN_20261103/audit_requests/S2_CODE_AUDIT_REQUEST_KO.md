# S2-C — 선택적 상태 공분산 복구: 독립 코드 구현 감사 요청

**역할:** INDEPENDENT CODE AUDITOR S2  
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

1. ΔP=Σq u uᵀ의 q≥0, PSD, 단위 검산. 전체 P를 diagonal로 바꾸거나 cross-covariance를 임의로 지우지 않음.
2. 주입 직후 평균 x가 변하지 않는지, 기존 큰 분산을 target으로 오히려 줄이지 않는지 확인.
3. 접선/Heading 축, near-axis isotropic fallback, bg 평균 불변. B0라는 정답으로 bias=0 리셋 금지.
4. P 확대는 predict 이후·측정 이전, 원래 σb timing은 보존. 동일 Reff로 새 K/P 갱신.
5. 한번의 episode에서 여러번 주입하지 않음. latch/cooldown/최대회수·geometry guard·skip 이유를 검산.
6. trigger는 truth/error가 아니라 causal 위험 이력·관측·운동만 사용. 작은 d0가 ‘정답상태’라는 판정을 하지 않음.
7. geometry guard의 단위 정규화와 nuisance bg 제거를 독립 검산. bg를 이미 안다고 가정한 조건부 정보만으로 PASS하지 않음.
8. 동일 손상 snapshot A/B/C/D는 state/P/controls가 완전히 동일한 곳에서 시작.
9. 공통 trigger 메커니즘시험과 arm별 trigger 운용시험 구별. P 확대 때문에 gate가 임의로 완화되지 않음.
10. ν=0 및 측정 OFF 음성시험: P 확대만으로 평균이 움직이면 FAIL. geometry가 부족한 상태의 fallback 확인.
11. 신규 Qbg, mean reset, 재학습, IEKF를 몰래 같이 추가하지 않음. bg variance ablation은 별도 arm.

## 감사자가 만들어야 할 근거

양성시험뿐 아니라 각 오류를 의도적으로 만든 음성시험이 FAIL하는지 제출하십시오. 서로 다른 runner에서 동일 입력의 결정론·gate·출력 hash를 확인하고, 비교가 저장 정밀도 차이에 불과한지 구분하십시오.

## 승인 조건과 출력

모든 P0/P1 문제가 해소되고 필수 시험이 충족돼야 `GO_S2_DEV` 또는 별도 동결 평가 승인 토큰을 발급할 수 있습니다. 미해결 항목이 있으면 HOLD/FAIL. 

제출물: `CODE_AUDIT_S2.json`, `CODE_FINDINGS_S2.md`, 독립 테스트 코드·입출력·runner 로그. 이 승인은 성능 개선이나 다음 단계 승인 자체가 아닙니다.
