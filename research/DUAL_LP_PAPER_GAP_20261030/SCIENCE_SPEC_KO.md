# Science/measurement contract — DLP-EKF-GAPS-001
Status: DRAFT; equations are proposed reference definitions, not new experimental conclusions.

## Units and states
4state x_k=[p_x(m),p_y(m),psi(rad),b_g(rad/s)]^T; timestamp seconds; gyro increment rad; wheel distance meters; known tag height z_t=0.45 m; fixed anchor a_i=(a_ix,a_iy,a_iz) m.
x^-_k=f(x^+_{k-1},u_k); F_k=partial f/partial x; P^-_k=F P^+ F^T+Q_k. Original locked f/F/Q and initial x/P must be used without deriving alternative controls from GT. The exact numeric f/F/Q are P0_TO_RESOLVE per selected original 4state source; neither 3state nor 6state is an identical substitute.

## C0 RF observer
H_f(k,rx,tx) complex, frequency grid 257, TX0(+45); IFFT/Hann/4N and detector per archived observation.py. n0 = first 30%-of-strongest-port peak threshold crossing, same n0 for two ports; P1=|h_+(n0)|²,P2=|h_-(n0)|²; z_s=(P1-P2)/(P1+P2) dimensionless. z_r detector-derived meters. First-path extraction and range calibration/source convention must be locked per arm; no invented range data.

LoS model h_s(x,a_i,mount) = SourceFFD(p,psi; a_i) with full frequency FFD source, evaluated from ESTIMATED state in filters. h_r(x,a_i)=sqrt((p_x-a_ix)^2+(p_y-a_iy)^2+(z_t-a_iz)^2)+b_{r,det} [m]. Existing legacy b=-0.5315983906250129 m is an older continuous bridge and not a claim of exact detector likelihood. All model choice and source SHA must be locked before replay. H_s=[∂h_s/∂x,∂h_s/∂y,∂h_s/∂psi,0]; H_r=[dx/d,dy/d,0,0]. b_g directly unobserved, but indirectly via F and P cross-terms.

## Baselines
M0 = same 4state f/Q motion with RF disabled.
M1-A = 1 anchor range-only using same 4state f/Q, scalar R_r and predeclared chi²_1 gate.
M1-B = 1 anchor joint [r,s] conventional mean-zero diagonal R0 and chi²_2 gate. If original conventional baseline uses a different observer, compare separately rather than rewriting its historical score.
M1-C = ≥3 anchors Range-only. For synchronized t, z_r,t ∈ R^m, h_r,t ∈ R^m, H_r,t ∈ R^{m×4}, R_t∈R^{m×m}. Either batch joint update with full joint covariance or deterministic per-anchor sequential update only when covariance conditional transformations make them algebraically equivalent. Announce simultaneous vs asynchronous packet policy, missing packet, gate dimensionality, correlated inter-anchor measurement errors, shared clocks, effective R and update count. 3-Anchor data cannot be synthesized from copied A/B packets or independent unrelated scenes.
M2=single anchor [r,s] characteristic-aware candidate, RESERVED.

## Fair comparison
Match physical scene, anchor pattern/banks, carrier/grid, receiver/noise/observer, route, exact pose/timestamp, gyro/wheel control input, known z, evaluation t>=30s and both B0/L2, initial x/P, state dimension and numerical filter. Treatment is observation modality + number of anchors; cost difference is explicitly unavoidable. Require two comparisons:
(A) realistic baseline per architecture: multi-anchor receives more RF resources, plot resulting accuracy plus count/resources;
(B) same-resource secondary sensitivity: equal total update rate or packet budget, if defined and feasible, and disclose information sacrificed. Never claim both identical antenna count and identical RF geometry. Extra anchors must not modify original C0 H or other arms.
Same scene new anchor is same scenario family, but new physical channel data and extension C0+; do NOT label as byte-identical frozen C0.

## Statistical objects
e^{RF}_r=z_r-h_r(x_GT), e^{RF}_s=z_s-h_s(x_GT): offline truth-only diagnostics.
nu=z-h(x^-) pre-gate innovation; S=HP^-H^T+R; K=P^-H^TS^{-1}. Error/innovation/conditional mean/variance are distinct. Joint R_rs has units meter (s dimensionless). Full covariance PSD.
Primary Heading wrapped RMSE deg, XY RMSE m, gyro-bias RMSE deg/s; coverage/NEES/NIS calibrated by correct dof, gate acceptance/starvation, trajectories, resource budget, LoS harm; independent scene count = 1 for current C0. Include both matched-prior one-step mechanism and actual self-gated full recursive performance when available. Truth/oracle never at online input.

## Source/data consistency gates
P0 compare exact hashes and full pose keys; H_FULL/H_LOS/channel order/tx rx/frame/mount; stored z vs freshly extracted z; h vs known direct source; time order; f/F/Q and initial seed parity; all missing/invalid packets. No interpolation of uncomputed new-anchor poses, no borrowed same-sample synthetic copy, no silent threshold changes.
No new RT until geometric feasibility and canary and cost sign-off. Data equivalence depends on physical configuration, not just file name. P0 interim classification: SAME_C0_RAW / SAME_C0_RECOMPUTED / C0_EXTENSION_NEW_RF / EXTERNAL_DATA / ORACLE_ONLY / MISSING / UNVERIFIED.

## 3-D reserved
Spatiotemporal covariance, effective information, signal reuse and time/space decomposition not specified or interpreted here; use existing MBVAR-INFO governed process separately. Other sections must not preempt this choice.

## Pre-run falsifiability
H0: Existing R-only 4state and ≥3-anchor equivalent C0 traces exist and pass exact provenance; H1: they do not. Primary outcome of this proposer scope is evidentiary status, not numerical estimator advantage. For any future generated anchor data, the target is reproducibility and same-scene identity, not an assumed M2 win.
