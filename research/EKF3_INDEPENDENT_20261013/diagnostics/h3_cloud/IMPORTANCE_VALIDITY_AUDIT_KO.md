# G3 Range-aware importance numerical validity audit — 2026-10-14

## Final verdict

**NOT_VALIDATED_AT_PREREGISTERED_BUDGET / FAIL_CLOSED.**

- The proposed **current implementation** (Range-likelihood-truncated-radial proposal + S/prior-adaptive azimuth + randomized Sobol importance) is **not a reliable numerical reference** for the single frozen G3 failure case.
- This does **not** prove that all adaptive importance samplers are unsuitable. The present proposal ignores the XY prior when drawing radial samples, creating a severe overlap problem.
- No G2/G3 method ranking, inference performance comparison, retrospective threshold relaxation or recursive fusion was carried out.
- scientific_PASS=false. No further experiments were automatically launched.

## Immutable provenance

- Repository: myoungsunk/sionna-resimulation
- Evaluation branch: research/g3-range-aware-qmc-audit-20261014
- Validation code commit: b29a98136046a9b15d975b0fe97cdbe620d16065
- Base commit: 10d138c787aa5f0a0b3933a03c0be5651df6fa9f
- GitHub Actions run: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38515429481
- Original frozen H3 source: 32ee990b0d9dfc3bf3010e5ccabf404fa9d3aa20
- Archived evidence ZIP: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38515429481/artifacts/11871726353
- The audit commit adds only h3_qmc_validity.py and h3-g3-importance-validity.yml. No original RF H, LUT, sensor generator, DR, gate, or R0 matrix was changed.

## Frozen case

R2_aA_m0 / gyro_bias L2 / seed 0 / LoS / B_OLD / sample 978 / t=195.6 s.

- DR prior mean: (3.7012827074 m, -6.0181823400 m, -2.4914201759 rad)
- Reference Anchor XY: (4 m, 0 m), vertical separation: 2.2 m.
- Frozen corrected Range: 3.6721958255 m, Rr=0.0068578637 m², sigma_r=0.0828122195 m.
- DR-mean predicted Range: 6.4146512530 m.
- Residual: -2.7424554275 m = -33.1166 sigma_r.
- Original Range innovation covariance H P H^T + Rr ≈ 0.0670389863 m².
- Computed Range NIS ≈ 112.18937; far above frozen NIS gate 6.6348966, which rejects the observation.
- Conditional p(XY|psi) covariance eigenvalues: 0.01068385, 0.01166421 m²; std approximately 0.1034 and 0.1080 m.
- The observed-Range horizontal ring radius is approximately 2.94024 m; the horizontal radius at the DR mean is 6.02559 m (difference ~3.08535 m).

## Pre-registered algorithm and acceptance

For each of 1440 Heading-grid points:
1. The radial proposal is proportional to the frozen Range likelihood for physical slant range >=2.2 m. It is sampled by exact truncated-normal inversion.
2. A 512-bin, full-support azimuth proposal is adapted from the frozen S likelihood and p(XY|psi) evaluated at seven pilot radial quantiles, mixing in a 10% uniform floor.
3. Randomized scrambled 2-D Sobol point sets with independent seeds 1069 and 2099, and up to 65536 samples, use the exact corresponding proposal densities in importance weights.
4. A separate deterministic uniform-azimuth / Gauss–Legendre radial quadrature uses the same exact truncated-Range variable substitution but **does not** use the Sobol points or azimuth pilot proposal.

The importance identity is w = sqrt(2*pi)*sigma_r*Z * r * p(XY|psi) * L_s / q(alpha|psi).
Normalizing factors independent of psi are irrelevant for posterior shape. No duplicate Range factor.
A synthetic isotropic Gaussian × Range + known multimodal azimuth factor with an independently evaluated radial integral is used to audit importance Jacobian/weights.

Acceptance required both separate scrambles and the converged independent numerical reference to agree in posterior TV <= 0.001, relative evidence <= 0.005, and posterior-weighted ESS/N >= 0.05, without changing the numerical thresholds.

## Observed results (actual GitHub Actions run)

| Numerical comparison | Value | Decision |
| --- | ---: | --- |
| Synthetic importance identity seed 1069 relative error | 1.29555e-5 | PASS |
| Synthetic importance identity seed 2099 relative error | 2.56190e-5 | PASS |
| Deterministic polar reference 1024×12 -> 2048×20 TV | 0.02444822 | FAIL |
| Deterministic polar reference 2048×20 -> 4096×28 TV | 0.01516879 | FAIL |
| Deterministic reference log evidence: three levels | -295.85506 -> -290.01782 -> -286.56175 | Non-convergent |
| RQMC at n=16384: independent scramble posterior TV | 0.81096132 | FAIL |
| RQMC at n=65536: independent scramble posterior TV | 0.62874648 | FAIL |
| RQMC n=65536 vs deterministic highest reference TV, seed 1069 | 0.14114989 | FAIL |
| RQMC n=65536 vs deterministic highest reference TV, seed 2099 | 0.69096482 | FAIL |
| RQMC n=65536 posterior-weighted ESS fraction, seed 1069 | 1.54163e-5 | FAIL |
| RQMC n=65536 posterior-weighted ESS fraction, seed 2099 | 1.76395e-5 | FAIL |

At n=65536 the ESS fractions correspond to roughly 1.01 and 1.16 effective samples per posterior-weighted average. Posterior estimates depend on rare high-weight draws. Larger sample count produced neither sample-independent agreement nor convergence to the reference.

The deterministic reference does not pass, so it cannot be adopted as a ground-truth posterior either. Its evidence drifts dramatically with increased radial/azimuth resolution, consistent with integrand peaks being missed. We cannot assign the discrepancy solely to azimuth resolution or solely to radial tails from these runs.

## Source-level audit and interpretation

- Frozen source, parameters and selected RF-input SHA values in VALIDITY_AUDIT.json were carried through; the Phase-1 cloud reproduction and G0 parity had already passed.
- Synthetic identity PASS supports the implemented Jacobian and density-ratio algebra **in that controlled case**, not the adequacy of the real-case proposal.
- The prior is concentrated around a predicted slant range ≈6.415 m, but q_r draws around 3.672 m with sigma≈0.083 m. The relevant posterior-overlap region may be many sigma away from the radial proposal center. This is a strong mechanism for the observed ESS≈1, but its exact multimodal structure is not yet proven.
- The azimuth proposal is adaptive, but the **radial proposal is not adapted jointly to prior × Range × S**; calling this implementation adequate adaptive importance integration would be misleading.
- Deterministic radial quadrature was also performed in the Range-likelihood measure, explaining why this alternative can share a failure mode even though the azimuth/quadrature algorithms are different.

## Confirmed / unconfirmed

**Confirmed**: GitHub cloud execution, original RF/preflight input recreation, synthetic weight identity, observed non-convergence at pre-registered budget, extreme prior–Range disagreement, low effective sample size.

**Not confirmed**: true G3 Heading posterior, whether full posterior-adaptive / defensive mixture importance works, correctness across LoS/Full or other gyro-bias cells, G2/G3 performance differences, recurrence and covariance calibration.

## Disposition

**STOP after this validity audit**, as requested. A possible *new* hypothesis for a separately approved investigation is to construct a defensive, multi-component proposal covering p(XY|psi), the Range likelihood, and conditional posterior overlap, with independent bridge/SMC or numerical reference checks. This follow-up is **not implemented, executed, approved, or claimed PASS** here.
