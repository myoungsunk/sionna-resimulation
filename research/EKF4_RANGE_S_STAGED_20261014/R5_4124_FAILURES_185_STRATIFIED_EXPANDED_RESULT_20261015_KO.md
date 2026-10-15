# R5 원본 LUT 경계 인식형 MAP 확대 검증 보고 (2026-10-15)

## 범위·실행 결과

**결론:** 원본 P4 R4 solver·Gaussian MAP 목적함수·원본 LoS LUT·R0 Q/R·gate 및 gradient threshold를 **수정하지 않은 별도 비매끄러운 연구용 솔버 파일럿**에서, 4,124건의 원본 수치 실패를 재현하고 185건 층화 표본에서 local candidate 품질을 검사했다. 이 검증은 원본 P4 결과를 소급 PASS로 만들지 않는다. `scientific_PASS=false`.

- Original archived P4: [Run 38658117256](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38658117256), artifact `11937707221`, original ZIP SHA256 `db1bda22f9fdbb56ba95817ea4c02016bba294c35a4c126daca448284a285ec4`; source `46d679a32f55cae460d9ed35b4bb944bc48cc4ce`.
- Expanded fixed-input validation exact commit `119dab26bfa3f370b56001b41c6e26ad5c983348`. [Run 38677036116, attempt 2](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38677036116), [artifact 11947760931](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38677036116/artifacts/11947760931), SHA256 `dfc9c3ed43ac82e27c152141c563fc71c9767545f3ed644126669dc891995bf2`. Audit GO, source ZIP checksum/CRC PASS, 18 mathematical/source regression tests PASS, complete artifact CRC PASS.
- Previous attempt 1 of the **same source SHA**, artifact `11945834661`: 4,034/4,124 identical status+gradient replays; **90 source-identical Anchor-B failures had status or gradient mismatch**. Outcome cannot be attributed to changed LUT/source. The exact cause (float environment/BLAS/near discontinuity/order etc.) is not yet isolated. Attempt 1 was FAIL/HOLD and is NOT retroactively PASS; attempt 2 reproduced 4,124/4,124. Therefore portability/reproducibility across hosted numerical environments remains an outstanding issue.

## Full 4,124 original invalid model-attempt geometry

| Source failure class | All original cases | Terminal LUT grid distance ≤0.001° | Percentage |
|---|---:|---:|---:|
| LINE_SEARCH_FAILED | 3,369 | 3,357 | 99.64% |
| MAX_ITERATIONS | 755 | 9 | 1.19% |
| total | 4,124 | 3,366 | 81.62% |

Remaining **12 invalid LUT geometry** (near anchor horizontal singularity) were kept and reported, not silently deleted. 2-degree LUT facets at theta/phi_tx/phi_rx. 3,357/3,369 line-search failures are on/near LUT grid knot; boundary association is strong but not a formal universal causal proof. MAX_ITERATIONS failures generally have separate local convergence/numerical cause.

## 185 deliberately stratified candidate validation

Sample selection predetermined seed `20261015`, 28 (7-case × 2 channels × 2 initialization methods) strata, 6 per stratum (168), plus historical 20 controls, **185 unique frozen invalid inputs**; deliberately close/far-to-knot extremes + reproducibly hash-ranked cases. Not a prevalence estimator for 4,124 or new RF environments.

| Candidate outcome | Count |
|---|---:|
| `NONSMMOOTH_LOCAL_CANDIDATE_VERIFIED` (approximate probes and sampled Clarke hull) | **177** |
| `NONSMMOOTH_LOCAL_UNVERIFIED` | **5** |
| `EXPORT_OBJECTIVE_INCREASE_BLOCKED` | **3** |
| `DIAGNOSTIC_ERROR` in final run | **0** |
| Original smooth 1e−8 gradient passes at new candidates | 3 (NOT 177) |

`NONSMMOOTH_LOCAL_CANDIDATE_VERIFIED` means the new research thresholds passed on finite directional probes and approximate Clarke-hull checks. **This does NOT certify a 4D local minimum, original `CONVERGED`, global optimum, or posterior covariance validity**.

Three blocked cases (candidate internally equal to old double cost, but exporting back to physical delta then rewhitening produces strictly positive new double delta):
- `R2_aA_m45/LoS/k868/M4_P`: export ΔJ `+1.0842021724855044e−19`.
- `R4_aB_m0/Full/k365/M4_R`: export ΔJ `+2.7755575615628914e−17`.
- `R4_aB_m0/LoS/k455/M4_R`: export ΔJ `+8.673617379884035e−19`.

Magnitude is not a physical RF performance target; the important issue is the **sign preservation and acceptance eligibility under numerical representation**. They were explicitly `candidate_admissible_for_fusion=false`, not silently converted into smooth success or counted as accepted. Old frozen MAP invalid status unchanged. Recorded `internal_whitened_candidate_delta_J`, `rejected_candidate_exported_delta_J`, original and candidate cost/source SHA and probe evidence.

## Frozen R2 phi sensitivity secondary analysis

- Same run reverified original `hs_lut_2deg.npy` R2 Anchor A mount0/45 979 frozen LoS prior points, no new Full yaw-specific channel.
- Median `|ds/dphi_tx|` vs `|ds/dphi_rx|` (per degree): mount0 0.007240 vs 0.006983; mount45 0.027174 vs 0.030340. `phi_tx` dependence is not negligible even though a stationary yaw sweep actuates only `phi_rx`.
- Absolute 11-point LoS `s` swing medians: ±10° mount0 0.15387/mount45 0.60405; ±45° mount0 1.31287/mount45 1.88433 (original R5 comparison **used 11 samples for both spans**, not new 19-point Full scans).
- Independent **11 fast vs 19 wide** LoS self-match now separately available [Run 38677812640](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38677812640), and documented in `R5_R2_FAST11_WIDE19_LOS_S0_RESULTS_20261015_KO.md` on a separate S0 branch. It is theoretical LoS template information only.

## Next research gates (not claimed done)

- **Numerical stability**: reproduce the 90 same-SHA Anchor-B mismatches across controlled hardware/BLAS/CPU flags/array layout and capture step rejection direction, genuine finite-precision divergence vs chart/LUT grid-knot sensitivity. Identical git SHA is insufficient by itself for floating reproducibility.
- **New local solver certification**: rigorously assess Clarke/directional first-order stationarity with all active neighboring cells and tangent directions, not only the current 112 finite probes. Test local/global mode ambiguity and numerical error bound at facet boundaries. Separate one-step posterior covariance/coverage evaluation.
- **Full P4 validation**: after a new verified solver contract passes controls, run all 4,124 previously invalid plus non-failing held-out inputs. Preserve complete denominators, no automatic substitution into historical P4 results and no tuning of Q/R/gate/LUT from truth.
- **Independent sweep likelihood**: requires per-orientation Full RF H/CIR or physical yaw scan data. Frozen original one-azimuth RF data is insufficient for actual Full sweep success claim.

## Verdict

`R5_4124_REPLAY_PASS_IN_ATTEMPT2`; `R5_STRATIFIED_185_AUDITED_COMPLETE`; `177_APPROXIMATE_LOCAL_CANDIDATES`, `5_UNVERIFIED`, `3_BLOCKED_NO_POSITIVE_COST_ACCEPT`; portability and 4D nonsmooth stationarity still **UNVERIFIED**. `scientific_PASS=false`.
