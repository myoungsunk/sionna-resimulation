# MBVAR-INFO-001 — 2026-11-03 독립 감사 REVISION_REQUIRED 신규 구현자 보완 보고

**ROLE: IMPLEMENTER / SELF_REVIEW_ONLY**
**A010 science status: DRAFT. 기존 C3/C3V4 FAIL 결과·FROZEN A008/A009/A010-P0 변경 없음. DEV3/HOLDOUT2/reserve/RT = NO-GO.**

## 0. 원본 출처

- 기준 독립 감사: 2026-11-03 PR #13 / tested SHA `4dece4c63ef62e046366e6c062f63a21ad89e05f` / 판정 `REVISION_REQUIRED`.
- 기준 구현·기술 검증: PR #13 head `9fc38a7ffa356a93678e2ff0fbbda22ceacf82bf`, original 2-runner DEV2 K1/K2 Actions #41453446631 PASS 범위는 2 case로 제한.
- 현재 새 수정 브랜치 `implement/mbvar-a010-audit-r1-r6-fix-20261103`; Draft PR #16.
- 현재 수정 코드 기술검증 source SHA `6733fb52510e7f4687a8f117f6a01e22b703538e` (후속 문서 commit은 source SHA를 변경하지 않음).
- 새 technical QA: https://github.com/myoungsunk/sionna-resimulation/actions/runs/41560555661

## 1. R1–R6 시정 사항

| ID | 감사 시정 요구 | 신규 구현 | 제한/추가 필요 |
|---|---|---|---|
| R1 | S1V5·C3V5 등록 표본 정확 집합 | `a10_validation.exact_registered_keyset`, `dataframe_row_keys`, `expected_s1_row_keys`, `expected_c3_row_keys`로 unique/missing/extra/compensated duplicates 전부 검사. C3 `set_index` 전에 원본 참조 중복 거부. S1/C3 키 coverage JSON에 전체 집계 | 별도 독립 감사 필요 |
| R2 | arm별 상태 안정성 | `mode_identifiability` 각 arm별 99% within 1 d_ref 및 max 2 d_ref를 legacy-full과 clean 집합에 각각 적용. pool average 사용 중단. 모든 ambiguous 유효 행 메인 H/CAL에 포함 | R5 과학 해석은 proposer 승인 필요 |
| R3 | 실제 optimizer 입력 전달 검증 | 저장된 `z,x0,ds_m,gy_m,Sigma_model,dts,taps` 7개 SHA 검사를 `T.estimate`의 실제 `FL.batch_map_v2_ms` 호출 직전·직후 실행, X/P/E′ 출력 SHA 기록. C3 진단 `batch_map_v2`, E300 경로에도 원본 입력 검증 | helper 의존성 보완 여부 독립 감사 필요 |
| R4 | NaN/Inf fail-closed | S1 batch·C3 원본·reference·replay 차이에 명시적 finite 검사. 독립 two-runner comparator에도 cost, state, C10, NEES NaN/Inf 거부. 음성 fixture 추가 | 미실행 raw 자료 전체 점검 별도 |
| R5 | truth-free 선택 규칙 동결 | 기존 estimator 및 모드 선택 방식 미변경. 신규 `contracts/AMENDMENT-010-R5-PROPOSER-DECISION-PENDING-DRAFT.md`에 후보·경계·후속 결정 항목 작성 | **PROPOSER_R5_APPROVED=false.** 동일 수렴 정밀도·과학적 효과 임계값 미동결 |
| R6 | 독립 재감사·코드 SHA 재잠금 | 새 기술 시험, 등록키 coverage 증거, 수정 코드 Git blob 및 독립 감사 체크리스트 준비 | **독립 감사 미서명, 전체 DEV3 1,080행 검증 NO-GO** |

## 2. 감사자가 재현할 음성 시험

- `tests/test_a10_audit_r1_r6.py`: duplicate가 missing row를 정확히 상쇄하는 동수 반례, arm B 99% fail이 pooled 집계에 가려지는 반례, optimizer 7개 original input에 대한 ULP/shape/dtype/NaN/bytes 공격, NaN/Inf cost/state/NEES/C10 comparator 공격.
- `tests/test_a10_s1v5_c3v5_exec.py`: 2-field SMOKE에서 S1 registered row coverage 정확성을 별도 확인, C3는 전체 등록 72행 중 일부 10행이므로 missing 62와 science FAIL을 유지, actual optimizer-boundary SHA 검사를 추가.
- Source interpreter: Python 3.11.11, numpy 2.3.3, scipy 1.16.2, pandas 2.3.2, pytest 8.3.3 (GitHub Actions pinned).
- 새 fast CI 42/42 PASS, full SMOKE integration status는 원본 Actions #41560555661 최종 job 성공·아티팩트로 별도 확인할 것.

## 3. 해석 경계

- 비용이 근접한 K2의 truth-free 출발점 다섯 개는 다섯 고유 최소점을 뜻하지 않는다. 2-runner numeric PASS와 MAP uniqueness는 서로 다른 판단이다.
- 새로운 code/tests pass는 900/901 기술적 축소 검증에 대한 증거로만 사용. Full 1,080 rows, field-level H-tests, covariance calibration과 RT는 실행하지 않음.
- 처음의 실패 `STATE_STABILITY_FIXED`와 기존 과학 결과를 소급 수정하지 않음.
- 독립 감수인 서명이 없는 현 문서 및 자동 CI 성공은 A010 science freeze를 승인하지 않음.

**현재 요청:** 별도의 AUDITOR가 full source·artifact·row set·arm별 stability·actual solver call-site SHA·finite failures를 독립 검산한 후 ROLE_AUDITOR 규칙에 따라 새로운 판정을 기록할 것.