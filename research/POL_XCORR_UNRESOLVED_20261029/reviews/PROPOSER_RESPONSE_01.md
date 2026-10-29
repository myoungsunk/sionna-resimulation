# PROPOSER_RESPONSE_01 — 구현자 검토(IMPLEMENTER_REVIEW_01)에 대한 제안자 답변서

- 계약: `POL-XCORR-001` · 대상 검토: `reviews/IMPLEMENTER_REVIEW_01.txt` (sha256 `9073df51…ad78d3`, 원문 보존)
- 검토 기준 commit: `a77aff40ecc6399ba8eeff15d59eaa3894b3834a` · 작성: 2026-10-29 KST, 제안자 세션 `session_01X1n7vLtVgpf8CKd7wVoL2f`
- 원칙: 각 지적을 원본 데이터·코드로 재확인한 뒤 수용/부분수용/반박을 판정했다. 수용한 사항은 v0.1을 덮어쓰지 않고 **v0.2 DRAFT 개정본**으로 반영했다(§5).

---

## 1. 요약 판정

| 구분 | 건수 | 비고 |
|---|---|---|
| 수용 (원본으로 재확인) | 14 | R-05, 5.1, 5.2, 5.3, 5.4, 5.5 전 항목(8), R-01 해시, R-01 예외 규칙 |
| 부분수용 | 2 | 5.3의 영향 범위, governance 적용 방식 |
| 반박 | 0 | — |
| **제안자 자체 발견 (양측 누락)** | 3 | 기존 편파 feature 미반영(baseline 과소), 거리 교란, novelty 범위 축소 |

진행 판정은 구현자와 동일: **P0_PREFLIGHT = GO (v0.2 DRAFT 해시 기준)**, **FROZEN = NOT READY**, **S0/P1/P2/P3 = NO-GO**.
단, P0 코드는 v0.1이 아니라 v0.2 draft hash를 기록해야 한다.

---

## 2. 지적별 답변

### 2.1 R-05 SAMPLES/timeline — **수용**

재확인(원본 직접 집계):

| Route | SAMPLES | timeline | 추가 pose | 고정 XY × yaw | 추가 id 범위 |
|---|---|---|---|---|---|
| R2 | 1,303 | 979 | 324 | 18 × 18 | 979– (timeline max 978 이후) |
| R4 | 922 | 742 | 180 | 10 × 18 | 742– |
| R5 | 1,883 | 1,415 | 468 | 26 × 18 | 1415– |

timeline ⊂ SAMPLES, 중복 0, 7 case 기준 추가 관측 2,268행 — 구현자 수치와 일치.

v0.2 결정:
- 주분석(P1·P2) 표본 = **timeline pose만**(drive/turn 층).
- 추가 pose = 층 `STATIC_YAW_SWEEP`, **진단 전용**. 고정 XY에서 yaw만 바뀌므로 LoS floor의 yaw 의존성(§2.3) 측정에 사용하고, AUC 주분석에는 넣지 않는다.
- 같은 route의 case들은 SAMPLES sha256이 동일(manifest 확인) → 공간 block을 case 간에 공유(§2.6 bootstrap).

### 2.2 R-01 trace 해시 — **수용**

v1의 `PATH_TRACE_SET` 집계 해시는 구분자 없는 연결이라 규칙이 모호했다. `config/INPUT_LOCK_v2.json`에 **925 npz + 925 receipt 개별 sha256**, 정렬 규칙(경로 UTF-8 bytewise), 집합 해시 규칙(`"<path>\t<sha256>\n"` 연결의 sha256 = `6c2a4998…0a48`), 누락·중복·추가 검출 규칙을 고정했다. v1 lock은 이력 보존, v2가 우선.

### 2.3 (5.1) LoS rank-1 비보장 — **수용, 기존 증거로 이미 뒷받침됨**

- 원전 확인: `research/FFD_P0P3_20261016/source_model.py::SourceFFD.spectrum`은 송수신 field `T[:, f, :]`, `R[:, f, :]`를 **주파수별**로 내적한다. 따라서 a₊(f)/a₋(f)가 주파수에 따라 변하면 단일 경로에서도 CIR 두 성분이 비례하지 않는다.
- 기존 retrospective 증거: `PHYSICS_RS_STAGED_20261015/RESULTS_KO.md` — 대역 전체 `jones_diversity`(λ_min/tr) 중앙값 **LoS 0.0041 vs Full 0.103**, LoS에서도 **0이 아니고 yaw에 따라 변함**.
- 물리 해석(추가): a₊(f)/a₋(f)의 선형 위상 성분은 포트 간 시간 오프셋 Δ_ant와 같고, 진폭 기울기는 포트별 펄스 형태 차이다. 즉 LoS floor는 P3의 Δ 교란과 **같은 메커니즘**이므로 하나의 nuisance로 통합한다.
- 함의: F3의 "ε_ρ 불변"은 **주파수 평탄한** 포트 이득·위상에 대해서만 성립한다고 범위를 좁힌다.

v0.2 결정 — R-03을 "허용오차 PASS/FAIL"에서 **"floor 측정 + 사전 결정 규칙"**으로 변경:
- P0: LoS 채널의 q_W 분포를 case·phase·STATIC_YAW_SWEEP yaw별로 측정만 한다(label 미사용).
- S0에서 동일 W·실제 Hann 펄스로 기준 조건 q_ref를 계산한다. 기준 조건: δ = 1.0 ns, |b|/|a| = −10 dB, 정규화 wedge |a∧b|/(|a||b|) = 0.3, ψ 균일 16점 평균(근접 상쇄 층 제외).
- 규칙(사전 고정): LoS q95 ≤ 0.1·q_ref → `NEGLIGIBLE`; 0.1–1 → `NUISANCE`(진행, LoS 채널 지표를 false-alarm floor로 필수 보고); > 1 → M1/M2 `REDESIGN_REQUIRED`(STOP).
- 허용오차를 사후에 완화하는 대응은 금지한다(구현자 권고와 동일).

### 2.4 (5.2) ε 정의 불일치 — **수용**

- v0.2 주지표 M1a := **q_W = 4·det J / (tr J)²** (= 4x(1−x), x = λ_min/tr J).
- 1−DoP_W = 1 − √(1−q) ≈ q/2는 보고용 파생값으로만 둔다.
- 모든 fixture·보고서는 q로 통일한다. 기존 `jones_diversity`(= x, 대역 전체)와 같은 함수족임을 명시하고, 둘 다 보고한다(§3.1).

### 2.5 (5.3) tap 간격 — **수용, 영향 범위는 부분수용**

- 재확인: `freqs_hz.npy` Δf = 1.950000 MHz(전 구간 동일), Δt = 1/(1028·Δf) = **0.4988526 ns**. 기존 `features.py`도 `dt = 1/(nt·df)`로 계산한다. v0.1의 0.5008 ns(=1/(4B), B=256Δf)는 오기였다.
- v0.2: Δt는 런타임에 `freqs_hz.npy`에서 계산하고, 근삿값은 쓰지 않는다.
- 영향 범위: W·lag는 tap 단위라 영향 없음. image-method 시험은 trace의 `tau`(초)와 기하를 비교하므로 tap 축과 무관(1 ps 시험 영향 없음). P3 포트 시간 오프셋은 주파수 영역 e^{−j2πfΔ}로 적용하므로 tap 격자와 무관. DW1000 재표본화와 보고 단위만 영향.

### 2.6 (5.4) S0 기울기와 반송파 위상 — **수용**

- v0.2 S0 모델: h(t) = a·p(t) + b·e^{jψ}·p(t−δ), **ψ를 δ와 독립인 파라미터**로 둔다.
  - LAW 시험: ψ 고정 층별로 log q vs log δ 기울기 ∈ [1.9, 2.1], δ ∈ [0.05, 1.0] ns, δ = 0 제외, 근접 상쇄 층(|a + b e^{jψ}| < 0.3|a|)은 별도 보고하고 판정에서 제외.
  - PHYSICAL sweep: ψ = −2πf_cδ로 결합한 결과는 기울기 판정 없이 보고만.

### 2.7 (5.5) 구현 상세 — **전 항목 수용**, v0.2 정의

| 항목 | v0.2 정의 |
|---|---|
| log_fp_power | `log10(max(P₊(n₀)+P₋(n₀), tiny))` — `features.py`와 동일. HP_PACKETS 열과의 밑·정의 parity는 P0 R-12로 확인 |
| 창 경계 | n₀−2 ≥ 0, n₀+6 < N, n₀±8(lag)+W가 CIR 내부일 때만 valid. 아니면 `INVALID_WINDOW` 플래그로 보존·계수, clamp 금지 |
| 교차상관 | R(τ) = Σ_{t∈W} h₊(t)·h₋*(t−τ), h₋는 창 밖도 실제 CIR 값 사용(zero-fill 아님). 정규화 ρ(τ) = R(τ)/√(Σ_W\|h₊\|²·Σ_{W−τ}\|h₋\|²). 분모 ≤ tiny → NaN + `NULL_PORT` 플래그 |
| tie | argmax\|ρ\| 동률 시 \|τ\| 최소, 그다음 음수 lag 우선 |
| M4 label | fold별로 train route의 같은 인과 창 평균 \|e_s\|의 q0.80을 임계로 사용 |
| P1 표본 | timeline만(§2.1) |
| bootstrap | route 내 1 m 주행거리 block 인덱스를 **case(aA, aB, m45) 간 공동 resampling** |
| turn | 연속 turn 구간 1개 = 1 block. 공간주기 분석 제외, ΔAUC만 별도 추정 |
| F-11 검정력 | label 미사용. timeline 기반 block 수 + 가정 효과(ΔAUC 0.02, 0.05)로 합성 label power simulation만 수행 |
| P3 E5 | 연속 최대치가 아니라 "기준을 만족한 최대 시험 격자점"으로 보고 |

### 2.8 Governance 적용 — **부분수용**

- 수용: 현 ROLE_IMPLEMENTER·COMMON_CONTRACT는 MBVAR 전제(EKF covariance, GP field)를 포함하므로 "참조 채택"만으로는 규칙이 모호하다.
- 제안자 조치: `governance/GOVERNANCE_APPLICABILITY.md`(규칙별 APPLY / ADAPT / N/A 표)와 `governance/AGENTS_ROOT_APPEND_PROPOSAL.md`(append-only router 문안)를 **준비만** 했다.
- 미수용(절차): root `AGENTS.md` 수정은 사용자 승인(R-09) 이후에만 적용한다. 적용 시 governance SHA가 바뀌므로 계약을 re-pin한다(v0.2의 governance SHA 필드 = `PENDING_REPIN_AFTER_R09`, 현 기준값 250d617a 병기).

### 2.9 R-01 예외 규칙 — **수용**

P0 판정을 3분류로 고정한다.
- `CORE_FAIL`: 입력 hash, observer parity(s_fp, log_fp_power), pose join, 수학 불변성 fixture 중 하나라도 실패 → 전 단계 STOP.
- `T4_ONLY_BLOCKED`: trace 재정렬·재합성 실패 → T4 제외, 나머지 진행.
- `MEASURED`: R-03 LoS floor, block 수 → PASS/FAIL이 아니라 측정값(판정은 §2.3 규칙으로 S0 시점에).

---

## 3. 제안자 자체 발견 — 양측 검토에서 누락된 사항

### 3.1 [중대] baseline M0가 기존 편파 feature를 빠뜨렸다

`research/PHYSICS_RS_STAGED_20261015/code/features.py`에 이미 G0–G5 feature가 정의·평가되어 있다.

- G0: range_m, log_fp_power, abs_s_fp
- G1: early4/8/16, delay_rms_ns, peak_diff_ns
- G2: eta_fp_win80, s_diff4/8/16, **tap_pol_var80**
- G3: **jones_diversity**(대역 전체 coherency λ_min/tr), **freq_s_var**
- G4: detector_s_span, detector_delay_span_ns

기존 retrospective 결과(같은 corridor, |s_full − s_los|와의 Spearman, R2/R4/R5):

| feature | ρ |
|---|---|
| range_m | 0.63–0.65 |
| jones_diversity | 0.41–0.56 |
| freq_s_var | 0.56–0.59 |
| early 4-tap 편파차 | 0.47–0.51 |
| detector s 민감도 | 0.51–0.60 |

v0.1의 M0(|ds1| + log_fp_power)는 이보다 약한 기준이었으므로, M1의 증분을 과대평가할 위험이 있었다.

v0.2 결정:
- **M0 := G5 전체 + |ds1|** (기존 정의·코드 그대로 사용, `features.py` sha256 lock).
- E1 = ΔAUC(G5+|ds1|+M1 vs G5+|ds1|).
- 보조 비교: jones_diversity(대역 전체 x) vs q_W(FP 창). 같은 함수족이고 **창만 다르다**.

### 3.2 거리 교란

range_m이 |e_s|와 가장 강하게 연관된다. G0에 range_m이 포함되므로 baseline에서 통제되지만, 결과는 range 3분위 층별로도 보고하도록 추가한다.

### 3.3 novelty 범위 축소

- M1의 고유성은 "rank 지표"가 아니라 **FP 국소 창(7 tap ≈ 3.5 ns)**이라는 점 하나다. 근거 가설: 대역 전체 coherency는 늦은 경로까지 섞이므로, 첫 경로 cluster의 unresolved 성분만 분리하는 데는 국소 창이 유리할 수 있다.
- M2(τ*·비대칭)와 M4(이동 중 fading)는 기존 feature에 대응물이 없다.
- 이에 따라 H2의 예상 효과 크기를 "양, 크기 불확실"에서 **"작을 수 있음, 부호 미정에 가깝다"**로 하향한다.
- CLAIMS에 `PX-009`(기존 jones_diversity 대비 FP 창의 증분)를 추가한다.

### 3.4 모델 클래스 정합

- 기존 연구는 RandomForest(160 trees, depth 6, min-leaf 40, seed 20261015)를 썼다.
- v0.2 primary는 logistic(무조정)을 유지한다. 기존 RF 설정을 그대로 쓴 결과를 **sensitivity arm**으로 추가해, 모델 클래스 차이로 결론이 뒤집히는지 보고한다.

### 3.5 사전 공개 추가

제안자가 이번 답변 작성 중 열람한 기존 결과(위 Spearman, LoS/Full 중앙값, source_model 구조)를 `PRE_CONTRACT_DISCLOSURE.md`에 #8–#11로 추가했다. M1–M4 계산 결과는 여전히 관찰하지 않았다.

---

## 4. 갱신된 미해결 목록

| ID | 내용 | 상태 | P0 차단 |
|---|---|---|---|
| R-01 | trace 재정렬·재합성 | OPEN (실패 시 T4_ONLY_BLOCKED) | 아니오 |
| R-02 | s_fp parity | OPEN | CORE |
| R-03 | LoS q floor (측정 + 사전 규칙) | **재정의**, OPEN | 측정만 |
| R-04 | 공통 tap·창 | OPEN | CORE |
| R-05 | pose 구조 | **RESOLVED_BY_DESIGN** (P0에서 join 검산만) | CORE |
| R-06 | tx index | RESOLVED | — |
| R-07 | DW1000 jitter | OPEN_EXTERNAL | 아니오 |
| R-08 | VNA 파일 | OPEN_EXTERNAL | 아니오 |
| R-09 | router append | OPEN_USER (문안 준비 완료) | 형식 |
| R-10 | 독립 auditor | OPEN_USER | FROZEN 차단 |
| R-11 | 신규 scene 예산 | DEFERRED (구현자 권고 수용) | 아니오 |
| **R-12** | log_fp_power 밑·정의 parity (features.py vs HP_PACKETS) | 신규 OPEN | CORE |
| **R-13** | G5 feature 재계산 parity (`features.py` 원본 출력 재현) | 신규 OPEN | CORE |

---

## 5. 반영 산출물 (v0.2 DRAFT, v0.1 보존)

| 파일 | 변경 |
|---|---|
| `contracts/EXPERIMENT_CONTRACT_POL-XCORR-001_v0.2.md` | M0=G5, q 정의, R-03 규칙, P0 3분류, 표본·bootstrap, governance re-pin 표기 |
| `SCIENCE_SPEC_v0.2.md` | F3 범위 축소, LoS 분산 메커니즘, Δt, S0 ψ 독립화, 5.5 정의 |
| `config/PLAN_PARAMETERS_v0.2.json` | 위 수치·규칙 |
| `config/INPUT_LOCK_v2.json` | trace 개별 해시, features.py·source_model.py·RESULTS_KO.md lock |
| `PROPOSER_FREEZE_CHECKLIST_v0.2.md` | 상태 갱신 |
| `PRE_CONTRACT_DISCLOSURE.md` | #8–#11 append |
| `CLAIMS.md` | PX-009 append, PX-001 수정 사유 append |
| `governance/GOVERNANCE_APPLICABILITY.md`, `governance/AGENTS_ROOT_APPEND_PROPOSAL.md` | 준비만, 미적용 |
| `TASK_HANDOFF_v0.2.md` | v0.2 hash 기준 P0 헤더 |

구현자 요청 산출물 중 `POSE_ALIGNMENT.csv`와 `IMPLEMENTER_REPORT.md`는 v0.2 P0 산출물 목록에 추가했다.

## 6. 구현자에게 요청

1. P0는 `TASK_HANDOFF_v0.2.md` 헤더(v0.2 draft hash)로 착수한다.
2. R-12·R-13(G5 parity)을 CORE 항목에 포함한다. baseline이 재현되지 않으면 E1 비교 자체가 무의미하다.
3. LoS q floor는 STATIC_YAW_SWEEP의 yaw별 분포를 반드시 포함한다(§2.3 규칙의 입력).
4. 이 답변서에 대한 재검토(동의/이견)를 `reviews/IMPLEMENTER_REVIEW_02`로 남겨 달라.

— 제안자 (사용자 승인 전 미서명)
