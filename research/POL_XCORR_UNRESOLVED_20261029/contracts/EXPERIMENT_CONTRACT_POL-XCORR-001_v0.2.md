# EXPERIMENT_CONTRACT-POL-XCORR-001 (v0.2)

Status: **`DRAFT`** — 사전등록이 아니다. 허용 실행은 `P0_PREFLIGHT`(source/math/geometry audit 및 label 미사용 측정)뿐이며, S0·P1·P2·P3는 `BLOCKED_CONTRACT_INCOMPLETE`.
v0.1(`EXPERIMENT_CONTRACT_POL-XCORR-001.md`, sha256 `c65f54e4…33ca`)을 대체한다. 변경 근거: `reviews/PROPOSER_RESPONSE_01.md`.

## Authority

- Contract ID: `POL-XCORR-001`, protocol v0.2-DRAFT (2026-10-29)
- Role proposer: Claude (Opus 5.5) session `session_01X1n7vLtVgpf8CKd7wVoL2f`, 사용자 MSK 승인 시 서명 유효
- Full immutable base Git SHA: `250d617ad89a4105fa1af546cc83ceed9de98f42`
- Governance Git SHA: 현 기준 `250d617ad89a4105fa1af546cc83ceed9de98f42`; **`PENDING_REPIN_AFTER_R09`** — router append(R-09) 적용 시 해당 commit SHA로 re-pin하고 v0.3 발행
- Governance 적용표: `governance/GOVERNANCE_APPLICABILITY.md`
- Contract SHA256: `package_provenance/PACKAGE_MANIFEST_v0.2.json`
- Source models/code SHAs: `config/INPUT_LOCK_v2.json` (`v_replay.py`, `features.py`, `source_model.py` 포함)
- Config: `config/PLAN_PARAMETERS_v0.2.json`
- Allowed phase: `P0_PREFLIGHT` only. 출력 `research/POL_XCORR_UNRESOLVED_20261029/results_p0/` 신규 생성만
- Allowed inputs: `config/INPUT_LOCK_v2.json` 전 항목 (읽기 전용)
- Pre-run independent auditor: 미지정 (R-10)

## Question and estimand

- **Scientific question:** 첫 경로 해상 셀 안(δ < 1/B ≈ 2.0 ns)에 도착한 반사가 두 RX 편파(±45)에 서로 다른 복소 계수로 섞일 때, (i) FP 국소 창 coherency·교차상관(M1, M2), (ii) 이동 중 두 편파의 differential fading·펄스 형태 변동(M4)이 **기존 G5 편파·지연 feature + |ds1|**보다 오염 판별 정보를 더하는가. 모든 지표는 heading prior 없이 계산한다.
- **Estimands (route r, timeline pose만):**
  - E1 = ΔAUC_r(M0+M1 vs M0), label 1{|e_s| ≥ train q0.80}, drive/turn 분리. **M0 = G5(features.py) + |ds1|**
  - E1b(보조) = ΔAUC_r(M0−jones_diversity+q_W vs M0) — 같은 함수족에서 대역 전체 → FP 창 교체 효과
  - E2 = ΔAUC_r(M0+M1+M2 vs M0+M1)
  - E3 = ρ_sep (P2a 분리성)
  - E4 = ΔAUC_r(M0+M1+M4 vs M0+M1), 인과 창 L = 0.6 m
  - E5 = P3에서 기준을 만족한 최대 σ_Δ 시험 격자점
  - LAW = S0 ψ-고정 층 기울기
  - FLOOR = LoS 채널 q_W 분포(case·phase·STATIC_YAW_SWEEP yaw별) — 측정량
- **Null / alternative / 예상:**

| ID | Null | Alternative | 예상 |
|---|---|---|---|
| H1 (S0) | ψ-고정 층 기울기 ∉ [1.9, 2.1] | ∈ | 2 |
| H2 (P1) | E1 ≤ 0 | E1 > 0 | **작거나 0일 수 있음** — 대역 전체 jones_diversity(ρ 0.41–0.56)·freq_s_var(0.56–0.59)가 이미 M0에 있음 |
| H2b | E1b ≤ 0 | > 0 | 부호 미정 |
| H3 | E2 ≤ 0 | > 0 | 부호 미정 (zero-lag ≡ M1) |
| H4 (P2a) | ρ_sep < 0.6 | ≥ 0.6 | 혼재 |
| H5 (P2c) | E4 ≤ 0 | > 0 | H4 PASS 조건부 양 |
| H6 | ε_ρ가 주파수 평탄 diag 이득에 불변 아님 | 상대 변화 ≤ 1e-12 | 불변(수학). **주파수 의존 포트 응답에는 불변 아님** |

- **경쟁 설명:** SCIENCE_SPEC_v0.2 §6. 추가: 주파수 의존 안테나 포트 응답에 의한 LoS floor(= 포트 간 등가 시간 오프셋 Δ_ant), 거리 교란(range_m).
- **고정:** H(14 파일), observer(Hann, 4N IFFT, 30% stronger-port, 공통 tap), Δt = 1/(1028·Δf) 런타임 계산, tx = +45, W·L·분위수, 모델 형태.
- **변경:** 지표 arm, P3 합성 교란.
- **통제 불가:** 단일 corridor scene, anchor 천장 근접(ceiling 경로 상존), 재료, route 기하.

## Data and sampling

- **주분석 표본 = timeline pose만** (drive, turn 층). R2 979 / R4 742 / R5 1,415 × case.
- `STATIC_YAW_SWEEP` (timeline 밖 972개 고유 pose, 7 case 2,268행): **진단 전용** — FLOOR의 yaw 의존성, 고정 XY에서의 Full 지표 분포. AUC 주분석 제외.
- Independent sampling unit: scene variant, n = 1. route·anchor·mount·pose는 반복관측.
- 분류: 전체 corpus `RETROSPECTIVE/DEV`. LORO는 dev 내부. final holdout `BLOCKED`(R-11 DEFERRED). 과학 판정 상한 `SUPPORTED_RETROSPECTIVE`.
- Bootstrap: route 내 1 m 주행거리 block, **같은 route의 case(aA·aB·m45) 간 block 인덱스 공동 resampling**, 2000회, seed 20261029. turn은 연속 turn 구간 = 1 block.
- 결과 보고 층: drive/turn × range 3분위.

## Mathematics

- 필터 상태: 사용 안 함.
- 지표 정의: SCIENCE_SPEC_v0.2 §3. 주지표 **q_W = 4·det J / (tr J)²**.
- LoS floor 규칙 (사전 고정, S0 시점 판정): q_ref = S0 기준 조건(δ = 1.0 ns, |b|/|a| = −10 dB, 정규화 wedge 0.3, ψ 16점 평균, 근접 상쇄 제외)의 q_W. LoS q95 ≤ 0.1·q_ref → `NEGLIGIBLE`; 0.1–1 → `NUISANCE`(진행, LoS floor 필수 보고); > 1 → M1/M2 `REDESIGN_REQUIRED`. 사후 완화 금지.
- 모델: primary logistic(standardized, C = 1.0 고정). sensitivity: RandomForest(160, depth 6, min-leaf 40, seed 20261015 — 기존 연구 설정 그대로).
- 통계: route별 ΔAUC, block bootstrap 95% CI. go rule: CI 하한 > 0이 ≥ 2/3 route이고 부호 3/3.

## Implementation & evidence

- P0 판정 3분류:
  - `CORE_FAIL` → 전 단계 STOP: 입력 hash, s_fp parity(R-02), log_fp_power parity(R-12), G5 feature 재현(R-13), 공통 tap·창(R-04), pose join(R-05), 수학 불변성 fixture
  - `T4_ONLY_BLOCKED`: trace 재정렬·재합성 실패(R-01) → T4만 제외
  - `MEASURED`: LoS floor(R-03), route·phase별 block 수 → 판정 없음
- Tolerances: `PLAN_PARAMETERS_v0.2.json.tolerances_fixed_before_run`.
- P0 산출물: `P0_CHECKS.json`, `TRACE_REALIGN.csv`, `LOS_FLOOR.csv`(case, pose_id, stratum, yaw, q_W, eps_rho, jones_diversity), `POSE_ALIGNMENT.csv`(case, pose_id, stratum, phase, travelled_m, block_id), `G5_PARITY.csv`, `MANIFEST.json`, `IMPLEMENTER_REPORT.md`.
- P0 금지: 어떤 지표와 label(e_s, e_r, η)의 관계 계산·출력.
- Acceptance vs verdict: 스크립트 PASS = `TECHNICAL_QA_ONLY`. 과학 판정은 auditor만 내린다.
- Forbidden claim language: v0.1 목록 + "기존 편파 feature 대비 우월"(E1 미실행 상태), "LoS에서 ε = 0"(FLOOR 측정 전).

## P0_TO_RESOLVE ledger

| ID | 항목 | 상태 | 분류 |
|---|---|---|---|
| R-01 | trace 재정렬·재합성 | OPEN | T4_ONLY |
| R-02 | s_fp parity ≤ 1e-9 | OPEN | CORE |
| R-03 | LoS q floor | 재정의: MEASURED, 판정은 S0 시점 규칙 | MEASURED |
| R-04 | 공통 tap·창·경계 플래그 | OPEN | CORE |
| R-05 | pose 구조 | RESOLVED_BY_DESIGN (join 검산만) | CORE |
| R-06 | tx index | RESOLVED | — |
| R-07 | DW1000 jitter | OPEN_EXTERNAL | — |
| R-08 | VNA 파일 | OPEN_EXTERNAL | — |
| R-09 | router append | OPEN_USER (문안 준비) | 형식 |
| R-10 | 독립 auditor | OPEN_USER | FROZEN 차단 |
| R-11 | 신규 scene 예산 | DEFERRED | — |
| R-12 | log_fp_power 밑·정의 parity | OPEN | CORE |
| R-13 | G5 feature 재현 parity | OPEN | CORE |

## Pre-contract disclosure

`PRE_CONTRACT_DISCLOSURE.md` #1–#11. #8–#11은 기존 retrospective 결과(PHYSICS_RS_STAGED Spearman·LoS/Full 중앙값) 열람 기록. M1–M4 계산 결과는 미관찰.

## Changes and signoff

- v0.1 → v0.2 변경 요약: M0 = G5 + |ds1|; q 정의 통일; Δt 정정; S0 ψ 독립화; R-03 측정 + 규칙화; timeline 주분석·STATIC_YAW_SWEEP 진단; case 공동 block bootstrap; P0 3분류; R-12·R-13 추가; RF sensitivity arm; governance re-pin 대기.
- Proposer signature: _미서명 — 사용자 승인 대기_
- Pre-run auditor verdict: _없음_
- 이 문서는 **명시적 P0_PREFLIGHT만** 허가한다.
