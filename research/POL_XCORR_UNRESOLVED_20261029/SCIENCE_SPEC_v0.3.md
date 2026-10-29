# SCIENCE_SPEC — POL-XCORR-001 (v0.3 DRAFT, pre-audit)

v0.2(`SCIENCE_SPEC_v0.2.md`)를 계승한 DRAFT. 변경 근거: `reviews/PROPOSER_DECISION_03.md`의 P0 label-free R-14 감사. 기존 v0.2 파일·실행 결과는 보존한다.

각 식에 단위와 추정 성격을 표기한다: **[model-truth]** = 가정한 물리 모델에서의 유도, **[deterministic]** = 학습 없는 관측 함수, **[learned]** = train route에서 적합, **[ORACLE_ONLY]** = 채점·진단 전용.

## 1. 관측 체인

1. H_c[pose, k, rx, tx] (복소, 무차원), k = 257 bins, 6.2504–6.7496 GHz. 주분석 tx = 0(+45).
2. CIR: h_rx(n) = IFFT_{4·257}( H·w_Hann ) · 257, tap 간격 **Δt = 1/(1028·Δf)**, Δf는 런타임에 `freqs_hz.npy`에서 읽는다(현 자산 Δf = 1.95 MHz → Δt = 0.4988526 ns). 공칭 해상도 1/B, B = 256·Δf = 499.2 MHz → 2.003 ns. 복소 baseband(대역 하단 기준) [deterministic].
3. 첫 경로 tap n₀: 강한 포트의 |h| 최대값의 30% 이상인 첫 tap; 두 포트 공통 [deterministic, v_replay 동일].
4. s(n) = (|h₊(n)|²−|h₋(n)|²)/(|h₊(n)|²+|h₋(n)|²) [무차원]; s_fp = s(n₀); ds1 = s(n₀+1)−s(n₀).

## 2. 물리 모델 [model-truth]

단일 TX 편파, 두 RX 포트 벡터 h(t) ∈ C²:

h(t) = a·p(t) + Σ_k b_k e^{−j2πf_c δ_k} p(t−δ_k)

- a, b_k ∈ C²: LoS/반사 경로의 RX 포트 투영 Jones(안테나 패턴·자세 포함).
- p(t): Hann 창 대역제한 펄스(실수, 대칭). B_rms² = ∫f²|P|²/∫|P|².
- **F1 (이상화):** k 없음이고 **a가 주파수에 무관**하면 rank J = 1 ⇒ det J = 0, q = 0. a의 타원성(φ, S3)과 무관.
- **F1′ (실제 안테나):** SourceFFD는 포트 field를 주파수별로 적용한다 → a_±(f). a₊(f)/a₋(f)의 선형 위상 성분은 포트 간 등가 시간 오프셋 Δ_ant(θ, φ), 진폭 기울기는 포트별 펄스 형태 차이이다. 따라서 **LoS에서도 q > 0일 수 있고 방향(yaw·고도각)에 따라 변한다.** 기존 증거: 대역 전체 jones_diversity 중앙값 LoS 0.0041 / Full 0.103 (PHYSICS_RS_STAGED). 이 floor는 F3의 Δ와 같은 nuisance로 취급하며, 크기는 P0에서 측정하고 S0 기준 q_ref와 비교한다(계약 v0.2 규칙).
- **F2 (2-path, 소 δ):** S0에서는 h = a·p(t) + b·e^{jψ}·p(t−δ), **ψ를 δ와 독립 파라미터**로 둔다. b̃ = b e^{jψ}, h ≈ (a+b̃)p − b̃δ p′.
  det J = |(a+b̃) ∧ (−b̃δ)|² · det G, G = Gram{p, p′} on W ⇒ **det J ≈ δ²|a∧b|²(E_pE_p′ − |⟨p,p′⟩|²)**, a∧b ≡ a₊b₋ − a₋b₊.
  **q ≡ 4detJ/(trJ)² ≈ 4δ²(2πB_rms)²|a∧b|²/|a+b̃|⁴** (대칭 W에서 ⟨p,p′⟩≈0). ψ 고정 시 log q vs log δ 기울기 2. 실제 이동에서는 ψ = −2πf_cδ로 결합되어 분모 |a+b̃|가 함께 변하므로 기울기 판정 대상이 아니다.
  1−DoP = 1 − √(1−q) ≈ q/2 (파생값). 기존 `jones_diversity` x = λ_min/tr과는 q = 4x(1−x) 관계(같은 함수족, 창만 다름).
  range bias(첫 경로 tap 이동)는 O(δ), 감지량은 O(δ²).
- **F3:** **주파수 평탄한** D = diag(g₊, g₋)에 대해 h → Dh ⇒ J → DJD^H ⇒ ε_ρ = detJ/(J₁₁J₂₂) 불변. 주파수 의존 포트 응답(F1′)이나 포트 간 시간 오프셋 Δ(h₋(t) → h₋(t−Δ))에는 불변이 아니며, F2와 같은 구조로 단일 경로에서도 det J > 0 ⇒ false positive.
- **F4 (이동):** 주행거리 x에 대해 Δd(x) = d_ref − d_LoS.
  - 반송파 위상 ψ(x) = 2πΔd/λ, 공간주기 **Λ = λ/|dΔd/dx|** (λ = 4.61 cm).
  - 포트별 |h_±(n₀)|² ∝ |a_± + b_± e^{−jψ}|² → b₊/a₊ ≠ b₋/a₋ 이면 두 포트가 서로 다른 위상으로 fading. s_fp(x)는 Λ 주기 성분을 가진다.
  - envelope shape(폭·왜도·peak–centroid)는 Λ 주기로 진동, 진폭 ∝ |b/a|·δ/T_p.
  - δ 자체의 변화 스케일 c/(B|dΔd/dx|) = Λ·f_c/B ≈ 13Λ ⇒ "breathing"은 δ→0 접근이 아니라 ψ 회전 현상.
  - LoS 단독에서도 s(x)는 yaw·고도각에 따라 변한다(heading 신호). 따라서 "LoS면 두 편파가 같은 비율로 감소"는 성립하지 않는다.

## 3. 지표

| ID | 정의 | 단위 | 성격 | 위상 동시성 | prior |
|---|---|---|---|---|---|
| M0 | **G5 전체** (`features.py`: range_m, log_fp_power, abs_s_fp, early4/8/16, delay_rms_ns, peak_diff_ns, eta_fp_win80, s_diff4/8/16, tap_pol_var80, jones_diversity, freq_s_var, detector_s_span, detector_delay_span_ns) + \|ds1\| | 혼합 | deterministic (기존 코드 그대로) | 일부 필요 | 불필요 |
| M1a **PRIMARY** | **q_W = 4detJ/(trJ)²**, W = n₀+[−2,4] | 0..1 | deterministic | 필요 | 불필요 |
| M1b **SECONDARY** | ε_ρ = detJ/(J₁₁J₂₂) | 0..1 | deterministic | 주파수 평탄 이득·위상에 불변, 시간 오프셋·주파수 의존 응답에 민감 | 불필요 |
| M2 | R(τ) = Σ_{t∈W} h₊(t)·h₋*(t−τ), τ ∈ [−8,8] tap, h₋는 창 밖도 실제 CIR 값; ρ(τ) = R(τ)/√(Σ_W\|h₊\|²·Σ_{W−τ}\|h₋\|²); τ* = argmax\|ρ\| (동률: \|τ\| 최소 → 음수 lag 우선); A_k = (\|R(τ*+k)\| − \|R(τ*−k)\|)/(\|R(τ*+k)\| + \|R(τ*−k)\|), k = 1, 2 | tap, – | deterministic | 필요 | 불필요 |
| M3 | 포트별 \|h_±\|² 창 n₀+[−2,6]에서 2차 모멘트 폭 σ_t [ns], 왜도 γ, peak–centroid 오프셋 [ns]; 포트 차 Δ | ns, – | deterministic | 불필요 | 불필요 |
| M4a | 인과 창 L(0.6 m) 안의 s_fp(x)와 log\|pk₊\|−log\|pk₋\| 의 국소분산(창 내 1차 추세 제거) | – | deterministic | 불필요 | 불필요 |
| M4b | 같은 창의 M3 각 성분 국소분산 | ns², – | deterministic | 불필요 | 불필요 |
| M4c | 연속 샘플 간 Stokes 단위벡터 측지거리의 창 평균, \|Δyaw\| < 1°/step 구간만 | rad | deterministic | 필요 | 불필요 |
| M4d | segment의 high-pass s(x) PSD 중 예측 Λ_floor/Λ_wall ±20% 대역 전력 비율 | – | 진단(기하 예측 사용) | 불필요 | 대략적 위치 |

- 유효성: n₀−2 ≥ 0, n₀+6 < N, 그리고 lag ±8 적용 시 h₋ 인덱스가 [0, N) 안일 때만 valid. 아니면 `INVALID_WINDOW` 플래그로 보존·계수하고 clamp하지 않는다. 분모 ≤ tiny → NaN + `NULL_PORT`.
- log_fp_power = log10(max(P₊(n₀)+P₋(n₀), tiny)) (`features.py` 정의). HP_PACKETS 열과의 parity는 P0 R-12.
- 참고(비교 제외): d0 = s_Full − h_s(prior) — prior 필요.
- 진단 전용(negative control): φ_fp = arg(h₊(n₀)h₋*(n₀)), S3_fp. 단일 경로에서도 0이 아님을 S0·LoS 채널로 시연.

### R-14 — 7-tap coherency weak-port rule (post-P0, pre-freeze; label-free)

Let \`a=Re(J11)\`, \`b=Re(J22)\`, \`tr=a+b\`, \`det=ab-|J12|²\`. For valid finite PSD J with tr>0 and a,b>0, define
\[
u=\frac{\min(a,b)}{a+b},\quad
\mathrm{WEAK\_PORT}=\mathbf1[u<0.05],\quad
q_W=4u(1-u)\epsilon_\rho.
\]
The P0 LoS measurements (9519 rows) imply 3492/9519 WEAK_PORT; TIMELINE 3105/7251 (42.8%). Rates vary by case from 1.0% to 67.0%. This is a **post-P0, label-free observation**, not a label-optimized threshold. A high \(\epsilon_\rho\) is not proof of numerical corruption.

- **Keep original validity:** \`INVALID_WINDOW\`, \`NULL_PORT\`, and numerical large-negative-det errors remain fatal/invalid as already specified. A finite weak-port observation stays \`VALID\` plus independent boolean \`WEAK_PORT=True\`.
- **Primary E1** has q_W only as the incremental M1 feature. M1b epsilon_rho is secondary/diagnostic, never a primary gate.
- **No weak-port row deletion or feature clipping** in E1/E2/E4. \`q_W\` is defined and retained even when weak. \`epsilon_rho\` is stored for ALL finite valid rows.
- **Secondary E1c:** assess epsilon_rho added to M0+q_W; all-valid and strong-only sensitivity. Strong-only analysis filters BOTH baseline and comparator to exactly the same test/train keys and reports counts per held-out route, case, phase. If missing epsilon is intentionally created for an exploratory arm, use train-only imputation with an indicator and retain all test observations; never silently discard.
- **Weak-port threshold sensitivity:** 0.02 and 0.10 are descriptive only; 0.05 is the single declared nominal flag. Do not choose a threshold using performance labels.
- **P0-v0.3 extra sanity:** independently compute u from the 7-tap J diagonal (not FP-tap power), verify q=4u(1-u)epsilon and direct \`tap\`/\`branch\`/\`valid\` parity on Full+LoS. A strict \`WEAK_PORT\` flag is not a reason to assign NaN; only invalid windows/NULL_PORT are.

### v0.3 primary comparisons

\[
E1=\Delta AUC_r(M0+[q_W],M0).
\]
\[
E1b=\Delta AUC_r((M0-\mathrm{jones\_diversity})+[q_W],M0)\quad\text{(secondary)}.
\]
\[
E1c=\Delta AUC_r(M0+[q_W,\epsilon_\rho],M0+[q_W])\quad\text{(secondary; matched-key analyses)}.
\]
For E2/E4: the phrase \`M0+M1\` now **means \`M0+[q_W]\` only**. All other previously frozen proposed timeline/LORO, bootstrap, S0 q-law, R-03 q_ref floor and hardware rules are unchanged.

## 4. Label [ORACLE_ONLY]

- T1 e_s = s_Full − s_LoS, T2 e_r, T3 η_W = Σ_W‖h_F − h_L‖² / Σ_W‖h_L‖² (두 포트, tx=0), T4 경로별 δ_k, |a∧b_k| (R-01 PASS 시만).
- 정적 성분 경고: ceiling 경로(δ ≈ 0.05–0.3 ns, Λ ≈ 10–22 m)는 F2·F4상 M1–M4로 감지 불가. T4로 e_s 중 그 몫을 분해 보고.
- positive class = |T1| ≥ train route q0.80. 창 지표(M4)는 같은 인과 창의 |T1| 평균으로 label하며, 임계는 fold별 train route의 창 평균 |T1| q0.80.
- 표본: timeline pose만 주분석. `STATIC_YAW_SWEEP`(timeline 밖, 고정 XY × 18 yaw)은 진단 전용.

## 5. 단계별 설계

| 단계 | Gate | 입력 | 내용 | 판정 |
|---|---|---|---|---|
| P0 | G0→G1 | `INPUT_LOCK_v2` | CORE(R-02, R-04, R-05, R-12, R-13, 불변성 fixture), T4_ONLY(R-01), MEASURED(R-03 LoS q floor, block 수) | CORE 전부 PASS (T4_ONLY 실패는 T4만 제외) |
| S0 | G2 | 합성 | LAW: ψ 고정 층별 기울기 ∈ [1.9, 2.1] (δ ∈ [0.05, 1.0] ns, δ=0·근접 상쇄 층 제외); PHYSICAL(ψ=−2πf_cδ) 보고만; a∥b → 0; 단일 타원 경로 → q=0·φ≠0; q_ref 계산 → R-03 규칙 판정; SNR·σ_Δ별 noise floor | H1 PASS, R-03 ≠ REDESIGN |
| P1 | — | 7 case | E1, E2; drive/turn 분리; LoS 채널 동일 지표 = floor; m0 vs m45 | go rule (PLAN_PARAMETERS) |
| P2 | — | drive segment ≥ 2 m | P2a E3(결정 gate) → P2b 주기 일치 → P2c E4 → P2d turn 대조 | P2a 미달 시 M4a/M4b STOP |
| P3 | — | P1/P2 생존 지표 | 포트 위상·이득 무작위, σ_Δ, SNR, 1.0016 ns 재표본화 | E5 산출(판정 아닌 허용치) |
| P4 | — | VNA 2×2 (외부) | 반사체 vs face-to-face 부호 검정 | 부호만, 정확도 주장 금지 |

## 6. 경쟁 설명과 통제

| 경쟁 설명 | 예측 서명 | 통제/개입 |
|---|---|---|
| LoS 자체 타원성(안테나 cross-pol, 자세) | φ, S3 ≠ 0이지만 (주파수 평탄 시) q = 0 | S0 fixture, LoS 채널 비교 |
| 주파수 의존 포트 응답(F1′) | LoS에서도 q > 0, yaw 의존 | P0 LOS_FLOOR(STATIC_YAW_SWEEP 포함), R-03 규칙, LoS 채널 지표 = false-alarm floor |
| 거리 교란 | range와 \|e_s\| 강한 연관(기존 ρ 0.63–0.65) | M0에 range_m 포함, range 3분위 층별 보고 |
| 기존 feature와 중복 | M1이 jones_diversity·freq_s_var 정보 재사용 | M0 = G5, E1b(창 교체 효과) |
| yaw·고도각에 의한 LoS s 추세 | M4a가 LoS 채널에서도 상승 | LoS 채널 동일 지표 = false-alarm floor; turn 구간 대조; P2a |
| ceiling 정지 경로 | e_s 큼, M1–M4 낮음 | T4 분해, 실패가 아닌 원리 한계로 보고 |
| fp tap 전환 | n₀ 변동 시점에 지표 계단 | W 민감도 2종, n₀ 변화 플래그 층화 |
| 포트 시간 오프셋 | 단일 경로에서도 ε > 0 | S0·P3 σ_Δ sweep |
| 공간 aliasing | 예측 Λ와 관측 주기 불일치 | 4 cm 샘플, Λ < 8 cm 비율 ≤ 1% (사전 확인) |
| route/anchor 재사용 | route 간 과대 일관성 | 1 m block bootstrap, scene n=1 명시 |

## 7. 통계

- 단위: route(LORO) 내 ΔAUC, 1 m 주행거리 block bootstrap. **같은 route의 case(aA·aB·m45)는 SAMPLES가 동일하므로 block 인덱스를 공동 resampling**. turn은 연속 turn 구간 1개 = 1 block, 공간주기 분석 제외. scene 독립 단위 n=1 → 과학 판정 상한 `SUPPORTED_RETROSPECTIVE`.
- 다중 비교: primary는 E1(P1), E3·E4(P2) 3개만. 나머지는 secondary/diagnostic으로 표기.
- 모델: primary logistic(C=1.0 고정). sensitivity: RandomForest(160 trees, depth 6, min-leaf 40, seed 20261015 — 기존 PHYSICS_RS_STAGED 설정).
- 검정력: label 미사용. P0의 timeline 기반 block 수 + 가정 효과(ΔAUC 0.02, 0.05)로 합성 label power simulation만 수행해 FROZEN 전에 기록.
- P3 E5: 기준(AUC 손실 ≤ 0.05)을 만족한 최대 시험 격자점으로 보고.

## 8. 산출물 (FROZEN 이후)

- P0(DRAFT 허용): `results_p0/P0_CHECKS.json`, `TRACE_REALIGN.csv`, `LOS_FLOOR.csv`, `POSE_ALIGNMENT.csv`, `G5_PARITY.csv`, `MANIFEST.json`, `IMPLEMENTER_REPORT.md`
- `results_s0/S0_LAW.csv`: mode(LAW/PHYSICAL), delta_ns, psi, wedge, amp_ratio_db, snr_db, offset_ps, seed, q_W, eps_rho, phi_fp, S3_fp, near_cancel
- `results_p1/P1_FEATURES.csv.gz`: case, route, pose_id, stratum, phase, n0, valid_flags, q_W, eps_rho, tau_star, A1, A2, sigma_t_±, gamma_±, ds1, G5 열 전부, T1, T2, T3, channel(full/los)
- `results_p1/P1_AUC.csv`: heldout_route, arm, phase, auc, auc_lo, auc_hi, delta_auc, n_pos, n_blocks
- `results_p2/P2_PSD.csv`, `P2_PERIOD.csv`, `P2_DETECT.csv`
- `results_p3/P3_ABLATION.csv`: arm, sigma_ps, snr_db, gain_phase_randomized, auc, delta_auc_vs_clean
- `DECISIONS.json`: estimand별 status(PASS/FAIL/BLOCKED/NOT_RUN)와 verdict 분리
- 각 폴더 `MANIFEST.json` (COMMON_CONTRACT V)
