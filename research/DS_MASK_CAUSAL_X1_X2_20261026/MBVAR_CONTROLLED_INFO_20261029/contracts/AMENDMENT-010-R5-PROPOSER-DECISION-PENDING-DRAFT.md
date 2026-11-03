# AMENDMENT-010 — R5 제안자 선택 필요 / PRE-FREEZE DRAFT

**Status:** `DRAFT / R5_PROPOSER_DECISION_PENDING / NO_EXECUTION_AUTHORITY`

**Scope:** MBVAR-INFO-001 / A010 / 2026-11-03 독립 감사 R5 보완 후보. 본 문서는 `AMENDMENT_LOCK`이 아니며 기존 `AMENDMENT-010.md` 지위를 변경하지 않는다.

## 1. 기존 구조 유지 후보

- **Operational estimator:** 기존 S1V5 E′ (`batch_map_v2_ms` + F2 polish) 및 state selection 유지. 과거 결과를 본 뒤 기본 estimator를 변경하지 않는다.
- **Diagnostic arm:** 9개 truth-free 출발점(yaw 7개, x+1, y+1) 각각에서 동일 `FL.batch_map_v2` objective, `T.polish` 알고리즘, `POLISH_TOL`·`POLISH_MAX`. Start별 고정 hash seed로 reproducible 실행.
- **정밀도 주의:** E′는 multi-start/rescue 포함 경로인 반면 진단은 `batch_map_v2 + F2`다. 목적함수와 F2 기준을 공유하더라도 실제 수렴 수준의 동일성은 별도 점검해야 한다. DEV3 이전 제안자 동결 필요.
- **Ambiguity 후보:** `|C_s-C_E′| ≤ 1 χ²` AND `d_ref(x_s,x_E′) > 2`인 truth-free 시작점이 하나 이상이면 해당 행은 ambiguous. 근접해가 있으면 unique-MAP 주장은 허용하지 않는다.
- **Oracle boundary:** truth-start는 별도 진단/참값 점검용이며 nonoracle 선택 또는 operational 모드 채택에 사용하지 않는다.
- **주 H/CAL 모든 행 유지:** ambiguous 행을 H1/H2/H3/CAL/H4에서 삭제하지 않는다. Clean subset은 보조 진단이며 99%/2 d_ref 조건은 각 arm별 검사.
- **Field-paired sensitivity:** 기준 E′ 대비 Δcost, d_ref, state squared error, full C10, ΔP, ΔNEES4, Δlogdet(P)를 같은 field·role·cell·sensor·arm에서 전부 보고. 의미 있는 변화 임계값은 proposer/독립 감사 전 미확정.
- **Multiplicity:** K2의 ‘대안해 5개’는 조건을 충족한 *출발점 다섯 개*다. 고유한 local minimum 다섯 개라고 주장하지 않는다. Clustering/unique-mode 수는 미동결.

## 2. Proposer + 독립 auditor가 최종 결정할 항목

1. E′와 진단 출발점의 최종 수렴/최적화 정밀도와 300 iteration cap 처리 규칙.
2. Start grid, random-probe seed, fixed objective와 계층적 gate 역할의 최종 계약.
3. Near-cost 해 중복/클러스터링 기준을 채택할지; 미채택 시 n_ambiguous_starts만 보고.
4. Field-paired sensitivity의 과학적 중요성 기준 및 반복 field 단위 통계 처리.
5. 기존 DEV2 K2 결과는 forensic이며 DEV3 confirmatory 증거로 사용하지 않는다는 경계.
6. 원래 STATE_STABILITY_FIXED_LEGACY FAIL 보존과 별도 사전 동결 감사 서명.

## 3. 승인·실행 상태

`PROPOSER_R5_APPROVED=false`, `INDEPENDENT_AUDITOR_SIGNED=false`, `A010_SCIENCE_FROZEN=false`, `DEV3/HOLDOUT2/RT=NO-GO`.

이 문서는 제안자 결정문과 독립 감사 서명을 대체하지 않으며 즉시 실행 권한을 부여하지 않는다.