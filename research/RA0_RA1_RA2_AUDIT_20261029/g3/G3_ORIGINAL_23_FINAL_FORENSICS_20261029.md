# G3 original 23 trace forensic — executed result and H scope (2026-10-29)

## Reproducible execution
- Source: branch `audit/g3-23-original-h-forensics-20261029`, workflow head `82fe07a6019c7a127bab974c260e0d1000b4b910`.
- [Successful GitHub Action #40867280947](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40867280947); [complete CSV/JSON artifact](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40867280947/artifacts/12894501730).
- Audit: `g3_original_23_full_audit.py`, sha256 `dc49a67f085fb1287ffda676b80fc27ca978e2e4f295102b601202fc057aba8e`.
- Original ZIP SHA256 `4f625c84172fecd7539273eb8d19c841fd2eb204b61d9062a3b901cca6dc4a62`.
- Exact 23 original receipts match historically frozen SHA. All 23 NPZ pass transferred-byte hashes, CRC, tau/Jones shapes, status, coordinate and strict fail-count checks. Note historical publication did not preserve raw NPZ digests.
- **No original raw, stored H, original BB/MB_VAR, solver, or original results modified. No RT rerun.**

## G3 ray result — all 25 recovered offending paths
- Group counts: R2_aB 1; R4_aA 3; R4_aB 3; R5_aA 9; R5_aB 9 (=25 rays from 7 locations, two with two unmatched).
- Historical merged-class strict exceed reproduced **25/25**, strict threshold `5e-14 s`, relaxed `2e-13 s`; original `TIE_S=1e-13 s`.
- Independently constructed up-to-third-order image candidate delays matched source `image_delays` to <`1e-21s`. Raw, unmerged nearest image criterion: **0/25 strict exceeds**; max residual `6.387236181671969e-15 s`.
- Original class representative criterion: **25/25 strict exceeds**; max residual `1.0064188592380668e-13 s`.
- Each original ray was classified `TIE_CLASS_ARTIFACT` *for the delay-based G3 numerical check*. The origin is conflating nearby but distinct image delays into a minimum representative when testing a stricter tolerance. This is **not proof** that each geometric sequence corresponds to a physically valid bounce sequence or that Sionna internal path vertices/materials are correct.
- Previous R2_aA ray (pose 915, index 62) is **not** a tie artifact: previous raw/merged residual both `5.1090357159952736e-14s`. Therefore recovered 25/25 tie does **not** mean all 26/26 G3 failures are the same.

## H reconstruction — directly demonstrated, not inferred
- With 23 original raw trace Jones/tau/angles, original SHA-verified LP+45/LP-45 FFD banks and 23 original pose/yaw, all **23 stored original m0 H rows** numerically reconstructed.
- Maximum over all 23 rows of `max(abs(H_rebuild-H_saved))/max(abs(H_saved))` = **`7.277741102925175e-16`**. This establishes provenance and implementation replay parity for those rows, **not physical correctness**.
- The retained earlier R2_aA single-row original 0°/45° H parity remains separately established in #40851669162.
- **Important scope:** the current preserved FULL_RF archive has m0 stores for the 5 recovered anchor/route groups, plus 45° for only R2_aA. Therefore **the other recovered 23 m45 H rows have not been parity-verified against historical stored H**. The earlier conditional 48-row m0/m45 exposure table was a hypothetical scope, not 48 rows actually present and checked.
- Original RA2 seven-case H -> packet replay passed 7/7 on its own archived-input terms, independently of G3 physical validity.

## Counterfactual sensitivity: illustrative only, not a correction
All offending raw tau for each location were hypothetically replaced by the nearest unmerged image delay while retaining Jones/angles. This **is not a physical repair**, and in fact all 25 traces already satisfy the unmerged G3 threshold. Its purpose is to measure numerical sensitivity.

- Largest relative `||ΔH||_2 / ||H||_2` across affected m0 locations: `4.41379057476847e-05`.
- Largest absolute `Δs` = `5.591089658141257e-06` (R5_aA x14.9640_y0.0469); largest recovered absolute `Δr` = 0 m.
- No first tap or selected RX port switch in 23 hypothetical comparisons.
- All 23 hypothetical `Δs` exceeded numerical packet-replay tolerance `1e-12`; **this is not an observational error found in historical packets**. It demonstrates that an arbitrary tau substitution has measurable effect in the detector even when delay residuals are picosecond fractions; its physical necessity and downstream effect remain unestablished.
- No B0/L0/L1/L2 EKF replay or mu/R refit justified solely by this counterfactual.

## Engineering and scientific decision
1. G3 implementation defect `stations=0` false PASS was separately confirmed historically; the revised strict G3 result should not be silently relabeled PASS. Record dual metrics: unmerged raw-image residual and original class residual, with preserved frozen thresholds. If the scientific G3 gate changes, do so through a new versioned acceptance contract, not retrospective replacement.
2. **25/25 recovered discrepancies: numerical class-representative attribution cause established.** The remaining previous R2_aA 1/26 is an actual unmerged strict excess, source-precision/RT geometry cause unresolved, though its original one-ray H counterfactual effect was below archived observation replay tolerances.
3. **H SOURCE VALIDITY: PASS in 23/23 recovered original m0 rows. H PHYSICAL VALIDITY: NOT PROVEN.** A perfect source reconstruction may faithfully reproduce shared upstream physical errors. Path vertices, visibility/occlusion, reflection order, material/Jones convention and FFD orientation need physics-level independent checks if claiming physical truth.
4. **Do not rewrite source tau to image delay.** Reconstructed original H agrees with archived H, and the 25 recovered G3 failures were caused by the validator's delay-class representative selection. No physics bug in tau/Jones was demonstrated by G3.
5. **No bulk H/BB/MB_VAR rerun authorized by present evidence.** Condition a local rerun on independently demonstrated physical source error, actual delta H/packet, original fixed fold/retraining effects and changed downstream output. Preserve original 392/336-arm results as retrospective conditional-on-H evidence.

## RA4 briefing (distinct executed workflow)
- [336-arm RA4 Action #40859507594](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40859507594) COMPLETED/SUCCESS; [results artifact](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40859507594/artifacts/12890904334).
- 28 correlated condition rows, original-vs-BB comparison:
  - mean only: BASE_FIXED heading 9/28, XY 17/28, both 8/28.
  - corrected mean + legacy variance: BASE_FIXED heading 23/28, XY 20/28, both 19/28; SELF_NIS heading 12/28, XY 12/28, both 8/28.
  - corrected mean + PRIOR variance: same improvement counts, not necessarily same numerical errors.
- RA4 result is technical retrospective evidence on the archived H, not independent scenes or deployable online q-clean correction. SELF_REVIEW_ONLY; independent audit pending.

## Required independent scientific validation
- Independent implementer verify 25/25 original raw image and merged-class residuals against raw NPZ and historic G3, not merely import current checker.
- For prior R2_aA unmerged violation, inspect original RT bounce vertices/path validity/solver precision before claiming physical solver error.
- If broader physical H truth is requested, validate actual Sionna path geometry (including reflection sequence feasibility) and coordinate/Jones/FFD conventions against a separate analytic/reference solver or bounded RT canary. H source-replay alone is not sufficient.
- Any future data changes must use new versioned immutable branch/manifest and never overwrite 2026-10-07 original evidence.

Verdicts: `G3_25_RECOVERED_TIE_CLASS_NUMERIC_CAUSE=SUPPORTED`; `G3_ALL_26_PHYSICAL_ROOT_CAUSE=PARTIAL`; `H_23_M0_SOURCE_RECONSTRUCTION=PASS`; `H_PHYSICAL_FINAL_VALIDITY=NOT_PROVEN`; `RA4_336_TECHNICAL_QA=COMPLETE`; `SCIENCE_RELEASE=SELF_REVIEW_ONLY`.
