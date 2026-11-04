# MBVAR-INFO-001 — A010 science policy: proposer FINAL DECISIONS (not an applied freeze)

**Decision date:** 2026-11-04 · **Role:** PROPOSER · **Decision:** `PROPOSER_RULES_FINAL_NO_DEV3_OPENED`  
**Base:** audited A18 implementation PR #20 @ `8590cbc409c9f34d5b87dee9e35181f16532038d`; Python technical execution @ `360b496d089c54aaaa488ff1c2a571605547d96b`.  
**Approval status:** A18 `ACCEPT_WITH_BOUNDARIES` for technical fixes; **no distinct actor GitHub APPROVE for full A010**. This file alone is **NOT** `AMENDMENT-010 FROZEN_LOCK`.

## 1. Final science-affecting design choices — no post hoc relaxation

| Frozen proposer *choice* (not yet effective lock) | Exact decision | Reason/STOP |
|---|---|---|
| Primary estimator | **Original S1V5 E′ unchanged**: `batch_map_v2_ms` + F2 `polish`, `POLISH_TOL=1e−3 χ²`, max **30** steps. No best-start replacement. | Existing audited blob `s1v5.py=01c84e028ee2326d5127ecdaa62d74fcd697ce54`. |
| Kink classification | **`KINK_CLASS_UNCERTAIN` if classifier not independently geometry-certified; no kink-specific exception, no special tolerance.** | A geometric 1° cell-boundary distance classifier is **not required** to apply a blanket strict gate. Any later geometric tolerance is a new prospective amendment, not a retrospective fix. |
| Numeric replay | **Preserve the existing strict `c3v5.py` hard gates for *all* cases**: `z≤1e−9`; `control≤1e−12`; `fp_rel≤1e−12`; `state≤1e−6 d_ref`; `cost≤1e−6 χ²`; `full C10 natural relative≤1e−3`; `|Δlog10cond|≤1e−3`; `cross-field covariance≤1e−10`. | No nonzero kink allowance, no threshold widening based on historical C3/C3V4 or DEV2 failure. Byte-identical original inputs a separate non-negotiable gate. |
| Mode identification | E′ + **nine fixed truth-free** diagnostic starts. End-state ambiguity iff `|C_alt − C_E′| ≤ 1 χ²` and `d_ref(end)>2`. **No global/unique MAP claim**, no clustering 5 starts into 5 minima. | Same final F2 objective/probe, all 10 terminal receipts; cap, NaN/Inf, extra descent below −1e−3 χ² = `UNRESOLVED_PRECISION`. |
| G5 dual verdict | **`G5_NUMERIC_REPLAY` hard separate from `MODE_IDENTIFIABILITY` / `R5_SCIENTIFIC_CONCLUSION_SENSITIVITY`**. Preserve `STATE_STABILITY_FIXED_LEGACY` on every row even when FAIL. | Numerical pass cannot mask one-arm 99%/2d_ref fail or authorize scientific PASS; original C3/C3V4 FAIL historical. |
| Statistical unit | All valid registered keys retained, no removing ambiguous, field block bootstrap **B=4000**, seed **20261029**; H1=8/H2=2/H3=4/CAL=8/H4=8/H4_REPRO=32 (**62**). | Every field×sensor×role×cell×arm registered; any missing/failed row returns `NOT_EVALUATED_INCOMPLETE`. |
| Input replay | D2 field-qualified 180×180 factor and full Σ; D3 exact seven-array boundary `z,x0,ds_m,gy_m,Sigma_model,dts,taps` with dtype/shape/C-order SHA; C10 4×4 SPD/NEES; D6 entire prior `S_field` copy and only new DEV3. | K1/K2 prior diagnostic not independent new field; original receipt failure/corruption stops gate. |
| Interpretation | Scientific H/CAL sign and 95% CI, field-paired alternative effect envelopes, material sensitivity (Δsquared error/D_ref²≥1, |ΔNEES4|≥0.4, |ΔlogdetP|≥ln1.10) preserved unchanged. | Material result or sign/CI flip -> reviewer caveat/NO-GO; no all-case success or best-case selection. |

**PROPOSER STATUS:** `DESIGN_CHOICE_RESOLVED=true`; `S1V5_PRIMARY_CHANGE=false`; `KINK_EXCEPTION_ALLOWED=false`; `PORTABLE_RELAXATION_ALLOWED=false`.

## 2. Registered DEV3 universe to lock before reading any DEV3

- `DEV3=[20,21,22,23,24,25,26,27,28,29]` = **10 unseen field IDs**; independent sample is **field**, not the 3 seeds or each arm.
- `sensor_seeds=[0,1,2]`; 5 LH cells, 3 RV cells, 2 XMODEL RV cells.
- Per field×sensor: 2×5×2 LH Batch + 2×(3×2+2) RV Batch = **36 Batch**; `C3V5` target **10×3×36=1080** registered replay rows. The entire S1V5 output includes 3 additional non-Batch LH arms and therefore has expected **10×3×66=1980** total rows (verify using frozen `code/s1v5.py` code).
- All old `S_field` tracks (SMOKE, DEV, POST_HOC, DEV2, HOLDOUT2, HOLDOUT2_RESERVE) retain exactly their prior IDs and key conventions. Never read/open `HOLDOUT2=5000..5059` or `RESERVE=5060..5119` at this stage.
- DEV3 is **not** permitted to execute from this decision document. Effective code/input/split locks and audit authorization must be separately satisfied.

## 3. Audit independence and process change

The original `COMMON_CONTRACT.md` and `ROLE_AUDITOR.md` require a **distinct auditor** before science freeze. The **same implementation GitHub account `myoungsunk` cannot create an independent `APPROVE`**. Existing report `ACCEPT_WITH_BOUNDARIES` is limited technical acceptance and must not be transformed into a fake signed independent review.

**External-review waiver is NOT assumed by this decision**: A user-authorized single-actor alternative is documented as an **explicit separate governance change option**, not yet made effective. Such an exception, if subsequently approved, must be prospectively recorded before DEV3; findings under that route are `USER_AUTHORIZED_NONINDEPENDENT` and must never be labeled `INDEPENDENT_AUDITED` or `CONFIRMATORY_INDEPENDENT`. A successful CI is not an auditor signature.

## 4. Remaining mechanical A010-FREEZE inputs

- [ ] **Exact 49 Python code/scripts/tests/audit** file SHA256 ledger pinned after all scientific code/test changes; contract/source/config SHA and governance commit; use *file bytes* SHA256 (Git blob SHA1 is NOT interchangeable).
- [ ] Immutable base experiment contract digest and applied A008/A009/A010-P0 hashes checked; exact **full** `S_field` base-vs-D6 keys; SHA-locked FFD input receipt and complete numerical source manifest.
- [ ] A010-FREEZE pre-run audit verdict explicitly includes historical FAIL, all G5 strict gates, K2 ambiguity, independent status and potential mode sensitivity.
- [ ] Apply a **separately authorized audit path** (distinct external reviewer or clearly approved governance exception); until then `AMENDMENT-010.md` remains **DRAFT** and `RUN_REQUEST.json` remains on P0 forensic.
- [ ] Only after effective lock & authorization may DEV3 field IDs be opened and failure cases counted (even if resulting gate FAILs).

**This source-level decisions file is append-only; it does not overwrite `AMENDMENT-010.md`, `RUN_REQUEST.json`, legacy FAIL or historical frozen amendments.**

## 5. RT relationship

This is a Track S/D3 contract finalization decision only. Track R RT/P3 has a distinct signed **pre-P3 amendment** for material, mesh/scene, direct/floor path parity tolerances, frozen source/extractor SHA, runtime/throughput and numeric user-approved budget. **No RT canary, bulk RT, HOLDOUT2 from this file.**

`A010_SCIENCE_FROZEN=false` · `INDEPENDENT_AUDITOR_SIGNED=false` · `DEV3/HOLDOUT2/P3_RT=NO-GO`.
