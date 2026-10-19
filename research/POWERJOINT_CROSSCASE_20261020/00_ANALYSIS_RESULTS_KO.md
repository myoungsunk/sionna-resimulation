# POWER_JOINT cross-route Heading harm / physical ambiguity / corrected RF memory — 2026-10-20

**Scope:** Existing frozen R2/R4/R5 7 valid Full/DirectLoS cases + NEW six C01–03, O01–03 M45 release cases. Main methods Joint4 and POWER1. No new EM scene simulations. Evaluation includes offline causal RF-skip replays (NOT online policies). One existing corridor physical scene + one Office physical scene; multiple routes ≠ independent scenes.

## A. Existing 30 RF-skip events, consistent after-30-second score

30 events based on preregistered contiguous x-bins and visit index. `improvement = RMSE(original posterior full RF) − RMSE(only event RF skipped; subsequent original POWER1)`, measured on a common 30-second post-event horizon (positive is skip beneficial).

- R5 A M0 x10–16 V1: +7.751deg (first visit antenna-relative heading ~−177deg, |s_LOS|>.95 100%, weak slope |H_sψ|<.2 rad^-1 39.3%).
- R5 A M0 x10–16 V2: −1.025deg (revisit antenna-relative heading ~0deg, |s_LOS|>.95 0%, weak slope 0%). Therefore same x-region, different visit, opposite causal effect.
- R5 B M0 x10–16 V1 +.829deg, R5 B x1–4 V1 +.422deg.
- R2 A M45 x10–16 V1 −2.439deg, V2 +.314deg; R2 A M45 x16–20 V1 +.360deg.
- R2 A M0 x10–16 V1 +.346deg.
- 6/30 events have >.2deg and >15% relative improvement; 2/30 >.5deg.
- Physical event Spearman associations across 30 are weak, max absolute rho approx .240. Underlying repeated time/positions share a corridor and should NOT receive naive independent-event p-values.

## B. Physical weak Heading + ambiguity definition and falsification

**Weak Local Heading slope** is |partial h_s(x,y,ψ)/partial ψ|<0.2 rad^-1, a preregistered descriptive threshold (NOT independently validated sensitivity danger cutoff). **Near-extremum LoS s** is |s_LOS|>0.95 (bounded polarization ratio near ±1). At fixed GT-XY, **multi-root** is >=2 numerically verified roots in true yaw ±45deg of `h_s(ψ) − [s_full−μ_s −(C_rs/V_r)(r_full−μ_r−h_r(GT))]`; grid 1deg and bisection, residual<1e−5. This conditional inverse diagnostic is not an actual full-state EKF posterior or an online feature.

Sample 483 points in 11 frozen route/visit events (one in every four saved RF frames):
- R5 A M0 x10–16 V1: 35/38 (92.1%) multi-root, 39.5% weak-slope, 100% near-extremum; skip +7.751deg.
- R5 A same region V2: **27/38 (71.1%) multi-root but skip −1.025deg**, no local weak/near-extremum. **Multiple roots alone is NOT sufficient** for harmful RF.
- R5 B V1: 21/38 (55.3%) roots, skip +.829deg.
- R2 A M0 V1: 31/38 (81.6%) roots, skip +.346deg (weak 50%, near extremum 97.4%); not sufficient for R5-scale harm.
- R2 A M45 x10–16 V1: 0/38 roots, skip −2.439deg. 
- R4 A/B M0 x10–16: ~15–17% roots, skip harmful (−.965/−1.615deg).
**Root cause conclusion:** low LoS slope/s saturation/multiple roots are R5-like vulnerability conditions but **not a sufficient or unique causal mechanism**. Need additionally account for signed Full−LoS contamination, update gain, gate, and prior/bias.

## C. Corrected 6-state RF time-memory model re-executed across all available valid cases

Fixed observation equation `ν = z − h(x) − μ_POWER(q) − β`, beta included both in observation mean and Jacobian. Offline train-route-only rho (do not equate observed ACF to rho), total measurement variance partitioned to avoid double counting. Five arms: POWER1, MEMORY_RHO0, MEMORY_2D_RHO_TRAIN, MEMORY_S_ONLY, MEMORY_R_ONLY. 11 case×bias B0/L2 sets; MEMORY_RHO0 reproduces POWER1 with ~1e−14 state and zero gate mismatch.

**B0** (Heading RMSE deg, 95% nominal coverage):
| Case | POWER1 | MEMORY_2D | Interpretation |
|---|---|---|---|
| R2 A M0 | 1.799/68.6% | 3.023/77.2% | worse accuracy |
| R2 A M45 | .983/63.6% | .857/92.4% | improves both |
| R2 B M0 | 1.516/64.8% | 1.105/96.1% | improves RMSE but nominal coverage high |
| R4 A M0 | .659/46.8% | 1.040/75.2% | worsens accuracy |
| R4 B M0 | 1.508/13.2% | 1.325/47.0% | RMSE improves but still overconfident |
| R5 A M0 | 4.556/39.7% | 7.630/16.1% | worsens BOTH |
| R5 B M0 | 1.056/97.2% | .819/100% | RMSE improves, 100% potentially overwide |

**L2** selected: R2 A M0 1.559→2.957 worse; R2 A M45 .942→.768 better and coverage 64.7→95.4%; R5 A M0 4.790→7.940 worse; R5 B M0 .695→.809 worse.
**Conclusion:** direction/mount matters, but anchor/route/quality matter too. B0 4/7 cases improve RMSE, 3/7 worsen. Time-memory model is a **conditional research candidate** not a globally approved solution.

Orientation bins from observable pose+known anchor, NOT independent intervention: R2 A M45 front+0.154deg, side+0.239deg memory RMSE benefit; back −0.050deg; R2 A M0 memory bad across all angle bins; R5 A M0 bad across all bins. Thus "mount45 universally benefits" is false.

## D. NEW original RF releases C01–03, O01–03 acquired and physically verified (M45)

GitHub releases `route-rf-c01-20261019-r01`, `...c02...`, `...c03...`, `...o01...`, `...o02...`, `...o03...`; full immutable source/QA: [Actions run 39277485012](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39277485012), 6 successful matrix jobs. Nine actual Anchor cases 2647 radio poses (C01 A/B 242 each; C02 A/B 253 each; C03 A/B 423 each; Office O01 192, O02 207, O03 412). SourceFFD direct LoS vs actual direct H polarization s RMSE ~4.6e−7 to 7.4e−7 in valid LoS frames, first-path observer parity excellent. O03 direct LoS only 176/412, blocked samples are masked and **not assigned invented LoS**.

**New RF native with synthetic sensor B0** (0.25s motion, radio original 1Hz moving + sub-second yaw; not equivalent to old 5Hz route) POWER1 Heading RMSE/95%:
C01 A 3.966deg/.392; C01 B 5.028deg/.198; C02 A 2.236deg/.529; C02 B 1.221deg/.745; C03 A .610deg/.983; C03 B .801deg/.431; O01 .456deg/.927; O02 2.220deg/.401; O03 6.868deg/.448. Main Joint4 and DR4 baselines preserved. Not validated across independent motion noise seeds, not direct comparability to original Sensor-v2 source.

47 preregistered geometry-bin contiguous local RF-skip post effects:
- C01 A M45 x16–21 V1 +5.393deg; **s Full−LoS RMS .506, FP mismatch .902, MP/LoS .654, weak-slope fraction only .098**, different from R5A low-slope/near-extremum signature.
- C01 B M45 x16–21 V1 +4.340deg; FP mismatch1.0, MP/LoS .018; detector / phase vs simple power ratio issue candidate.
- O03 O0 M45 y4–8 V1 +1.798deg, **90% direct-LoS blocked**; not near-LoS extrema cause.
- C02 A M45 x4–10 V1 +1.775deg, weak-slope fraction 0 / s residual RMS .118 / MP/LoS .004.
- C03 A M45 x1–4 V1 +.767deg, weak0 and near-zero Full−LoS s residual RMS .003; **possible estimator/model/prior harm without large multipath**, not evidence for same physical root.
- C03 B M45 x10–16 V1 +.610deg, V2 +.537deg, small s residual .023.
Strong counterexamples: O03 y4–8 V2 −15.347deg and y0–4 V2 −14.462deg skip harmful, O02 y4–8 V1 −4.330deg, C03 A x4–10 V1 −3.115deg, C01 A x10–16 V1 −3.079deg.
**No single physical cause across all improved events.** Could share a broader failure in filter interpretation/gain/prior but not proven.

## E. R4/R5 new M45 regenerated

GitHub releases [R4 regenerated](https://github.com/myoungsunk/sionna-resimulation/releases/tag/legacy-rf-r4-20261019-r02) and [R5 regenerated](https://github.com/myoungsunk/sionna-resimulation/releases/tag/legacy-rf-r5-20261019-r02). Original catalog Full/Direct-LoS, raw paths, Sionna source, **T10 first-visit mapping**; FULL RF sequence not identical to Tnone/T10 full repeated trajectory. Snapshot workflow [Actions run 39279851027](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39279851027) extracts source/mapping; scientific time-alignment must be audited before treating them as normal continuous recursive controls. Cannot claim M45 regenerated R4/R5 EKF results until pose/time binding certified.

## F. scientific status

- CONFIRMED within existing sources: new valid RF Full/LoS; time-memory corrected replay parity and heterogeneous efficacy; old30 and new47 local ablations; conditional multi-root definition and counterexamples.
- SUPPORTED_BUT_LIMITED: R5 A first x10–16 RF updates cause later heading degradation, but different events can arise from other mechanisms; physical near-extremum and weak slope related but non-sufficient.
- NOT ESTABLISHED: one universally causal physics metric to gate Full RF; calibrated Bayesian posterior; multi-scene generalization; real hardware deployment; regenerated R4/R5 M45 timeline EKF parity.
- Next discriminator: at each "helpful skip" event, (1) first harmful RF update, (2) signed r/s innovation and Kψrνr/Kψsνs, (3) firstpath/LoS existence and path group, (4) prior error and covariance, (5) same episode range-only/s-only and state-vs-cov crossover. Test separate mechanisms rather than enforcing a shared single root.

**Full reproducibility:** Local numerical output files and replay scripts are saved under `/mnt/data/POWERJOINT_CROSSCASE_HEADING_CAUSES_20261020`, newest released RF original sources under release tags and Actions run; code GitHub branch `research/powerjoint-crosscase-mechanism-20261020`.
