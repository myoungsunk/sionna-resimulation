# FP-SC — S3 posthoc accuracy and S1/S2 alignment hardening

## Status

- **BASE:** \`e4930310987ca89c4ce7d71f33f1a7e3d799fddf\`
- **PROPOSED CHANGE:** S3-only code path and synthetic tests. No S1/S2 RF data, decisions or score coefficients were changed.
- **SCIENCE:** \`S3_NOT_RUN / E1_02_NOT_RUN / E2_NOT_RUN\`.
- **QA:** [GitHub Actions #42181727977](https://github.com/myoungsunk/sionna-resimulation/actions/runs/42181727977) synthetic/syntax PASS, 95 tests across 7 suites, including prior selector-reach and protected-integrity regressions. This does NOT constitute scientific accuracy acceptance.

## Why an S3 patch rather than executing the existing S3

The previous S3 update already persisted F00/F10/F01/F11's \`x,P,K,innovation,S,nis,accepted\` and original \`prior,Pprior,h,H,mu,R,mask\`. Two remaining **interpretability and integrity gaps**:

1. The S3 runner checked SHA-locked S1/S2 artifacts but did **not verify the S1 decision and S2 evaluated decision matched for every (k,mode)** before applying the frozen S1 observation in a single EKF update.
2. Saved updated states enabled arithmetic examination but **did not provide a ground-truth-labeled, per-packet change in Heading/XY absolute one-step error**. Merely reporting \`Δψ = KΔz\` is not evidence that the posterior is closer to truth.

## New S3-only checks

- \`crosscheck_s1_s2_for_s3(case,S1,S2)\`: requires all 4 mode rows per packet, unique packet-mode identity, same case/time/pose from S1, same raw and selected tap and changed flag in S2, correct source scopes. Rejects mismatch before S3 fixed update.
- \`same_prior_shadow_one_step()\`: **unchanged**, still uses frozen W0 \`prior,Pprior,h,H,muMB,Reff,mask\` with all four observations. No own-gate recalculation, covariance respecification, learned selection confidence, or recursive filtering.
- S3 runner first serializes \`ROWS.json.gz\`; only **after** that does it read \`evaluator.npz\` truth with exact time/pose join. \`posthoc_s3_one_step_errors()\` writes \`POSTHOC_ONE_STEP_ACCURACY.json.gz\` and SHA to the receipt.
- For each valid posterior and F00/F10/F01/F11, store **signed heading error, absolute Heading error, XY norm error, heading std, XY covariance trace, differences versus F00**. A rejected frozen mask must yield no fictitious state improvement.
- For 3-column truth, gyro bias and 4D NEES **NOT_TESTED**, never filled with 0.
- This is *same-prior per-packet* diagnosis; do not call it EKF recursion, or proof of improved Heading RMSE over trajectories.

## What S1/S2 have actually shown

Original S1/S2 results remain fixed under \`d1d2ee5\`, \`3a06799\`, \`e493031\`. Full: 1,003 wrong FP; 1,000 had eligible reference and built score, 3 had HOLD_HISTORY. Among 1,000:
- 886 raw had \`p=m=0\` so a wrong FP was inside both intervals;
- 965 had \`J_raw<2\`;
- reference was rank1 in only 88, other 912 had better-scored wrong candidates.
- The six PM changes: 0 exact restore, 2 closer, 2 equal-distance, 1 farther among five wrong inputs, plus one correct→wrong. Only 2/6 polarization absolute errors improved.
- Six changes have real eligible reference; correct reference was disfavored by previous wrong raw M and lower RF q versus selected candidate.

## Why the score needs scientific revision

Existing \`J=.7(-ln q)+max(p,m)^2\`, with \`q\` from lobe prominence/left-rise and relative tap amplitude, is **not** a first-path likelihood. q measures current signal strength/visibility and can favor a later strong reflection over a weak earlier direct component. P/M penalties are zero everywhere inside comparatively broad intervals; 4cm motion is not an independent state-error certificate. Wrong previous raw automatically shifts M. \`max(p,m)\` is a pessimistic penalty for either source disagreement, not Bayesian fusion of independent likelihoods.

The \`J_raw>=2\` and \`gain>=.8\`, \`margin>=.5\` gates were deliberately **NOT** modified in this S3 patch. Lowering thresholds alone cannot reverse an incorrect candidate ranking. Before a new selector version, run frozen-score causal decompositions and evaluate alternate first-arrival evidence/robust M and P source-specific abstention in a **new** predeclared development study.

### Suggested next contract (not implemented here)

- Raw misdetection and candidate ranking as distinct objectives; enumerate all source reasons.
- Compare \`q\` versus a physically motivated early-arrival/CFAR/noise evidence and temporal transition evidence.
- Compare P trusted / M trusted / P-M disagreement/abstain; inject intentionally wrong prior/history (as separate stress, not observed frequency).
- Preserve all old errors and normal-FP protection; evaluate normal→wrong, wrong→correct, wrong→closer, wrong→farther separately; F01/F11 consequences.
- R2 development only for new fit, R4/R5 as **already exposed** confirmations, not truly untouched holdouts.
- No posthoc numerical pass criterion, no source/GT in online feature extraction, no declared VALID provider without independent evidence.

The S3 patch is for **future diagnostics only**. Given current S2 failure, do not issue automatic S3 approval; require a separate user decision after reviewing the failed PM policy.
