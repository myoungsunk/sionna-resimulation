# POL-XCORR-001 — v0.3 pre-freeze checklist (updated after P0)
**Status: DRAFT, FROZEN prohibited.** Authority: governance router SHA \`d5f84d9d04d28d465f3357e9299352eb184e6bfc\` (this branch only), original base SHA \`250d617ad89a4105fa1af546cc83ceed9de98f42\`.

| Gate | State | Evidence / remaining acceptance |
|---|---|---|
| F-01 R09 scoped router | **DONE ON v0.3 BRANCH** | Root AGENTS append-only commit d5f84d9d; scope POL-XCORR only. Implementation starts from this branch or cherry-picks router. |
| F-02 governance + contract/config/source hashes | **PARTIAL** | Governance and base SHA known; compute/record SHA256 of v0.3 science spec/config/contract, source code, workflow after implementer review. Never reuse v0.2 hash. |
| F-03 source/observer/input hash | **P0 TECH PASS, AUDIT PENDING** | P0 successful run 40867521966, all core assets and trace set hash match. |
| F-04 R02/R12/R13 stored feature parity | **P0 TECH PASS** | Full 9519 ×17 G5 and supplementary Full/LoS 19038 ×17, max 7.11e-15; strict key coverage. Shared upstream not independent science replication. |
| F-04b R04 exact tap/branch/valid | **OPEN_IMPLEMENTER** | Compare n0+strong-port branch explicitly. Verify \`features.valid\` with its 80-tap rule separately from FP detection validity; negative fixtures. |
| F-05 R03 LoS q floor | **MEASURED, S0 RULE PENDING** | 9519 VALID LoS rows, q95 timeline ~0.00621. The q_ref NEGLIGIBLE/NUISANCE/REDESIGN test is deferred to frozen S0 and unchanged. |
| F-06 R01 trace re-synthesis | **T4_ONLY_BLOCKED ACCEPTED** | 925+925 structure/hash; T4 withheld, other stages may continue. |
| F-07 R05 pose/phase isolation | **DONE TECH** | Timeline 7251; STATIC_YAW_SWEEP 2268 diagnostic only. |
| F-08 F2 physics/slope derivation | **AUDITOR PENDING** | Separate algebraic check under LAW psi-fixed and PHYSICAL psi-linked. |
| F-09 R14 status/model threshold | **DECISION MADE, IMPLEMENTATION PENDING** | Primary E1 M0+q_W, eps_rho secondary; WEAK_PORT 0.05 flag only, no primary row exclusion. Direct J energy math/negative tests required. |
| F-10 split/bootstrap/retrospective ceiling | **DRAFT READY** | LORO, cases of same route held together, route-shared blocks, single-scene retrospective limit. |
| F-11 updated label-free power simulation | **OPEN_IMPLEMENTER** | Simulate nominal q-only E1 and assumed ΔAUC 0.02/0.05; no actual labels before FROZEN. |
| F-12 baseline M0=G5+abs(ds1) | **DRAFT READY** | Existing stored G5 not to be pruned; q added only in E1. |
| F-13 R11 new RT scene/budget | **DEFERRED** | No new scene inference allowed. |
| F-14 R10 independent auditor | **BLOCKING** | Distinct auditor/session with independent math/raw-H path and signed report required before FROZEN. |
| F-15 CI negative fixtures | **OPEN_IMPLEMENTER** | Hash, duplicate/missing key, index/branch/valid, infinity/NaN, weak-port/NULL_PORT, no-label access. |
| F-16 R13b supplement archive | **OPEN/EXPIRY** | Source artifact 39376076166, sha256 \`6a69a36ad0f521e33a130a1bc1fbde5a4b7aae17ba62ec347ccc611fdd5c6fe4\`; expires 2026-11-19, archive approved bytes/provenance before expiry. |
| F-17 v0.3 delta P0 technical rerun | **NOT RUN** | New script/workflow, append-only outputs, all new QA gates and full provenance; no label/metric use. |

## Gating logic

- **Current:** P0 v0.2 CORE TECH PASS; R01 T4_ONLY_BLOCKED; R03 MEASURED; R09 installed on new decision branch; R10 independent sign-off missing; R14 conditional decision frozen only as v0.3 DRAFT implementation guidance.
- **Before FROZEN:** F-02/F-04b/F-08/F-09/F-11/F-14/F-15/F-17 must be independently accepted, plus one complete reviewer receipt.
- **After FROZEN:** S0 evaluates q_ref LoS floor under v0.2 inherited rule. S0 failure may stop M1/M2. P1/P2/P3 follow registered gates only.
- Do NOT rename \`TECHNICAL_QA_ONLY\` from run 40867521966 to independent audit PASS.
