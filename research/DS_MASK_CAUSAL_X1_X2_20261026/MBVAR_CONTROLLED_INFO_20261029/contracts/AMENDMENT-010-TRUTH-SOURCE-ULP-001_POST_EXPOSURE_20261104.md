# MBVAR-INFO-001 — A010 C3V5 TRUTH-SOURCE-ULP-001 (post-exposure exploratory correction)

**Decision date:** 2026-11-04 · **Role:** USER_AUTHORIZED_NONINDEPENDENT / PROPOSER-IMPLEMENTER  
**Contract status:** revision to the operational A010 code lock PENDING hash validation. **Do not execute DEV3 C3V5** before the exact corrected 49-file source hash set is applied. **Original S1V5 DEV3 and A010 FROZEN source contract remain preserved.**

## Exact triggering original evidence

- Original DEV3 S1: GitHub Actions [#41769652106](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41769652106), source SHA `0bd5d706710f172ff6becb562eadd7573b5d3ffd`, 1,980/1,980 S1 all-arm rows; original source artifact ID 13296915471, outer ZIP SHA `c5625668e1dcd00852fa3661b06b2e3ffafde236bb3424efa36def5846985481`.
- Original C3: [#41780677692](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41780677692), guard and S1 original artifact acceptance PASS, but multiple C3 shards stop with `ERR_A010_TRUTH_ONLY_REPLAY`. This is a **pre-science byte-identity gate failure**, not a science hypothesis FAIL. Original failure artifacts must remain accessible.
- Separate read-only [#41781114661](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41781114661) compared 768 saved vs regenerated truth array slots: 648 exact, 120 differing, sampled fields {20,22,27,29}, components {Xtrue,poses,ds_true,dth_true}, worst max |Δ|=8.881784197001252e−16. Other fields may behave differently on other CPUs. No full 1,080-row inference has been obtained.

## Scope of correction, fully separated from science rules

1. **Original S1 source SHA is authoritative.** Both the GitHub Actions artifact outer SHA and S1 `MANIFEST.json` + original 49-file source-code hashes and every receipt ZIP/array index must be verified. The C3 patched source code hash must **not** be substituted for S1 source code hash.
2. **No new truth generation for scoring.** Use the exact previously stored S1 `TRUTH|field|role|cell|Xtrue,poses,dts,ds_true,dth_true,prior_P0,mu,pose_keys_sha` arrays, copies only. Never modify S1 archives. Refuse missing/corrupt/mixed-field/cell/role source files.
3. Independently regenerate geometry for **diagnostic only**. For numerical float64 deterministic geometry Xtrue/poses/ds_true/dth_true, report raw SHA mismatch and maximum absolute difference; reject if difference > **32×float64 machine epsilon×max(1, max|regenerated|, max|original|)**. This factor is explicitly selected **after the DEV3 failures were inspected**, for a limited engineering portability diagnostic; it is NOT a new G5 or scientific tolerance and does not permit confirming historical failures. All other truth inputs (dts/prior_P0/mu/pose_keys_sha) require byte-exact reconstruction.
4. **The optimizer input contract is immutable:** every row's exact `z,x0,ds_m,gy_m,Sigma_model,dts,taps` is rehashed/attested before and after E′ and each diagnostic solve. Operating estimator `s1v5.py` is unchanged; `c3v5.py` is the sole scientific-code change. Rejected rows and all seed/arm/field keys remain in the denominator.
5. Keep old `c3v5.py` numeric/solver G5 tolerances, previous failures, F2 cost threshold, 9 truth-free starts + E′, full C10/SPD/NEES, 62 registered H/CAL contrasts and the field-bootstrap B=4000/seed=20261029. Never assert global/unique MAP.
6. **Exploratory-only after exposure.** C3 source correction occurs after the DEV3 source truth was opened and can only be labeled `POST_EXPOSURE_USER_AUTHORIZED_NONINDEPENDENT_EXPLORATORY`. It is not independent confirmatory science or an externally audited release.
7. After a new immutable post-correction 49-file code SHA lock is applied, first run positive/negative fixtures and 1–2 original source C3 key canaries. Only then rerun the exact 20 field groups = 1,080 Batch rows + 10,800 terminal candidate records. Report G5, precision, ambiguity and H/CAL verdicts separately.

## Required tests before moving to all DEV3

- [ ] Signed source lock contains exactly the original `MANIFEST.source_git_sha=0bd5d706...` and original `source_code_sha256` 49-file map. Wrong S1 source SHA, tampered original ZIP or array → STOP.
- [ ] Saved `Xtrue`, `poses`, `ds_true`, `dth_true` within ULP diagnostic bounds → use original saved truth for scoring; record per-key/difference SHA; exact solver input arrays unaffected.
- [ ] Missing original truth, altered dtype/shape, nonfinite, non-geometry modification, wrong field/role/cell, larger numerical mismatch → STOP.
- [ ] Exactly same 49-file corrected Python hashes in current effective lock; corrected lock appended, not overwriting original frozen amendment or historical failures.
- [ ] Small 1–2 original DEV3 key canary PASS + 2 runners / exact source receipt duplicate and C10/NEES parity evidence before 1,080 Batch launch.
- [ ] Historical `STATE_STABILITY_FIXED_LEGACY` FAIL, new G5 FAIL and all log/manifest evidence never silently relabeled PASS.
- [ ] HOLDOUT2, reserve, P3 Sionna RT are independent tracks and remain unsealed / not executed here.

**Technical contract verdict:** `AMENDMENT_POST_EXPOSURE_PENDING_CODE_HASH_LOCK`; `S1_ORIGINAL_PRESERVED`; `C3_1080_REPLAY_NOT_CERTIFIED`; `RT_SCOPED_SEPARATELY`.
