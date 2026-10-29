# PRE-P3 AMENDMENT — DRAFT, UNSIGNED (P3 RT is NO-GO until signed)

| Field | Value |
|---|---|
| Status | `UNSIGNED_DRAFT`. Not executable; no RT job may read it. |
| Contract | MBVAR-INFO-001 FROZEN (`68d73bd2…`) + AMENDMENT-003/004 |
| Needs before signing | (1) a **numeric RT budget approved by the user**; (2) an independent auditor review of the AMENDMENT-003/004 results (P0_GEO2, S0V2, S1V2); (3) a decision on the open design item D1 below |
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
