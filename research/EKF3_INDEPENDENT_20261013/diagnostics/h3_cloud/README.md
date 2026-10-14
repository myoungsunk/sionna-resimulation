# G3 staged GitHub cloud validation

Source: research/ekf3-independent-p0-20261013 at 32ee990b0d9dfc3bf3010e5ccabf404fa9d3aa20.
Work branch: research/g3-cloud-staged-20261014.

## Freeze policy
Use published RF H, LUT, P0 sensor/motion generator, original R0 Range/S covariances
and archived Stage4 numerical gates without modification. Do not alter the
original failed outputs. All new files reside in h3_cloud/ or are clearly
named separate diagnostic/CI files. No scientific PASS based on GH smoke.

## Stage 1: cloud reproduction
The GitHub Actions workflow performs a sparse checkout (no Windows cache),
recreates DR prior for R2_aA_m0 / gyro_bias L2 / seed 0 / LoS B_OLD /
sample 978, and independently checks D0 aggregate RMSE and original G0 MAP.
Then it repeats GH41/65 on 1,440 Heading bins for JOINT, S-only and
Range-only likelihoods. Outputs include numerical TV/log evidence,
original Range NIS gate, source commit and input hashes.

Pre-registered hypotheses:
H0 - original G3 TV 0.38706501555739936 is reproduced (tolerance 0.005).
H1 - Range-only unstable and S-only stable at 41->65 under TV=0.001.
H2 - Range NIS gate rejects this sample.

If any hypothesis contradicts evidence, an additional GH25 experiment
measures evidence/TV drift and the job fails closed. No automatic change
of thresholds, models or geometry and no speculative Phase2 rollout.
The report separates confirmed, contradicted and unresolved findings.

## Further stages / strict dependency
Phase2: independent position integral reference; it cannot be PASS before
Phase1 source/G0 parity and documented hypothesis audit.
Phase3: GH/reference TV <=0.001, MAP delta <=0.1 deg, HPD delta <=1 deg;
independent synthetic Gaussian and joint-vs-conditional factor tests.
Phase4: paired G0/G1/G2H/G2X/G3 and gate-matched G3, R0 LoS/Full.
Phase5: full 3-state posteriors and recursive position/Heading/covariance.

Later stages are intentionally NOT_IMPLEMENTED in this initial commit.
A cloud workflow start is not proof that a run passed. Read the artifacts
and receipt before allowing the next implementation stage.

Stage 1 Actions artifacts:
- STAGE1_REPORT.json
- STAGE1_DIAGNOSTIC.csv
- joint_posterior.npz, s_only_posterior.npz, range_only_posterior.npz

The original research branch and input assets are read-only. Stop after
the final validated stage, or after one bounded follow-up analysis for a
contradicted hypothesis, with explicit confirmed/unconfirmed results.
