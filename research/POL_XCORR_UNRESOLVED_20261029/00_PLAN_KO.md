# POL-XCORR-001 — Unresolved reflection 편파 오염 감지: 두 수신편파 CIR 교차상관·시간변동 지표 검증 계획

2026-10-29 · 상태: **DRAFT (실행 전 고정 초안, 결과 없음)** · base: `origin/research/mbvar-info-governance-20261029` (9986 files 기준 확인)
역할: PROPOSER 산출물. MBVAR-INFO-001 범위 밖이므로 root `AGENTS.md`의 데이터 보호·claim 규칙을 그대로 따르고, 형식만 governance 템플릿(가설→estimand→경쟁설명→gate→stop)을 차용한다.

---

## 0. 질문과 범위

**Q.** 같은 tap 안에 LoS와 함께 도착하는(unresolved, δ < 1/B ≈ 2.0 ns) 반사 경로가 두 수신편파(±45° RX) 사이에 서로 다른 복소 계수로 섞일 때,

- (정적) 한 패킷의 두 편파 CIR 교차상관 `R_{+-}(τ)` 에서 오염을 감지할 수 있는가?
- (시간/공간) 로봇 이동에 따라 δ(t)와 반송파 위상 2πf_cδ(t)가 변할 때, 두 편파의 진폭 엇박자(differential fading)와 펄스 형태 변동(breathing)이 오염 지표가 되는가?
- 그 지표가 **heading prior 없이** 계산되는가? (d0 = s_Full − h_s(prior)의 재귀 문제를 피하는 대체 후보인지)
- 기존 power-only 지표 `ds1 = s(fp+1) − s(fp)`보다 정보를 더하는가?

**범위 밖:** EKF R 팽창 통합, d0 대체 선언, Office/타 scene 일반화, 실측 정확도 주장. P1–P3 통과 후 별도 계약.

---

## 1. 기존 자산 (재시뮬레이션 없음)

| 자산 | 경로 | 내용 |
|---|---|---|
| Full/LoS H 쌍 | `results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/{FULL_RF/H_*.npy, H_LoS_*.npy}` | 7 case(R2/R4/R5 × aA/aB, R2_aA_m45), 9,519 pose, layout `pose, freq(257), rx(+45,−45), tx(+45,−45)`, 6.2504–6.7496 GHz. Full = max_depth 3, LoS = max_depth 0, 동일 pose·안테나·기하 |
| Manifest/hash | `research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json` | 모든 H의 sha256, observer 정의 (Hann, 4N zero-pad, 30% first edge, s=(P1−P2)/(P1+P2)) |
| 패킷 표 | `research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz` | e_s, e_r, sF/sL(±8 taps), fp_full/fp_los, log_fp_power 등 63열 |
| 기존 지표 코드 | `research/PJ_DS_GATED_20261021/v_replay.py::ds1` | s0, ds1 (power-only intra-window 편파 변화) |
| Path trace | `BLOCK_C/STORED_PATH_TRACES_R2_aA/*_trace.npz` (925 위치) | jones(17 node, P, 3, 3), tau, ang, signature, present |
| 궤적 | `BLOCK_C/INPUTS/timeline_R{2,4,5}_Tnone.csv`, `*/SAMPLES.json` | t_s, x, y, yaw, phase(drive/turn) |

### 1.1 P0 사전 점검에서 이미 확인한 사실 (2026-10-29, 로컬 read-only)

- **tx 축은 2개(±45)** 이나 배치 계획(단일 포트 anchor)에 맞춰 주 분석은 `tx=0(+45)` 한 열만 사용. 2×2 전체는 상한 진단용.
- 해상도: 1/B = 2.003 ns (≈ 60 cm), zero-pad tap = 0.501 ns. λ_c(6.5 GHz) = 4.61 cm.
- RF 샘플 간격: drive 구간 0.040 m/step (0.2 m/s, 5 Hz). turn 구간: R2 54, R4 195, R5 72 샘플.
- **Path trace 정렬 결함:** `tau`는 오름차순, `signature`는 알파벳순으로 각각 정렬되어 있음. image-method로 계산한 1차 경로 지연과 대조하면 LOS·ceiling만 signature가 일치하고 floor·wall은 다른 signature 위치에 놓임. `jones` 축이 어느 쪽에 정렬되어 있는지 미확인 → **path-level 분석(T4) 전에 재정렬·검증 필수.**
- Image-method 예측 (anchor (4,0,2.65)/(10,0,2.65), 천장 2.70 m, 바닥 0, 벽 y=±1.2, tag z=0.45):

| 경로 | δ q10/q50/q90 [ns] | 반송파 fading 공간주기 Λ 중앙값 [m] | 의미 |
|---|---|---|---|
| ceiling | 0.05 / 0.11 / 0.30 | 10–22 | 항상 unresolved, 거의 정지 → 시간·창 지표로 **원리적으로 감지 불가**, 정적 s bias로만 나타남 |
| floor | 0.56–0.89 / 1.2–1.5 / 2.8 | 1.1–2.2 | unresolved, 천천히 fading |
| wall ± | 0.45–0.81 / 1.4–1.8 / 3.3–3.9 | 0.9–1.7 | 대부분 unresolved |

  4 cm 샘플링 대비 Λ < 8 cm 비율 ≤ 1% → aliasing 위험 낮음. 대신 Λ(≈1–2 m)가 LoS 기하·안테나 패턴에 의한 s 추세의 공간 스케일과 겹칠 수 있음 → P2a가 결정적 gate.

---

## 2. 물리 모델과 사전 유도

복소 baseband, 단일 TX(+45), 두 RX 포트 벡터 `h(t) = [h_+(t), h_-(t)]^T`:

```
h(t) = a·p(t) + b·e^{-j2π f_c δ}·p(t − δ),   a, b ∈ C²   (LoS / 반사의 RX-포트 투영 Jones)
```

창 W(첫 경로 tap 기준) 위의 2×2 coherency `J = Σ_{t∈W} w(t) h(t) h(t)^H`.

- **F1 (단일 경로는 타원이어도 rank-1):** h(t)=a·p(t)이면 det J = 0. LoS의 포트 간 위상 φ≠0, S3≠0은 안테나 cross-pol·자세·경사 반사의 TE/TM 위상차만으로도 생긴다 → **φ·S3 자체는 다중경로 증거가 아니다** (첨부 문서 §1·§3의 판정 규칙은 negative control로만 사용).
- **F2 (δ² 법칙):** 작은 δ 전개 h ≈ (a+b̃)p − b̃δ·p′ (b̃ = b e^{-j2πf_cδ}) 에서
  `det J ≈ δ² · |a ∧ b|² · (E_p E_p′ − |⟨p,p′⟩|²)`, `a∧b = a₊b₋ − a₋b₊`.
  ⇒ `ε ≡ 4 det J / (tr J)² ≈ 4 δ² (2πB_rms)² |a∧b|² / |a+b̃|⁴`.
  감지량은 δ의 **2차**, range bias는 δ의 **1차** → 작은 δ에서 감지가 bias보다 먼저 사라짐. a∥b(편파 보존 반사)면 δ와 무관하게 0.
- **F3 (불변성):** `ε_ρ ≡ 1 − |ρ_W|² = det J / (J₁₁J₂₂)`는 포트별 복소 이득 D=diag(g₊,g₋)에 불변 → 패킷 간 포트 위상/이득 오프셋에 강건. 그러나 **포트 간 시간 정렬 오차 Δ는 δ와 같은 형태로 rank-2를 만든다** (false positive 원천).
- **F4 (시간 변동의 실제 구조):** 이동 거리 s에 대해
  - 반송파 위상 ψ = 2πf_cδ 가 공간주기 `Λ = λ / |∂Δd/∂s|` 로 회전 → 두 포트 진폭이 서로 다른 위상으로 fading (b₊/a₊ ≠ b₋/a₋ 이므로).
  - 펄스 형태(폭·왜도·peak–centroid 오프셋)도 **같은 Λ로** 진동하며 진폭은 ∝ |b/a|·δ/T_p.
  - δ 자체의 변화(포락선 스케일)는 `c / (B |∂Δd/∂s|)` ≫ Λ 로 훨씬 느리다.
  - 따라서 "breathing"은 δ가 0에 가까워졌다 멀어지는 현상이 아니라 **반송파 위상 회전이 포락선 합을 바꾸는 현상**이다. 보강 시점에 펄스가 "더 뾰족"해지는 것도 아니며, 높이가 커지고 형태 비대칭은 ψ에 따라 부호가 바뀐다.
  - LoS 구간에서도 s(x)는 일정하지 않다(heading/고도각 신호 그 자체). "LoS면 두 편파가 같은 비율로 감소"는 성립하지 않으므로 추세 제거가 필요.

---

## 3. 지표 (모두 Full H에서 온라인 계산 가능, GT 미사용)

| ID | 지표 | 위상 필요 | prior 필요 | 비고 |
|---|---|---|---|---|
| M0 | s_fp, \|ds1\|, log_fp_power, 기존 CIR-only feature | X | X | **비교 baseline** |
| M0-ref | d0 = s_Full − h_s(prior) | X | O | 참고용(재귀 문제 있음) |
| M1 | ε_W = 1−DoP_W, ε_ρ = 1−\|ρ_W\|² (W = fp−2…fp+4 tap, 주분석; ±1 tap 민감도) | 포트 간 동시성 필요 | X | F2·F3 |
| M2 | 사용자 제안 교차상관 R₊₋(τ)=Σ h₊(t)h₋*(t−τ): 정규화 최대 \|ρ\|max, lag τ*, 비대칭 A_k = (\|R(τ*+k)\|−\|R(τ*−k)\|)/(…) | 〃 | X | zero-lag 정규화값은 M1과 동치 → 추가 정보는 τ*·A 에서만 |
| M3 | 포트별 envelope shape: 2차 모멘트 폭, 왜도, peak–centroid 오프셋, 포트 차 Δshape | X | X | power-only |
| M4a | Differential fading: s_fp(x) 또는 log\|pk₊\|−log\|pk₋\| 의 high-pass 국소분산 (창 L) | X | X | 사용자 추가 가설 2단계 |
| M4b | Breathing: M3의 국소분산 (창 L) | X | X | 사용자 추가 가설 1단계 |
| M4c | ε 또는 Stokes 벡터의 연속 샘플 간 증분(Poincaré 측지거리) 국소 거칠기 | O | X | 상수 yaw 구간만 |
| M4d | high-pass s(x)의 PSD 중 image-method 예측 Λ 대역 전력 비율 | X | X (기하 예측엔 대략적 위치만) | 메커니즘 검정 |

- L = {0.3, 0.6, 1.2} m 사전 선언, 주분석 0.6 m. 주분석은 **인과 창**(과거 샘플만), 중심 창은 진단.
- 첫 경로 tap은 기존 observer(강한 포트 30% first edge)를 그대로 사용, 두 포트 공통 tap.

---

## 4. Truth label (채점 전용, 온라인 입력 금지)

- **T1** e_s = s_Full − s_LoS (HP_PACKETS 기존 열, 재계산 일치 검사)
- **T2** e_r (기존 열)
- **T3** η_W = Σ_W\|h_F − h_L\|² / Σ_W\|h_L\|² (포트 합, 동일 W) — 창 내 unresolved 에너지. path trace 불필요.
- **T4** (R2_aA, 재정렬 통과 시) 경로별 δ_k, \|a∧b_k\|, 1차 반사 종류 → F2 법칙·ceiling 비중 분해
- 주의: Full에는 ceiling 경로가 거의 항상 포함 → T1/T3의 정적 성분은 M1–M4가 원리상 못 보는 몫. T4로 그 비중을 분리 보고.

---

## 5. 단계와 판정

### P0 — Preflight (과학 판정 없음, 실패 시 STOP)
1. 14개 H + freqs sha256 = manifest.
2. s_fp 재계산이 HP_PACKETS `sF_+0`과 \|Δ\| < 1e-9.
3. **LoS 음성대조:** LoS H의 ε_W, ε_ρ 분포 상한 < 1e-8 (단일 경로 rank-1, 수치 floor). 실패 시 정의 또는 데이터 STOP.
4. 불변성 unit test: 임의 diag(g₊,g₋) 적용 시 ε_ρ 변화 < 1e-12; R2_aA m0 vs m45 LoS 모두 ≈0.
5. Path trace 재정렬: 1차 경로 image-method 지연과 < 1 ps 일치; node 주파수에서 Σ path → 저장 H 재합성 상대오차 기준(사전값 1e-3) 통과 시에만 T4 사용. 불통과 시 T4 제외, P1–P3은 진행.

### S0 — 합성 대수 (RT 없음)
- 동일 band·Hann 창의 p(t)로 2-path 합성, δ∈[0, 4] ns, ψ∈[0, 2π), \|a∧b\| 격자.
- 판정: log ε vs log δ 기울기 2 ± 0.1 (δ < 0.5/B 구간); a∥b에서 ε < 1e-10; 단일 타원 경로에서 ε=0이나 φ·S3≠0 (첨부 문서 규칙의 false positive 시연).
- 산출: SNR(10–30 dB)·포트 시간정렬 오차 σ_Δ(0–250 ps)별 ε 노이즈 floor → P3 기준표.

### P1 — 정적 per-pose 감지 (7 case, drive/turn 분리)
- **Primary:** \|e_s\| 상위 20%(임계는 학습 route에서만 결정) 판별 AUC — M1/M2 추가 vs M0 baseline(\|ds1\| + log_fp_power). leave-one-route-out, 1 m 구간 block bootstrap 95% CI.
- Secondary: M1 vs T3 Spearman; partial correlation(\|ds1\|, log power 통제); M2 τ*·A의 M1 대비 추가분; e_r에 대한 동일 분석.
- 대조: LoS H 위 지표(=0 이어야), m0 vs m45.
- **판정:** ΔAUC 하한 > 0 이 3 route 중 ≥ 2에서, 부호 3/3 일치 → PASS. 아니면 "복소 교차항은 이 corpus에서 ds1과 중복" 결론, M1/M2 STOP (M3·M4 power-only 경로는 계속).

### P2 — 시간/공간 변동 (사용자 추가 가설; drive 구간만, turn은 별도 대조)
- **P2a 분리성 (결정 gate):** 직선 구간별로 s_LoS(x)와 e_s(x)의 공간 PSD 비교. s_LoS 분산의 95%가 놓이는 대역보다 높은 공간주파수에 e_s 분산의 ≥ 50%가 있는 구간 비율 보고. 사전 기준: 구간의 ≥ 60%에서 성립하지 않으면 high-pass 기반 M4a/M4b는 **prior 없이 식별 불가** → STOP (prior 기반 detrend는 d0 재귀로 회귀하므로 이 계획에서 채택하지 않음).
- **P2b 메커니즘:** η 상위 절반 구간에서 high-pass e_s(x)·M3(x)의 지배 주기가 image-method 예측 Λ(floor/wall) ±20% 내인 비율. ceiling은 예측상 정지 → 해당 비중이 큰 구간에서 M4 미검출이 기대값.
- **P2c 감지 효용:** 인과 창 L=0.6 m에서 M4a/M4b(/M4c)가 같은 창의 평균 \|e_s\|, \|e_r\| 상위 20%를 판별하는 AUC; M1(순간값) 대비 증분, M0 대비 증분. LoS H에서 계산한 M4 = 기하·패턴 추세만의 false alarm floor.
- **P2d turn 대조:** 제자리 회전은 Δd 변화가 작아 반송파 fading이 기하로 생기지 않음 → turn 구간 M4 상승은 yaw에 의한 s 변화(혼동변수) 크기로 보고.
- **판정:** P2a PASS 이고 P2c ΔAUC 하한 > 0 (≥ 2/3 route) → PASS.

### P3 — 하드웨어 현실성 (P1/P2 생존 지표만)
- Arms: 포트별 패킷 독립 위상·이득(ε_ρ는 불변이어야 함), 포트 시간정렬 오차 σ_Δ ∈ {0, 25, 50, 100, 250 ps}, thermal noise fp SNR ∈ {30, 20, 15, 10 dB}, DW1000 tap(≈1.0016 ns) 재표본화.
- 현 tag 구성(포트 A/B를 별도 수신 이벤트로 얻는 route A/B)에서는 포트 간 위상은 패킷마다 무작위, 시간정렬은 각 패킷의 fp 추정 jitter에 의존 → M1/M2/M4c는 σ_Δ 허용치가 관건, M3/M4a/M4b(power-only)는 영향이 작을 것으로 예상(검증 대상).
- 산출: AUC 손실 ≤ 0.05를 유지하는 최대 σ_Δ, 최소 SNR. 실제 jitter는 미측정 → 별도 측정 필요 항목으로 기록.

### P4 — (선택) 홀 VNA 2×2 실측 부호 검정
- VNA는 포트 간 coherent → M1/M2의 상한 조건. 동일 거리에서 반사체 조건 vs face-to-face 조건의 ε, M3 부호 비교만. 정확도·라벨 재구성 주장 금지. **입력 파일 경로는 사용자 제공 필요(저장소에서 미발견).**

---

## 6. 경쟁 설명과 통제

| 경쟁 설명 | 통제 |
|---|---|
| 안테나 cross-pol·자세로 LoS 자체가 타원 | F1: LoS H에서 ε≡0 확인, φ/S3 규칙은 negative control |
| yaw/고도각에 따른 LoS s 추세 | LoS H로 계산한 동일 지표 = floor, P2a PSD 분리, turn 대조 |
| ceiling 정지 경로 | T4 분해로 몫 보고, 감지 불가를 실패가 아닌 원리 한계로 기록 |
| fp tap 선택 전환(tap switching) | 공통 tap 고정, W ±1 tap 민감도, tap 전환 시점 표시 |
| 포트 간 시간 정렬 오차 | S0·P3 σ_Δ sweep |
| 단일 scene·동일 corridor | 7 case를 독립 환경으로 세지 않음, route block 단위 통계 |

---

## 7. 통계·재현

- 분석 단위: route(3) × anchor(2) (+m45); pose는 독립 표본 아님 → 1 m 구간 block bootstrap.
- 임계·창·W·L은 이 문서에서 고정, 결과 확인 후 변경은 amendment ID로만.
- 결정적 계산(RT 재실행 없음, CPU 수 분). 출력은 `research/POL_XCORR_UNRESOLVED_20261029/results_*`에만 기록, 기존 파일 덮어쓰기 금지.
- 산출물: `RESULTS_P0.json`, `S0_LAW.csv`, `P1_AUC.csv`, `P2_PSD.csv`, `P2_DETECT.csv`, `P3_ABLATION.csv`, `DECISIONS.json`, 입력 sha256 lock.

## 8. Claim boundary

- 이 실험은 **오염 감지 지표의 정보량**만 다룬다. range/heading 오차 감소, EKF 방어를 주장하지 않는다.
- ceiling처럼 δ≪1/B·Λ≫구간인 경로는 이 계열 지표로 감지 불가함을 사전에 명시한다.
- 시뮬레이션은 noise-free frozen 채널 단일 scene; 일반화 주장 없음.
