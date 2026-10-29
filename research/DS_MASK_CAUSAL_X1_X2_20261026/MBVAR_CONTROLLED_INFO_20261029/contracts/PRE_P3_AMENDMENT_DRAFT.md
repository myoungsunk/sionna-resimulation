# PRE-P3 AMENDMENT — DRAFT, UNSIGNED (P3 RT is NO-GO until signed)

| Field | Value |
|---|---|
| Status | `UNSIGNED_DRAFT`. Not executable; no RT job may read it. |
| Contract | MBVAR-INFO-001 FROZEN (`68d73bd2…`) + AMENDMENT-003/004 |
| Needs before signing | (1) a **numeric RT budget approved by the user**; (2) an independent re-audit of the AMENDMENT-003…007 results (P0_GEO2, S0V2, S1V2, C2) |
| Author | IMPLEMENTER (proposal only), SELF_REVIEW_ONLY |

All values below are **proposals**. They resolve the contract's deferred RF fields (`MATERIAL`, `DIRECT_PARITY_TOL`, `RF_BUDGET`) only when signed.

## 1. Scope: P3 canary only

| Item | Proposal |
|---|---|
| Windows | LOW `A\|S_c7.5_A0.4_W4\|0`, HIGH `A\|S_c7.5_A0.8_W4\|0`, revisit `A\|REV60_y7_x3.0\|0` (31 unique poses), all anchor A |
| Poses | 24 per window: the LOW/HIGH windows at indices round(k·59/23), k = 0…23; REV60 at its first 24 unique poses |
| Scenes | `C00_DIRECT` (LoS only, no floor/plate); `C01_FLOOR` (floor z = 0); `C10_PLATE` (floor + C10 plate of that window); `C11_PLATE` (floor + C11 plate) |
| Configurations | 24 × 3 windows × 4 scenes = **288** (the PLAN cap) |
| Repeat-pose QA | T5 spin pose (6, 6) yaw 0°/360° in C00 and C01 (4 configurations). Identical H is required (RF-02/DATA-01). |
| Plates | From the AMENDMENT-004 lock `PLATE_DESIGN_PRE_P3` (P0_GEO2 image-source design; 100 % of window poses have the specular point inside the plate) |

## 2. Physics and solver (resolves `MATERIAL`)

| Item | Proposal |
|---|---|
| Solver | Sionna RT. Exact version and wheel hash pinned at P3 preflight; the PLAN candidate `sionna-rt==2.0.1` must be verified to exist first. |
| Interactions | Specular reflection on, max depth 3. Diffuse, refraction and diffraction off. LoS on (C00 = LoS only). |
| Plate material | ITU `metal`, thickness 5 mm (near-PEC; strongest controlled specular intervention) |
| Floor material | ITU `concrete` |
| Sensitivity C12 | Deferred (plate `glass`), only after C10 parity |
| Frequencies | The 257 FFD-bank bins, sha256 of the grid stored in the cache key |
| Antennas | The same FFD complex banks as `SourceFFD` (anchor + two robot ports ±45°), via an adapter. Robot z 0.45 m, mount 0°, anchor (2, 2, 2.65). |
| Observation | Frozen extractor (Hann window, 4× zero padding, leading edge 0.3, first-path tap, signed two-port power ratio). Raw tap index and port powers are logged. |
| Cache key | `rt_keys.rf_cache_key` with scene-geometry, materials, solver, flags, frequency-grid and extractor hashes |

## 3. DIRECT parity (resolves `DIRECT_PARITY_TOL`; RF-01). Any failure = STOP

C00 RT channel vs `SourceFFD.physical_h_col` at the same poses:

| Quantity | Tolerance |
|---|---|
| Per-pose relative complex error ‖H_RT − H_FFD‖ / ‖H_FFD‖ | median ≤ 1e-3, max ≤ 1e-2 |
| First-path tap index | identical in ≥ 99 % of poses |
| \|Δs\| | ≤ 1e-3 |
| \|Δr\| | ≤ 1 cm |
| C01 and C10 path ledgers | Distinct path counts. The predicted specular point (P0_GEO2) is matched by an RT path within 5 cm on the plate and 0.1 ns in delay. |

## 4. Budget (resolves `RF_BUDGET`; requires the user's numeric approval)

| Item | Proposal |
|---|---|
| Hard cap | 288 + 4 configurations; no automatic scale-up |
| Compute | GitHub Actions CPU runners, ≤ 20 parallel jobs, ≤ 4 h wall per job, ≤ 12 runner-hours total |
| Stop rules | First DIRECT-parity failure; any invalid or blocked path; repeat-pose mismatch; measured time > 2 × the benchmark of the first 8 configurations |
| Output | `RT_CANARY_QA.json`, `RT_BUDGET_RECEIPT.json` (measured throughput), `RT_POSE_KEYS.csv`, `RT_PATH_LEDGER.csv` |
| After the canary | No pilot or bulk RT without a new numeric approval |

## 5. Track R effect sizes (resolves `EFFECT_SIZE` for R)

To be set from the S1V2 HOLDOUT2 results and canary QA, **before any R holdout**. Proposal: reuse the Track S equivalence factor 1.5 and the DID rule. Independent unit: `scene_variant_id` (reserved 2000–2239).

## 6. Open design item D1 (decision needed before signing)

The §D plate rule optimised only geometric containment. The reported specular **excess delay** is:

| Window | C10 | C11 |
|---|---|---|
| LOW | 6.2 taps (0.93 m) | 10.5 taps |
| HIGH | **26.3 taps (3.93 m)** | 6.5 taps |
| REV60 | 6.0 taps | 7.6 taps |

A reflection arriving 26 taps after the first path barely touches the first-path tap. The HIGH C10 intervention on `s` could therefore be close to null, and that would confound the scene contrast.

Proposal: add the constraint "median excess delay ≤ 8 taps (1.2 m)" to §D and re-select by the same objective and tie-breaks, before any RT. This is a design choice that must be made without RT outcomes, so it is left for the user/auditor.


---

## REVISION 2 (2026-10-29, AMENDMENT-007): proposer decisions D1–D4 after the re-audit

This section supersedes §1 (scope), §4 (budget) and §6 (D1) above. Everything else in the draft stays a proposal.

**D1 — FINAL (proposer).** Use one shared C10 plate for every window:
- Centre (2.75, 1.50) m, length 2.0 m, orientation 0°, z 0–2.7 m, ITU `metal`, 5 mm.
- Specular point inside the plate for 100 % of poses in LOW, HIGH, REV60 and FWD60.
- Excess delay ≤ 6.32 taps at every pose; the rule is ≤ 8 taps at all poses.
- LoS not cut, footprint clearance ≥ 0.10 m, anchor distance 0.50 m.
- C11 is excluded from confirmatory comparison until a shared C11 passes the same rules.
- Plates are never moved after RT outcomes.

**D2 — initial canary scope (proposal).**
- 3 scenes (C00 DIRECT, C01 FLOOR, C10 SHARED) × 3 windows (LOW, HIGH, REV60) × 8 poses, at window indices round(k·59/7), k = 0…7. REV60 uses its first 8 unique poses.
- Total 72 configurations, plus 4 repeat-pose QA = **76**.
- **Stage 1** (8 C00 configurations): DIRECT complex parity and extractor check. Any failure stops the canary.
- A mismatch is decomposed by phase reference, port orientation, frequency mapping and tap. Tolerances are not relaxed silently.
- **Stage 2:** the C01/C10 comparisons, including the measured Δs of the first-path observation.

**D3 — physics/numerics.** As in §2/§3:
- Sionna RT 2.0.1, exact install and hash verified.
- Same 257 bins and FFD banks.
- C00 = direct only; C01 = C00 + concrete floor sheet; C10 = C01 + shared metal plate.
- Max depth 3; diffuse, diffraction and refraction off.
- Frozen extractor.
- Outputs: complex H, paths, delays, first-path tap, r, s, and a per-pose configuration hash (`rt_keys.rf_cache_key`).
- The DIRECT parity tolerances stay candidates, not proof of equivalence. The metal-reflection-coefficient claim must be checked per frequency.

**D4 — budget (REQUEST FOR USER APPROVAL; not approved).**

| Item | Proposal |
|---|---|
| Configurations | ≤ 76 |
| Parallelism | ≤ 4 workers |
| Total | ≤ 8 runner-hours |
| Checkpoint | parity after the first 8 configurations |
| Platform | one able to reproduce the earlier RF computations |
| Scale-up | no automatic scale-up; a 24-pose expansion needs a separate approval |
