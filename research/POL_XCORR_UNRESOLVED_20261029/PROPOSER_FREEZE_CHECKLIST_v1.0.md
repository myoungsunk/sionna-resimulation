# POL-XCORR-001 — freeze checklist (v1.0)

| Gate | 상태 | 근거 |
|---|---|---|
| F-01 governance 적용 | DONE | router `d5f84d9d` (보존 branch `governance/pol-xcorr-router-d5f84d9d`), `governance/GOVERNANCE_APPLICABILITY.md` |
| F-02 SHA·contract hash | DONE | `FREEZE_RECORD_v1.0.md` |
| F-03 입력 hash·observer | DONE (TECH) | P0 run 40867521966, AUDIT-01 A |
| F-04 s_fp / log_fp_power / G5 parity | DONE (TECH) | AUDIT-01 B·C (R-13b 포함) |
| F-05 LoS floor + 규칙 | 측정 DONE, 판정은 S0 | D6 입력 고정 |
| F-06 trace 재합성 | T4_ONLY_BLOCKED | D8 |
| F-07 pose 층 | DONE | P0 POSE_ALIGNMENT |
| F-08 F2 유도 검증 | DONE (SELF_REVIEW) | AUDIT-01 I (기울기 1.9991) |
| F-09 R-14 구현 | DONE (TECH) | P0V3 run 40884686972, AUDIT-01 D |
| F-10 split·bootstrap·holdout | DONE | 계약 v0.3 §Data + v1.0 D1 |
| F-11 검정력 | DONE | `power/results_f11/run_40984998584`, D1·D2 |
| F-12 baseline 적정성 | DONE | M0 = G5 + \|ds1\| |
| F-13 RT 예산 | NOT_REQUIRED | R-11 DEFERRED |
| F-14 독립 auditor | **OPEN** | SELF_REVIEW_ONLY 서명만 있음 → D5 제한 |
| F-15 CI negative fixture | DONE (TECH) | P0V3 21/21, P0 fixture |
| F-16 R-13b 보존 | DONE | `evidence/r13b_run_40983557008/` |
