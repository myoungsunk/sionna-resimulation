# MBVAR-INFO-001 AMENDMENT-009 — 독립 감사 (2026-10-30 KST)

**Verdict:** \`REVISION_REQUIRED_GATE_LOGIC\` / \`C3V4 TECHNICAL RUN CONDITIONALLY GO\` / \`HOLDOUT2 NO-GO\` / \`P3 RT NO-GO\`.

## 0. 범위·권한·출처

- **계약:** \`MBVAR-INFO-001\`, base contract SHA256 \`68d73bd22bf467625559f3092433f250cbe91cb3f250cbe91cb...\` (**canonical full SHA**: \`68d73bd22bf467625559f3092433f250cbe91cb2fef011f92151975975b00f34\`), A009 frozen at commit \`cbcd76e67af6765f501de49e9b72221c204848d3\`.
- **A009 freeze timing:** \`git compare bf17158...cbcd76e\` shows **no code or tests file changes**, only A009 text and S1V3 results. Independent Git blob spot checks: \`a9_class.py\`, \`s1v4.py\`, \`c3v4.py\`, \`b_tap.py\`, \`c_rfres.py\`, \`tests/test_a9_class.py\`, and frozen A008 files unchanged between draft and freeze. Source blobs used by four CI run commits match freeze blobs.
- **Prior execution:** S1V3 DEV2 run \`40981032471\` (PASS technical). Original aggregate artifact \`mi-aggregate-40981032471\` artifact id \`12946712270\` was downloaded and independently parsed. 1980 rows, 1080 batch, unique composite keys 1980/1980, SHA of archived outputs compared to MANIFEST with **no mismatches in existing referenced files**.
- **A009 in-flight at last review check:** C3 \`40992589158\` in progress; S1V4 \`40992623257\`, BTAP \`40992660047\`, RFRES \`40992695655\` queued. **This report does not claim those runs passed.** Read newest run status/QA before any release decision.
- **Independence:** Code/contract inspection with separate reviewer and independent raw-CSV arithmetic, not implementer helper. No new full FFD rerun, no S1V4/C3V4 1080-case QA performed. Original implementation and run artifacts remain untouched. This review itself is **not** an independent numerical replication of every run.

## 1. Verified science results (S1V3 DEV2; pilot, not confirmatory)

- S1V3: 1980/1980 OK, 1080 batch, \`NOT_CERTIFIED\` 0 under A008 (original rule), C10 P PD all; 11 polished batch rows; no KINK_P_UNCERTAIN under 5% diag-spread convention.
- S1V3 G2 retrospective W1: **four** cases \`dec_A_fixed<=1e-10\` and \`probe_min_dcost<-0.01\`, all XMODEL, all \`kink_poses_at_E=0\` under tiny 1e-6 probe; this is not evidence they sit *exactly on* a sampled knot. They can have descending central-FD steps crossing a knot/curvature at a larger stencil. Original A008 technical status remains as recorded, but **new v3.1 classification would fail three per-cell gates (one cell 2/30)**. Treat A008 claim about convergence as retrospective invalidated, without rewriting run.
- S1V3 H2 tan: observed DID ~\`-0.98970\`, 95% field bootstrap CI \`[-1.5638,-0.1464]\`, S0 predicted \`+0.43486\`. Original raw-row independent calculation gives \`-0.99027\` (round/aggregation differences).
- **Key mechanism decomposition**, independently from 10 per-field means of batch rows: H2 tan log-DID of actual MSE = \`-0.96603\`; log-DID of claimed C10 P = \`+0.02424\`; total \`-0.99027\`. **Zero of the 120 IID_BATCH rows used for H2 (4 cells ×30) were polished under S1V3.** Thus neither changes in E' polish nor a large change in the P denominator explain the observed H2 tan sign reversal *in this pilot*. Remaining candidates: nonlinear forward/inference effect, field sampling variation, geometry/state coupling.
- Heading H2 psi: observed ~\`-0.7848\` vs S0 \`-0.42765\` (direction matched). Under \`s1v2.decide_v2\` **H2 psi is the preregistered primary H2**, tan is secondary. Overall \`NOT_SUPPORTED\` is driven by **H1 LOW/POSE_HIGH/tan FAIL**, not by secondary tan H2 alone.
- Six of eight A8-5 ORACLE C10 calibration strata passed and two RV/nonkink strata undetermined; no A8-5 FAIL. Field n=10 means inconclusive precision and power n=60 underpowered at upper cap.
- All these statements remain synthetic **FFD LoS with Gaussian spatial/time residuals, ideal true tap**, anchor A; do not claim independent physical ray-traced RF validation.

## 2. Local SMOKE technical value

Reported reduced \`SMOKE 900/901\` exercises S1V4/C3V4/BTAP and a single-case RFRES code path. It validates the existence of the execution path, Python imports/shapes, serialization, and that basic unit checks can be reached. It **does not** establish:
- all 10 DEV2 fields, 1080 batch rows, per-cell zero-NOT_CERTIFIED rule;
- C3V4 source/input/cost/complete-P reproducibility or independent optimizer calibration at knots;
- BTAP field-level robustness or confidence in physical detector errors;
- RT residual transfer conclusions across seven correlated corridor cases;
- scientific H1/H2/H3/CAL/H4, or independence of a second code path.
Preserve SMOKE as software smoke, not preregistered quantitative evidence.

## 3. G1–G7 audit

| Gate | Evidence | Audit status/needed correction |
|---|---|---|
| G1 | S1V3 40981032471 PASS; S1V4 40992623257 pending | \`PENDING\`. New \`S1V4_QA.pass\` tests expected total rows, statuses, Mahalanobis, revisit and C10 PD etc. \`n_input_receipt_files\` is **recorded but not compared** to number of field files in \`pass\`. Independently assert \`n_receipts==10\`, unique (field,role,cell,sensor_seed,arm) and full key coverage before accepting. C3V4 INPUT_REPRO should catch absent receipts but is a separate gate. |
| G2 | A008 4 counterexamples, class v3.1 new code | \`PENDING/LOGIC FIX\`. Source \`s1v4.py::cmd_aggregate\` computes \`G2_smooth_with_probe_descent\` from **old E \`newton_decrement\`** plus **E' post-polish \`probe_min_dcost\`**. They are different evaluation points. A correct final-state diagnostic uses \`dec_A_fixed\` and \`probe_min_dcost\` from the same E' point, with row keys reported. Additional \`class_v31\` must reject any descent >0.01 even when analytic decrement <=1e-10. The A9 code does have the correct order \`a9_class.class_v31\`; existing unit negative test covers the A008 counterexample. Do not silently repin A009 code during an in-flight run; independently recompute from stored S1V4 CSV, preserve original output, and use explicit follow-up audit/amendment for change. |
| G3 | A8-5 8 named kink×LH/RV×tan/psi + C10 NEES4 reported | S1V3 6 PASS/2 UNDETERMINED; S1V4 pending. \`nees4_C10\` is a full 4×4 covariance-based quantity at the end pose, but being numerically stable or PD is **not** proof of true posterior calibration. Include n_independent_fields and coverage. If stratum unavailable mark UNDETERMINED, not PASS; any actual CALIBRATION_FAIL blocks calibration claim. |
| G4 | Six P conventions and two exclusion sensitivity filters | \`PENDING/LOGIC FIX\`. A009 correctly separates \`A86_convention_outcome\` and \`A86_exclusion_outcome\`. **But \`s1v4.cmd_aggregate\` computes power when \`not multi_conv\`, ignoring \`multi_excl\`.** It can propose n_confirm even if \`EXCLUSION_CHANGES_RESULT\`, contrary to A009 no-single-conclusion rule. Independent G4 must block a single adoption when either changes, or label the power as non-authorizing diagnostic. Exclusion is **sample selection**, not a pure P-method intervention; report rows and independent field counts for all compared arms/cells. In S1V3 358/1080 batch rows had a detected kink; deleting them left some primary ORACLE cells only 8/10 fields. |
| G5 | C3 A008 and C3V4 A009 | C3 in progress; C3V4 **CONDITIONALLY GO only after S1V4 aggregate and receipt publication**. It is legitimate technical replay (not independent science audit). S1V4/C3V4 compares diag P_C10 and state/cost/status, but \`c3v4.py\` does **not** compare all ten rotated full-C10 covariance entries or \`nees4_C10\`. Thus F4 joint covariance reproducibility is *not fully certified* by C3V4 PASS. Add separate audit-only complete 4×4/NEES verification before scientific full-state claim. |
| G6 | HOLDOUT2 5000–5059 | **NO-GO** until G1–G5, including gate logic audit and independent signed review. A valid \`NOT_SUPPORTED\` is legitimate hypothesis result; technical QA alone is not. Underpowered-at-60 status remains and is not a justification to modify thresholds after observing holdout. |
| G7 | signed pre-P3 RT amendment | **NO-GO**. Shared C10 plate and <=8-tap specular geometry are pre-RT only; must demonstrate actual complex H, extracted tap from modeled CIR, detector/port parity, material and solver assumptions, bounded independent scene variants, and explicitly approved numeric compute budget. Option C historical RT is diagnostic, not new physical RT validation. |

## 4. Option B / C pre-RT usefulness

**BTAP (B).** The generator remains \`z=h_{\rm FFD,true-tap}+\epsilon\` and only the estimator tap information changes. ±1/±4 detector indices at 10% of poses are **synthetic stress tests**, not a calibrated detector-error distribution. \`ROBUST\` requires only identical **categorical H1/H2/H3/CAL verdicts**, so it can remain ROBUST when continuous Heading RMSE doubles. Store paired field-level RMSE/MSE ratios, tap-error rate and gate/coverage alongside the verdict. The local SMOKE 0.68°→1.25°/2.06° is **not** formal evidence. Match tap-known recursive EKF vs batch when comparing covariance models.

**RFRES (C).** Uses the already analyzed DRIVE_SIM BLOCK_C Full/LoS channels. The quantity \`obs(Full)-obs(LoS)\` is a valid *difference of nonlinear receiver outputs* and captures detector tap switches; it is **not** the complex-path additive contribution at a common tap. Pair-based correlogram \`n_pairs>=200\` consists of dependent spatial pairs from the same trajectory; do **not** count pair number as independent scenes or statistical power. Descriptive BIAS/SCALE/NON_GAUSSIAN/FP_SWITCH/CORR flags are useful pre-P3 risk indicators only.

## 5. Proposer recommendations / decisions

1. **Allow** existing frozen CI runs C3/S1V4/BTAP/RFRES to finish; preserve their outputs unchanged including FAIL. No new rule/code edits while these runs are in flight.
2. **C3V4 engineering execution** is conditionally authorized once committed \`S1V4_RESULTS_DEV2.csv\`, ten input receipts and manifest are available, matching the frozen A009 code. If S1V4 QA FAIL, C3V4 is permitted only for **forensic reproduction**, not gate release; no HOLDOUT2.
3. **Before any HOLDOUT2:** independent audit-only recompute of G2 final-point flag, G4 paired sample counts and \`multi_excl\` handling, G5 full C10 covariance/NEES, plus original G1–G5 technical outcomes. Fix demonstrated release-gate defects prospectively using a separately named amendment/addendum; do not retroactively make A009 PASS.
4. **H2 tan sign mismatch:** do **not** change S0 predictor or H2 thresholds based on the observed sign reversal. If explanatory analysis is necessary, use the same fixed DEV2 fields and cached RF/FFD assets to separate linearized exact Gaussian posterior vs nonlinear MAP, and MSE numerator vs P denominator, while preserving untouched HOLDOUT2. This is exploratory diagnostic, not a new confirmatory arm.
5. **No new large-scale RT now.** Option B/C may provide a small risk/assumption check; A008/A009 Track S completion precedes pre-P3 physical canary approval.

## 6. Verdict and execution order

\`S1V3 technical=PASS\`, \`S1V3 scientific pilot=NOT_SUPPORTED\`, \`A009 code/freeze provenance=SUPPORTED\`, \`A009 local SMOKE=PIPELINE_ONLY\`, \`G1–G5=NOT_COMPLETE\`, \`C3V4=CONDITIONAL_TECHNICAL_GO\`, \`HOLDOUT2=NO-GO\`, \`P3_RT=NO-GO\`.

These statements refer to the run states **at audit observation time**, not guaranteed future statuses. Refer to GitHub Actions URLs at actual handoff for up-to-date completion records. This report is an independent evidence and design review, **not** full independent FFD rerun or joint signed scientific release.
