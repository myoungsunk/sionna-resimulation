# AMENDMENT-010-P0 — execution lock for the A010 forensic ablation only

| Field | Value |
|---|---|
| Scope | Runs `code/a10_p0.py` (phases P2_A010P0_GEN, P2_A010P0_ABL) on **4 existing DEV2 keys**. Forensic and **not confirmatory**. No estimator, threshold or scientific rule is adopted. AMENDMENT-010 stays DRAFT. |
| Why a lock | The workflow runs only under a FROZEN lock with matching code hashes. This lock fixes the code and the key list before any A010 result exists. |
| Keys | K1 `10/LOW/TIME_1/s2/ORACLE` (C3 kink bifurcation) · K2 `11/REV60/TIME_HIGH_5/s0/ORACLE` (near-alternative minimum) · K3 `10/LOW/LOWCORR/s1/IID` (smooth no-kink control, the first S1V4 row meeting the rule field ∈ {10, 11}, LOW, LOWCORR, IID, CONVERGED_SMOOTH, kink 0) · K4 `15/REV60/POSE_HIGH/s1/ORACLE` (largest C3V4 Δcost) |
| Canonical input | S1V4 run `40992623257` receipts, byte copies. The S1V3 receipt hash is recorded alongside. |
| Replicates | Each key is run in two separate CI jobs (A, B) from identical archived inputs. The CPU and library of each job are recorded. Distinct CPUs cannot be forced, so their number is reported, not assumed. |
| Fixed parameters | Polish τ ∈ {1e-3 (baseline, ≤ 30 steps), 1e-3, 1e-6, 1e-9 (≤ 300 steps)}. Perturbation fixture: 1e-14 · N(0, 1) on z, seeds 1–3, τ ∈ {1e-3, 1e-9}. `Lhalf` check: \|LLᵀ − K_psd\|_max / \|K\|_max ≤ 1e-10. K2 straight-line profile at t ∈ [−0.25, 1.25], 31 points. |
| Preserved | Everything earlier. G5 FAIL stands. HOLDOUT2 and P3 are NO-GO. |
| Role | IMPLEMENTER, SELF_REVIEW_ONLY |

## AMENDMENT_LOCK
