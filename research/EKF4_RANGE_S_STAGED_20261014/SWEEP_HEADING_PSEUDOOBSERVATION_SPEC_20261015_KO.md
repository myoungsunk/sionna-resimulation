# Sweep RF Heading 모듈 독립 연구·구현 사양서 — 2026-10-15

> 상태: **설계 검토 / 신규 실험 미실행**, 기존 EKF4/P3/P4 및 동결 H·LoS LUT 불변. 기존의 `scientific_PASS=false` 유지. 본 모듈의 출력은 **GT가 아닌 검증이 필요한 RF-derived probabilistic heading factor**.

## 1. 적용 맥락과 기존 P3/P4

- P3: 7 RF case × LoS/Full 14 trace × 14,502 관측값의 관측·Jacobian·원 prior parity. 추정 정확도 평가 단계 아님.
- P4 fixed: 14,502 동일-prior one-step J3/J4/frozen-sequential 정합 PASS. Full R0 joint에서 DR prior 대비 오차 악화, MAP LUT 비매끄러움으로 4,124/28,372 추정 무효. P4 재귀 Gyro Bias 평가가 아님.
- 별도 R2 Bias 실험 [Run 38664617622](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38664617622), `81cdffbdedf43b318ebf8eddb4fcbac1fd30d878`: R2 mount0/45 × LoS/Full × B0/L0/L1/L2 × seed0에서 s-only3/4, Joint3/4, relinearized3/4 및 DR 비교 수행. 이는 **순수 positive gyro bias + white noise** stress이며 Sensor-v2 `condition=all` 복합 drift test가 아님. s-only 4로 bias 관측 가능하지만 Full에서 heading 오차·과신은 남는다.

## 2. LUT·센서 하드 계약

- Frozen LUT numeric 3D `hs_lut_2deg.npy` shape `(46,180,180)`, dtype float64, `s[theta,phi_tx,phi_rx]`, theta 0:2:90° / phi_tx,phi_rx −180:2:178° periodic. Trilinear piecewise interpolant, inside-cell analytic gradient, grid facet gradient discontinuity.
- FFD LoS banks from Tx0 +45° LP and Rx ±45° LP; 257 frequency bins 6.2504 to 6.7496 GHz, Hann, `4N` IFFT and strongest RX 30%-peak leading edge shared tap. `s=(P1-P2)/(P1+P2)` from first-path powers, no cross-port coherent phase assumption. LoS construction at reference distance 10m; original distance/first-tap quantization may cause departures.
- Frozen LUT interpolation check `gate_L1_interpolation`: max 0.023972 > max allowed 0.01; median 0.000530 < 0.001. Original report `passed=false`. Reproducing identical LUT semantics is NOT a physical accuracy certificate; report this limitation.
- Frozen R0 `R_s=.0081`, `R_r=0.0068578637m²`, `R_{sr}=0` as **unverified** model, average detector range mean offset `B_old=-0.5315983906250129m`.
- R2 Anchor A=(4,0,2.65)m, mount 0°/45°, robot antenna height 0.45m, source route Tnone 979 poses at dt nominal 0.2s (duration195.6s). Other anchor data independent only in geometry, not in physical scene.

## 3. New RF observation/measurement model

At a scan station hold robot-base center fixed, use known body yaw `psi_i = psi_DR(t0)+delta_psi + alpha_i` with **measured relative** `alpha_i` rather than commanded-only angles. Account for antenna lever arm `p_tag_i=p_center+R(psi_i)l_tag` if nonzero.

Record each pose: measured timestamp, `alpha_i` wheel/encoder and covariance, angular velocity/settling indicator, raw per-port `P1_i,P2_i`, `s_i`, `r_i`, CIR leading edge/FP power/noise/SNR/detection metrics, anchor/mount, `p_i` estimator prior and quality flags. Do NOT fabricate Full RF samples by querying a LoS LUT at new headings.

Under LoS control:
```
s_i = s_LoS(p_tag_i, psi_DR+delta_psi+alpha_i) + epsilon_i
```
Full RF adds nuisance `m_i`:
```
s_i = s_LoS(p_tag_i,psi_DR+delta_psi+alpha_i) + m_i + epsilon_i
```
where `m_i` cannot be arbitrary per-sample if heading shall be identified: arbitrary `m_i` exactly absorbs any trial `delta_psi`. Baseline robust model assumes over short scan a shared common `c` (and optionally low-order smooth drift) with pre-registered prior/covariance; this is a scientific assumption to verify, not a physical fact.

## 4. Identifiability and risk of ±10° scan

- Model response vector `h_i(delta)=s_LoS(p_i,psi_DR+delta+alpha_i)`, `J_i=dh_i/d delta`. With unknown shared offset `c` and sensor noise covariance `Sigma`, marginalize intercept. `W=Sigma^{-1}`, `Q=I-1(1^T W1)^{-1}1^TW`. Effective heading Fisher information is `I_delta=J^T WQJ`.
- If the ±10° response is locally affine (e.g. `h≈a+b(psi+alpha)`) then `J≈b 1`; after removing unknown offset `QJ≈0`, the sweep provides essentially **no reliable absolute heading information**, even with many precise measurements.
- Opposite extreme: if the RF pattern has multiple indistinguishable peaks or `P1+P2≈0`, the scan is ambiguous or poorly conditioned. More scan points can reinforce a wrong multipath response if their errors are correlated.
- Check posterior profile vs delta and nuisance, its mode count, second-to-first peak likelihood ratio, curvature/posterior credible interval, sensitivity to position uncertainty, and leave-one-angle-out consistency. If ambiguous, output `NO_HEADING_UPDATE` rather than false GT.
- Use the original LUT within support, but avoid stepwise derivatives at LUT knots for optimizer; bounded 1D global angle grid + local per-cell exact objective checks is preferable to smooth GN near active 2° knot.

## 5. Proposed pure scan experiment (separate from EKF4 core)

**S0: Mathematical observability and LoS-only canary.** R2 Anchor A mount0/mount45, B0 and positive-bias L0=.01,L1=.05,L2=.20°/s. Compare sweep span ±5, ±10, ±20; nine proposed measured yaw offsets `[-10,-7.5,-5,-2.5,0,2.5,5,7.5,10]`° for ±10; forward/back to test temporal stability. Use known center position as *control* then estimated-position `P_{xy}` integrated version. Compare unknown- vs known-offset, test profile likelihood uniqueness, `I_delta`, and errors only offline.
**S1: New Full-RF yaw-specific channel generation.** Original frozen trace stores a single yaw per position, so its `H(p,psi)` cannot be legitimately reused for other `psi`. Generate new frozen yaw-sweep Full and LoS observations by consistent receiver pattern rotations applied to original ray/FFD model, or acquire actual stationary UWB packets on robot. Hash frequency/channel/geometry/antenna source and all angle-specific `H`; do not generate fake Full by rotating LUT-only LoS.
**S2: Probabilistic scan heading factor.** Fit `delta_psi` and pre-registered low-dimensional nuisance `c` (and optional slow drift) via robust likelihood on `s_i` optionally port powers/FP/range. Use temporally correlated RF covariance or scan-session bootstrap. Include `p_i` uncertainty jointly/marginally. Output `ScanHeadingFactor{time,delta_psi,posterior/modes,variance,confidence,quality,used_sample_ids,source_hash}`, **not GT**.
**S3: 10s/20s schedule fusion.** Research arms: no-scan DR4/S4/J4/SR4, same arms + scan factor; 10s vs20s scan scheduling, plus 0-angle repeated-acquisition control with equal number of RF packets; identical random sensors, duration/distance, and stop/move policy; run separate LoS/Full and mount0/45. Optionally 3-state arms as bias ablation. For first prototype, halt at designated stations and rotate about known center, then return to center; include scan travel/settling time, raw event timestamps and encoder yaw.
**S4: Source separation / avoid double counting.** Raw sweep packets used to compute the scan factor must not ALSO enter the normal raw s/r filter as if independent. Simplest: during sweep freeze normal s update and substitute a single batch factor (range separately only if cross-covariance model accounts for it); otherwise propagate RF sample cross covariance explicitly. Wheel-based relative angle from same IMU/gyro and motion model causes dependency; handle joint covariance or use independent wheel/encoder reference.

## 6. State/covariance and bias correction

In a valid single-Gaussian case, a scan Heading observation `z_scan=psi+noise` gives `H_scan=[0,0,1,0]`; because `P_{b,psi}` is generally nonzero under biased gyro prediction, `K_b=P_{b,psi}/(P_{psi,psi}+R_scan)` updates bias **indirectly**. The factor quality `R_scan` must include scan ambiguity, nuisance multipath and uncertain position—not simply sharp fit curvature under an ideal LoS LUT. If `psi_scan` was inferred using the same prior, do not reapply the resulting posterior as independent measurement: build a likelihood factor that excludes prior or perform joint update once.

## 7. Go/No-Go criteria and metrics

- No inference truth leakage; no physical GT label until validated externally, no false accepted factor in flat/symmetric LUT response. Hard detect `r` offset, `s` amplitude, mount yaw, phase-center position and packet order failure.
- Source audit → S0 canary → S1 actual yaw-specific Full RF archive → S2 held-out likelihood calibration → S3 paired recursive robot runs. No training/test contamination across station locations/scene/route.
- Report scan yaw error mean/bias/RMSE, Heading coverage/NEES/credible set, multiple mode fraction, factor abstention, full pose & gyro bias error, signed range residual, route completion, added stop duration/energy. Units and independent group denominators explicit.
- Calibrate on independent positions/scenes; do not claim broad Full multipath suppression from one R2/seed. Sweep can be ineffective if Full fingerprint is inconsistent across reflection changes, if the response is locally affine/degenerate, or if scan relative angles are inaccurate.

## Research priority

1. **LoS observability / ±10° sufficiency test first:** without information under LoS, a Full pseudo heading is not justified. Determine where short-sweep curvature provides identifiability vs unknown offset.
2. **Full multipath signed error and scan-shape stability second:** do not assume increasing sensor count cures systematic heading bias.
3. **S4/J4/SR4 recursive bias and coverage third:** evaluate not only RMSE but overconfidence and calibrated abstention; study 10s/20s duty-cycle tradeoff.

Outside scope: replacing frozen LUT or retraining its antennas without separate scientific preregistration, altering original R4/P4 failures or promoting pilot nonsmooth statuses to historical `CONVERGED`.
