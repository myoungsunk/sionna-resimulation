# 새 구현자 세션 최초 전달 프롬프트 — MBVAR-INFO-001 A010 (2026-11-02)

당신은 이전 구현자와 **다른 신규 구현 세션**의 `IMPLEMENTER`입니다. 예전 구현자 자신의 QA를 독립 감사로 수용하지 말고 실제 GitHub SHA·코드·Actions를 확인하십시오. 이 task의 실제 수행은 GitHub repository `myoungsunk/sionna-resimulation`에 한정합니다.

## 기준 SHA

- 검증된 이전 코드: `research/mbvar-info-a010-s1v5-fix-20261101@9e0686602b612cd9f948e8a2f9f8e9098facd434`
- 인수 문서: `handoff/mbvar-info-a010-new-implementer-20261102`의 `research/DS_MASK_CAUSAL_X1_X2_20261026/MBVAR_CONTROLLED_INFO_20261029/reviews/NEW_IMPLEMENTER_START_HERE_A010_20261102_KO.md`
- 제안자 결정: 같은 디렉터리의 `PROPOSER_A010_D2_D3_D4_D6_DECISIONS_20261102_KO.md`
- 코드 감사: `audit/A010_LATEST_IMPLEMENTER_FIX_REVIEW_20261102_KO.md`
- `role=IMPLEMENTER; contract_id=MBVAR-INFO-001; governance_git_sha=250d617ad89a4105fa1af546cc83ceed9de98f42; base_git_sha=af8e0a1b5299ae5e279f9b602afd2f1bb710c4e3; experiment_contract_sha256=68d73bd22bf467625559f3092433f250cbe91cb2fef011f92151975975b00f34`.

## 명령

1. 새 개발 브랜치를 인수 문서 기준에서 생성하고 `AGENTS.md`, `COMMON_CONTRACT.md`, `ROLE_IMPLEMENTER.md`, 기존 실험 계약, A008–A010를 순서대로 읽으십시오. 코드/실험 출처와 기존 FAIL/C3V4/H1/H2 내용을 먼저 검증하십시오.
2. 현재 코드에서 통과한 26개 테스트를 먼저 독립 재실행하고 S1V5·C3V5의 **SMOKE 900/901만** 실행하십시오. DEV3/holdout을 열지 마십시오.
3. 제안자 결정을 다음과 같이 구현하십시오. **D2(a) 수용 + field 간 Σ 수치 동등성 게이트; D3 receipt integrity·generator law·solver replay·full C10 분리; D4 technical reproducibility vs mode identifiability 이중 verdict, legacy gate 보존; D6 기존 S_field 전체 복제 후 DEV3만 추가, 전역 merge 알고리즘 변경 금지.**
4. 새로운 음성 fixture, 2-runner forensic 검증, full source/input SHA, code-hash lock 초안을 준비하고 독립 감사 요청을 제출하십시오.
5. **본 지시 자체는 A010 FROZEN 승인이 아닙니다.** 사용자·제안자·별도 감사자의 동결 승인 전 `RUN_REQUEST.json` 전환, DEV3 20–29, HOLDOUT2, reserve, 신규 RT 실행을 금합니다. 과거 결과를 덮어쓰거나 결과를 보고 기준을 완화하지 마십시오.
6. 첫 답변은 `BASE_SHA`, `NEW_BRANCH`, `CODE_BLOB_PARITY`, `D2_ACCEPTANCE`, `D3_DESIGN`, `D4_TWO_VERDICTS`, `D6_SPLIT_DIFF`, `TEST_PLAN` 8개 필드를 포함해 주십시오.

**완료 조건:** 새 구현 diff·실제 GitHub Actions 증거·기계적 PASS/FAIL 및 과학적 판정 분리·원래 C3/C3V4 FAIL 보존·별도 독립 감사 인수. 기술 QA PASS는 scientific PASS가 아닙니다.
