# PROPOSER_DECISION_03 — P0 acceptance and v0.3 science decisions

- **Role:** PROPOSER (decision). Independent scientific auditor sign-off: **NOT YET OBTAINED**.
- **Contract:** POL-XCORR-001, draft v0.2 (sha256 \`468249a7b32c9699c20a3227fc0241eef3ab92773d00bc52a981a32cf6e56ddb\`). All existing v0.1/v0.2 documents and runs are read-only.
- **Sources:** Actions P0 \`40867063352\` (workflow FAIL after P0 exit 0), \`40867521966\` (workflow success, actual P0 exit 0); implementation source \`51bf02337f6a067b3f42f392196bb083105559b4\`; P0 proposer execution patch on run head \`0574d26f4d71ec11b455d80374e4b6683b9f9f36\`.
- **New governance router installed:** \`d5f84d9d04d28d465f3357e9299352eb184e6bfc\` (R-09). This is the **governance_commit** to re-pin for v0.3; source/data base \`250d617ad89a4105fa1af546cc83ceed9de98f42\` remains distinct from P0 execution head.
- **Disclosure:** decision made **after seeing P0 LoS q_W / epsilon_rho without any metric–label/AUC analyses**. This is pre-science-freeze but not pre-P0. Changes to primary arm must be disclosed and frozen before S0/P1.

## 1. Acceptance table

| ID | Decision | Implementation obligation / evidence boundary |
|---|---|---|
| R-02, R-05, R-12, R-13a | **ACCEPT technical parity** | Full key coverage, existing reference and hash preserved; no scientific superiority claim. |
| R-13b | **ACCEPT supplementary** | 19038 Full+LoS rows from historical artifact; same upstream lineage as R-13a, NOT an independent scientific replication. Retain source artifact receipt, checksum and expiry. |
| R-04 | **PARTIAL / additional direct check required** | The P0 code compares s_fp/log-power against features.py but does not explicitly assert per-packet equality of \`tap\`, \`branch\` and \`valid\`; add such direct checks on 19038 Full+LoS rows, with negative fixtures. **Important:** `features.valid` additionally requires an 80-tap feature window (`tap+80<=1028`), whereas independent_observer's current `valid` checks the first tap/denominator only; assert two separately recomputed definitions, not their general equality. |
| R-01 | **ACCEPT T4_ONLY_BLOCKED** | 925+925 file schemas and hashes are intact; no independently verified Jones/signature/tau reordering or H resynthesis. T4 omitted, P1/P2/P3 still permitted after freeze under v0.3. |
| R-03 | **ACCEPT measured only** | LoS q_W floor is measured; no q_ref or NEGLIGIBLE/NUISANCE/REDESIGN judgment until S0 after freeze under unchanged predeclared rule. |
| R-09 | **ACCEPT and IMPLEMENT** | Append-only root AGENTS.md role router installed in this branch. Governance commit sha as above; existing MBVAR governance untouched. |
| R-10 | **ACCEPT as REQUIRED GATE; NOT COMPLETED** | Independent auditor must be a distinct session/runner from proposer and implementer; audit original H->CIR->tap->J and a sample of 7-case raw channel features by an independent code path; FROZEN remains BLOCKED until signed AUDIT report. |
| R-14(a) | **ACCEPT** | Make \`q_W\` the sole new primary M1 addition for E1, keeping M0=G5+abs(ds1) unchanged. |
| R-14(b) | **ACCEPT** | Demote \`epsilon_rho\` to secondary physics/sensitivity/negative-control feature, NOT part of E1 main learner. Keep gain invariance fixture. |
| R-14(c) | **ACCEPT FLAG ONLY** | Define \`WEAK_PORT = min(J11,J22)/trace(J) < 0.05\`. Finite valid rows retain q_W and epsilon_rho; flag is distinct from invalid tap/window/null port. No label-dependent threshold selection. |
| R-14(d) | **REJECT blanket exclusion** | Do not erase weak-port rows or set all primary model features to NaN; do not delete case/route observations. Only secondary complete-case sensitivity with baseline and candidate using identical subset, with coverage/selection report. |
| R-14(e) | **ACCEPT as secondary analysis** | Compare epsilon_rho on all valid rows, with flag, and strong-only restricted sensitivity. Any imputation is trained on training routes only and accompanied by explicit missingness indicator; optional 0.02/0.10 flag thresholds are sensitivity only. |
| R-07/R-08 | **DEFER external** | Hardware timing and VNA inputs unavailable; no physical-measurement claims. |
| R-11 | **DEFER** | New scene/RT budget not required for retrospective S0/P1/P2/P3; holdout independent physical generalization unavailable. |

## 2. Independent P0-result checks done in this decision session

Artifact \`POL_XCORR_P0_40867521966_EVIDENCE.zip\`, contents from original Actions. Both run manifests list eleven file SHA256 hashes and those hashes matched archived files (except self-referential manuscript excluded); P0 statuses all CORE PASS with no reported problems. P0 output source remains distinct from scientific pre-freeze audit. Numeric \(q_W,\epsilon_\rho\) from the two run copies agree within max 1.2e-15, by matched 9519 (case, pose_id) keys.

Actual P0:
- R02 9519/9519 max 1.11e-16.
- R12 9519/9519 max 1.33e-15.
- R13a 9519 x17 max 7.11e-15.
- R13b 19038 x17 max 7.11e-15.
- R01 T4_ONLY_BLOCKED, not a general stop.
- 9519 valid LoS local coherency rows, TIMELINE 7251, STATIC_YAW_SWEEP 2268.

**New label-free R14 audit**, recomputed from P0 \`LOS_FLOOR.csv\` (sha256 \`d2c08dbac53975d13b880cc93f3293c9eaaf8f4ae75c4fe07a7eee1cdaf24dd6\`):

For any 2x2 Hermitian PSD \(J\), \(a=J_{11}\), \(b=J_{22}\), \(D=\det J\):
\[
q_W=4D/(a+b)^2,\quad \epsilon_\rho=D/(ab),\quad
u=\min(a,b)/(a+b)\in[0,1/2].
\]
Therefore **exactly** \(q_W=4u(1-u)\epsilon_\rho\); for \(\epsilon_\rho>0\), \(u=(1-\sqrt{1-q_W/\epsilon_\rho})/2\).

| Stratum | n | u<0.05 | share |
|---|---:|---:|---:|
| ALL LoS | 9519 | 3492 | 36.7% |
| TIMELINE | 7251 | 3105 | 42.8% |
| STATIC_YAW_SWEEP | 2268 | 387 | 17.1% |
| TIMELINE drive | 6555 | 2938 | 44.8% |
| TIMELINE turn | 696 | 167 | 24.0% |

TIMELINE weak-port shares by case: R2_aA_m0 54.2%, R2_aA_m45 **1.0%**, R2_aB_m0 55.7%, R4_aA_m0 8.9%, R4_aB_m0 8.5%, R5_aA_m0 66.6%, R5_aB_m0 67.0%. Thus blanket exclusion causes **strong pose/yaw/route selection bias**.

All 1015 LoS rows with \(\epsilon_\rho\geq 0.05\) also have \(u<0.05\). The \(\epsilon_\rho\) 95th percentile is 0.1585 overall, 0.0223 in non-weak rows, and 0.3057 in weak rows. This demonstrates **weak-port concentration**, not a proof of numerical failure. As a normalized coherence quantity, \(\epsilon_\rho=1-|J_{12}|^2/(J_{11}J_{22})\) is theoretically bounded [0,1]. It can be physically legitimate in deterministic/noise-free LoS with frequency-dependent port patterns. Do NOT describe all large values as floating-point amplification.

## 3. Exact v0.3 learner definitions (BEFORE ANY LABEL VIEWING)

- **E1 primary:** \(\Delta \mathrm{AUC}_{r}\left(M0+[q_W], M0\right)\), timeline only, route-held-out; original block/bootstrap logic unchanged.
- **E1b secondary:** \(M0-\mathrm{jones\_diversity}+[q_W]\) versus \(M0\), same corpus and folds.
- **E1c secondary:** \(M0+[q_W,\epsilon_\rho]\) versus \(M0+[q_W]\), with all-valid, flagged and strong-only analyses separately; NOT a primary multiple-testing family.
- **E2 secondary:** \(M0+[q_W]+\mathrm{M2}\) vs \(M0+[q_W]\).
- **E4 primary within P2:** \(M0+[q_W]+\mathrm{M4}\) vs \(M0+[q_W]\).
- **No blanket exclusion.** For restricted strong-only E1c, both arms must be evaluated on the identical strong-only test keys and each route/case/phase removed fraction reported; train-only fit/transform and imputation if used.
- **Weak flag** computed from *7-tap W coherency*, not the first-tap scalar port power ratio. Validity status remains \`VALID\` for a finite weak-port row. \`WEAK_PORT\` must not replace \`INVALID_WINDOW\` or \`NULL_PORT\`.

## 4. Additional implementation / provenance blockers before FROZEN

1. **R04-index:** compare exact per-packet \`tap\`, \`branch\`, \`valid\` from the independent observer versus \`features.extract\` over both channels; fail closed on disagreement. The previous P0 R04 PASS was primarily algorithm-convention parity, not a printed per-index assertion.
2. **R14 direct-energy check:** compute \(u=\min(J_{11},J_{22})/\operatorname{tr}J\) directly from the 7-tap coherency, record \(q_W\), \(\epsilon_\rho\), \(u\), \`WEAK_PORT\`, and compare to algebraic inverse \(u(q,\epsilon_\rho)\) within a fixed numerical tolerance. Add \`WEAK_PORT\` fixtures (near-zero but nonzero port, balanced gain, a null-port case).
3. **Evidence lineage:** retain separate \`base_git_sha\` (existing 250d...), \`execution_source_git_sha\` (actual workflow head \`0574d26...\` for successful P0), \`governance_git_sha\` (d5f...), \`source_script_sha256\`, \`reference SHA\`, artifact ID/expiry. The old P0 manifest is immutable; new versions add fields.
4. **Negative fixtures:** bad tap, swapped ports, incomplete keys, duplicate keys, all-NaN / nonfinite sentinel and unexpected reference value. Current \`compare_reference\` explicitly checks NaN-pattern, but **must also fail mismatched infinity and enforce both rows' finiteness unless a column is documented to permit NaN**.
5. **Independent auditor:** independently recompute random and adversarial raw H packets from Full+LoS. Confirm labels are not loaded in the P0 path; run source/geometry/math checks and report sign-off with same governing SHA. A script originally patched by proposer must be reviewed by implementer before use as canonical v0.3.
6. **Power:** label-free power simulation uses updated E1 (q only), real route/block counts and assumed \(\Delta AUC\in\{0.02,0.05\}\), not observed labels.
7. **R13b preservation:** historical artifact expiry 2026-11-19; preserve immutable checksum receipt and a permitted evidence copy before expiry; any derived label-containing table remains isolated from the label-free pipeline.
8. **R03 unchanged:** no \(q_{\mathrm{ref}}\) or scientific LoS floor decision before a new pre-registered S0 run.

## 5. Gate / authorization

- \`P0_CORE_TECHNICAL=PASS\` for v0.2, source run 40867521966.
- \`R01_T4=BLOCKED\`.
- \`R03=MEASURED_ONLY\`.
- \`R09=ACCEPTED_AND_INSTALLED\`, R10=REQUIRED_NOT_YET_SIGNED, R14=PARTIAL_ACCEPT.
- **v0.3= DRAFT. S0/P1/P2/P3=NO-GO until** (i) above mandatory v0.3 index/energy/negative tests, (ii) full governance/config/contract SHA freeze, (iii) independent auditor report and proposer approval.
- Prior v0.2 P0 is **not** relabeled retrospectively as governed by R09. The old actions are preserved; governance re-pin applies prospectively.
