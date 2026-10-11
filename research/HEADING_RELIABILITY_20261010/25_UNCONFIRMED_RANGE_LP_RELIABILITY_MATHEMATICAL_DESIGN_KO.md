# 25 — 단일 앵커 Range + Dual-LP 편파 + 위험 감지 Active Probe: 수식 기반 후보 설계 (미확정)

작성일 2026-10-11. 이 문서는 채택한 설계가 아니라 **경쟁가설·모형·ablation/중단 기준**을 명확히 한 검토안이다. 실제 자료 검증: 19 (7case 1008-run Range bias), 20/23 (원본 SHA LP FFD vs theta0 LUT 문제), 21 (128seed 한 station 6×6 cross-time), 24 (7case full-P6 range→Heading direct Kalman gain 개입), 17 (1344-run 3point mixture+NEES). 동일 corridor이므로 다른 환경 일반화 근거 없음.

## 1. 기준 상태와 측정 가능 정보

기존 고정 Sensor-v2 x6=[x,y,ψ,b_g,sf_g,ε_w]^T, dt0.2s, known single anchor a=(ax,ay,az), antenna z_robot=.45m. IMU/wheel 추정으로 x_k^- 및 P_k^-를 전파한다. RF에는 only measured P_{+45},P_{−45},s_FP=(P1−P2)/(P1+P2), detected,tap,first-path range r, optional magnitude-CIR first-arrival common gates; 단일 anchor range는 2D(x,y) GT가 아니라 1D 거리 제약이다. Native H, path coefficients, LoS direct/truth, FFT coherent phase는 **offline evaluation only**. mount0/45 모두 비교.

정상 주행: 매 0.2s 센서 예측+odom 수용→ range 신뢰도/평균 편향과 s 신뢰도 평가→ 명목상 유효한 range/s 업데이트. s 저신뢰일 때 원 s withheld→실제 정지 위치에서 신규 s0, +δ s1/s2→site+point 다중모드 posterior→전체 P6 보존→원래 heading 복귀→같은 filter로 주행 재개. True moving trigger s를 정지 위치의 RF observation으로 바꾸지 않는다.

## 2. Range measurement 오차를 분리하는 세 계층

원거리 model:
z_r,k = d(p_k;a) + b_hw + μ_r(f_r,k) + b_{r,k} + ε_{r,k}.

- b_hw: 정확한 수신기/antenna delay + TOA leading-edge pulse shift의 **장치/알고리즘 상수**; multiple known-distance calibration에서 추정/수정. 현 frozen source b_hw 대신 첫-path detector offset −.531598390625m 별도 반영. 실제 안테나의 물리 delay와 동일하다고 주장하지 않는다.
- μ_r(f): corrected range, Psum, firstpeak contrast, relative yaw, geometry, NIS, multipath detection/crosspol features를 이용하는 **conditional mean bias**. Training other route/site only, test site truth 금지; model uncertainty Var(μ̂_r−μ_r) estimate.
- b_{r,k}: persistent site/environment correlated residual; 반드시 더할 필요는 없으며 아래 A/B/C 후보 중 하나를 선택해 비교할 것.
- ε_r: thermal/detector noise. Angle/tap-dependent receiver floor, independent noise realization.
Score q_r=P(|z_r−d−b_hw−μ̂_r|<τ_r | online features) is optional calibrated **specific target**; mode probability of NLOS needn't match it.

현재 168 matched runs×6arm evidence: uncalibrated B full range range-only NEES1285.37, position RMSE1.285m; train-other-route conditional mean+R+AR1 scalar info E NEES146.52, pos RMSE0.804m, coverage51.3%. Thus simple correction beneficial but **not statistically consistent**.

### 후보 A — 기존 6상태 그대로, learned mean + independent-equivalent covariance

z̃_r=z_r−b_hw−μ̂_r(f);
R_eff = Var(ε_r)+Var(e_model−μ̂_r | f) + Var(μ̂_r uncertainty);
if empirical AR1 residual ρ>0 and a fixed averaging horizon is empirically validated, compare R_proxy=R_eff × min(α_max,(1+ρ)/(1−ρ)). 이것은 스칼라 근사일 뿐 정확한 temporal innovation whitening이 아니다. 기존 E 실험이 여기 해당.

### 후보 B — 7상태 persistent range bias Gauss–Markov augmented EKF

x7=[x6,b_r] and
 b_{r,k+1}=α_k b_{r,k}+w_{b,k},
 α_k=exp(−Δt/τ_r) or exp(−Δdistance/ℓ_r); Q_b=σ_b²(1−α_k²) under stationary Gauss–Markov.
 z_r=d(p)+b_hw+μ̂_r+b_r+ε_r,
 H_r=[h_x,h_y,0,0,0,0,1].
 Use full 7×7 Joseph covariance or exact state-noise correlations; do not also add σ_b² into R_eff when b_r is explicit state.

**식별성 경고:** 한 순간 linearized z≈d+h_r^T δp+δb_r에는 radial δp와 δb_r가 동일 range innovation 방향으로 등장해 rank가 부족하다. An uncertain unknown absolute b_r with one anchor cannot be separated reliably from radial position error at a fixed site using range only. Motion excitation, external calibration, bias prior or additional independent polar heading information required. Repeated readings alone don't solve identifiability.

### 후보 C — Schmidt–Kalman/consider/mixture for weakly observable nuisance

Track b_r prior covariance and pose–bias cross without forcing correction of b_r (Schmidt gain b_r=0), or use robust contaminated likelihood
 p(z_r |x,f)=Σ_{m∈{good,bad}} p(m|f) N(d(p)+b_hw+μ_{r,m},R_{r,m}).
Good/bad mode prior fitted on train sites; unknown positive bias cannot simply be forced positive in this exact first-path chain because after fixed pulse offset signed range errors and miss-detection both occur. q values require Brier/calibration and false-accept check.

Compare A/B/C, no preselection without experimental NEES and identifiability pass. Same old target 6-state P6 is not directly comparable to new 7-state P7; compare pose marginal Ppose and Monte Carlo error under matched noise.

## 3. Range→Heading causality: source-backed original P6

H_r=[h_x,h_y,0,0,0,0], S_r=H_r P6^- H_r^T+R_r,
 K_{r,ψ}=(P_{ψx}h_x+P_{ψy}h_y)/S_r, Δψ=K_{r,ψ}(z_r−d−bias).

The P6 cross is mathematically legitimate. If nominal observation is biased, this gain can transfer the bias to Heading and calibration states, then accumulate over subsequent sensor integration.

Actual 7case×3drift×8seed run causal intervention on original RF:
| Configuration | Heading RMSE deg | Position RMSE m | Pose NEES | Heading NEES | conditional XY NEES |
|---|---:|---:|---:|---:|---:|
| A odom/gyro only | 8.93467 | 1.00736 | 8.87 | .785 | 8.085 |
| B full range gain | 9.79224 | 1.28536 | 1285.37 | 43.58 | 1241.79 |
| C original range with Kpsi=0 | 8.49065 | 1.12411 | 467.71 | 2.10 | 465.61 |
| D original range with K[ψ,bg,sf,eps]=0 | 8.93467 | 1.23772 | 344.63 | .785 | 343.85 |
| E corrected range full K | 6.95167 | .80415 | 146.52 | 11.96 | 134.56 |
| F corrected range Kpsi=0 | 6.95863 | .84019 | 68.69 | 1.20 | 67.49 |

This is *diagnostic constrained gain Joseph* not production solution. Range-only B/C cause comparisons prove existing range→Heading pathway can be harmful; after bias calibration full K improves XY relative to constrained K. Reverse path: F_xy,ψ = Δs[-sinψ,cosψ] (SE2 exact analogous), hence heading→predicted XY→future range innovation. Need separate physical route feedback to claim absolute navigation improvement.

The 0.9cm prior claim is minimum **conditioned on heading** XY covariance eigenaxis, not overall 2D covariance nor physical sensor intrinsic precision. Filter repeated range R^.5≈8.281cm many times with underestimated systematic bias, making radial Pcond shrink while actual radial error remains high.

## 4. Pole-safe physical FFD s model (must repair before accepting polar s near vertical)

Original LP+45 and LP−45 LFS NPZ banks actually downloaded, sha-verified. θ=0 Cartesian E across 361 phi directions: relative complex std ~2.8e−8 at 6.5GHz for both LP ports; FFD original is smooth. Their direct original Cartesian contraction vs native Sionna matched LOS near pole maximum error .000675. Frozen LUT theta0 slice at fixed yaw0 but 8 approach bearings predicts s range1.953; theta2 slice range.0104. On nine actual rho<.10m native LOS, original LUT RMS .33909 while θ≥2° diagnostic clamp RMS .001374 and 2/4 extrapolate .001159; **raw pole basis interpolation rather than physical antenna** strongly implicated. Current hs_lut.build_lut at theta0 computes az_v=atan2(v_y,v_x) for vx=vy=0 (undefined azimuth), yet uses az_v−phi_rx to set yaw, then trilinearly interpolates theta0 and theta2. Fix using Cartesian world vector direction and actual antenna yaw (no independent polar azimuth gauge at θ0) and physically continuous field interpolation near pole. Clamp is diagnostic not approved filter replacement; compare pole guard theta_est/rho_est and uncertainty margin before using new model; new LUT version SHA required.

## 5. S and range joint reliability (not yet confirmed model)

 z_s,k = h_FFD(p_k,ψ_k+mount)+ μ_s(f_s,k)+b_{s,site,k}+ε_s,k.
 Prediction residual r_s=z_s−h_FFD(p_hat,ψ_hat+mount) contains pose error, so high r_s alone is not proof of RF corruption. Candidate features: measured signed s_FP, |s_FP|, Psum, first-arrival s_gate4/s_gate8/s_gate16 and their differences (hardware magnitude-CIR accessibility unverified), h_s Jacobian and prior innovations. Actual physical depolarization cannot be uniquely computed from two LP amplitude powers; use polar mismatch risk.

Separate calibrated targets:
 q_r=P(|e_r|≤τ_r |features), q_s=P(|e_heading_RF|≤5° |features,prior),
 q_site=P(max_i |e_MP,s,i|>.1 |site features),
 q_i=P(|e_MP,s,i|>.1 |features).
These are four different statistics, not interchangeable scalar confidence weights. Original "R_eff=R0/q²" is ONLY ablation heuristic; true conditional bias/variance/calibrated mixture must justify K/R.

Joint model for a same-time RF packet [range,s]:
 z=[z_r,z_s]^T,
 h=[d(p)+b_r, h_FFD(p,ψ)+b_s]^T,
 H=[H_r;H_s].
 S=H P H^T + R_{rf} [+ H P_b H^T if an external bias uncertain, not if bias already in augmented P].
 R_{rf} has range-s offdiagonals when empirically identified; don't add a site bias covariance twice if b-state already in filter.

For 2–3 yaw observations **not simultaneous**, state x_i evolves between samples. Correct generic linearized cross-time innovation covariance:
 Σ_ij = H_i P_{ij} H_j^T + H_i C_{x_i,v_j} + C_{v_i,x_j} H_j^T + R_{ij}.
The pilot 128 independent sensor/thermal seed on ONE station reconstructed approximate P_ij and empirical error. At t18s P_predψ=.002503rad², centered MC .002909, uncentered mean-square .005401 (×2.16). Receiver thermal cross-yaw s correlations near0.06–.10, while deterministic bias across 169 sites s correlations ~.8. Both are true and must be modelled separately; 128 noise seeds at one fixed site do NOT sample new multipath geometry.

### Two competing update architectures

- D1: 6state EKF + separate bias nuisance state/Schmidt + batch correlated mixture at final probe, explicit time-indexed crosscov P_ij.
- D2: small fixed-lag factor graph/smoother over states at 2/3 probe timestamps with sensor transition and joint site common nuisance; solve nonlinear MAP/mode-weighted approximation, carry marginal final x6/P6 into existing EKF. More physically faithful cross-time but computationally heavier.

Both retain all 2–3 s measurements with soft mode weights; no "pick point with smallest raw LUT residual." If common multipath rotates effective polarization like heading, no two/three amplitude LP points can necessarily identify true body yaw; posterior must admit ambiguity and regularize with gyro/odom prior.

## 6. Required ablations and evidence for selection (no architecture decided)

P0 (completed): existing 1008-run range-only 6arm, original 1008-run P6 Kpsi causal intervention, original LFS LP FFD + theta0/2/4 LUT audit, 128seed single-site pose×RF cross-time MC.
P1: ensure range-only baseline B vs corrected E + candidate AR1 bias-state/Schmidt F under SAME pose, seed/measurement, route, all full6 pose error/cov metrics.
P2: check persistent b_r identifiability by joint Fisher information singular/eigen/condition under route excitation; include known range calibration and a zero-mean/bias prior ablation, don't let true bias enter online estimator.
P3: correct pole-safe h and Jacobian and revalidate matched original native LoS & 0/45 mount. Create guard-only arm rho_est<.1m separately before adopting new LUT.
P4: full RF same station q_r/q_s/q_site/q_i calibration with withheld routes/sites then independent geometry, ablate first-gate availability and waveform hardware realism.
P5: closed-loop 5Hz driving risk trigger→brake→probe→joint posterior→return→resume; compare noRF, range-only, range corrected, fullRF, quality-only, SHAM,2yaw,3yaw, heldout route 0/45, new geometry. Preserve same physical time/cost/seeds. Report actual fullroute RMSE, p95, NEES df3 expectation3 and 95% coverage, heading uncertainty, NIS whiteness, pose RF cross-time 128+ independent repeats at multiple sites.
P6: experimental hardware test with actual measurable firstpath P1/P2 and amplitude-CIR availability confirmation.

**Decision gate:** no model chosen until both accuracy and consistency improve and self-reported q risk bins match actual heldout error. Existing scientific_PASS=false, F01/F02 OPEN, pole problem in original LUT, and all 7 original cases one corridor.
