# 05. 논문 스토리라인, Claim Boundary, Figure·Table 사전등록

**주의:** 본 문서는 기존 검증과 새로운 미해결 가설을 정리한 *submission planning*, 논문 채택/성공 보증이 아니다. F0 source physics, F3 clean LoS, F6 independent scene 데이터 없이는 강한 일반화 주장을 사용할 수 없다.

## 1. 과학적 중심: 안테나의 직접 Heading 정보 + 오염된 관측의 상태 결합

Range + dual-linear-polarization UWB:
$$
x=[x,y,\psi,b_g]^T,\quad z=[r,s]^T,\quad s=\frac{P_1-P_2}{P_1+P_2}.
$$

Instantaneous LoS FFD measurement Jacobian $H_{r,\psi}=0$, $H_{s,\psi}\neq0$인 물리적 작동점에서 s는 Heading을 직접 제약한다. Gyro bias는 r,s의 직접 Jacobian 항이 없지만, 운동모델의 $F_{\psi,b_g}=-\Delta t$와 $P_{\psi b_g},P_{xb_g},P_{yb_g}$를 통해 RF innovation에서 갱신된다.

**기존 관찰:** Full RF B0 actual bias=0에도 기존 J4 M0 Bias RMSE 0.08862°/s, Heading RMSE 7.490°; POWER M0 Bias RMSE 0.02160°/s, Heading 1.773°. 이는 *중요한 연구 동기*, Signed s bias vs Range cross-correlation 중 어느 원인으로 개선되는지 F2에서 반드시 기전 분리.

현행 q-only POWER의 역할은 Heading 센서가 아니라 same-packet RF observation r/s의 경험적 오차 조건부 보정. "19개의 독립 물리파라미터가 범용 복원" 등 과장 문구 금지. 19는 2 slopes+6 bin intercepts+9 covariance entries+2 quantile cuts의 유효 수치기술량이다.

## 2. Paper Option A: 현재 결과의 방어 가능한 좁은 메시지

**Possible safe working title:**

Dual-Polarized Single-Anchor UWB Heading Estimation under Multipath: Empirical Signed-Error Correction and Recursive Uncertainty Failure Modes

범위: 단일 corridor frozen simulation에서 Dual-LP Heading sensitivity와 spurious Gyro Bias state coupling, POWER empirical improvement, Native LoS negative transfer, source LUT pole issue, pointwise-vs-recursive uncertainty gap, explicit limits. F0 source LUT interpolation/FFT source issue는 본문/보충자료에 노출하고 검증된 수준만 주장.

**허용되는 contributions:**
- FFD-based geometry sensitivity (high/low-Hsψ, multiple-heading ambiguity), including source correction and actual observer QA.
- Spurious gyro-bias estimation under B0 true Bias zero and paired model improvements in explicitly stated single RF scene.
- C_rs can help at one mount but hurt another; same-packet mean and covariance sign/interactions cannot be universally advertised.
- Heldout RF packet residual NLL/coverage and Pose NEES/coverage are different statistical objects, so a model may improve one but fail on the other.
- Native LoS harm and pole singularity are scientifically meaningful falsifications/physical model-validation lessons.

**금지:** 16 independent scene success, posterior Bayesian-consistent, full robust recovery, source FFD pole corrected without raw bank, posterior covariance 95% from measurement 94.5% figure.

## 3. Paper Option B: F0–F7 성공 때만 가능한 강화 스토리

**Conditional working title:**

LoS-Preserving Dual-Polarization UWB Fusion with Geometry-Conditioned Multipath Integrity for Single-Anchor Heading and Gyroscope-Bias Estimation

추가 통과 필요: source-calibrated FFD no-pole and acceptable off-pole interpolation; independent LoS guard in actual EKF; signed mean / C_rs / Gate mechanism on new scenes; temporal/site contamination identification; independent scene-clustered state consistency and no degraded point RMSE/sharpness; tested hardware-available features for deployability.

**True Bayesian observation language only if** a coherent normalized $p(q,r,s|x)$ or correctly derived conditional equivalent is implemented and independent heldout likelihood verified. Even properly normalized observation likelihood does not guarantee Gaussian-EKF state posterior calibration under severe nonlinearity; need F7 posterior tests. If instead robust heuristic mean/R gate succeeds, call it exactly that.

## 4. Introduction and theory order (one message per Figure)

1. Single-anchor range geometry provides no direct heading at an epoch; Gyro integrates Bias, sparse anchor robotics needs other independent physical information.
2. Dual-LP three-dimensional TX/RX FFD and polarization ratio s provide heading-sensitive observation, information depends on mount/anchor/physical incidence, not universally invertible.
3. Multipath, FP tap and antenna radiation patterns corrupt signed s/r, which updates cross-correlated 4-state including weakly observed bias. B0 spurious Bias observation.
4. Empirical FP-power-conditioned correction is an informative *baseline*; signed means and correlated R must be causally separated; q's distance/path/gain dependence and shared packet cause endogeneity.
5. Critical paradox: Pointwise residual likelihood vs end-to-end recursive Pose uncertainty. Geometry-conditioned conditionalXY narrow axis, temporal site persistence, prior state error and source-model defect (pole).
6. Safe physical correction and uncertainty integrity: first repair source FFD LUT; correct training labels; ensure Native LoS protection; geometry+quality score and time/site-aware filter or honestly calibrated report-only cov.
7. Independent Full RF scenes to delimit generality; publish negative cases (mount45 C_rs removal and LoS harm) and validity limits even if improved method works.

## 5. Figure + Table evidence storyboard

| Paper item | Key visual and numeric message | Required sources / completion condition |
|---|---|---|
| **Fig.1 Antenna/geometry** | TX+45 RX±45, robot anchor, same FP tap port powers; LoS FFD s(Hψ) vs mount and yaw, duplicate Heading branches | N4-Q physical plus **F0 direct bank QA** |
| **Fig.2 Polar source integrity** | θ0 old vs candidate vs source-FFD direct response, $h_s$ and Jacobian X/Y/ψ, 1mm ring; off-pole F01 FAIL→fix | Pole observations existing; source **F0 pending** |
| **Fig.3 B0 false Gyro Bias** | Signed full timeline b_g true 0, R0 vs POWER, Heading; $K_{b_g,r}\nu_r$ and $K_{b_g,s}\nu_s$ from matched same prior | Existing N4-C; F2 mechanism completion |
| **Fig.4 Signed bias/Crs ablation** | μr / μs / Rdiag / C_rs / Gate-only / 4R0, both Mounts, one-step vs natural recursive. Preserve C_rs reversal | Exp2 existing, 4R0/gate-only and cross-scene F2/F6 |
| **Fig.5 Clean LoS non-degradation** | R0 vs Full-trained POWER vs corrected LoS-aware model: Native LoS/Full, R2 L2 Mount0/45 and independent scenes | Current Exp4 failure, F3/F6 model |
| **Fig.6 Pointwise-vs-recursive paradox** | N4-B G4 NLL −1.7038 vs POWER −1.5898, M45 G4 Heading 1.133° vs POWER .727°; RF residual95=94.51% vs Pose95=12.3%; gain/NIS diagnostics | Existing metrics + F5/G4 mechanism + F4 consistency |
| **Fig.7 Narrow XY axis and time** | Schur XY|ψ NEES and eig axes, matched LOS Range residual, M45 t95–135s. GT lowpass oracle upper bound not deployable | Exp1 0.984 alignment and Exp3 32.97→2.46 local; F4 site/time origin |
| **Fig.8 External science** | scene-split paired RMSE and consistency/LoS safety; each scene separately not just average across 829 samples | independent scenes F6+locked F7, omit if BLOCKED_INPUT |
| Table I Experimental source | FFD SHA, raytracer/observer, $Q,R_0$, RT modes, train/val/test scene/sample independent groups | 03/04 manifest, no false source provenance |
| Table II Algorithm ablations | 4-state vs S4/r-only, calibrated predictor, F0/F1 model variations and baseline | F2/F3/F7 |
| Table III End-to-end accuracy | B0/L0/L1/L2, Mount, full/los, Heading/Bias/XY, R0/POWER/new | F7 |
| Table IV Uncertainty trust | 4/Pose/Heading/condXY NEES/coverage, NIS, logdet/sharpness and test-scene CI | F4/F6/F7 |
| Supplement | extra R2/4/5 observations, G4 tails, pole seam failures, negative-control traces, scene hashes and scripts | All artifacts, no result cherry-picking |

**Clear caption rules:**
- N4-B "95% coverage" = joint 2D **measurement residual** [r,s]. N4-C "95% coverage" = **3D pose posterior**; different DoF/objects.
- B0 Gyro Bias 0.08862°/s = time-integrated **RMSE**, not constant signed offset.
- Each plot clearly labels whether GT is online unavailable (oracle), mounted geometry, channel (LoS/Full), time window, n scenes, n seeds and if source LUT is original/pole-candidate/source-validated.
- Do not use 829 dependent time steps as n=829 independent experiments; scene-level CI and source seeds distinct.

## 6. Final manuscript claim-gate checklist

| Desired phrase | Currently allowed? | Conditional acceptance |
|---|---|---|
| "A single anchor with dual-LP s yields geometry-dependent direct heading-sensitive RF observation" | Yes, with limitations | FFD source/physical observation QA strengthened by F0 |
| "Multipath can induce spurious gyro bias" | Yes for frozen B0 Full RF | F2 establishes causal contribution of s/r vs Gate |
| "POWER_JOINT recovers full robust s" | No | Too strong even if one scenario improved |
| "Cross covariance universally protects gyro bias" | No, contradicted by M45 | Only geometry-specific calibrated empirical effect if cross-scene validated |
| "Posterior covariance is 95% consistent" | No | F4/F7 heldout posterior consistency and honest interval sharpness |
| "LoS safe" | No, current version directly fails | F3 and independent F6/7 no-harm |
| "N4-B 94.5% proves EKF calibration" | No, different statistic | Never claim equivalence |
| "The new estimator generalizes" | No | Locked F6/F7 unseen multiple Full RF scenes |
| "Hardware-ready" | No | Real CIR/gain/time calibration SIM-D or explicitly simulation-only |

## 7. External methodological references (not evidence of this project's experimental success)

- Maranò, Gifford, Wymeersch, Win (2010), *NLOS identification and mitigation for localization based on UWB experimental data*, IEEE JSAC 28(7):1026–1035, DOI 10.1109/JSAC.2010.100907. Official MIT-hosted bibliographic/full paper record: https://dspace.mit.edu/entities/publication/28966aeb-352b-4d84-8f02-9d7193ad01b6 . Compare CIR-based LOS/NLOS quality learning and *limit of feature transport*, not one-anchor polarimetric state correction equivalence.
- Gneiting, Balabdaoui, Raftery (2007), *Probabilistic forecasts, calibration and sharpness*, JRSS-B 69(2):243–268, DOI 10.1111/j.1467-9868.2007.00587.x. https://academic.oup.com/jrsssb/article/69/2/243/7109375 . Use principle: increase interval width alone does not prove honest calibration; inspect calibration and sharpness.
- Gneiting and Raftery (2007), *Strictly Proper Scoring Rules, Prediction, and Estimation*, JASA 102(477):359–378, DOI 10.1198/016214506000001437. https://doi.org/10.1198/016214506000001437 . Use proper scoring rules when comparing probabilistic predictions and experimental NLL vs recursive performance.

Literature contributes accepted methodology/context. Numeric RF results, source-bug proof, s/R covariance and filter accuracy claims come exclusively from pinned original project artifacts and future completed F0–F7 data, not from citations to unrelated papers.
