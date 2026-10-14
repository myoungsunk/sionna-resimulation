# E pilot one-step evaluation: audited source and dependent evidence (2026-10-14)

Decision **GO_WITH_CLAIM_LIMITATION**. Scope is exactly frozen 195.6s R2_aA_m0 / gyro_bias L2 / seed0 / LoS B_OLD. This is NOT new G2/G3 policy, not a whole-route benchmark, and is not scientific adoption.

Why now: B signed residual route-split has a scientific calibration claim block (R2/R5 spatial buffer 0) but D resolved one **original** G3 numerical cell with new tilted GH / independent randomized QMC. This permits a truth-scored **single-cell original R0 G3** comparison without making full E/F performance claims.

Pre-run source and input requirements:
- approved run 38531405523 / artifact 11878356818 / full ZIP SHA256 93e41c0b7490ba0a5ddee06d91786ed82dcd919e721d8cdf1ff4b942a7e9f1fa
- exact D JSON SHA256 ae39d41cf5aa60934a88b7ade93da6d7563a90b18a3752824b2047261c30b7a4
- exact GH41 .npz SHA256 a02c17e0789355ee55aab0ece4ecd587a1a8a288c9a9427e262a292100047d29
- frozen original Stage4 partial CSV git blob 2c0186b8f62fd6a1ef47d52845dabd9786de8e47
- frozen original route timeline CSV git blob c1aed2e95d9a9be2af32e854f9eb7a2d239e1222
- D acceptance was TV<=0.001 / MAP<=0.1° and evidence<0.005 across independent randomizations. Rechecking D provenance is necessary, not a new target tolerance.

New scientific arithmetic:
- G3 MAP argmax on original 1440-angle grid; compare wrapped difference to original timeline truth *after* posterior generation. Never use truth as model input.
- Reconstruct archived G0/G1/G2H/G2X signed errors from same timeline truth for parity.
- Independent hpd95 discrete set from normalized posterior mass sorting, true-angle nearest-grid inclusion, and ±5° mass.
- Accuracy hypothesis that G3 must outperform G2H on this cell is NOT guaranteed by numerical convergence. Contradiction triggers a scoped report and STOP before uncalibrated fault prior retuning.
- Original G2H/G2X Range gate rejected this observation; original G3 accepted joint Range+S. The methods have different observation-use policies. Accuracy difference does NOT prove sequential versus joint inference intrinsically superior.
- No new RF calibration, gyro prior, unit, covariance or threshold changed.

Impact classes:
- HASH/pose alignment/invalid 1440 posterior -> HARD_EXECUTION_BLOCK for this pilot.
- Posterior numerical normalization/provenance failure -> CASE_RESULT_INVALID only for this G3 cell.
- G3 accuracy worse -> hypothesis contradicted for this cell, CLAIM_BLOCK for broad advantage and posterior adoption.
- Formatting-only failure -> diagnostic defect; preserve original D result.

Implementation is scoped one-cell E pilot, **not** full E, and F remains NOT_RUN_DEPENDENCY without calibrated B and full E. No automatic model switching or tuning after a contradiction. Written by assistant; no independent human reviewer; independent calculation uses different archived and new paths.
