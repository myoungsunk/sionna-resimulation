# RA5 P0-P3 non-RT engineering completion — 2026-10-30

**Status: TECHNICAL QA COMPLETE. Scientific approval and independent auditor: PENDING.** Original frozen H, RAW, SAMPLES, RA4, MBVAR-INFO contracts and prior research results unchanged; no RT solver used.

## Actual successful GitHub Actions

| Gate | Actual run | Source code commit | Result |
|---|---|---|---|
| P0 SourceFFD fractional observer/Jacobian, math/negative fixtures | [40994216940](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40994216940) | f94df162816b0ce602ebfacb3aa997ce108f436e | Success |
| P1 noisy first-tap conditional distribution | [41000128768](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41000128768) | b4e16ae333cb95a3296af67c25ace7d8616db04b | Success, 2/2 |
| P2 3x3 source-error covariance/Schur/LORO | [41003004315](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41003004315) | 551d8194fe6e29f12852cc99e84750cc5ecd0f6b | Success, 3/3 held routes |
| P3 prior-based SUB2/SUB3 fixed/self recursive EKF | [41003007124](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41003007124) | 6c5fcc8da5e1a6727a97d2ad047213e6a7907eaa | Success, R4B and R5A |

P2 artifact: https://github.com/myoungsunk/sionna-resimulation/actions/runs/41003004315/artifacts/12953489460
P3 R4B artifact: https://github.com/myoungsunk/sionna-resimulation/actions/runs/41003007124/artifacts/12954600758
P3 R5A artifact: https://github.com/myoungsunk/sionna-resimulation/actions/runs/41003007124/artifacts/12954435792

Source original archived H commit: 9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13. All seven original Full-H arrays, SAMPLES and 257-bin source frequency are SHA verified; all 7,251 timeline rows remain within one Corridor physical environment.

## Failures repaired and preserved

1. P1 original [40993838476](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40993838476): Python unmatched right parenthesis in tap switching output, fixed at b4e16ae333cb95a3296af67c25ace7d8616db04b; final run PASS.
2. P3 [40994444606](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40994444606): numpy.int64 JSON serialization failure after first new arm; fixed by 003f0096958db14a14ef98d33442ad9a1c15fc9b.
3. P3 [41000168328](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41000168328): four new-arm scores computed, but the historical BB_ORIG baseline summary omitted new-observer n_source_invalid counter and threw KeyError. Fixed at 6c5fcc8da5e1a6727a97d2ad047213e6a7907eaa by defaulting the historical baseline counter to zero ONLY in aggregated QA, not in arm logs.
4. P2 [41000484410](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41000484410): CSV writer did not account for heterogenous covariance and heldout summary row columns; fixed by union-of-keys at 551d8194fe6e29f12852cc99e84750cc5ecd0f6b.
All original failed logs and artifacts remain accessible. Separate unrelated powerjoint CI on every push is red; never declare the whole repository green.

## P0/P1/P2 technical and statistical results

P0 source fractional crossing and source Jacobian/negative fixtures PASS. Exact information basis transform max error 1.136868e-13. Structural duplicate covariance rejected before shrinkage.

P1: train 3072 complex CFR noise samples per case on one pose, test 3072 on another. R2A m45 weighted conditional Brier 0.132394 vs unconditional 0.150975 and conditional logloss 0.410807 vs 0.455249; R5A conditional Brier 0.133611 vs 0.141851 and conditional logloss 0.401197 vs 0.429299. Actual hardware distribution and online integration unvalidated.

P2: Full-minus-LoS deterministic residual R3 from two other routes, 15% shrinkage, offdiagonal covariance and positive rank/Schur tests PASS. Heldout empirical nominal 95%-interval coverage by tap-quality:
- R2 AMBIG: n796, Qmean 2.640, coverage 92.84%; STABLE: n2141, Qmean 2.608, 93.65%.
- R4 AMBIG: n440, Qmean 2.843, coverage 91.36%; STABLE: n1044, Qmean 2.936, 93.20%.
- R5 AMBIG: n762, Qmean 5.184, coverage 92.52%; STABLE: n2068, Qmean 4.144, coverage 95.41%.
Multiple strata under-cover 95%; covariance is not calibrated physical receiver noise and the observations are not iid.

## P3 actual recursive B0 results

Both cases: exact historical BB_ORIG full-state/P maximum numerical difference = 0; original BB acceptance mask exact. Full-H packet observer replay max range discrepancy R4 1.78e-15 m / R5 3.55e-15 m, signed polarization <=2.22e-16. Full negative basis/duplicate information controls PASS.

| Case | Arm | Heading RMSE deg | XY RMSE cm | XY 95% coverage | accepted packets |
|---|---|---:|---:|---:|---:|
| R4-B | SUB2 BASE_FIXED | 1.378705 | 27.9581 | 1.69% | 341/742 |
| R4-B | SUB3 BASE_FIXED | 1.094167 | 18.0674 | 3.55% | 335/742 |
| R4-B | SUB2 SELF_NIS | 1.425074 | 28.5147 | 0.34% | 347/742 |
| R4-B | SUB3 SELF_NIS | 1.210295 | 22.3196 | 0.00% | 323/742 |
| R5-A | SUB2 fixed and self | 1.996852 | 28.2998 | 6.09% | 671/1415 |
| R5-A | SUB3 fixed and self | 2.005026 | 27.6842 | 6.17% | 674/1415 |

Interpretation: R4 new tap correlates with lower RMSE, R5 heading slightly degrades despite XY small improvement. These are not paired exactly same acceptance masks; not proof of pure incremental tap information. Most crucial: XY NEES 15–30 and near-zero XY 95%-coverage demonstrate severe state-uncertainty inconsistency even though engineering parity PASS. No scientific release.

Tap-mismatch guards deliberately exclude very many observations:
- R4B SUB2 BASE_FIXED observed-vs-prior-LoS first tap mismatch 384 of 742; SUB3 388 of 742 plus one predicted branch-switch.
- R5A SUB2 BASE_FIXED 677 of 1415; SUB3 671 of 1415 plus two predicted branch-switch.
Do not silently relax or replace these observations. QA failed_source_model_updates summed across arms is not a count of unique packets. Repeated route and gyro observations are not independent scenes.

## Remaining science/physics gates

1. Separately validated mixture/categorical update for Full-vs-LoS first-path mismatch and a receiver-noise first-edge flip conditional distribution; the P1 switch model is not yet part of the EKF likelihood.
2. Calibrate stochastic receiver noise and scene-dependent RF model discrepancy separately; validate uncertainty and NIS/NEES/coverage with realistic antenna, clock, port, tap effects on independent scenes.
3. Check additional s1 information under matched prior AND identical observation masks, then full recursion and 4-state/5-state nuisance only if identifiable. Current SUB3 comparisons change update acceptance sets.
4. Independent auditor source-to-packet-to-K/P verification, FROZEN science contract, independent new RT/measurement TEST before publication-level generalization.
5. The original Corridor is one physical scene. Existing Office was already explored and is DEV, not a new blind TEST.

**Final verdict: P0_P1_P2_P3_ENGINEERING_PASS; PHYSICAL_EKF_UNCERTAINTY_FAILS_CALIBRATION; SCIENCE_RELEASE_SELF_REVIEW_ONLY; INDEPENDENT_AUDITOR_PENDING.**
