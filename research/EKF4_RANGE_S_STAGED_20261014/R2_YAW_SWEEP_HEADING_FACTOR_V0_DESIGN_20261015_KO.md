# R2 ±10°/±45° RF Yaw Sweep Heading Factor — separate research module (design, 2026-10-15)

**Status: DESIGN ONLY.** Do not change existing P3 observer, R4 P4/P6 SR4, frozen LUT, original R0 or original MAP source. This document does not demonstrate physical Full RF scan improvement.

## Goal and cadence

Maintain ordinary DR prediction plus RF Range and dual-LP s update at each normal instant. At every 10 seconds, schedule a center-preserving stationary fast yaw sweep **relative to the current estimated body direction** from −10° to +10°; return to original yaw. When the scan is uninformative or multimodal, optional wide −45° to +45° scan. Check 10 versus 20 second cadence in controlled experiments.

Fast pilot: 11 headings with 2° spacing. Wide pilot: 19 headings with 5° spacing, plus 11-heading same-count control and 2° full sweep (46 headings) as a separate sampling-density study. Compare wall-clock dwell, acceleration, wheel slip and actual relative yaw uncertainty; a commanded angle is not angular ground truth. Safe stop rule at station; record robot center translation, time alignment and packet reliability.

## Frozen LUT roles

The frozen first-path LoS LUT is 46×180×180 for theta=0..90° (2°), phi_tx, phi_rx = −180..178° (2°), from FFD + TX0 (+45 LP) / RX dual ±45 LP, Hann, 4N IFFT, first-edge common tap, s=(P1−P2)/(P1+P2).

At fixed x,y,z and anchor geometry, theta and phi_tx are constant when yaw changes. phi_rx decreases by the yaw increment. Hence only phi_rx is controlled by stationary yaw; phi_tx still changes the LUT cross-section's shape across locations. Quantify absolute derivative |ds/dphi_tx| versus |ds/dphi_rx| and the actual s swing over ±10/±45 before claiming information. Frozen interpolation metadata L1 validation median error 0.00053024, maximum 0.0239721 greater than the 0.01 max threshold (FAIL). Model parity does not guarantee perfect angular calibration.

## Observation and nuisance model

For K timed orientations, observe raw s_j, dual-port first-path P1/P2, CIR/complex H if available, range, tap IDs/quality, measured delta yaw with covariance, motion center drift, case/mount/anchor and unique packet source IDs.

A preliminary model is
s_j = h_LUT_s(p, psi_0 + delta_j) + a0 + a1*delta_j + epsilon_j,
where a0/a1 are nuisance channel polarization and angle-dependent multipath coefficients; epsilon has a correlated covariance C. Test nested a0-only, a0+a1delta and raw Full orientation H likelihood. Nuisance x,y,calibration parameters and relative yaw errors also matter. No matched Full RF heading GT is supplied just by this fit.

The conditional Fisher information for heading after eliminating nuisance parameters N=[1,delta,dh/dx,dh/dy] is:
I_heading|n = g.T (C^-1 - C^-1 N (N.T C^-1 N)^-1 N.T C^-1) g
where g_j=dh_s(p,psi+delta_j)/dpsi. Rank-deficient or small conditional info => NO_INFORMATION. Estimate noise correlations (0/0.8/0.95 AR1 positive controls), optimize scan positions only after calibration on independent samples. If likelihood multimodal keep modes, do NOT send a spuriously precise scalar heading.

## Integration: one scan = one factor, NEVER duplicated RF likelihood

During a scan, existing navigation filter remains defined but raw scan RF packets are quarantined with a unique scan_id. Either pass their full joint likelihood once as a fixed-lag factor to pose,bias or derive ONE scan-conditioned heading likelihood with calibrated covariance; never first update SR4 with each RF scan packet and then count the identical samples again as an extra heading measurement. After returning to the original heading and verifying center displacement, resume ordinary per-instant RF processing. No data added if contradictory or uninformative.

Output record:
ScanHeadingFactor(scan_id, anchor, mount, start_time, relative_yaw/K, offset_cov,
packet_ids, raw_s_and_port_CIR, correlation_model_id, likelihood_grid/modes,
conditional_information, consistency_score,
status=HEADING_FACTOR | QUALITY_ONLY | NO_INFORMATION | AMBIGUOUS | ABORTED,
calibrated_covariance_optional, source_sha).

Use model state [x,y,psi,b_gyro]; H at one instant does not directly observe b, but prediction creates pose-bias cross-covariance. Scan adds a pose/history factor, not a physical direct bias GT observation.

## CRITICAL Full RF dependency

The old 14 frozen Full/LoS case traces include one actual antenna orientation per pose. They DO NOT supply extra Full channel snapshots at fixed position for ±10°/±45° rotations. Varying only phi_rx in the LoS LUT generates LoS predictions, NOT Full sweep data.

For valid Full simulated yaw sweeps regenerate full frequency-domain H/CIR at every angle by recomputing antenna coupling to the unchanged per-path FFD/ray data at the same stationary positions. Otherwise record physical robot measurements from both LP ports. Keep origin scene, geometry, timestamp and source hashes; truth is only for offline evaluation. Do not treat a synthetic rotation of two recorded RX port powers as exact Full-channel antenna rotation without separate calibration.

## Controls and evaluation

R2 straight corridor, Anchor A, mount0/45, B0=0,L0=+0.01,L1=+0.05,L2=+0.20°/s; LoS versus true orientation-resolved Full. DR-only, S4, J4, SR4, SR4+K repeated same yaw, SR4+Fast, SR4+Wide. Paired development seeds 0..19 and heldout 10000..10049; independent RF scenes needed for generalized claims. Report pose/heading/gyro bias RMSE, signed error, NEES/95% coverage, ambiguity rate, false confident factors, scan duration and number of stopped segments.

Source and safety test gates: code audit before numerical execution, RF H source identity, no estimator truth access, packet ID deduplication, measured yaw confidence, run-scoped covariance calibration, pose center bounds, no posterior RF packet reuse. On failed source/data test output BLOCK/NO_UPDATE; never claim more accurate Heading GT.

## Candidate technical references

- Chang and Scholtz, Polarization measurements in a UWB multipath channel, MILCOM 2004, DOI 10.1109/MILCOM.2004.1493268. Orientation-specific UWB polarization is physically observable; this does NOT prove any absolute heading from current scan.
- Sünderhauf and Protzel, Switchable constraints for robust pose graph SLAM, IROS 2012, DOI 10.1109/IROS.2012.6385590. The robust switchable factor idea is a possible back-end model, not a validated UWB polarization scanner.

Current phase: theory and preregistered v0 interface; no real Full yaw-sweep performance or scientific_PASS.
