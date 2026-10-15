# R5 LUT 격자 경계 검출·비매끄러운 MAP 후보 솔버 — 감사·실행 영수증

## 기준·범위

- Original R4 P4 one-step Run `38658117256`, full MAP accepted 14,186 snapshots × prior/range-first 2 = 28,372 attempts; original `LINE_SEARCH_FAILED` 3,369, `MAX_ITERATIONS` 755, original 4,124 numerical invalid preserved.
- Frozen model: original R4 `core.py`, frozen `hs_lut_2deg.npy`/meta and `P0_INPUT_MANIFEST.json`, identical Gaussian posterior, P3 RF adapter. No original R4 smooth result backfill or R0 parameter change.
- Experimental new separate solver: `p4_nonsmooth_local.py` + `p4_lut_boundary.py`. The former local derivative-free Powell/active-LUT-facet/true-objective directional search was **already a distinct nonsmooth pilot**. R5 adds `theta,phi_tx,phi_rx` grid-distance and segment-crossing detection (sampled angular path, unwrap periodic phi, bisect boundary), direct tests at boundary ±small offset, and exact-facet candidate evaluation.
- Source commit for final **strict-cost pilot**: `909c1b6d120d95a125b56189469bdc4fbb2dc73b`; [Actions run 38668988355](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38668988355), [artifact 11942943955](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38668988355/artifacts/11942943955), ZIP SHA256 `68c5eaa427a2b34f097bc2ac2428628a4b3994e22ceb8dadafd19e586d02f7a4`. Static pre-run audit GO, full source & original 4,124-case ZIP SHA/CRC, 11 mathematics/geometry regression tests PASS, source original failures 20/20 status/gradient reproduced.

## Code audit defects and repairs

1. R5 first tests blocked due to missing `case` to `boundary_report`; fixed with commit `1ced37cda1af...`. Next tests caught missing **exact-on-sampled-node** grid crossing for a known -156° `phi_tx` boundary; fixed `79d31984e5c7...`.
2. Initial R5 pilot `79d319...` produced 19/20 approximate candidates, but **allowed `J_final-J_start=+1.87894e−12`** in one accepted case due to old local optimizer `+1e−11` criterion. This violated non-increasing exact objective contract, despite Actions success. **Superseded, not promoted**.
3. Repaired R5 code `abf1b993b735...` removes positive objective slack, `14ba99ed98a6...` includes original iterate as fail-closed objective candidate, `909c1b6d120d...` hard-fails any `J_delta>0` and uses **strict `J_delta<=0`** count. All repairs passed unchanged 20 fixed-case source regression.

## Final audited results

| Item | Strict result |
|---|---:|
| Immutable original 20 failures re-solved with unchanged R4 to same status | **20/20** |
| Boundary detector geometry / numerical tests | **11/11** |
| R5 new status `NONSMMOOTH_LOCAL_CANDIDATE_VERIFIED` | **18/20** |
| R5 new status `NONSMMOOTH_LOCAL_UNVERIFIED` | **2/20** |
| J_final <= J_original_terminal, no positive allowance | **20/20** |
| Local directional sampled probes accepted as nonnegative | **19/20** |
| Sampled Clarke hull proxy small | **19/20** |
| Original smooth `gradient_tol=1e−8` reached | **0/20** |
| Explicit LUT crossing events during candidate local rays | 14 |
| Explicit boundary intersection candidates considered | 14 |
| Final state flagged near some LUT knot | 14/20 |

**Unverified 2:**
- `R2_aB_m0/full/k89/M4_P`: objective decreases (≈−9.79e−7), local probe condition okay, but estimated Clarke-gradient-hull norm ≈0.00215 exceeds pilot threshold 0.001.
- `R2_aA_m0/full/k220/M4_R`: objective decreases (≈−9.78e−6), hull proxy ≈0.00025, but one sampled local direction slope ≈−1.60e−5 is more negative than allowed −1e−5, so local candidate NOT certified.

**Caution:** these thresholds are *new, approximate nonsmooth research criteria*—not equivalent to the frozen R4 smooth convergence threshold. Clarke proxy uses sampled gradients and is not exhaustive; the absence of descent in 112 directions at a finite radius does not prove a 4D local minimum. A strict per-case numerical status does not prove posterior uncertainty. Do not use local GN covariance at a kink without separate posterior validation.

## Next gate before integration into EKF4

- Independent mathematical check of generalized-stationarity test and finite-direction coverage (especially 2 unverified, and true 4D coupled descent), numerical error bounds near LUT knots, position/yaw prior branch handling and covariance calibration.
- Freeze a new R5 status namespace `SMOOTH_CONVERGED / KINK_LOCAL_CANDIDATE_VERIFIED / UNVERIFIED`, not a silent mapping of old invalid.
- Non-preselected validation across **all original 4,124 failed MAP updates** and independently held-out R2/R4/R5 RF samples; compare unchanged frozen MAP objective and posterior-quality outcomes. Report invalid denominator.
- Never smooth/refit LUT as a hidden numerical fix; any altered interpolation means a *new RF model* and requires repeat P3 parity, physical source audit, and science pre-registration.

`scientific_PASS=false`; R5 is isolated and does not change the historical P4 full output.
