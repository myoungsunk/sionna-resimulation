# DLP-EKF-GAPS-001 / P3 — New third-anchor geometry and SourceFFD direct-LoS canary

**PROPOSER_LOCKED — AUDITOR_PENDING — FROZEN=FALSE — P3 NOT_RUN.**

## Parent and question

P1 SourceFFD source/native parity and the completed P2 recursive DR4 vs R4 vs J4_SRC were physically based on the same one Corridor C0 with only two existing anchor positions A=(4,0,2.65) and B=(10,0,2.65) metres. P2 Full and LoS results are retrospective, not multiple RF environments.

Question: Can a **third noncollinear ceiling anchor C** be specified in the same 20×2.4×2.7m corridor, with valid physical LoS geometry and the same actual FFD source/observation process, without fabricating missing multipath H or synchronized packets?

P3 is **strictly a bounded canary**, not P4 three-anchor RF production or 4-state filter replay. The planned fixed C=(16,0.8,2.65)m yields horizontal triangle area 2.4m², a different y-coordinate from A/B, and ceiling transmitter boresight down via diag(1,-1,-1). The case uses the same tag antenna z=0.45m, TX+45°, dual RX ±45°, 257 bins and 1028 tap IFFT. Geometry, sample-selection algorithm and test thresholds must be frozen **before** computing any new C pilot spectra.

## Source classes / proof boundary

Original C0 7 case-pairs include only A/B. Original R2/R4/R5 pose/timestamps and the A/B original Native LoS H must be verified by raw bytes/hash. The C TX complex channel is **NOT** in the locked original RF manifest. P3 will calculate a new synthetic *source-FFD direct-only LoS* H as an independent field-model canary, with a physically specified single geometric ray per anchor/pose, **not** native Sionna-RT output or a measured packet. This is a model-generated test; it cannot be called third-anchor multipath evidence.

For original A and B, randomly plus adversarially selected deterministic pose IDs from all three original route timelines will be compared with their actual frozen Native LoS, including first-path tap, signed s and complex channel. For C, SourceFFD spectrum versus separate direct spherical-field/vector contraction and independent H→Hann→IFFT detector are tested on pilot points away from the source-specific near-pole cap, while cap behavior is separately recorded as a non-native interpolation region.

Original same-route timestamp/pose IDs remain **source timeline labels only**, not evidence of physical synchronized RF packet arrivals from 3 transmitters. Direct H path count is assumed one by construction. **Native Sionna-RT path counts are not measured** unless an independently frozen RT canary + resource budget later exists. Never write fabricated physical path counts.

## Proposed test gates

P00 unchanged original P2/P1 hash and C0 only-two-anchor inventory; P01 original route exact time and pose correspondence; P02 C inside scene and triangle area; P03 unobstructed **empty rectangular prism geometry** for line-of-sight segments and proper antenna frames; P04 geometrical two-dimensional [x,y] range-Jacobian rank and crosscheck finite-difference derivatives; P05 physical bank bytes and FFD frequency + field finiteness; P06 genuine original A/B NativeLoS parity on deterministic pilot samples; P07 third C SourceFFD direct-H vs independent field contraction for non-cap points; P08 independent leading-edge H→CIR→[r,s] / first-tap parity; P09 cap, seam and yaw 2π marker; P10 original pose/time source/step and failure ledger, no silent omission; P11 resource and claim boundary; P12 append-only artifacts and receipts.

Numerical thresholds are fixed in P3_NUMERIC_TOLERANCES.json. If a check fails, report FAIL and all cases, no posthoc anchor movement, fit or tolerance change. No definitive "new RF channel generated" without actual RT output and source manifest. C cannot receive an artificial original C0 H or an independent measurement clock. No new RayTracing solver is launched under this phase; the separate RT computational budget is unresolved, and P4 is not authorized by P3.

## Transition criteria

A separate GitHub Actions pre-run mathematical/geometry audit must compare P3_CONFIG_LOCK + P3_NUMERIC_TOLERANCES and source bank snapshots, and produce an evidence SHA. Only after that, issue append-only P3 FROZEN ratification against untouched proposer hashes. Then execute SourceFFD/direct-LoS canary and independently verify rows. A successful P3 source/geometry canary is **not** a signed Sionna multipath physical canary. P4 remains BLOCKED_RT_INPUT until real native H_FULL/H_LoS of C, path counts, common timestamps/clocks, an RT budget and a dedicated separate approval/contract.

Proposer role is authored by the user's explicit request "P2 완료한뒤, p3 실행한다". Same account/GitHub and same model conversation as auditor implementation cannot impersonate an independently authenticated human reviewer; separate GitHub Linux runner is separate compute provenance only.
