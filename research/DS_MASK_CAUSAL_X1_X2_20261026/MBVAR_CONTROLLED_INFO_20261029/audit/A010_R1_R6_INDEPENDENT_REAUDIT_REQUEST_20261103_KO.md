# MBVAR-INFO-001 A010 — R1–R6 보완 코드 독립 재감사 요청

**상태: AUDIT_REQUEST / IMPLEMENTER_SELF_REVIEW_ONLY / A010_SCIENCE_DRAFT / DEV3-HOLDOUT2-RT NO-GO.**

## 고정 감사 범위

- 원래 두-runner 실행: https://github.com/myoungsunk/sionna-resimulation/actions/runs/41453446631 ; 수행 SHA `4dece4c63ef62e046366e6c062f63a21ad89e05f`, 기존 DEV2 K1/K2 2-key 범위.
- 새로운 수정 코드: `implement/mbvar-a010-audit-r1-r6-fix-20261103`; Draft PR #16.
- 새 시험: https://github.com/myoungsunk/sionna-resimulation/actions/runs/41560555661 ; code source SHA `6733fb52510e7f4687a8f117f6a01e22b703538e`.

## 필수 감사 검증

1. **R1 keyset:** 등록된 모든 `(field,role,cell,sensor_seed,arm)`의 정확한 Set/Multiset 대조를 SOURCE LOCK으로 독립 계산. **동수 duplicate+missing** fixture를 직접 재현. S1 QA와 C3 G5 rows gate 모두 검사.
2. **R1 reference duplicate:** C3가 `.set_index` 하기 전에 S1 source reference duplicates를 fail-closed 하는지 확인.
3. **R2 arm stratification:** Pooled 99%가 PASS라도 한 arm FAIL인 반례를 독립 재계산. 기존 legacy full-row per-arm 원칙 보존 및 subgroup 누락 여부 확인.
4. **R3 actual call:** 7 original estimator arrays의 bytes-SHA와 실제 `FL.batch_map_v2_ms` 인수를 호출 직전/직후에 확인; E300·진단 start 경로도 감사. 저장 원본 검증과 자체 비교를 구분.
5. **R4 finite:** 비용·state·full C10·NEES·수치 비교 deltas에 NaN/±Inf를 주입했을 때 PASS가 나지 않는지 코드/CI 결과로 검증.
6. **R5 mode:** truth-free starts의 단순 중복과 고유 국소 최소점 수를 구분. E′ vs diagnostic solver precision, F2 polish seed/stop criterion, ambiguous 행 main H/CAL 포함, field-paired error/P/NEES sensitivity를 별도 제안자가 승인해야 할 미확정 항목으로 기록.
7. **R6 freeze:** 기존 A008/A009/A010-P0/RUN_REQUEST/contract_lock 및 과거 C3/C3V4 FAIL blob 불변. 신규 후보 계약 DRAFT, no new DEV3 inputs, whole-S_field overlay only DEV3 prospective, unrelated old HOLDOUT not revived.
8. **성과 범위:** CI 900/901 (S1 44 vs original full 132, C3 10 vs full 72) 및 이전 K1/K2 두 runner를 1,080-row full science PASS로 승격하지 않는다.

## 감사자 산출물

- 직접 계산한 rowkey coverage SHA/duplicate-missing fixture, per-arm stability table, 7-array optimizer SHA at actual call, finite negative test evidence.
- 원본 SHA·source snapshot·input/source manifest·test command·수치 tolerances·independence and reuse disclosures.
- 코드 결함 발견 시 재현 조건·파일·라인·최소 수정안을 명시.
- 최종 판정 하나: `ACCEPT_WITH_BOUNDARIES / REVISION_REQUIRED / REDESIGN_REQUIRED / BLOCKED_EVIDENCE`.
- 만약 동일 구현자/헬퍼만 사용했다면 `SELF_REVIEW_ONLY`, 독립 감사 서명 공란.

**서명·동결:** `INDEPENDENT_AUDITOR_SIGNED=false`, `PROPOSER_R5_APPROVED=false`, `A010_SCIENCE_FROZEN=false`.