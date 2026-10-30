# RA5 integrated model: original objectives, code audit, required fixes and budget

2026-10-30. Status: IMPLEMENTER SELF-REVIEW ONLY. Original H/trace, RA4, POL-XCORR and MBVAR-INFO frozen contracts and data remain unchanged. No RT ran in this integration.

## 1. Original purpose and transfer boundary

| Source | Intended study | Usable for RA5 | Incorrect inference |
|---|---|---|---|
| POL-XCORR P0V3 | First-path, raw CIR, weak-port and unresolved-reflection detector; conditional feature discrimination against existing G5 | Historic 19,038 Full+LoS tap/branch/valid parity, 21 adversarial negative tests, shared common tap | Treat q_W or ds1 as an independent new EKF measurement or prove deployed hardware coherence |
| MBVAR-INFO S1/S1V3 | Known-generative additive Gaussian r/s spatial/time/white error, Jacobian vs covariance information calibration | info_core.k_pose, k_time, obs_covariance, s1_mc independent field/time draws, REV60/FWD60 | Claim Gaussian r/s additive noise is original complex CFR noise, or certify the original batch MAP posterior despite kink-related QA failure |
| MBVAR-INFO world.h_H_tap | SourceFFD LoS prediction and *fixed* detector tap 2x4 Jacobian for stable MAP | Reuse twice for s0 and s1 and construct Jds = Js1 - Js0 | Assume Full-multipath derivative or differentiability through tap index switching |
| MBVAR-INFO Track R PRE-P3 | Intervene on physical reflection (direct vs floor vs plate), RT source parity, scene hash | Geometry/collision, plate predesign, solver/FFD/extractor cache-key contract | Claim unsigned draft allows RT; no completed Track R runner or new RF physical results |
| Office M0/M45 producer | Actually create/verify Full and Direct-LoS physical RF for three Office routes | Known Sionna producer, banks, raw paths, receipts and QA | Already analysed Office O01/O02/O03 is a new blind independent TEST |

Source pinned at MBVAR-INFO commit c4d84e02b878af9835bef09d515d45f4010caa74. Git blobs: world.py 2129aefa65e8dba7abd39dd4a66a89c066eac593; info_core.py 151861fe9020e070f1632b6e32749c2e5c2ac3cd. Original preserved H commit 9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13 and original EKF3 P0 input manifest hash checked independently. The new integration never edits those upstream modules.

## 2. Exact code changes required

| ID | Work | Status / implementation | Stop criterion |
|---|---|---|---|
| OBS-01 | LoS [r,s0,s1] 3x4 Jacobian and Jds=Js1-Js0 at a fixed source detector tap | Implemented in integration/tap_jacobian_adapter.py; finite-difference independent parity | Tap changes under state perturbation or failed J parity must be excluded/flagged, never smooth through discontinuity |
| OBS-02 | CFR complex noise before Hann/IFFT/30% first-edge; common noise across 2 RX, optional port timing jitter, joint r/s0/s1 R | Implemented in integration/raw_tap_covariance.py, same noise samples for all features, PSD and transformed R parity | No physically calibrated noise claim; retain null/port/tap switches and non-Gaussian mixture strata |
| OBS-03 | Definition of range measurement likelihood vs Jacobian | UNRESOLVED: SourceFFD predicts continuous range distance+B_OLD but historical first-edge packet r is an INTEGER tap index converted to metres. Full 3x3 noise covariance can be singular. Do not silently combine continuous-range J with a quantised-range R or regularise to invertibility. Must choose validated sub-tap ToA, a separately justified existing Rrr surrogate, or raw complex likelihood. | Full [r,s0,s1] Fisher / filter BLOCKED if range model and full rank not consistent |
| OBS-04 | FFD LoS J and R estimated at the SAME pose and with SAME H, not hybrid new-world J with Corridor-H R | Implemented in integration/conditional_tap_information.py as s0/s1 conditional Fisher, with full covariance basis-change identity. | Keep Full multipath J and real receiver noise as NOT_PROVEN; do not convert data-only Fisher into an unseen-scene performance claim |
| OBS-05 | Full model joint covariance over receiver-time/port/frequency, weak port, tap switching, train-only calibration | NOT COMPLETE. Current CFR noise is known-assumption Gaussian, not measured DW1000 hardware. | Cannot approve online calibration, first-path detector uncertainty and actual operational feature availability |
| OBS-06 | New 3-component EKF with Joseph P and NIS gating, exact 2-tap transform parity, BASE_FIXED/self gate separation | NOT IMPLEMENTED. Requires OBS-03/05 first. | Do not use ad hoc positive R or independent diagonal same-tap covariance |
| FT-01 | Known-generative spatial/time/white separation and same-pose revisit | Implemented in field_time_identifiability.py calling unchanged info_core kernels, 600 independent field realizations per scenario | Only synthetic field/time model identified, not physical time drift in static Sionna H |
| FT-02 | Repeat time at exact same x/y/z/yaw/anchor/mount/scene and estimate covariance temporal variogram, compare FWD60 | Done for known-generative testing; physical correlation model and independent seed/wall perturbation missing | No original static RT temporal field inference |
| ENV-01 | New receiver-noise/jitter regime applied to stored H | Implemented; NEW observation-stress condition but NOT new physical environment | Cannot count changed noise draw/trajectory/gyro label as independent RT scene |
| ENV-02 | Novel geometry/echo synthetic DEV without RT | Feasible from SourceFFD spectrum and world trajectory generators, separate from source Track S locked tests; new generator needed if used | No physical reflected-ray truth from synthetic delayed echoes |
| ENV-03 | New physical C00/C01/C10 test | Proposed PRE-P3 76 config maximum, first eight direct-only parity; NOT STARTED. Needs signed contract, numerically approved RT budget and solver/FFD adapter | RT STOP if preflight/parity fails; do not open original HOLDOUT2 |
| ENV-04 | Independent new physical blind TEST | NOT AVAILABLE in existing already-analysed Corridor and Office; must prefreeze unseen scene/measurement | Generalisation NOT_TESTED until truly unseen environment and independent auditor |

## 3. Quantified NO-large-RT technical experiments

- Original Full H: R5_aA_m0 pose IDs 100,900, R2_aA_m45 IDs 200,500. Three per-bin complex CFR SNR {-5,5,20} dB, RX relative timing jitter {0,150} ps, noise port correlation {0,0.5}, 512 realizations/cell: 48 cells and 24,576 noise draws. These are assumed per-bin SNR values; they are not measured SNR.
- Six SourceFFD LoS poses at anchor A with h_H_tap of the original world: source first tap and Jacobian parity vs central finite difference. Source geometry is FFD LoS, not new RT.
- REV60, FWD60 and REV60 no-time synthetic fields: three cases x 600 independent fields x 60 time points = 108,000 synthetic time observations, spatial field reused at exact revisit poses. No physical time dependence is introduced into original H.
- Same-scene SourceFFD FFD J and CFR assumed-noise covariance for six poses x three SNR x two port-jitter levels x 768 draws = 36 cells/27,648 draws. Assess conditional information in [s0,s1] not invalid full quantized-r Fisher.
- Zero new RT calls. Future proposed PRE-P3: no larger than 76 configurations including 4 repeated-pose QA, first stage 8 direct-only parity. Separate budget and independent audit before run.
- An independent RF scene cannot be generated from finite archived H by reassigning pose/time/seed IDs. Existing Office data are valid for development robustness, not a new blind test.

## 4. Required gate and stopping logic

P0: code SHA and original source lock, first tap/source parity and negative fixtures.
P1: joint R basis invariance, conditional same-pose tap Jacobian, PSD/rank/tap-switch flags, local Fisher with nuisance constraints.
P2: synthetic revisit vs forward spatial-time separation; bootstrap across independent fields and no-time control.
P3: optional new synthetic geometry/receiver noise (DEV ONLY), no physical RT claim.
P4: online EKF 3-observation and 4 vs 5-state sensitivity only after measured or separately validated full observation likelihood and white/colored nuisance split; matched BASE gate and SELF gate separately.
P5: new physical RT canary after PRE-P3 source/solver/budget agreement and independent audit, independent direct path parity before reflectors.
P6: never-before-seen scene/measurement with frozen TRAIN/DEV/TEST and independent auditor. Missing external TEST is BLOCKED_NOT_TESTED, not the failure of a synthetic feasibility study.

Negative findings (rank deficiency, performance deterioration, kink, observable lacking hardware capability) remain valid findings. Green technical workflow and same-session code review are never independently validated physics.
