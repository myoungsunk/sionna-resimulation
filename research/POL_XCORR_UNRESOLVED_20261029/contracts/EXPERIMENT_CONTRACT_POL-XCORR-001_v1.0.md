# EXPERIMENT_CONTRACT-POL-XCORR-001 (v1.0 — FROZEN)

Status: **`FROZEN`**. 서명 상태는 `FREEZE_RECORD_v1.0.md`에 있다. 제안자 서명 완료(사용자 승인). 감사자 서명은 `SELF_REVIEW_ONLY`이고, 독립 감사(R-10)는 OUTSTANDING이다.
이 문서는 v0.3 DRAFT(`EXPERIMENT_CONTRACT_POL-XCORR-001_v0.3.md`, sha256 `39c396c72688d88efa84d0fcb7779ad2b5b693891ab87aaae803bd26793cb76e`)를 **본문 그대로 승계**하고, 아래 §Freeze deltas D1–D8만 추가·변경한다. v0.3의 다른 조항과 `SCIENCE_SPEC_v0.3.md`(sha256 `5db75dcc0a332833de50d87ba2081bea5ca0cd74e7e093ae00ce987728368450`)는 변경 없이 구속력을 갖는다. 충돌이 있으면 이 문서가 우선한다.
FROZEN 이후 변경은 `AMENDMENT-POLX-NNN.md`로만 할 수 있다. 결과를 본 뒤의 변경은 해당 run을 `EXPLORATORY`로 만든다.

## Authority

| 항목 | 값 |
|---|---|
| Contract ID | `POL-XCORR-001`, protocol v1.0 (2026-10-30 KST) |
| Base data/source SHA | `250d617ad89a4105fa1af546cc83ceed9de98f42` |
| Governance SHA | `d5f84d9d04d28d465f3357e9299352eb184e6bfc` (보존 branch `governance/pol-xcorr-router-d5f84d9d`) |
| Governance 적용표 | `governance/GOVERNANCE_APPLICABILITY.md` |
| Science spec | `SCIENCE_SPEC_v0.3.md` (위 sha) + 이 문서 D1–D8 |
| Config | `config/PLAN_PARAMETERS_v1.0.json` (sha는 `package_provenance/PACKAGE_MANIFEST_v1.0.json`) |
| Input lock | `config/INPUT_LOCK_v2.json` (sha256 `bddab15801f8d8c653eeb7f825ff71352d48bda7bf7b650f59a2feb300458184`) |
| Stored references | `config/P0_REFERENCES_v0.2.json`; R-13b 보존본 `evidence/r13b_run_40983557008/` |
| P0 evidence | `results_p0/run_40867521966`, `results_p0_v03/run_40884686972`, 감사 `audit/results_audit01/run_40982122546` |
| Power evidence | `power/results_f11/run_40984998584/F11_POWER_ALL.csv`, `power/results_f11_corrlen/` |
| Contract sha256 | 이 파일 자체에는 기록할 수 없다 → `FREEZE_RECORD_v1.0.md`, `PACKAGE_MANIFEST_v1.0.json` |

## Freeze deltas

### D1 — ΔAUC estimand의 주 판정 규칙 (E1, E2, E4 공통) — v0.3 go rule 대체

- route r의 held-out ΔAUC_r는 v0.3과 같다(LORO, logistic C=1 고정, timeline drive).
- **Pooled 통계량:** Δ̄ = Σ_r w_r·ΔAUC_r, w_r = n_r/Σn (n_r = held-out route의 평가 행 수, case 합산).
- **CI:** route별 1 m block bootstrap(B = 2000, 같은 route의 case는 block 인덱스 공동 resampling, route 간 독립)을 replicate 단위로 가중 결합한 percentile 95% CI.
- **GO (주 판정):** Δ̄의 CI 하한 > 0 **그리고** ΔAUC_r > 0인 route ≥ 2/3.
- **보조(일관성) 보고:** v0.3 route별 규칙(CI 하한 > 0이 2/3 이상, 부호 3/3)도 그대로 계산·보고한다. 주 판정에는 쓰지 않는다.
- 근거(F-11, label 미사용):
  - 실측 G5 공간 상관길이 중앙값 0.96 m.
  - ℓ = 1 m, AUC₀ = 0.70/0.80, Δ = 0.05에서 power는 pooled 0.42/0.74, route별 0.07/0.25.
  - Δ = 0에서 pooled type-I은 전 조건 ≤ 0.013.

### D2 — 판정 해석 규칙 (사전 고정)

| 조건 | 판정 |
|---|---|
| D1 GO | `SUPPORTED_RETROSPECTIVE` (scene n = 1 상한 유지) |
| GO 아님 **그리고** Δ̄의 CI 상한 < 0.05 | `NOT_SUPPORTED_AT_0.05` (ΔAUC ≥ 0.05 배제) |
| 그 외 | `INCONCLUSIVE_UNDERPOWERED` |

- ΔAUC 0.02 수준은 이 corpus로 검출할 수 없다(ℓ ≥ 0.5 m에서 power ≤ 0.37). 따라서 "효과 없음"으로 보고하지 않는다.

### D3 — 층별 보고 (판정 아님, 필수 보고)

- **phase:** drive가 주 판정이다. turn은 route별 turn block이 3/13/4개뿐이라 **기술 통계만 보고**하며 GO 판정을 하지 않는다.
- **mount:** 0°(6 case) / 45°(R2_aA_m45 1 case). mount 45°의 결과는 route·anchor와 분리할 수 없다고 명기한다.
- **WEAK_PORT**(u < 0.05, LoS 7-tap 기준을 Full 채널에도 같은 정의로 적용): all / weak / strong. 행 삭제는 금지하고 층별 AUC만 보고한다.
- **range_m 3분위:** train route 기준 cut.

### D4 — E1-ctrl (선택적 secondary)

- E1-ctrl = ΔAUC(M0 + [4u(1−u)] vs M0)
- E1-dec = ΔAUC(M0 + [4u(1−u), q_W] vs M0 + [4u(1−u)])
- secondary로 보고한다. LoS에서는 balance 항의 log q_W 분산 기여가 −2.1%였다(AUDIT-01 AF-7). Full에서 E1-dec ≤ 0이고 E1 > 0이면, PX-009 주장은 "포트 균형 정보 포함"으로 한정한다.

### D5 — 실행 권한

| 단계 | 권한 |
|---|---|
| S0 (합성, label 없음) | **GO.** 출력은 `TECHNICAL_QA_ONLY` |
| P1, P2 (label 첫 사용, 비가역) | **HOLD.** 사용자의 명시적 진행 지시 **또는** 독립 감사자(별도 세션)의 pre-run 서명 중 하나가 기록돼야 시작 |
| P3 | P1/P2 생존 지표가 있을 때만 |
| P4 | R-08 입력 전까지 BLOCKED |
| RT·신규 scene | 금지 (R-11 DEFERRED) |

- 모든 S0–P3 결과는 독립 사후 감사 전까지 `TECHNICAL_QA_ONLY / SELF_REVIEW_ONLY_FREEZE`로 표기한다. CLAIM 승격과 `RESEARCH_RELEASE`는 금지한다.

### D6 — 고정 수치 (v0.3 값 승계 확인)

- W = n₀+[−2, 4], lag ±8, L = 0.6 m(인과), positive class q0.80(train route), B = 2000, seed 20261029, logistic C = 1.0, RF sensitivity(160/6/40/20261015).
- R-03 q_ref 규칙(δ = 1.0 ns, −10 dB, wedge 0.3, ψ 16점)과 NEGLIGIBLE/NUISANCE/REDESIGN 경계는 그대로 둔다. **S0에서 처음 계산한다.**
- WEAK_PORT 0.05(명목), 0.02와 0.10은 기술 통계용 민감도.
- **R-03 판정 입력(모호성 제거):** `results_p0/run_40867521966/LOS_FLOOR.csv`에서 TIMELINE 전체(7,251행) q_W의 q95(np.quantile, linear) 하나만 쓴다. case별 q95 최대값은 보고만 한다.
- **q_ref 기준 조건 구성(모호성 제거):**
  - 주파수: 실제 `freqs_hz.npy` 257 bin. 관측: v0.3 observer(Hann, 4N IFFT, 30% stronger-port, 공통 n₀, W = n₀+[−2, 4]).
  - 채널: H(f) = a·e^{−j2πfτ₀} + b·e^{jψ}·e^{−j2πf(τ₀+δ)}, τ₀ = 20 ns, δ = 1.0 ns.
  - 벡터: a = (1, 1)/√2. â⊥ = (1, −1)/√2. b = 10^(−10/20)·(√(1−0.3²)·a + 0.3·â⊥).
  - ψ = 2πk/16 (k = 0…15). 근접 상쇄 층(|a + b·e^{jψ}| < 0.3|a|)을 제외하고 q_W를 산술평균한 값을 q_ref로 한다.
  - 같은 구성으로 a를 (1, 0.3j)/‖·‖로 바꾼 민감도 값도 보고하되, 판정에는 쓰지 않는다.

### D7 — 증거 보존

- R-13b: `evidence/r13b_run_40983557008/R13B_G5_EXTRACT.csv.gz` (key + G5 열만, label 8열 제외, 19,038행, sha256 `bbad246e…7168`). 원 파일 sha256 `6a69a36a…6fe4`.
- 원 artifact는 2026-11-19에 만료된다. 이후 R-13b 재검증은 이 보존본과 원 sha 기록으로 대체한다.

### D8 — R-01 / T4

- `T4_ONLY_BLOCKED`를 유지한다. ceiling 경로의 몫 분해 등 경로 단위 주장은 금지한다.

## Forbidden claim language (v0.3 목록에 추가)

- "검정력 충분", "효과 없음"(D2의 `NOT_SUPPORTED_AT_0.05` 외)
- "독립 감사 완료"(R-10 미충족)
- "mount 효과"(case 1개)
- "turn에서 유효/무효"(기술 통계뿐)

## Signoff

`FREEZE_RECORD_v1.0.md` 참조.
