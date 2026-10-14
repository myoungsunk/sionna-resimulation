# RF Heading inversion H1-H4: execution contract

Frozen revision: e157c99c12377c69fc407514cb0337060e7b4e14.
Outputs isolated from the repository and parent-task output directories.
H1/H2: all 7 cases, paired original LoS/Full s, truth XY, t>=30s; RF geometry once (no seed replication).
H3: same Full s, RF-free D0 predicted XY/heading; noise_pair L1 and gyro_bias L0/L1/L2, seeds 0/1/2. Record prior-nearest selection and oracle-nearest separately. Truth NEVER selects the deployable result.
H4: archived M0/Huber/Cauchy A and C traces under the same four conditions, all 7 cases and 3 seeds, LoS B_OLD and Full B_OLD/E1. Original s, ranges, R0, gates, robust shapes, filter states remain unchanged.

Inverse: enumerate every segment of the original piecewise-linear periodic LUT at fixed XY. Include touching vertex roots, wrap boundary deduplication, and flat solution intervals. This is exact for the frozen interpolant, not for unknown underlying physics. Verify against original vectorized s_model at knots, midpoints and off-grid points with tolerance 1e-10. Refine each segment into halves and compare inverse results (angle tolerance 1e-8 deg). Numerical tolerances are not observation gates.
Band: |s_obs-h|<=1.96 sqrt(R_s), labelled nominal, not claimed calibrated. Record width, connected components, truth inclusion, unique/multiple/no exact roots and angular separations. Do not force no-root cases into a point estimate. All selected-point RMSEs report valid denominators.
Linear H3: residual at truth, position contribution, cross term, actual inverse error and approximation remainder; truth derivative is ORACLE_DIAGNOSTIC_ONLY. Also record derivatives at DR state. Small derivatives are recorded, never floored; invalid divisions remain undefined. Root selection equality with oracle is a descriptive wrong-root label, not certified branch continuation.
H4: reconstruct prior full covariance from the previous recorded posterior and frozen motion prediction; compare stored prior diagonals/state, NIS and Joseph posterior at unchanged 1e-8. Skip only the first stored sample per trace group because its predecessor is not saved. Gaussian/robust effective-R formulas retain their original meaning. Report original s-model ambiguity at estimated prior XY and nominal angle band, pre/post heading covariance, gain, gate, weights, error change, coverage. Scalar s-only information calculation is primary; Joint uses full block.

Stages: synthetic tests + native-model parity -> single-case noise/seed0 smoke -> all H1/H2/H3/H4 -> aggregation + receipt.
No parameter tuning, new RF generation, online oracle injection, parent process interaction, repository edits or Git publication. scientific_PASS=false.
