# DLP-P4-COV-001 — D1 독립 사전 감사 요청서

**받는 역할: AUDITOR (PROPOSER·IMPLEMENTER와 분리된 세션/검증 주체).**
**현재 판정: PENDING, 본 문서는 감사 승인이 아님.**
**대상 GitHub:** myoungsunk/sionna-resimulation
**기준 원본 SHA:** e365b2f79eb86a3fd53d0d350f8e2d9364f285fe
**Contract:** FROZEN_SCIENCE_CONTRACT_D1_KO.md와 D1_NUMERIC_LOCK.json, INPUT_SOURCE_LOCK.json의 **개별 SHA-256** 및 GitHub 동결 commit을 확인할 것. 인용할 브랜치 이름이 아니라 40자 commit SHA를 기준으로 판단할 것.

## 독립 감사 범위 (D1 실행 전)

1. GitHub의 P4 원본 12개 trace ZIP과 P1/legacy GT Actions 아티팩트를 각각 새로 다운로드하고 SHA를 검사. D0 구현자의 PASS receipt만 보아 승인하지 말 것.
2. route/pose_id/t_s/full precision GT 정합, 84개 조건·12 trace·총 75208 평가 arm-epoch·모든 R2/R4/R5의 LoS/Full/B0/L2/7 arm 포함을 검증.
3. 원본 3-DOF pose95/heading95 재현 가능성과 신규 2-DOF XY NEES, Schur 분해, 고유축·실제 오차 비교의 수학적 적합성을 **구현자 함수와 다른 수식·계산 경로**로 점검. 3-DOF pose와 XY marginal 혼용, bias 4D conditioning, Schur heading과 marginal heading 혼동 여부 확인.
4. 샘플 시간창 10/20/40s의 t=30 고정, 잔여 부분창 포함, Schur/PSD/시간/score 1e−9 판정의 기계적 실행 가능성 확인. 기존 frozen 숫자 변경 금지.
5. 설계 leakage 여부: 2026-11-02의 기존 proposal 탐색 결과가 보였음을 기록; C0+ 외부 일반화·독립 복제·동기화 claim 없음, data-driven threshold 선택 없음.
6. D1은 읽기 전용, 변경 가능한 old code/R/Q/gate/GT 없음. D2–D4·원인 후보 정량 검정·모든 새 RF/재귀 필터 개입은 권한 밖.
7. 자기 점검과 제3자 검증의 구분: auditor_actor, audit_session_identity, code reused/not reused, 직접 실행한 검증, 각 확인 SHA, 최종 판정 evidence를 필수 기록.

## 사전 승인 기준 / 즉시 중단

- SHA/원본/결측/GT 정합 틀림, 84개 행 중 일부 제외, 수치공식 해석 불명, 시점 독립성 주장, freeze 변경 → REVISION_REQUIRED 또는 BLOCKED.
- 실험 수행 코드를 확인하지 않은 경우에도, 설계·자료·수학·구현 전제 수준에서만 PRE_RUN_GO_D1를 부여할 수 있고, 구현자 첫 실행 시 사후 QA 확인 책임은 남는다.
- 같은 세션/동일 작성자의 자체 계산은 SELF_REVIEW_ONLY 및 GO 발행 금지.

## 요구 회신 형식

AUDITOR_PRE_RUN_VERDICT_D1.json: {contract_id, phase, audit_actor, audit_session_id, independence_statement, frozen_commit_sha, frozen_contract_sha256, numeric_lock_sha256, input_lock_sha256, source_files_reacquired, math_checks, leakage_assessment, blockers, verdict: GO_D1|REVISION_REQUIRED|BLOCKED_EVIDENCE, evidence_paths, UTC_timestamp}.

**이 문서를 받는 AUDITOR는 검증을 실제로 실시하고 본인의 서명/증거로 회신해야 한다.** PROPOSER가 감사 결과를 임의로 작성하거나 PASS라고 대리 기록할 수 없다.
