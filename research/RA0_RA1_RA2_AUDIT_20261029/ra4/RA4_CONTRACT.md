# RA4-MBVAR-FACTORIAL-001 — retrospective implementation and effect separation contract (2026-10-29)

Status: **FROZEN FOR RETROSPECTIVE MECHANICAL TEST**, not preregistered evidence of unseen-scene performance. Research release status `TECHNICAL_QA_ONLY`; reviewer `SELF_REVIEW_ONLY`.

## Scope and immutable inputs

Repository `myoungsunk/sionna-resimulation`. Historical input/algorithm source `9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13`, prior RA3 reference `audit/g3-ray-forensics-ra3-20261029@ac9941f4fe5463a325c4c3899c1d9af73d4b6be4`. E1 7 archived case control streams from `reflect_model/fetch_inputs.sh` with `FETCH_RF=0` and two SHA-verified FFD banks, identical same original `t,z,R,mu_B,mu_M,truth` across 4 gyro levels. No H regenerate. Cases: `R2_aA_m0,R2_aB_m0,R2_aA_m45,R4_aA_m0,R4_aB_m0,R5_aA_m0,R5_aB_m0`. Gyro levels: `B0,L0,L1,L2` (shared RF, not 28 independent scenes).

## Canonical algorithm names
- `BB_ORIG` = `mu_B`, `R` without extra `sigma_b`.
- `MB_ORIG` = archived packet-aligned `mu_M`, `R` without extra `sigma_b`. Changes **mean only** relative to BB_ORIG.
- `BB_VAR_LEGACY` / `MB_VAR_LEGACY` = respective `mu_B/mu_M`; `R_ss <- R_ss + sigma_b(rho(x_previous_posterior))**2` **before motion prediction**. This is original `pol_bias_model/exp_pb.py::run` execution. Original published `MB_VAR` is always this variant.
- `BB_VAR_PRIOR` / `MB_VAR_PRIOR` = respective `mu_B/mu_M`; same R, same sigma table; lookup on `x_current_predicted_prior` **after** prediction, before current measurement update. Counterfactual semantic change, never relabel as historical MB_VAR.
- `BASE_FIXED` = precomputed base BB_ORIG joint NIS accept-mask `A_B`, threshold 9.210340371976184, same mask all arms.
- `SELF_NIS` = recompute gate using each arm's current `x,P,mu,R` and NIS, same threshold. Only BB_ORIG's `SELF_NIS` must equal `BASE_FIXED` (algorithmic check). Since `mu_B/mu_M` are archived packet-keyed estimates, **SELF_NIS is not fully online deployable**.
- Same state `[px,py,psi,b_g]`, `F,Q,Joseph covariance,wrap`, `z`, initial state and sensor controls, no changes to FFD or path. All the arms use their own updates; fixed-mask only externally frozen decisions.

## Frozen arms / comparisons

Full factorial `2 mean(mu_B,mu_M) × 3 variance(none,LEGACY,PRIOR) × 2 gate(BASE_FIXED,SELF_NIS) × 7 case × 4 gyro = 336 independent trajectory *executions*` (not independent experiments). Comparison unit `case,gyro,gate,var_semantic`.

For each fixed gate/semantic, denote metric (lower is better) `Y_{m,v}` with m=0/1 mu_B/mu_M and v=0/1 no extra sigma/extra sigma. Compute:
- mean-only `Y10−Y00`
- var-only `Y01−Y00`
- combined `Y11−Y00`
- incremental variance on corrected mean `Y11−Y10`
- incremental mean with variance `Y11−Y01`
- interaction `Y11−Y10−Y01+Y00`.

Repeat for Heading RMSE deg, XY RMSE cm. A gate effect is **paired `SELF_NIS−BASE_FIXED` at exactly the same mean/variance arm**, separate from the 2×2 decomposition. Self-gate itself can alter accepted packets and state recursively. Report accepted counts and mask flips.

## Technical gates (stop on any mismatch)
1. Input manifests record original bank SHA, control file SHA, original code SHA and full run source SHA; no silent missing files, extra packet mutation, or nonfinite result.
2. `BB_ORIG/BASE_FIXED`, `MB_ORIG/BASE_FIXED`, `BB_VAR_LEGACY/BASE_FIXED`, `MB_VAR_LEGACY/BASE_FIXED` states and covariance must match original `exp_pb.run` <=1e−10 absolute across entire trace; not rounded RMSE.
3. Archived B0/L2 BASE acceptance mask parity and BB_ORIG SELF_NIS mask parity (0 mismatches). No skipping failed conditions. `28×12=336` arms, `28×2×2=112` interaction rows, `28×6=168` gate contrasts.
4. Algorithmic factor identity `interaction = (Y11−Y10)−(Y01−Y00)` within 1e−9; paired baseline B00 identical across semantic types.
5. Early stop on zero rows, missing source, mismatch, corruption, unregistered cases, no-cache output handling. Preserve failed receipts, no scientific PASS when tests only show numerics.
6. Group conclusions by seven case families. B0/L0/L1/L2 and packet rows are repeated treatments, **not 28/1000+ independent RF draws**; no unwarranted p-values.

## RA4 handoff

**PROPOSER:** freeze matrix/estimands/source locks in this file, no outcome-dependent threshold changes.
**IMPLEMENTER:** new audit script/workflow and all arm results, run manifest and hashes; no writes under `results/**` or original `research/DS_MASK_CAUSAL_X1_X2_20261026/**`.
**AUDITOR:** independent recomputation of a random and adversarial case 2×2 contrasts, check source parity, verify negative fixtures, check masks and denominators. Same session => `SELF_REVIEW_ONLY`, no false independent signoff.

## G3 physical-risk boundary
RA4 is conditioned on **original archived H/packet**. Its retrospective causal *computational* effects are identifiable, but whether original H is physically accurate remains `BLOCKED_25_RAY_SOURCE`. A G3 checker-only change does not modify H; if a new physics/solver change is needed, freeze new H first and rerun only changed packet conditions with a separate amendment.
