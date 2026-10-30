# MBVAR-INFO-001 — AMENDMENT-010 제안자 구현 인수 계약 (DRAFT, 실행 승인 전)

> **권한:** `role=PROPOSER`, `contract_id=MBVAR-INFO-001`. 본 문서는 지침·결정안이며 **FROZEN 계약이 아니다.** 구현자와 다른 세션의 독립 감사자가 원본 코드·반례·해시·과학적 추론을 검증해야 한다. 본 세션은 제안/감사 관점을 함께 작성하므로 `INDEPENDENT_AUDITOR_SIGNED=false`.
>
> **입력:** implementation branch `research/mbvar-info-001-20261029`, audit source SHA `5f537ab2734e8f354f27302dc6815554cb03a64a`. Prior S1V3 `40981032471`, S1V4 `40992623257`, C3 `40992589158` FAIL, C3V4 `41005158792` FAIL. Original rules, input and artifacts immutable. Original governance SHA `250d617ad89a4105fa1af546cc83ceed9de98f42`. Contract SHA256 `68d73bd22bf467625559f3092433f250cbe91cb2fef011f92151975975b00f34`. Frozen A009 `cbcd76e67af6765f501de49e9b72221c204848d3`.

## Decision — choose modified Option 1, NOT an omnibus pass patch

- **R1 canonical input:** ACCEPT and mandatory. Freeze the exact `Lhalf` float64 byte array `180x180`, the pose-ledger order, full true+modeled observation covariance arrays and per (field,role,cell,sensor) `z,x0,ds_m,gy_m,taps`. `Lhalf.npy` is not currently covered by the repo's `*.npz` LFS rule; record SHA256, shape, dtype, endianness. Archive bytes in immutable input assets. Do not merely store seed or covariance trace/Frobenius/\(\Sigma r\) fingerprint.
- **R2 robust polishing:** CONDITIONALLY ACCEPT as a **separately labelled candidate**, \(\tau_{\rm cost}=10^{-9}\chi^2\) / maximum 300 accepted/proposed steps. Retain `S1V4` as baseline arm. Log full cost monotonicity, accepted steps, cap, time, E→E' state, and per-row C10 P. Do not claim it solves alternative mode selection. Limit large-scale work until the known bad row and non-kink controls are checked.
- **R3 replay tolerance:** Do **not** use relaxed thresholds to relabel historical C3/C3V4 PASS. For new DEV3 prospective testing, retain strict original metrics side by side. Candidate portable-solver equivalence metrics: an independent canonical INPUT_EXACT hard gate; smooth no-kink rows use old tolerance (state ≤1e-6 d_ref, cost ≤1e-6 chi², P diag rel ≤1e-3), **geometrically verified** kink-near rows additionally report proposed ≤1e-2 d_ref, ≤1e-5 chi², ≤1e-2 relative covariance (only if full-key population impact checks pass). This candidate bound was formulated **after seeing C3** and cannot claim a blind pre-C3 proof. If kink distance to a known 1° interpolation cell boundary cannot be independently computed, mark `KINK_CLASS_UNCERTAIN` and do not grant a favorable exception based on `LOCAL_MIN_CERTIFIED` or failed-run outcomes. No new gates silently override original pass flags.
- **R4 close minima:** Do NOT silently turn `STATE_STABILITY_FIXED` FAIL into a reproduction PASS. Define `AMBIGUOUS_STATE_IDENTIFICATION` when the existing registered pair of conditions \(\Delta C\le1\chi^2\) and end-state distance \(>2d_{\rm ref}\) both occur. Forensic (pre-DEV3) comparison: (i) unmodified `S1V4` E'; (ii) deeper-polished E'; (iii) truth-free nine-start **diagnostic candidate** (yaw k = −3..+3 SD, x+1 SD, y+1 SD; `psi0` is the default start); choose the lowest observed objective under its predeclared search. `truth` start may be recorded only as `ORACLE_ONLY` and may NEVER select an estimator solution. No candidate is promoted to the main H-tests until a separate prospective frozen choice. If near-equal but meaningfully different solutions persist, record state/covariance/mode ambiguity and test scientific sensitivity rather than hiding it.
- **R5 reproducibility architecture:** Do not rely solely on setting `OPENBLAS_CORETYPE` or disabling AVX. Pin environment/NumPy/SciPy/FFT and thread count as diagnostics, but use immutable **canonical inputs** for primary C3V5 to isolate solver differences.

## Phase A010-P0: forensic ablations on existing DEV2 (not confirmatory, no new AUC claim)

1. Recompute `Kp`; once on a designated deterministic generator runner, serialize `Lhalf.npy`. Verify \(L L^\top\) matches Kp (PSD projection and diagonal), with mathematically justified fixed tolerance. Lock SHA and source, pose order, config/FFD SHA.
2. Generate a paired set of inputs for field 10 LOW TIME_1 sensor2 ORACLE and field 11 REV60 TIME_HIGH_5 sensor0 ORACLE, plus one non-kink and one POSE_HIGH case. Compare:
   - fresh local regen from `eigh`,
   - frozen-`Lhalf` regen,
   - **byte-for-byte input receipt replay**.
   Report independently `INPUT_EXACT`, `GENERATOR_DISTRIBUTION`, `SAME_INPUT_SOLVER`, `FORWARD_FFD`.
3. For field10 exact receipts: sweep \(\tau_{\rm cost}=10^{-3},10^{-6},10^{-9}\) with fixed max steps; record E' final state, \(\chi^2\), C10 P and full matrix; perform \(\pm10^{-14}\) perturbation negative fixture. No tuning of thresholds after DEV3.
4. For field11 exact receipts: compare the prior original result, `psi+2` alternate, and diagnostic fixed start grid, compute \(\Delta\chi^2\), coordinate-wise \(d_{\rm ref}\), posterior-SD distance and H1/H2/CAL impact for a paired sample. Check whether two modes are connected by a flat valley using a fixed interpolation path/profiling of objective; do not call a single Gauss-Newton Hessian a proof of unique posterior.
5. Repeat selected cases on at least two distinct runner CPU/library configurations from **identical archived inputs**. Fail closed on missing original key or hash.

### Machine-readable outputs

`A010_GENERATOR_FACTOR_LOCK.json`, `A010_INPUT_CANONICAL_SHA.csv`, `A010_DEV2_ABLATION.csv`, `A010_MODE_PROFILE.csv`, `A010_NUMERICAL_DIAGNOSTICS.json`, `MANIFEST.json`, and negative fixture report. Full original inputs under nonoverwritten paths.

## Phase A010-FREEZE: decide primary estimator and thresholds, before DEV3

- The **default primary scientific comparator remains unchanged S1V4** until a distinct prospective estimator is approved. If choosing a deeper solver or fixed-grid best-start as primary `S1V5`, disclose that it is a *new estimator* and freeze it separately; preserve paired S1V4 outputs as a baseline.
- **Never treat a cost difference ≤1 chi² as unique optimality.** Record ambiguity if different solution states lead to different scientific claims.
- **G4 interpretive split:** Jacobian method differences *on identical keys* are pure P-convention sensitivity. Excluding kink cases changes the target population, and should be reported as subgroup heterogeneity/selection sensitivity, not automatically as evidence that P itself is wrong. **Primary H tests continue on all valid fixed keys.** `EXCLUSION_CHANGES_RESULT` remains a MATERIAL caveat; do not print power as authorization or assert a single universal mechanism if subgroups conflict. Any change of the old A009 G4 policy needs a distinct logged prospective rule; old A009 remains FAIL where applicable.
- Lock original + new gate outputs, source/contract/governance SHAs, split seed list and `RUN_REQUEST`. Audit as independent actor on frozen hash. New `DEV3=20..29` is opened only after this freeze; HOLDOUT2 5000..5059 and 5060..5119 remain sealed.

## Phase A010-DEV3 / C3V5: exact tests and release gates

| Gate | Operation & required evidence | FAIL behavior |
|---|---|---|
| G5-I exact input | Hash all canonical raw arrays `z,x0,ds_m,gy_m,taps,poses,full Sigma_true,Sigma_model`; exact match of keys/dtype/shape; `INPUT_EXACT` independent of output tolerance | STOP, no substitution with fresh `eigh` |
| G5-D field law | Independent `Lhalf*Lhalf.T` PSD and Kp checks, duplicate-pose identity, white/time component distributions; per `field_id` untouched | FAIL generator; do not silently redraw |
| G5-O numerical solution | Compare same frozen-input MAP estimates and objective on at least two runners, old strict pass flags **and** new portable metrics. No outcome-based kink exceptions. | `NUMERIC_UNSTABLE`; preserve all |
| G5-M mode ambiguity | Frozen fixed-grid non-truth starts (diagnostic), \(\Delta\chi²\), \(\Delta x\), uncertainty and science-claim impact. Never choose truth start for estimate. | `AMBIGUOUS_STATE_IDENTIFICATION`, scientific single-estimate claims withheld if impact material |
| G5-P 4x4 covariance | Compare ten unique C10 entries using symmetric coordinate scales, PSD/condition and `nees4_C10`; diagonal alone insufficient | FAIL full covariance replay |
| G2/G4 corrections | G2 compare both final E' `dec_A_fixed` and final probe; G4 output all method-fixed-key tests and subgroup selection counts; failure changes are not suppressed | FAIL release automation |
| CAL/SCIENCE | Under same fixed input, compare H1/H2/H3/CAL/H4 statistics and CI/NEES across original/new estimator and replay convention. All invalid and ambiguous cases reported. | No single-claim adoption if material changes |
| TEST SEAL | `DEV3` is engineering/dev, not final; all new results kept out of HOLDOUT2; **separate audit** required | HOLDOUT2 NO-GO |

**Candidate portable solver thresholds** for geometrically audited kink-near rows: \(\max_j|\Delta x_j|/d_{{ref},j}\le10^{-2}\), \(|\Delta\chi²|\le10^{-5}\), \(\max|P^{(1)}-P^{(2)}|/\mathrm{scale}(P)\le10^{-2}\), and \(|\Delta\log\mathrm{inflation}|\le0.02\) for key primary state contrasts plus unchanged pre-registered categorical verdict. This \(\log\)-influence check is **not** a substitute for retained original strict fail status. If no justified geometric kink classifier is available, do not apply kink-only tolerance. Numeric thresholds must be finalized before DEV3 and accepted independently.

## Decisions for legacy G1–G7 and physical RT

- G1 S1V3/S1V4 = technical PASS under original code (not retro scientific PASS).
- G2 v3.1 fix on DEV2 = supported; maintain separate E' state-consistent diagnostic rather than mixing old E and E' metrics.
- G3 C10 P strata = no FAIL on DEV2, RV nonkink 2 UNDETERMINED; calibrated posterior not guaranteed in new scenes.
- G4 `EXCLUSION_CHANGES_RESULT` observed and power emitted: this release bug remains until repaired. Do not use those power files as user permission to unseal HOLDOUT.
- G5 C3/C3V4 = FAIL, not superseded by new threshold.
- G6 HOLDOUT2 remains closed pending new independent audit and explicit user decision.
- G7 P3 RT no-go; Option B `TAP_SENSITIVE` (1-tap error 10% raises Oracle heading RMSE ~1.70×), Option C historical RT BIAS/SCALE/NON_GAUSSIAN/FP_SWITCH/CORR_MISMATCH must be reflected in RT detector, real-complex-channel parity and common-plate design. New RT run requires independent signed pre-P3 lock and user-approved numeric budget.

### 추가 G7 교정: Full/LoS tap 불일치와 시간적 tap 변화 분리

`c_rfres.py`의 기존 `fp_switch=(idxF!=idxL)`는 **동일 pose의 Full vs LoS-only 검출 인덱스 불일치**를 뜻한다. 29–54 %는 시간 연속 프레임 사이의 tap 변동률이 아니다. A010 별도 사후 기록에서 `FULL_LOS_TAP_DISAGREE`, `TEMPORAL_TAP_CHANGE_FULL`, `TEMPORAL_TAP_CHANGE_LOS`, `TIME_CHANGE_OF_DISAGREEMENT` 네 지표를 서로 혼동하지 말고 정의/계산한다. 기존 A009 출력·임계값·성능 결과는 덮어쓰지 않는다. 사용자와 감사자에게 기존 `FP_SWITCH` 해석 수정을 명시하고, 실제 P3 tap 전환 검증에서는 시간 연속 프레임 차이와 단일 pose에서 Full–LoS 차이를 모두 판정한다.

## Output contract / signoff

All new reports append-only under `results/P2_A010_*` and `reviews/A010_*`. Emit code diff vs frozen A009 SHA, input, output and source SHA256, commands, system info, an explicit reason for every STOP and every primary/subgroup classification; no deleted rows. The proposer approves science changes, the implementer self-tests, the independent auditor signs only after a **distinct** execution and source check. **No auto-HOLDOUT, no auto-RT**.

**CURRENT: A010 DRAFT; no A010 code or DEV3 has been run as a result of this document.**
