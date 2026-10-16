# R5 Anchor near-pole LoS–LUT mismatch: audited root-cause and correction candidate (2026-10-16)

**Status:** `ROOTCAUSE_SUPPORTED`, `CANDIDATE_NUMERICAL_PASS`, **SOURCE_BANK_REGEN_PENDING**, **PRODUCTION_NO_GO**. This is an independent additive research branch, **not** a change to frozen original H, RF observer, LUT, S4/J4/SR4, or published baseline records.

## Proven mechanism in original code

Original `qclean_uwb/drivesim/hs_lut.py::build_lut` calculates `d_local=[sin(theta) cos(phi_tx),sin(theta) sin(phi_tx),cos(theta)]` and then derives `az_v=atan2(v_y,v_x)` to rotate the receive pattern. At **theta=0°**, both transverse components are zero and the source `phi_tx` is lost. The stored original `s[0,j,k]` is **identical for all phi_tx grid indices j**, while `s[1,j,k]` at theta=2° depends strongly on j. Trilinear interpolation between these angularly inconsistent layers creates a spurious s jump and artificially huge XY derivatives.

For this frozen ceiling-anchor orientation `diag(1,-1,-1)`, body-antenna yaw `psi+mount`, and original source azimuth convention:
`phi_tx + phi_rx = wrap(-180° - psi - mount)`. At the zenith limit, the true physical polarization depends on antenna yaw, not an arbitrary horizontal bearing. The experimental angle-consistent theta=0 layer is:

```python
j,k = np.indices((180,180))
s_corrected = s_original.copy()
s_corrected[0,:,:] = s_original[0,0,(j+k+90)%180]
```

This lookup transformation is specific to the pinned antenna orientation and uniform 2° azimuth grid. It is a **research hotfix candidate**, not a general replacement for independent FFD source generation.

## Source-backed empirical evidence

R5 Anchor B `pose_id=706`: actual horizontal rho=0.038388 m, LoS theta=0.999649°; native LoS CIR s=**−0.946821**. Old trilinear LUT s=**−0.069205**, corrected candidate s=**−0.945594**; absolute model error **0.877616→0.001226**. Old theta0/2 layer values at matching angles are +0.8057 and −0.9447.

Phase-referencing original LoS H(f) from ~2.2 m to 10 m changes measured s only −0.946821→−0.946501 (leading edge tap 11→63). Hence 10m reference distance and first-path fractional tap cannot explain 0.8776 error.

**Original Native LoS, all 9,519 paired poses:**
| Eval subset | n | Original LoS-LUT RMSE | Candidate RMSE |
|---|---:|---:|---:|
| theta<2° | 5 | 0.454941 | **0.001143** |
| theta>=2° | 9,514 | 0.009619 | **0.009619 (exactly unchanged)** |
| all | 9,519 | 0.014184 | **0.009616** |

Four s residuals >0.05 reduce to zero; overall maximum absolute residual 0.877616→0.046651. In the full 180×180 angular grid, theta0-to-theta2 |s| discontinuity median/P99 changes **0.704471/1.922303 → 0.008197/0.023440**.

**Jacobian, B/pose706** [ds/dx, ds/dy, ds/dpsi]: old **[−21.004, −17.847, −0.481]**, corrected **[+0.356, −0.074, +0.248]**. Direct central differences of eight near-pole native samples match the patched analytic Jacobian. For fixed yaw and 360 arbitrary azimuth bearings around a 1-mm circle, predicted s range **1.927769→0.000068** (eliminating artificial azimuth dependence).

## Historical P2 calibration: frozen predictions, label-only rescore

Existing R5 held-out (training on R2+R4) **G5+geometry signed mean and centered variance model** frozen, R5 LoS n=2,830. After correcting **only** the native LoS–LUT label for the same five samples:

| Metric | Original label | Corrected label |
|---|---:|---:|
| normalized residual squared mean | **3.793740** | **0.154034** |
| Gaussian NLL | −1.757050 | **−3.576903** |
| nominal 95% coverage | 99.258% | 99.435% |
| mean-adjusted residual RMS | 0.019618 | **0.004569** |

Thus the earlier extreme R5 LoS tail miscalibration was chiefly due to **source LUT label error**. This is NOT an approved statistical calibration (post-correction 0.154 suggests conservative variance). Models for R2/R4 folds previously trained on R5 corrupted labels **must be fully retrained**.

## Impact on online estimator is separate

Across the **14,502 original frozen DR3 one-step pre-RF priors**, **none** has predicted polar theta<2° (minimum saved prior horizontal rho≈0.148185 m). Therefore patching the frozen LUT cannot change their h/H/K/Gate/posterior; **no one-step RMSE improvement is claimed**. Four-state recursive behavior and model replacement remain NOT TESTED.

## Audit and deployment gate

- Source archive CRC and **120 input file SHA256** PASS. Original frozen LUT parity across all 9,519 LoS cases <1e−10; native H-to-CIR s replay <1e−12 for key near-pole poses.
- Candidate repair changes only theta=0 layer; 2°..90° grid bit-identical; geometrical relative-yaw identity, periodicity, no-silent-double-patch guards, central-difference Jacobians; **9/9 tests PASS**.
- Original LUT SHA256: `711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079`.
- Candidate independent NPY SHA256: `e6db187d2b8f0507ab588affb0bae66d26d2b778ce9244c36154342800f33f0b`. The file and raw numerical evidence are in a separate conversation ZIP, **not committed to GitHub**.
- No raw native FFD antenna bank attached for a source `theta→0+` rebuild. **Exact new FFD-source construction remains unverified**. Residual off-pole LoS-LUT error up to 0.046651 and existing F01 global LUT interpolation warning remain unresolved.
- Next: obtain original FFD banks, rebuild theta=0 via a **positive-angle limiting direction** rather than an undefined zero polar azimuth, independently validate new LoS measurements/Jacobian; refit all P2 route heldouts; rerun paired 4-state B0/L2 Full/LoS and NEES/coverage; new scene/heading geometries before considering replacing original LUT.

**Scientific decision: strong causal source identification and successful non-destructive pole-layer smoke correction, but final source rebuild / production adoption NOT YET APPROVED.**
