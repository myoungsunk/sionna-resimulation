# Evidence/Gaps/Minimal Work — DLP-EKF-GAPS-001
Status: DRAFT; all proposed work NOT_RUN; 3-D RESERVED.

## C0 canonical family
Frozen Corridor R2/R4/R5, 7 cases, Full/Native LoS pair 9519 poses, route timeline 7251 case-steps; TX+45 LP, RX±45 LP, 257 frequency points, identical Hann/4N IFFT, stronger-port 30% first-edge shared tap, signed s. Sensor-v2 gyro/wheel; 4-state [x,y,psi,b_g]. C0 is ONE scene, not seven independent RF environments. Source primary: EKF3 P0_INPUT_MANIFEST.json and FFD_P0P3/SOURCE_BANK_RECEIPT.json. Each source must be independently SHA-verified at P0.

## Gap decisions
| ID | Existing evidence | What is NOT proven | Minimal proposed work | Decision gate |
|---|---|---|---|---|
| G1 Source alignment | 9519 matched LoS/Full, FFD_P0P3 P0-P3; N4-B old LUT and PJ SourceFFD statistics | Earlier figures all reflect same h/H/calibration/keys; range continuous bridge equals physical detector | Build source-to-output lineage and key/units parity; identify precise quantities changed; rerun affected statistics on same saved C0, not raw RF | P0a lineage then optional P1 harmonization |
| G2 1-anchor R-only 4-state | EKF3 P2 one-step Range-only; drivesim 6state range EKF; EKF4 R2 DR/S/J/SR; rt_cp_uwb_py.localization.py known-z 2D | Final C0 4state range-only *full-recursive* trace parity with conventional J4 using same f/F/Q/initial/mask | Search archives/reports/results for exact arm, verify state/P/gate. If absent, add one range-only arm to locked EKF4 replay, no new H | P0b evidence search; P2 replay conditional |
| G3 ≥3-anchor baseline | rt_cp_uwb_py/localization.py WLS>=3 and known-z 2D EKF; frozen C0 only A/B anchors, each separately | 3+ synchronous real Full RF anchors in same C0 Corridor and 4-state heading EKF; 3state ≠ 3anchor | Search accessible inputs/artifacts including multi-anchor synchronized traces; check exact scene, trajectories, timestamp, antenna/pattern, observer, sensor seed. If absent, design additional anchor(s) on SAME scene and pose keys; canary/source physics/coverage, then bounded RF generation only after approval | P0c inventory -> P3 canary -> P4 RF (both conditional) |
| G4 R4/R5 mount45 | R2 A m45 exists, frozen C0 R4/R5 m45 not in seven | Existing stored R4/R5 m45 new RF with same C0 producer and observer | First seek preserved extensions; if absent keep as explicitly marked limitation; not compulsory for primary | P0d inventory |
| G5 M2 final EKF | POWER, MB_VAR, signed ds, CI, covariance and gate exploratory systems, various failures | Method chosen and fully validated under identical f/F/Q and calibrated source | Reserved for Section 3-D decision; NOT authorized | BLOCKED_SCOPE |
| G6 scene transfer | Office O01/O02/O03 and Corridor transfer with different RT scene | Same-family measurement identity or confirmatory independent scenes | Do not merge into C0; secondary retrospective only | OUT_OF_PRIMARY |
| G7 independent final holdout | all previous Corridor/Office histories analyzed | unseen environment generality; paper-ready multi-scene confirmation | optional future contract with locked scene-variant split; no claim currently | BLOCKED_SCOPE |

## Work order
0. Contract/dataset provenance only — no code or runs.
1. P0a raw file/artifact inventory, exact sha/shape/time/pose and C0 ancestry, source LUT vs SourceFFD, noise modes, 3state/4state/6state, biases and gate.
2. P0b search pre-existing R-only 4-state full recursion, avoid unnecessary implementation.
3. P0c search pre-existing actual ≥3 anchor same-scene packets and 4state integration. A 3-anchor WLS solver without 3-anchor measurement data is *not* sufficient.
4. P0d verify mount45 extensions.
5. Only after audited P0 gaps confirmed, draft bounded P1/P2/P3/P4 implementation schedule; nothing executed by this proposer phase.

## Allowed claims
C0 is a fixed RF family; selected historical observations were made in that family; exact cross-study equivalence remains unproven pending P0; existing multi-anchor *algorithm* exists but C0 three-anchor *data/4state result* not verified.

## Forbidden claims
No new RF required (until inventory checked); three anchors complete; full R-only 4state measured; C0 has scene-level independence; all earlier LUT/P0 quantities interchangeable; proposed M2 is validated; any future performance improvement established.
