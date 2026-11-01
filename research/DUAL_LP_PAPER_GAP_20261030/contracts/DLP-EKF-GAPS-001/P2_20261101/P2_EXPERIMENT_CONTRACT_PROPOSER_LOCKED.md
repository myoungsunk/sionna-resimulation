# DLP-EKF-GAPS-001 — P2 proposer-locked candidate v1

Status: PROPOSER_LOCKED / INDEPENDENT_PRE_RUN_AUDIT_PENDING / NOT FROZEN / P2 NOT RUN. This phase is NOT the unrelated EKF3/MBVAR experiments named P2.

## Research question and scope

P1 concluded on original Corridor C0 that SourceFFD greatly harmonized native LoS signed-s prediction without reliably reducing Full multipath residual. The next gap is an exactly four-state scalar range-only recursive comparison, not selecting M2 or inventing new RF. Original EKF4 R2 replay contains DR4/S4/J4/SR4, but does not include a scalar range-only R4 arm in its frozen arm enumeration. This does not establish that such code cannot exist elsewhere.

The P2 estimand is a retrospective comparison of M0 DR4, M1-A single-anchor R4 range-only, and M1-B joint J4 SourceFFD. All use state [x,y,psi,b_g], identical frozen EKF4 transition f/F and Q, initial x/P, same sensor-v2 controls, exact RF packet and full recursive prior propagation. R4 consumes one range measurement, J4 consumes both r and signed s. They are not equal observation dimension or equal information resource; report this openly. Every filter applies its own gate; no oracle mask.

## Immutable inputs

- Original P1 result HEAD: 21aa49ea809255a2dc863a4fbdb1e2c98dcaa16a.
- P1 science contract SHA256: 373781e0a2395032faa49ff0228d84ebf8d93bb9c880e0504105bc5e12e82594.
- P1 FROZEN 16/16 PASS run 41300302082 and QA SHA256 0e94c32edcbf4aaf10938c48fa548b813508a50f46bfcd4e01b09d46f779ad1d.
- Archived 14 RF trace ZIP run 38331588521, ZIP sha256 88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63.
- Original 39 C0 assets and two source FFD NPZ objects are inherited by byte-level checks against immutable P1 input lock. Git LFS pointers are never accepted as actual bank contents.
- EKF4 core.py git blob 0a0851e6867c14fec5eefe02df471100cb9e9e1d; Sensor-v2 blob 87ce04aa3c43130f3499008840fa395174f1124e; frozen R2 bias replay blob b1de0de13e82cd414306cba3182af18ac97607bf; SourceFFD source blob ea1cac65d6291681a4b5abf9a2c83b77f5997631.

## Recursion policy

At t0 update R4/J4 with the first RF packet; DR4 keeps initialized state. At subsequent steps each arm propagates its own prior one time using identical generated wheel/gyro increments, with NO future truth or state-replacement oracle. The motion simulator uses original historical truth to generate controls, but the filter never receives truth or true gyro bias. Controls seed 0; B0 noise_pair bias 0; L2 positive 0.20 deg/s gyro-bias-only perturbation plus the same white gyro/wheel noise, other deterministic drifts disabled, slip off, RW zero. These L2 controls are NOT full generic all-stress.

Initial pose: first truth pose plus rng(seed=0,stream=initial) Gaussian noise with sigma [0.1m,0.1m,5deg], initial bias=0; P0 diagonal variances [0.1m,0.1m,5deg,0.1deg/s] squared. Q_input diagonal [2e-5 |ds|, (0.015deg)^2 dt,0]. Original EKF4 transition uses the SE2 arc and gyro increment minus b*dt. The scripted truth was generated with legacy Euler motion and may differ slightly from exact SE2; retain model mismatch.

Original C0 seven cases: R2 A0/B0/A45, R4 A0/B0, R5 A0/B0; Full and Native LoS paired. Per bias each channel 7251 timeline case-steps, t>=30 gives 6201 each channel. Two bias levels, one seed and one Corridor scene only. All failed cases reported.

R4 scalar predictor d-0.5315983906250129m; Rr=0.0068578637m^2; chi2(1,99%) gate=6.6348966010212145. J4 SourceFFD joint [r,s] predicted at estimated state; R0=diag(0.0068578637,0.0081), assumed Rrs=0 without physical independence proof; chi2(2,99%) gate=9.210340371976184. Raw integer first-path detector range is distinct from continuous range bridge. Joseph updates and no hidden clipping, score reset, threshold tuning or filter fallback.

## Required outputs / claim boundaries

Full recursive x/P, pre-gate H/innovation/S/K/NIS, gate status, packet and scalar observation components, per-case per-arm timeline, failed-frame ledger. Separate offline scorer reads truth only after frozen inference outputs and computes wrapped heading RMSE deg, XY RMSE m, gyro-bias RMSE deg/s, NEES and nominal coverage, gate starvation; evaluation t>=30 but estimation begins t0.

Existing 7 cases are retrospective developmental evidence. One RF scene, correlated trajectories, same sensor seed, no independent-scene confidence/generalization claims. Do not infer bias direct observability from instantaneous H_b=0: F cross-terms may propagate bias correlations. No primary expected winner is predeclared.

## Gates / authority

This proposer lock is NOT final FROZEN. A distinct execution-runner preflight must verify exact original sources, physical 39-file and two FFD bank hashes, archived trace ZIP/14 traces, 4D dynamics and Q FD/Joseph, source frame/observer, initialization/controls, leakage, and all 16 P2_NUMERIC_TOLERANCES U00-U15. Auditor must include its code hash and actual raw measurements. An append-only separate ratification must then refer to unchanged contract/config/tolerance SHA256 and audit signature. The user explicitly authorized executing P2 on 2026-11-01. GitHub runner separation is independently executed arithmetic, but NOT a distinct human reviewer when authored under the same user-linked GitHub identity.

No new RF or scene, new P3/P4, M2, 3-D time/space covariance, new learned mean/covariance, Office, recovered Full-only R4/R5 M45, L0/L1 and no after-outcome tolerance changes. Preserve failures. All previous results/contracts/main remain immutable.
