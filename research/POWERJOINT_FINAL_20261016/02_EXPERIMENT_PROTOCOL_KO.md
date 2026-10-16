# 02. 최종 실험 F0–F7 구현 프로토콜과 통과 조건 (Pre-registration)

**실행 상태: 사전 계획 확정.** 완료된 실험을 다시 결과로 만들어내지 않는다. 각 F 단계는 기존 Frozen baseline을 입력으로 받고, 새로운 코드는 별도 branch/모듈에 추가하며, 자체 수치검사/원본비교/독립재검산을 필수로 통과한다.

모든 모델 비교: R0·DR4·S4·Joint4(J4)·SR4·Frozen POWER_JOINT·(적절한 경우)G4·새 후보. 근거가 있는 경우 SR4 대신 J4와 동일한 선형 frozen-H whitening test 추가. 목적별로 불필요한 모델 실행을 강제하지 않음.

## F0 — EM/FFD/LoS-LUT 모델 원인 수리 및 물리적 재현

**질문:** 천장 Anchor θ=0에서 송수신 극점각 gauge가 잘못 다뤄져 실제 LoS와 LUT가 다르다. 보정 후보의 물리적 의미가 FFD bank 직접 복소 채널로 확인되는가? θ≥2°에서 interpolation FAIL은 어떻게 해결되는가?

**동결 소스:** qclean_uwb/drivesim/hs_lut.py (Git blob a205e43bb381fbbdf3a41f9bb029ede0d4293231); pattern_apply.py / observation.py; original FrozenLut adapter p3_rf_adapter4.py (blob cb676aea8e6710ff2c0e175e1e422271b696cebe). Experimental, non-destructive pole_lut_fix.py (blob d2474fcac8bc02dc20d1bad253b6c39956412376).

**계획 구현:** 원 FFD banks의 complex frequency-dependent Cartesian vector E-field를 global frame으로 변환하고, original TX+45LP / RX±45LP, rotation convention, first-path detector, same propagation phase and geometry에서 *direct* complex H(f)를 생성. 구면 극점에서는 불확정 φ=atan2(0,0)를 고정 좌표라고 믿지 말고, 물리적인 global antenna axes와 θ→0+ 양의 극한을 사용. 동일 yaw에 대해 0.1°/0.25°/0.5°/1°/2°/3°/5°와 모든 azimuth seam, 1mm ring, 다른 anchor/mount를 스윕. direct complex channel로 얻은 s를 새 LUT에 넣고, finite difference Hsψ/Hsx/Hsy 및 보간격자에 대해 비교. 필요시 φ/theta 격자 적응 refinement를 만들되 original 2° LUT를 덮어쓰지 않음.

**예비 확인:** R5 Anchor B pose706 native LoS s=−0.946821, old LUT −0.069205, candidate −0.945594. θ<2° 5개 RMSE .454941→.001143. 기존 F01 meta에서 500 랜덤 보간 max .023972 > .01은 **별도 FAIL**. 수정된 LUT의 9519 Native LoS 예측 오차·θ별/max/p99/FP tap 변화를 표시; original LoS first-path Range bias B_OLD (−0.53159839m)와 방향별 잔차도 함께 확인. 과거 old/patch/source-generated 세 값을 모두 저장.

**Clean code QA:** original LUT SHA256 711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079 고정. New LUT는 다른 파일명/버전 메타, theta >=2° 유지 여부 및 변경 이유 기록. 원본 h/H & frozen experiments는 반드시 bit/SHA parity. FD Jacobian boundary near theta0/seam numerical scale-aware tolerance: absolute ~2e−3/m (기존 near-pole smoke) 및 relative tolerance를 명시; 경계 비미분점은 analytic derivative 불가로 별도 표기. 극점 스키마 9/9 기존 unit tests 재현.

**PASS 게이트:** FFD source bank hash + observer native channel parity + theta0 near-limit value/Jacobian + seam continuity + F01 interpolation re-audit. **원 bank 없을 때 candidate-only exploratory PASS, F0 full science HOLD**. Negative outcome도 정당한 결과로 기록.

## F1 — Source-corrected P2/N4-B 오차 레이블 재계산 및 train/heldout refit

**질문:** 원래 R5 five-pole LoS/LUT 잘못된 레이블이 N4-B/G4/POWER의 signed error, bin covariance, train folds 및 heldout 성능을 오염시켰는가?

**구현 기반:** research/R5_N4B_20261015/n4b_rf_errors.py (blob abd654dd9efde61fc7baffc350188b2a8b4904a3); exact same R0 Range h and RF observer; 14 archived P3 trace parity. Filter predictions training에서 GT 사용 금지; offline supervised target에는 GT 사용 가능.

**원인 분해:** $$e_\mathrm{Full}=z_\mathrm{Full}-h^\mathrm{source}_\mathrm{LoS}(x_\mathrm{GT}),\quad e_\mathrm{NativeLoS}=z_\mathrm{LoS}-h^\mathrm{source}_\mathrm{LoS}(x_\mathrm{GT}),\quad e_\mathrm{MP}=z_\mathrm{Full}-z_\mathrm{NativeLoS}.$$ 같은 original pose/time/FP observer 정의가 맞는 경우에만 패킷 대응. \(e_\mathrm{MP}\)는 native LoS observer와 Full observer 사이의 차이를 나타내며 그 자체가 정규화된 확률적 독립 noise는 아님.

**대조:** old LUT target vs candidate pole target vs source FFD target; POWER / G4 / unconditional mean / q-only / geometry-conditioned. 각 train split에서 평균·표준화·컷포인트·Ridge 계수를 train-only로 새로 추정 (기존 R2-fold weights/coefficients 재사용 금지). Native LoS noise and Full MP error를 혼합 평균으로 무차별 학습하지 않음; TRAIN scene/route overlap and same-XY overlap 제거는 기존 동일 corridor 데이터에서 여전히 독립 scene을 만들지 못함을 표기.

**검증:** error quantiles, signed mean vs second moment, $V_r,V_s,C_{rs}$/SPD/eigen, Gaussian NLL, conditional 95% residual coverage and sharpness, FP switches, direction/corridor/anchor/mount/θ<2°. G4와 POWER heldout NLL 및 CI; no GT in estimator. 저빈도 극점 관측 5개만으로 글로벌 모델의 물리적 PASS를 선언하지 않음.

**PASS:** corrected source h/H exact, label and route/split lineage, train/test feature leakage zero, all models refit same train folds, original frozen baseline retained. 본문 Claim에 쓸 통계적 일반화는 F6 independent scene 이후.

## F2 — Dual-LP Heading 정보 및 Bias leakage/Mean/Cov/Gate 인과분해

**질문:** 수신 편파비 s가 Range/q-only 대비 Heading·Bias에 제공하는 고유 정보량은 얼마이고, B0 zero-bias에서 오염된 RF가 Bias로 흘러가는 경로는? Mean, C_rs, Gate의 진짜 기여는?

**코드 재사용:** core.py (0a0851e6867c14fec5eefe02df471100cb9e9e1d), Frozen N4-C n4c_joint_sr4.py (40c795fa8799c4090c0766ebdccf6e2be83df6a0), Exp2 exp234_recursive.py (4ec38ff42a5daecf00067902369b03bfec3495cd), R2 Sensor-v2 frozen motion. 기존 Exp2 288-arm baseline 그대로 참조; 중복할 경우 source-refit model의 paired controls로만.

**필수 최소 비교:** DR4, Range-only 4state, s-only S4, Range+s J4/SR4, Range+q(no s observation), full. RF mean $\mu_r$ only/$\mu_s$ only/both, $R_0$, $4R_0$, conditional POWER diag(Vr,Vs) / full(R with C_rs), C_rs=0 *means and diagonals unchanged*, Gate-only relaxed, fixed natural gate, matched original POWER mask. **서로 다른 Gate-mask는 comparable natural online trajectories가 아니며 fixed mask는 offline mechanism control**.

**기전 수식:** $$\delta b_{g,k}=K_{b_g,r}\nu_{r,k}+K_{b_g,s}\nu_{s,k},\qquad K=P^-H^T(HP^-H^T+R)^{-1}.$$ R-only에는 H_{r,ψ}=0이지만 prediction cross-state에서 간접 Heading information 가능; s를 독립적인 측정치로 두 번 사용하지 않음. 동일 prior 기준 one-step squared-error $\Delta e_{\psi}^2,\Delta e_b^2$와 full recursive 다름을 기록.

**기록:** per packet K_b,r/s, K_ψ,r/s, H, innovation terms, before/after Gate NIS (preGate만 조건없는 calibration으로 평가), FP tap, heading/biased XY, time-mean/endpoint Bias 구분, accurate POSE/4state/XY|ψ NEES. M0 B0 spurious RMSE 0.08862°/s is NOT a signed constant. Per-geometry |Hψ| and range LOS alignment, selection bias.

**반증:** if no-s (with q and r) equals full → dual LP unique contribution re-examined; if C_rs off noninferior on independent scenes → drop universal correlation-mechanism claim; if constant 4R0/gate-only matches full → q-model novelty restricted. Exp2 already showed C_rs nonuniversal by mount: preserve negative evidence, do not tune on R2.

**PASS:** frozen N4C baseline parity, correct correlated whitening J4≈SR4 in linear case, all arm factor differences causally attributable under same prior; no hidden GT/future state; scene-generalizable mechanism only if repeated in F6.

## F3 — LoS-safe, state-/geometry-conditioned RF integrity model

**질문:** POWER의 signed error model can improve Full RF without adding ~5cm phantom Range bias in truly clean LoS?

**Two-stream source-aware architecture:**
1. Geometry/heading observable head, based on prior \(x^-,P^-\), source-corrected FFD Hsψ and integrated nuisance uncertainty. DO NOT equate small Jacobian to bad multipath; covariance weak/strong localization feature is separate.
2. RF integrity head, using hardware-visible FP/CIR morphology, power ratios, tap stability, short-window energy, range innovation when safe, and **LoS expected power residual** $\Delta q=q_\mathrm{obs}-\mathbb E[q_\mathrm{LoS}|x^-,m,a]$. Source power needs physically calibrated TX/RX gain and detector scale; if unavailable q-excess unavailable, mark BLOCKED instead of using GT q. The heads are distinct physical axes, not independent random variables by assumption.

**Main model options, complexity ladder:** (A) conservative LoS gate + Full empirical correction as heuristic with explicit online observables and no Bayesian interpretation; (B) two-component clean/MP mixture with train-only estimated means/covs, categorical uncertainty, extra between-regime covariance:
$$
\bar\mu=(1-w)\mu_0+w\mu_1,\quad
R_{\mathrm{mix}}=(1-w)R_0+wR_1+w(1-w)(\mu_1-\mu_0)(\mu_1-\mu_0)^T.
$$
Here \(R_0,R_1\) are **regime-specific trained covariances**, not necessarily the original experimental diag \(R_0\). \(w\) must be calibrated and not a GT oracle. If q is from the same packet as s, claim normalized probability only after deriving/checking \(p(q,r,s|x)\); otherwise publish model as *empirical robust update*, not formal Bayesian posterior. Do not multiply uncalibrated head probabilities.

**Negative controls:** Native LoS with true packet q and Full with identical pose/noise; current POWER-on-LoS failure as explicit non-degradation baseline; hidden port gain ±3/6dB; q-only vs delta-q; q-depth/distance/pattern covariates; reverse/mirror; port swap s sign transform; high-power constructive MP. Every correction must contain uncertainty of the classifier itself (no hard oracle gate pass).

**PASS:** LoS Heading/Bias/XY accuracy no meaningful degradation vs source-corrected R0/S4, Full R2 POWER benchmark not erased, classifier FN/FP and calibration improved on independent scene heldout; no ground truth/CIR oracle-only feature in deployed source.

## F4 — Time/site-correlated Range/s errors and Pose covariance consistency

**질문:** what portion of poor M45 Pose95/NEES arises from persistent RF bias, geometry mismatch, wrong $P_{X\psi}$, correlated measurement reuse, high-power R, or gate selection?

**Source model decomposition:** $$e_{r,s,k}=m(\mathrm{geometry}_k,\mathrm{FP}_k)+b_{\mathrm{site}}(\ell_k)+\eta_k,$$ where terms must be individually identified from independent RF realizations, repeated physical sites and two-port LoS/Full controls. Earlier N4-B s lag-1 up to 0.9 under one moving scene is **not** itself proof of stochastic AR(1) noise.

**Causal controls:** Raw and geometry-/site-/power-detrended ACF/PACF, pre-Gate whitened innovation, accepted-only selection-bias guard, temporal block stability, same-site revisit at different time, different material/reflector layout and seed. Existing GT-oracle 95–135s LPF improvement is offline upper bound; future-centered oracle cannot be used online. Original positive Bias floor 3cm is hypothesis, not measured stochastic covariance component.

**Algorithm arms:** original POWER, corrected source POWER, simple lagged signed-bias residual estimator with real online q/CIR only (no GT, no future), physically paired site random-effects or colored joint factor if identifiable, batch RF correlation vs sequential approximation, separate posthoc P_report calibrator trained on different scenes:
$$P_{\mathrm{report}}=P_{\mathrm{recursive}}+U\Lambda U^T,\quad\Lambda\succeq0.$$
The report-only correction **never alters recursive gain**, and is distinct from a true Bayes posterior; cannot be tuned on the evaluated scene itself. Alternative full recursive colored filter only if augmented state observability rank/SVD and unbiased dynamics pass.

**Measures:** per scene and across seeds Pose/4state/Heading/Bias/conditionalXY/narrow-axis NEES and 95% coverage; time-binned/FP transition performance; sharpness (detP/eig/credible volume), NLL/CRPS or appropriate multivariate proper score, bias point RMSE, predictive likelihood and pre-gate NIS; CIs cluster by **scene**, not 829 frames.

**PASS:** consistency improvement is real only if independent heldout scene coverage and proper scores improve **without point RMSE or sharpness collapse**. Optional reporting-only calibration can be published solely as independent heldout *reporting* if actual filtering posterior remains heuristic. Failure → document unresolved overconfidence honestly, keep POWER accuracy baseline.

## F5 — G4/NLL recursive inversion, two-port FP feature robustness and information geometry

**Question:** Why G4 heldout measurement NLL is better (−1.7038 vs POWER −1.5898) while its M45 full L2 J4 Heading is worse (1.133° vs POWER .727°) and M0 Pose NEES worse (G4 33.36 vs POWER 12.89)?

**Matched analysis:** G4/Pooled and POWER on identical prior/packet, separate mean prediction from bin covariance choice (G4 detector_s_span bin, POWER q bin), explicit mean↔cov swaps, no-G4/with-G4 quality, same gate one-step and actual recursive, $K_{\psi,s}$/$K_{b_g,s}$ spikes, min eigR, covariance condition number, fixed selected FP threshold tap transition, preGate NIS, packet harm. G4 M0 L2 Heading 1.845° is **slightly better than POWER 1.991°** and this exception must be preserved.

**Signal processing stress:** original 257 bins, Hann 4N zero-pad, 30% first-edge stronger RX common tap, $s=(P1-P2)/(P1+P2)$. Compare 20/30/40% first edge, 1/3/5 tap near-FP integrated energy, FP/total CIR power, receiver channel gain balance and common ±3/6dB AGC gain (s invariant only under common scaling), TX/RX port flip, group-delay offset and first-path tap jitter. Hardware variants must recalculate appropriate physically consistent packet r/s, NOT simply relabeling s after tap change. Keep same raw complex Full and native LoS per arm; hardware-available only for online predictor, complex coherent Jones as offline oracle.

**Geometry:** use actual Hsψ and $P^-$; nominal fixed-P reference info vs operational nuisance-marginalized info must be separately reported, FFD LUT seam/harm/alternate Heading branch negative controls. **Active yaw scan** requiring actual new RF Full channel at every yaw can be a later optional study; do not claim scan mitigates multipath from rotating just LoS LUT.

**PASS:** if no gain spike occurs, "G4 overfit causes gain spikes" rejected. If s-only/no q does not beat DR, RF architecture claim restricted. If corrected FP variant improves power shift + los guard + Full, validate on F6 independent scenes.

## F6 — Independent EM Full-RF scene & reproducible motion simulator

**Required data:** source FFD bank for F0; independent Sionna Full complex two-port H(f) and matched Native LoS per physical yaw/pose, independently generated geometry/material/reflector scenes, sensor-v2 matched true 0.2s interval inputs, scene hash+antenna mount+RF seed+sensor seed. Must not create Full RF by rotating LoS LUT or reuse the exact same corridor realization. See 04_SIMULATION_REQUEST_SPEC_KO.md.

**Statistical design:** old R2/R4/R5 purely legacy/pilot. Before model selection, new scene IDs split by physical layout, with TRAIN ≥2 scene, VALIDATION ≥1 scene, locked TEST ≥3 truly distinct multipath scenes (minimum publication-oriented plan; ≥5 TEST preferred). Each scene test B0/L0/L1/L2, positive and negative biases, 0°/45° plus unseen 15°/30°, anchor A/B or meaningful independent positions, straight/reverse/turn/curved/static-yaw, ≥5 paired sensor seeds where feasible. RF channels also require **independent multipath realizations**, not just independent motion noise. Hold all hyperparameters/feature selection after train+val freeze before test.

**CI:** scene clustered bootstrap/repeated scene means; report cluster sample count, show each scene tail and worst-case. Time frames correlated, 5 seeds on a single Full scene not equal five independent scene observations. Avoid significance claims when test scene sample too small.

**PASS:** bound train/test leakage, all source scene/seed hashes validated, unseen geometry sensitivity, stable Full RF benefit & clean LoS no-harm, claimable hardware robustness only with hardware evidence. Otherwise model remains one-corridor simulation exploratory result.

## F7 — Independent last-pass, frozen estimator and paper figure/data package

**Prerequisite:** F0 original FFD direct model PASS, F1 corrected labels/refit PASS, F2 mechanism attribution reported with falsified branches, F3 LoS-safe guard, F4 consistency mechanism or explicit irreducible limit, F5 feature/G4 negatives audited, F6 independent scenes. If hard blockers persist, downgrade paper to bounded *single-scene simulation and falsification study*, NOT secret PASS.

**Pre-register engineering margins on validation, not test:** compare all held-out scenes to corrected CLEAN LoS R0: Heading relative worsening and absolute small-angle tolerance (example design tolerance max(5% baseline RMSE,0.05°)), XY max(5%,1cm), Bias max(5%,0.005°/s); **these are proposed engineering margins, not universal statistical facts**. Final claim must additionally show scene-block paired CIs rather than PASS off arbitrary mean alone. Evaluate Full RF POWER vs improved candidate for Heading/Bias/XY noninferiority and Pose/conditionalXY NEES reduction and 95%-coverage improvement; posterior calibrated **only if** heldout interval/NEES consistency and sharpness jointly supported. If no statistically defensible CI, label insufficient evidence.

**Outputs:** finalized source/data/weights SHA; exact performance CSV by scene/route/anchor/mount/bias/seed/filter; independent per-frame x-/P-/x+/P+/z/q/H/R/μ/K/NIS/FP/oracle scoring; all failures including zero/NaN/invalid Jacobian explicitly tagged; 4 DoF/3 DoF/1 DoF/2 DoF, bias Schur/posterior coverage, LoS/Full, late hard cases; README formulas; figures main and supplementary; frozen analysis scripts; plot labels showing sample/DoF/GT usage. Original N4-C POWER never overwritten.

**Stop rule:** No independent scene or FFD bank => no "generalizable", "normalized likelihood", "probabilistically consistent" in title/abstract; leave missing stage as BLOCKED_INPUT and use bounded honest scope.
