# P1 SourceFFD observation and matched-error science specification — locked proposer candidate

**Retrospective/C0 only.** This supplements, but does not overwrite, `SCIENCE_SPEC_KO.md` and cannot change 3-D or M2.

### Antenna/source geometry

For known anchor `a_i=(a_x,a_y,a_z)`, tag height `z_t=.45m`, `d(x)=sqrt((x-a_x)^2+(y-a_y)^2+(z_t-a_z)^2)`. Physical LOS source banks (`LP_plus45_bank.npz`, `LP_minus45_bank.npz`, 257×181×361 complex64) supply frequency-dependent complex vector fields, rotated into the same world frame as the archived antenna producer. TX +45 orientation is encoded in the FFD bank and must **not** be applied a second time.

The direct-source frequency response for RX port `j` is `H_j(f;x,a,m)` as returned by the pinned `SourceFFD.spectrum`; source direct-only RF uses actual hypothesized distance and `(RX field)·(TX field)`, not a Hermitian conjugate or 10m fixed reference.

### Measurement prediction and raw RF observation

```text
H_raw[k, f, rx, tx] (complex) -> tx0 -> Hann 257 bins -> 1028-pt IFFT *257
-> select Rx with largest CIR peak -> earliest index >= 30% of that peak
-> sample SAME first index n0 on RX +45 and -45
-> P+ = |h_rx0(n0)|², P- = |h_rx1(n0)|²
-> z_s = (P+ - P-) / (P+ + P-), z_r = first-edge delay*c
```

Predict `h_s^{src}(x)` by applying precisely the same chain to source-computed direct two-port complex fields from **estimated** state. Predict `h_r(x)=d(x)+B_OLD`, `B_OLD=-0.5315983906250129 m`. **The physical detector range and continuous surrogate are intentionally distinct**.

```text
H_r = [(x-a_x)/d, (y-a_y)/d, 0, 0].
H_s = [d(s_src)/dx, d(s_src)/dy, d(s_src)/dpsi, 0].
H = stack(H_r, H_s), shape (2,4).
```

Analytic source Jacobian is valid only in fixed angular interpolation/source cap + fixed first-path active cells. `FIRST_PATH_SWITCH`, `FFD_CELL_SWITCH`, cap boundary and zero-strength denominators are separate diagnostic statuses, never silently treated as smooth derivatives.

### Matched offline objects

For every `(case_id,pose_id,channel)` with exact source pairing:
```text
e_r    = z_r - [d(x_GT) + B_OLD]           (m)
e_sold = z_s - h_s_LUT(x_GT)               (dimensionless)
e_ssrc = z_s - h_s_SourceFFD(x_GT)         (dimensionless)
delta  = e_ssrc - e_sold = h_s_LUT(x_GT) - h_s_SourceFFD(x_GT)
e_sMP  = z_s_FULL - z_s_NATIVE_LOS         (matched same pose, detector)
```
These are offline truth-diagnostic labels. `e_sMP` is a Full/LoS contrast, not a claim that this residual is an independent stochastic noise draw. At any given pose `e_r` must be identical between old-LUT and SourceFFD arms because `z_r` and `B_OLD` are fixed. Signed `s` must not be converted to `|s|`, port order must not be swapped, and true sensor yaw must not leak into filter runtime.

Within each predeclared stratum use `µ=(1/n)sum(e_i)` and `C=(1/(n-1))sum((e_i-µ)(e_i-µ)^T)`; display `C_rr(m²)`, `C_rs(m)`, `C_ss(1)`, eigenvalue/PSD check. Use n<2 as missing rather than fabricate inverse. Temporal ACF is **not** an inferential P1 target and remains Section 3-D RESERVED.

### Risk decomposition and negative controls

- Old LUT vs SourceFFD same raw H => isolates predictor/target model difference; NOT RT channel difference.
- `h_r`, raw r, first-path tap should remain fixed; any change is an error or separately labeled protocol change.
- Use 0/2π yaw invariance, interchange Rx ports (signed s flips), wrong complex Hermitian contraction negative control and near-pole stable-cell Jacobian checks.
- Inspect missing, duplicate, NoLoS, zero-power, near-pole, first-path and FFD-cell crossings with full counts and attached keys; do not cherry-pick.
- Source-native LoS s/H parity is an engineering source QA on *previously analyzed data*. Repeatability cannot establish independent-scene generalization, runtime posterior calibration or final M2 superiority.

### No P1 filter scoring

The previously pinned 4-state f/F/Q and conventional `R0` are source metadata only; P1 does not regenerate x/P, update gates or learn µ/R. New recursive comparisons require a separate frozen P2/M2 phase contract and independent pre-run audit.
