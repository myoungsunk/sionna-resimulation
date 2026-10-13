# 05 — 기존 sensor-v2의 1/2/3점 프로브를 이용한 위치·각도별 다중경로 신뢰도와 Heading 공동 추정

실행일: 2026-10-10 (KST)  
모델/사전 고정: 04_PROBE_SITE_MIXTURE_SPEC_KO.md  
재현 코드: run_probe_site_mixture.py  
성공한 GitHub Actions: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38047959200  
출력 artifact: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38047959200/artifacts/11668546268  
실행 상태: **EXECUTED_EXPLORATORY_ONLY**. No model calibration, no operational EKF rollout, no new Sionna RF, no proof of cross-geometry generalization.

## 결론

**2–3점 가운데 가장 작은 residual을 선택하는 것이 아니라, 동일 위치의 다중경로 상태 M_site와 각도별 오염 m_i를 잠재 변수로 놓고 모든 관측을 확률적으로 결합했다.** 그 결과 위치/각도 오염 score와 heading mean/sigma가 동시에 산출됐다. 다만 **정확한 다중경로 위치 판별에는 실패**했으며, 3점이 1점보다 heading MAE를 일관되게 개선한다는 증거는 없다. 기존 단일 분산 Gaussian 3점에 비해 위험을 완화하는 성향은 확인된다.

## 사용 원본

- 사용자 브랜치 codex/cir-heading-reliability-prereg-20261010의 sensor-v2 실행 자료 results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff.
- PROBES/07_PROBE_STATIONS.csv.gz: 35,550 stored rows, 15,300 usable rows (=5,100 station×seed×drift triples), missing prior 20,250 rows. 5,100 triples are **34 case-specific station groups, 16 distinct physical XY locations**, repeated for 3 drift×50 seeds.
- OUTPUT/01_FEATURES.csv provides measured s, OUTPUT/02_LABELS_EVAL_ONLY.csv provides truth e_s/e_MP and true yaw only AFTER inference. Frozen FFD 2° LUT hash verified 711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079.
- Same-position offsets from stored true yaw ~[0,±10,±20] deg, ideal actuation offline. Pre-RF x/y/yaw and heading prior variance are from RF-disabled sensor-v2 A. **Original full P6 is not present in the published PROBES CSV**; xy/heading cross covariance not propagated.

## Measurement and posterior

r_i(u)=s_i−h_LUT(x_prior,y_prior,psi_prior+u+delta_i). Heading correction u has original v2 Gaussian marginal prior. For n=1/2/3, fixed grid −90..+90 deg / 0.5 deg. Source r never matched to true yaw or true e_s during posterior inference.

Enumerate site M={normal,multipath} and n point contamination flags c_i∈{normal,multipath}. Each component has Gaussian observation covariance R=diag(sigma_point²)+tau_site_s² 11^T+tau_site_equivalent_heading² gg^T (g=prior LUT derivative). Integrate hypotheses and the nonlinear LUT over u. Output posterior q_site_bad, q_point_bad0/1/2, psi_est, sigma_heading. **Never select one minimum-residual point or hard-drop suspected points**. Site prior 0.35, point priors 0.06(clean site)/0.55(dirty site), sigma_point_good=.06, bad=.30; site common s std=.01/.15 and equivalent-heading bias std=1/15deg. These numbers were predeclared as illustrative, NOT estimated receiver noise or calibrated probabilities.

Compare GAUSS (all accepted, independent .09² s noise) and MIX (above) with identical n-angle inputs. Both use exact nonlinear LUT and same heading marginal prior.

## Heading 결과 (5100 paired blocks; case/seed/time-weighted descriptive metrics)

| Model | Points | Heading RMSE deg | Heading MAE deg | Empirical heading 95% coverage | Mean heading sigma deg |
|---|---:|---:|---:|---:|---:|
| v2 A RF-off prior | 0 | 9.555 | 6.882 | not in comparator | input prior |
| GAUSS | 1 | 7.753 | 5.529 | 0.747 | 4.761 |
| GAUSS | 2 | 7.701 | 5.889 | 0.550 | 3.035 |
| GAUSS | 3 | 7.756 | 5.868 | 0.469 | 2.343 |
| MIX | 1 | 7.289 | 5.210 | 0.926 | 6.596 |
| MIX | 2 | 7.125 | 5.306 | 0.863 | 5.249 |
| MIX | 3 | 7.030 | 5.347 | 0.757 | 4.474 |

Interpretation: equal Gaussian 3-point compresses reported sigma while actual 95% coverage collapses to 46.9%, consistent with duplicated/correlated multipath information. MIX3 makes covariance more conservative (75.7% observed coverage), but **still fails nominal 95%**. This is *yaw-only conditional* posterior coverage, NOT full pose NEES or validated v2 filter. MIX3 RMSE is lower than GAUSS3, but MIX3 MAE is higher than MIX1.

Paired absolute heading error differences with 1000 bootstraps of the **16 distinct physical XY sites** (same source station repeated across seeds/anchor within physical station):
- MIX3 − GAUSS3 = −0.521 deg; 95% interval [−1.162,−0.032]; improved seed/group cells 65.8%.
- MIX3 − MIX1 = +0.138 deg; 95% interval [−0.836,+0.978]; no established MAE gain from 3 points.
- MIX3 − RF-off prior = −1.534 deg; 95% interval [−2.995,−0.025]; conditional comparison, low physical location count.
- GAUSS3 − GAUSS1 = +0.339 deg; 95% interval [−0.759,+1.385].
Same corridor means cluster CI can still be optimistic for new buildings.

## Location-level multipath detection is NOT GOOD ENOUGH

Evaluation-only oracle: location_bad if any of 3 probed |s_full−LUT(true_pose)| >0.1. This label includes LUT model mismatch (F01) as well as multipath; not perfect physical reflection presence label.

- Ground-truth bad sites: 17 of 34 case-specific station groups (50%).
- Site median score AUROC: 0.619 (evaluating 34 case-specific stations), while repeated seed-level AUROC=0.625.
- MIX 3-point q_site Brier=0.386 (seed-level); constant q=0.5 for 50% prevalence would have Brier=0.25. **Not calibrated**.
- Threshold q_site_bad≥0.5 flags only 3/34 case-specific sites; 1 true positive, 2 false positives, 16 false negatives. **Site detection recall 1/17 ≈5.9%**.
- By route, seed-level AUROC: R2≈0.50, R4≈0.86, R5≈0.24. Large instability and route confounding.
- Per-angle point contamination AUROC in MIX3: point0≈0.652, point1≈0.769, point2≈0.736, but mean predicted bad probabilities ~0.10−0.12, less than oracle bad prevalence ~0.32−0.41. Strong under-detection.
- Example correctly flagged R4_aA_m0 station9: median q_site_bad=0.826; all 3 oracle point bad; median estimated heading error 9.3deg and predicted sigma ~9deg. Example missed R2_aA_m0 station1: q_site_bad median=0.268 despite all 3 points oracle bad. Example false-positive R5_aA_m0 station2: q_site_bad median=0.510 although no probe point exceeds oracle threshold.

Hence cannot claim "2/3 probes can reliably identify a multipath-contaminated location" on current evidence. It can *produce a risk score* and mitigate heading overconfidence, but the risk score misses many bad sites.

## Hard scientific boundaries

1. All recorded RF H and probe s are noise-free. Actual DWM1000 amplitude-only module may or may not provide magnitude CIR; no hardware interface verification.
2. True yaw offsets at same station were used (ideal rotation), not wheel/IMU-realized noisy motion; heading/turn time cost not evaluated.
3. Published probe file contains heading P only. The full sensor-v2 P6, position-heading correlation and temporal/probe error covariance were not available; no genuine filter F update or full pose NEES can be claimed.
4. Good vs bad components and site common-bias priors are hypothetical. They were frozen before viewing outputs, but were not calibrated using a held-out environment. Increased n can even worsen predicted score calibration.
5. Body yaw may be mimicked by common effective polarization rotation: 2/3-point shape agreement cannot separate these without independent heading information.
6. 34 case-stations share **16 physical positions** in one corridor. Not 5100 independent locations. Training and generalization cannot be claimed.

## Preferred next study

Preserve this negative/partial outcome. Use an out-of-route trained **amplitude-only CIR + total power + distance/slope + prior innovation** model to set per-point prior multipath odds, then update with 2/3 yaw observations and explicitly include a shared station component. Calibrate risk against **operational heading error**, not just |s| residual, using physical-location-heldout and ultimately new physical geometry. Record full pre-RF P6 and noisy body rotation time/encoder yaw to enable genuine sensor-v2 + probe F comparison. No heuristic threshold tuning to this same 16-site test.
