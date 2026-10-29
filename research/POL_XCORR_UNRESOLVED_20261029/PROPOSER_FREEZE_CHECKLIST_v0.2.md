# POL-XCORR-001 — contract freeze checklist (v0.2)

v0.1 체크리스트를 대체한다. 근거 없는 체크는 무효. 독립 reviewer 기록이 있어야 각 행이 `DONE`.

| Gate | Required proof | 현재 상태 | 근거 |
|---|---|---|---|
| F-01 | governance 적용 방식 확정(router append 또는 by-reference) | PENDING (R-09) — 문안·적용표 준비됨 | `governance/AGENTS_ROOT_APPEND_PROPOSAL.md`, `governance/GOVERNANCE_APPLICABILITY.md` |
| F-02 | full governance SHA, base SHA, contract sha256 | PARTIAL — governance SHA `PENDING_REPIN_AFTER_R09` | contract v0.2 §Authority, `PACKAGE_MANIFEST_v0.2.json` |
| F-03 | 입력 hash·observer 체인 고정 | DRAFT_DONE (auditor 재계산 필요) | `INPUT_LOCK_v2.json` (trace 개별 hash 포함, 불일치 0) |
| F-04 | observer parity: s_fp, log_fp_power, G5 재현 | PENDING (P0: R-02, R-12, R-13) | — |
| F-05 | LoS q floor 측정 + 사전 규칙 | 규칙 DRAFT_DONE, 측정 PENDING (P0 R-03) | PLAN_PARAMETERS_v0.2 `los_floor_rule` |
| F-06 | trace 재정렬·재합성 | PENDING (P0 R-01, 실패 시 T4_ONLY_BLOCKED) | — |
| F-07 | pose 구조·층 정의 | DRAFT_DONE by design, join 검산 PENDING | 답변서 §2.1 |
| F-08 | S0 유도식(F2, ψ 독립) 독립 대수 검증 | PENDING (auditor) | SCIENCE_SPEC_v0.2 §2 |
| F-09 | tolerance·규칙이 결과 전 고정 | DRAFT_DONE | PLAN_PARAMETERS_v0.2 |
| F-10 | split·bootstrap(case 공동 block)·holdout BLOCKED 명시 | DRAFT_DONE | contract v0.2 §Data |
| F-11 | label 미사용 power simulation | PENDING (P0 block 수 이후) | SCIENCE_SPEC_v0.2 §7 |
| F-12 | baseline 적정성: M0 = G5 + \|ds1\| | DRAFT_DONE | 답변서 §3.1 |
| F-13 | 신규 scene/RT 예산 | DEFERRED (R-11) | — |
| F-14 | 독립 pre-run auditor 수용 | PENDING (R-10) | — |
| F-15 | CI negative fixture(잘못된 hash, LoS에 Δ 주입 시 q>0 검출, train/test route 중첩, trace 집합 누락 파일) | PENDING (구현자) | — |

**현재 허용:** `P0_PREFLIGHT`. F-01, F-02, F-08, F-14, F-15가 PENDING인 동안 FROZEN 서명 불가.
