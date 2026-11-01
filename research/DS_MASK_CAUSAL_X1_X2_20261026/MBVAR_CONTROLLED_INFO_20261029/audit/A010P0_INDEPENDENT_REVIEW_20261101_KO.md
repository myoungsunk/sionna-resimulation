# MBVAR-INFO-001 — A010-P0 재감사 및 A010-FREEZE 제안자 결정 (2026-11-01)

**독립 코드·GitHub Actions 수치검증: `PASS_NUMERICAL_RECALC_ONLY` (run [41277884578](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41277884578)).**

**최종 scientific freeze 판정: `REVISION_REQUIRED` / A010 본문 DRAFT 유지 / DEV3 20–29, HOLDOUT2, P3 NO-GO.** 구현자 `SELF_REVIEW_ONLY`와 감사 코드 자체가 다른 런너에서 실행된 수학 검증은 구분한다. 본 세션이 제안·감사를 함께 수행한 기록이므로 새 구현의 최종 독립 감사 서명으로 간주하지 않는다.

## 증거 출처

- audited implementation branch `research/mbvar-info-001-20261029`, HEAD `7fd49a0b03d9560cdb286162308a21c2dac508a5`.
- GEN run `41269011836`, execution sha `a55edb415da780bad670ec9fbf2fad650e9fbfd0`; ABL run `41269246996`, execution sha `12b359bfc90a8fcd8286b9af65d081a89d7a4c4e`.
- first-party source `contracts/AMENDMENT-010-P0.md` forensic FROZEN only; `contracts/AMENDMENT-010.md` science DRAFT.
- independent source `audit/a10_p0_independent_verify.py`: no import from implementation code, on a distinct Actions runner `41277884578`, artifact `13071134800`, SHA `ab05d5779b51eb87af68fdefe2ac11dc55abfae8e6c73c193a2e4ac03b7153e3` (as reported in job log).
- separate local independent arithmetic checked the same downloaded immutable GEN/ABL ZIPs. No new ray tracing, no re-optimization of all 1080 examples.

## Independently reproduced facts

| Check | Result |
|---|---|
| `Lhalf.npy` byte SHA256 | `b09450fad48dc9f7c4eea6b59f5fe40995d7544c851ee2ea7daad7a28fc78fca` matches |
| Canonical input ZIP byte SHA256 | `316efcc04946197cbb5c10417e3b6bfca3e4e8f5e4d3433535dfbba09b7bb9f3` matches |
| Canonical float64/int64 arrays | 48/48 SHA-by-dtype+shape+bytes matches |
| Independent GP K(LOW first 60 pose) vs `Lhalf@Lhalf.T` | max abs `5.44e-15` |
| Factor diagonal unit variance error | max `5.44e-15` |
| `Sigma_true`, `Sigma_model` per K1–K4 | finite, symmetric, positive definite |
| ABL | 88 rows: 4 keys × 2 replicas × 11 variants; no duplicates |
| Replicate A/B max abs cost deviation | `6.11e-13` (K2); others 0 |
| Replicate full rotated C10 10-entry relative difference | max `1.27e-12` (K2); others 0 |
| Explicit `nees4_C10=e^T P^{-1} e` from rotated full C10 | relative max `2.07e-12` |
| K2 truth-free best deep start | `psi+2`, `Δχ²=-0.0510995722`, `2.2106799449 d_ref`, Δx `0.0442135989 m` |
| Negative fixtures | 1-bit z flip / absent array / 1-ULP factor change all detected |
| Manifests | GEN 4 + ABL 6 output SHA entries verified; `PASS` and no schema errors |

**Limits:** `Lhalf@Lhalf.T` over the first 60 LOW poses was independently checked against the analytic kernel. The **entire 180-pose K matrix** was not separately reconstructed by the audit script, and the independent runner did not reexecute the nonlinear FFD optimizer. The ABL job did that; this audit recalculated its outputs and checks, not an entirely separate numerical optimization.

## Mechanism decisions

**R1 canonical input:** ACCEPT. The previous C3/C3V4 input generator reproducibility problem is eliminated for the four verified forensic keys when original receipt bytes are replayed. Generalization to DEV3 requires explicit new receipt checks.

**R2 deep polish:** CONDITIONAL SECONDARY. K1/K4 cost improvements ~`-6.72e-4` / `-4.38e-4` χ² are real, but solutions change and thus constitute a new estimator. Do not silently replace S1V4 primary. The optional deep arm must be declared before DEV3 and must report compute cap, timing, and estimator changes.

**R3 kink special tolerance:** REJECT FOR PRIMARY G5. Canonical byte-replay passed the ORIGINAL strict tolerances by many orders of magnitude. Do not weaken tolerance based on historical C3 FAIL; no new geometric kink exception required to verify exact-input reproducibility. Keep strict rules unchanged.

**R4 alternate solution:** RECOGNIZE AS SCIENTIFIC `AMBIGUOUS_STATE_IDENTIFICATION`. K2 has two close-cost, different-state, smooth solutions under fixed truth-free starts. Deep polish alone does not change mode; strong candidate start `psi+2` has same expected posterior uncertainty direction locally. Report independent event rate and impact on H1/H2/CAL in DEV3 if a *prospectively frozen* diagnostic arm is permitted. Truth-based start MUST NOT select the operational estimator.

**Primary estimator for DEV3:** PROPOSE S1V4 frozen algorithm unchanged as PRIMARY with **new canonical frozen field generation inputs**; deep-polish and fixed-grid best-start separately labelled exploratory/diagnostic, never silently merged into main H tests. This maintains comparison to preregistered S1V3/S1V4 H1/H2 results.

**Known A010-P0 implementation aggregation defect:** `TAU=1e-9` rows exist in `A010_DEV2_ABLATION.csv`, but `A010_NUMERICAL_DIAGNOSTICS.json` omission due to float exact equality. Original P0 result stays immutable. In the NEXT script, compare logarithmic tau with a registered relative tolerance or normalize tau names; add negative fixture that the `1e-9` group has exactly 3 perturbation seeds. No backwards-changing the forensic result.

**G2/G4/G5 remaining:** G2 E′ vs E mixing corrected in next source; G4 `multi_excl` must block automatic HOLDOUT power-as-authorization and report changed population; G5 compares full C10 10 unique entries and NEES4, not diagonal only. Original A009 CI with `EXCLUSION_CHANGES_RESULT` and power emitted is a known technical release-gate flaw that must be fixed prospectively.

**G7:** RFRES `FP_SWITCH` was Full-vs-LoS tap index disagreement at a given pose, not sequential first-path change. New metric definitions are separated in A010 retrospective diagnostics. `TAP_SENSITIVE` from Option B remains a mandatory RF risk, not a measured receiver error rate.

## Next permitted implementation / execution

- **GO:** new A010-DRAFT isolated development branch and static/SMOKE checks on existing DEV2 forensic inputs only; explicit source code locks, no tests with DEV3 or HOLDOUT2 field IDs. An auditor with independent code path must inspect the final proposed S1V5/C3V5 implementation.
- **BEFORE DEV3:** resolve A010 primary estimator/mode policy, canonical-input storage scope, reproducibility numerical gates and per-group denominator; freeze A010 SHA/code/field split and obtain distinct audit approval.
- **NO-GO:** DEV3 (20–29) until A010 full contract independently accepted; HOLDOUT2 (5000–5059), physical RT P3 until dependent gates passed.
- **Scientific status:** S0V2 analytically establishes an interaction for its synthetic model. S1V3/V4 DEV2 did **not support** the specific H1 LOW POSE_HIGH tan and H2 tan predictions; numerical replay fix must not erase this observed outcome.

This document is an append-only audit/proposer analysis. It is not a frozen amendment or independent science release.
