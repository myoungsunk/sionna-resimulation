# A4 executed first-packet causal probe (2026-10-29)

## Provenance and execution
- [A4 selected-case + shadow 2x2 GitHub Actions #40870656667](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40870656667) — completed/success.
- [CSV, JSON and execution log artifact](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40870656667/artifacts/12895094092).
- Three B0 selected cases R5_aA_m0, R4_aB_m0, R2_aA_m45; 6 full-length MB_VAR_LEGACY/PRIOR fixed vs self gate comparisons; 42 identity fixture comparisons in first 60 packets and 12 sensor bias-only checks passed.
- Original RA4 336-arm full retrospective: #40859507594. Original H/packet/results unchanged.

## First divergence: same MB_VAR intervention, different gate
| Case (B0, LEGACY) | First difference | Accepted fixed / self | Head RMSE fixed / self | XY cm fixed / self |
|---|---|---:|---:|---:|
| R5_aA_m0 | k=217, 43.4s | 1349 / 1396 | 3.832590 / 8.886222 | 39.59727 / 87.74529 |
| R4_aB_m0 | k=14, 2.8s | 726 / 735 | 1.391430 / 1.431222 | 8.86543 / 9.43255 |
| R2_aA_m45 | k=37, 7.4s | 940 / 967 | 1.855649 / 1.435679 | 16.70369 / 14.61961 |

In all three pairs, before the **first** acceptance-mask difference, x-prior and P-prior were exactly equal, as were current mu, sigma and R for the paired MB_VAR fixed/self policies. BASE_FIXED rejects, SELF_NIS accepts at first flip. This establishes first recursive branch arose at gate decision; does NOT identify causal share of eventual RMSE or label accepted packets as physically bad.

## SAME PRIOR local 2x2 NIS (at first MB_VAR gate flip)
NIS threshold 9.210340371976184, same predicted prior from MB_VAR_FIXED for all four shadow alternatives. Note these are **not the four arms' historical independent recursive priors**.

| Case | NIS BB_ORIG | NIS MB_ORIG | NIS BB_VAR | NIS MB_VAR | Which intervention crosses threshold alone? |
|---|---:|---:|---:|---:|---|
| R5_aA_m0 | 30.0125 | 7.5569 | 27.0092 | 4.5385 | **mean-only** passes, variance-only does not |
| R4_aB_m0 | 12.3587 | 10.1524 | 5.5228 | 3.4681 | **variance-only** passes, mean-only does not |
| R2_aA_m45 | 14.8250 | 8.0359 | 11.5857 | 4.6720 | **mean-only** passes, variance-only does not |

This disproves the overly simple causal narrative “variance inflation alone admits every extra packet.” The first gate-crossing mechanism depends on case: μ_M shifts NIS enough in R5-A and R2-A m45; R_ss inflation does so in R4-B. Combined MB_VAR always passes for these three first flips.

For R5-A, first flip details: previous-posterior range 5.83167m, current-prior range 5.87175m, sigma_LEGACY 0.116072, R_ss 0.02846468, innovation (r,s)=(+0.105845,+0.310097), self NIS 4.53853 vs threshold 9.21034; BB_ORIG shadow NIS 30.0125. Initial state/P equal before k217. Later 47 additional accepted packet decisions and feedback accompany final deterioration, but are not a unique additive attribution.

## Prior vs legacy timing
First sigma-only semantic difference occurs at packet k=1 in each of the three cases; predicted prior x/P exactly equal at first difference and R_ss and posterior x/P then diverge. Example R5-A σlegacy=0.0471930075 vs σprior=0.0464409348, R_ss legacy=0.00523259 vs prior=0.00516217, first posterior max state difference 9.52e-5 and P difference 1.21e-5 (mixed state units; do not label as distance). Under BASE_FIXED, selected three cases show zero mask differences between LEGACY and PRIOR, but RMSE values differ. The original MB_VAR is LEGACY, not PRIOR.

## Identity/initialization limits
- σ=0 VAR→ORIG and μ_M=μ_B same-arm identity fixtures PASS for three selected 60-packet prefixes; this is not a 28-condition full-length invariant sweep.
- With fixed seed=0 and controlled sensor-v2 parameters, B0/L0/L1/L2 controls were verified to differ by specified gyro-bias increment alone in three selected cases; identical initial pose/noise streams. This is not a multi-seed initial XY/Heading/noise factorial.
- Full controlled XY initialization, heading initialization, gyro-bias, wheel/gyro noise, Q, and time correlation factorial remains NOT_RUN. Single first-flip trace does not prove which changes are harmful/beneficial across all 28 conditions.

## Next experiment priority
1. First-flip causal counterfactual: at k217 R5-A, force accept/reject only this packet and then follow otherwise identical SELF_NIS policy; separately hold all base masks. Record full packet-by-packet x/P, innovations, gain, NIS and masks. Do not infer attribution additivity from this one toggle.
2. Repeat first-flip shadow mean×variance at all 28 condition/arm policies, especially R5-B counterexample and all no-improvement cases; check full source parity and exact same R/μ exception ledger.
3. Factorial initial XY/Heading/gyro bias and wheel/gyro noise using independent RNG streams; control x0/P0/Q, no truth leakage, stratified repeated seeds.
4. Inform RA5 nuisance-field vs temporal and J×Σ hypotheses only after these technical checks. Maintain SELF_REVIEW_ONLY, no scientific release.
