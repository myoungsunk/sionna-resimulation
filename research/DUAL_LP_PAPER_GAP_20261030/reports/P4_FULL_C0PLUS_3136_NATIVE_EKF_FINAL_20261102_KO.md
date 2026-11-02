# DLP-EKF-GAPS-001 — P4 Full Native C0+ 3-Anchor EKF final report

**Date:** 2026-11-02 KST. **Final result:** 3,136/3,136 matched Native C RF epochs, all 84 full 4-state EKF arm trajectories, and all five independent-formula postrun tests **PASS**. Exactly one historical Corridor C0 scene; no hardware synchronization or independent-environment generalization is claimed.

## 1. Original Native RF acquisition, no interpolation

The previously frozen P3 supplied 39 actual native Sionna 2.0.1 C=(16,0.8,2.65)m Full/LoS complex H observations. The user authorized direct physical raytracing of the 3,097 missing original timeline epochs. All **80/80 original native RT shard jobs** succeeded in [run 41408877765](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41408877765). Each new pose used the original physical FFD port banks, C0 geometry and materials, actual 257 frequency bins, Full max_depth=3. The Full solver's unique direct path was independently proven equivalent to actual max_depth=0 NativeLoS on a fixed **6 poses × 9 frequencies** canary [run 41407549938](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41407549938) (relative error 0 vs fresh Native LoS; maximum delay error 2.86e-15 s). New physical shards also performed native-LoS spot checks. No SourceFFD-only C channel or frequency extrapolation was used to replace native RF.

| Original route | Preserved P3 C | Newly simulated Native C | Total verified original epochs | Missing |
|---|---:|---:|---:|---:|
| R2 | 13 | **966** | **979** | 0 |
| R4 | 13 | **729** | **742** | 0 |
| R5 | 13 | **1,402** | **1,415** | 0 |
| **Total** | **39** | **3,097** | **3,136** | **0** |

Every original native C pose is represented by physical 257-bin Full/LoS complex 2×2 H, actual path-count/tau metadata and independently recalculated leading-edge range/s. The maximum physical Full path count across complete routes was 63; maximum direct path delay error 6.16e-15 s.

## 2. Transparent execution and recovery history

- Original run 41408877765: 80 Native physical RT jobs **SUCCESS**, but aggregation failed because a quoted Python heredoc compared the literal run-ID variable string rather than the actual artifact ID.
- First recovered run [41434959439](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41434959439): all 80 original artifacts restored with no missing shard (R2 25, R4 19, R5 36); aggregation failed an erroneously exact literal 2.65 coordinate check. Raw old/new P3 data agree on the original computed Z=2.7−0.05=2.6500000000000004, a 4.44e-16 m float64 representation difference.
- Corrected native reconstruction [41435428514](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41435428514): **all three R2/R4/R5 Native source completeness and path/tau verification jobs PASS**. Its EKF job was blocked only by missing frozen qclean_uwb sparse dependency.
- **Final recovery [41435839892](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41435839892): GitHub Actions SUCCESS.** Reused the previously verified Native source artifacts rather than repeating ~797k expensive new Full RT frequency/pathsolver calls, included the original pinned SourceFFD dependencies and executed all 3 complete 4-state EKF route jobs. Postrun numerical QA **5/5 PASS, 0 failures**.

Original science thresholds, the original 39 native samples, original A/B RF, P1/P2/P3/P4 Pilot and main were not overwritten.

## 3. Full 4-state EKF setup

All original 3,136 route time epochs provide A/B/C Native H Full/NativeLoS. Original frozen EKF4 four states are [x,y,psi,b_g], original P2 B0/L2 (+0.20 deg/s gyro bias only) seed0 sensor increments, identical initial x/P and f/F/Q, and each arm's own posterior recurrence and 99% gate by number of measured scalar components. Ranging uses original first-path raw detector, continuous predictor d−0.5315983906250129m and Rr=0.0068578637m²; Joint uses R_s=0.0081. Cross-anchor R remains assumed diagonal, **not independently calibrated**. Truth is only in the offline control generator and scorer.

Arms: DR4, single-A Range-only, single-A joint SourceFFD [r,s], AB Range-only, ABC Range-only, and two equal-range-packet-count arms. Primary packet attempts over all routes: A **3,136**, AB **6,272**, ABC **9,408**. Secondary arms both consume **3,132** range packets, but A observes almost every epoch while ABC observes all three anchors every third epoch. This is not equal measurement cadence or hardware-energy cost.

**84 individual arm results** are derived from 12 original route×mode×bias time/P/NIS trace arrays, with **28 pooled** and **48 paired contrast** rows. Each pooled row contains 2,686 scored original time samples at t≥30s, all within the single simulated Corridor.

## 4. Heading RMSE in degrees (smaller is better)

| RF | Bias | DR4 | Single A range | Single A joint [r,s] | AB range | ABC range |
|---|---|---:|---:|---:|---:|---:|
| Native LoS | B0 | 0.498 | 3.437 | **0.419** | 2.380 | 0.990 |
| Native LoS | L2 | 29.225 | 6.306 | **0.616** | 2.188 | 1.120 |
| Full | B0 | **0.498** | 10.262 | 5.526 | 2.451 | 2.089 |
| Full | L2 | 29.225 | 13.836 | 5.731 | 2.718 | **2.306** |

ABC range offers large gains over single A in Full L2 (13.836°→2.306°) but consumes 3× as many anchor-range packets; it also improves on AB (2.718°→2.306°) with 1.5× packets. However Full B0 DR4 is still only 0.498°, and injecting ABC Full RF raises error to 2.089°. Native LoS joint [r,s] is the best heading result for both bias levels among shown methods, but its measurement dimensionality is different.

Selected XY RMSE: Full L2 A 1.9042m, AB 0.2432m, ABC **0.1753m**; Full B0 ABC **0.1762m**. No guarantee of gain beyond original C0.

### Equal 3,132 range packet count, different cadence

| Mode | Bias | Single A almost every epoch | ABC every third epoch |
|---|---|---:|---:|
| Native LoS | B0 | 3.437° | **0.904°** |
| Native LoS | L2 | 6.306° | **1.433°** |
| Full | B0 | 10.262° | **2.100°** |
| Full | L2 | 13.836° | **2.307°** |

ABC wins all four observed conditions when matching only the total range packet count. It does not isolate pure anchor-number causality because spatial and temporal coverage differ.

## 5. Severe posterior calibration boundary

Full mode, **nominal 95% pose coverage**:

| Bias | AB Range-only | ABC Range-only |
|---|---:|---:|
| B0 | 36.26% | **8.97%** |
| L2 | 27.66% | **8.23%** |

ABC Full B0 accepted 2,765/3,136 update epochs and rejected 371; L2 accepted 2,767 and rejected 369. Despite better Full heading and XY scores than A/AB, these very low pose coverage fractions warn of overconfident posterior covariance under a fixed diagonal measurement-noise model. Neither causality nor cross-environment calibration is established by this single-seed, time-correlated run.

## 6. Final verified artifact and provenance

[GitHub Actions 41435839892](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41435839892): **workflow SUCCESS**, original full P4 postrun receipt status **PASS_FULL_C0PLUS_4STATE_EKF**, all 5/5 numerical checks pass, no failures. Max independent own-posterior prediction difference **0**; max independent Joseph covariance difference **5.68e-14**. The original **12 full 4-state trace ZIP** SHA256 is **5ecf2a326ec17c8ce4ccc7a42fe76227ecf6ad7ec027df9cdfcd2304dcb0acfe**.

Source Native route ZIP SHA256:
- R2: 706811d5af4503fd310b598040419cc0ee63ec30ee8f1d26b764763575aa2e6f
- R4: 93f9e9bd71ed045fdf8f8ad42886caeac0dc57add126efd986ec43b0a9fb0776
- R5: c65864473a685476708c77fea7031684577452acb50d0167e023dd0e229e2111

Original source route ZIPs are preserved in GitHub Actions and in Git as consecutive **≤45MB numbered .part.000/.001/... files** plus full ZIP checksum. Reconstruct using concatenation in ascending part order and verify its SHA256. This avoids GitHub's single-file 100MB push limit.

### Inspectable material
- [P4 FULL numeric QA](../runs/P4_FULL_C0PLUS_NATIVE_41435839892/P4_FULL_POSTRUN_QA.json)
- [84 original case scores](../runs/P4_FULL_C0PLUS_NATIVE_41435839892/P4_FULL_84_CASE_METRICS.csv)
- [28 pooled statistics](../runs/P4_FULL_C0PLUS_NATIVE_41435839892/P4_FULL_28_POOLED_METRICS.csv)
- [48 matched contrasts](../runs/P4_FULL_C0PLUS_NATIVE_41435839892/P4_FULL_48_PAIRWISE_CONTRASTS.csv)
- [12 full 4-state x/P/NIS traces](../runs/P4_FULL_C0PLUS_NATIVE_41435839892/P4_FULL_12_COMPLETE_4STATE_EKF_TRACES.zip)
- [R2/R4/R5 complete Native H/tau SHA indexes and route ZIP parts](../runs/P4_FULL_C0PLUS_NATIVE_41435839892/)
- [Original frozen P4 FULL source/science contract](../contracts/DLP-EKF-GAPS-001/P4_FULL_20261102/P4_FULL_PROPOSER_CONTRACT.md)
- [Actual native RT generator](../p4_full_runtime/p4_full_native_c_rt.py), [full EKF](../p4_full_runtime/p4_full_ekf.py), [postrun verification](../p4_full_runtime/p4_full_postrun.py)

**Disposition:** P4 Full 3,136 Native C RF = **PASS**; P4 Full 84 EKF results and 28 pooled = **PASS**; numerical postrun QA = **5/5 PASS**; real hardware clock calibration = **NOT TESTED**; independent-scene generalization = **NOT TESTED**. A separate Linux computational runner does not imply a different human/agent peer reviewer, since the test and implementation were authored within the same ChatGPT conversation.
