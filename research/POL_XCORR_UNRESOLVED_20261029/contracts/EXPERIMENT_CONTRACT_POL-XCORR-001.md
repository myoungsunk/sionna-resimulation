# EXPERIMENT_CONTRACT-POL-XCORR-001

Status: **`DRAFT`** — 사전등록이 아니다. 이 문서로 허용되는 실행은 아래 §Authority의 `P0_PREFLIGHT`(source/math/geometry audit)뿐이며, S0·P1·P2·P3는 `BLOCKED_CONTRACT_INCOMPLETE`.

## Authority

- Contract ID: `POL-XCORR-001`
- Role proposer: Claude (Opus 5.5) session `session_01X1n7vLtVgpf8CKd7wVoL2f`, 사용자 MSK의 지시로 작성. Proposer 서명은 사용자 승인 후 유효.
- Full immutable base Git SHA: `250d617ad89a4105fa1af546cc83ceed9de98f42` (`research/mbvar-info-governance-20261029` HEAD)
- Full immutable governance Git SHA: `250d617ad89a4105fa1af546cc83ceed9de98f42` (`docs/research-governance/*` 설치 commit)
- Governance 적용 근거: root `AGENTS.md`의 governance router는 `MBVAR_CONTROLLED_INFO_20261029/**` 범위에만 적용된다. 이 실험은 **자발적 채택(by reference)**이며 router 확장 여부는 사용자 결정 사항(F-01, R-09).
- Contract SHA256: 이 파일 자체에는 기록할 수 없음 → `package_provenance/PACKAGE_MANIFEST.json`의 `contract_sha256`.
- Source models/code SHAs: observer 기준 `research/PJ_DS_GATED_20261021/v_replay.py` (sha256은 `config/INPUT_LOCK.json`). 신규 코드 없음(구현자 몫).
- Frozen config SHA256: `config/PLAN_PARAMETERS.json` (DRAFT_CANDIDATE, 해시는 PACKAGE_MANIFEST).
- Allowed phase/Gate: `P0_PREFLIGHT` only (G0→G1). 출력 경로 `research/POL_XCORR_UNRESOLVED_20261029/results_p0/` 신규 생성만.
- Allowed input paths: `config/INPUT_LOCK.json`에 나열된 30개 자산(25개 manifest 일치 확인 + 5개 신규 lock). 읽기 전용.
- Pre-run independent auditor and evidence: **미지정 (F-14 PENDING)**. 같은 세션 검토는 `SELF_REVIEW_ONLY`.

## Question and estimand

- **Scientific question:** LoS와 같은 해상 셀에 도착하는(δ < 1/B = 2.0 ns) 반사가 두 RX 편파(±45)에 서로 다른 복소 계수로 섞일 때, (i) 한 시점의 두 편파 CIR 창 coherency·교차상관, (ii) 이동에 따른 두 편파 진폭 엇박자·펄스 형태 변동이 heading prior 없이 그 오염을 판별하는 정보를 기존 power-only 지표(|ds1|, log_fp_power) 이상으로 제공하는가.
- **Estimands (route r 단위):**
  - E1 = ΔAUC_r(M0+M1 vs M0) for label 1{|e_s| ≥ q0.80(train)} — drive/turn 분리
  - E2 = ΔAUC_r(M0+M1+M2 vs M0+M1)
  - E3 = segment 비율 ρ_sep: e_s 분산의 ≥50%가 s_LoS 95% 대역 위에 놓이는 직선 segment 비율 (P2a)
  - E4 = ΔAUC_r(M0+M1+M4 vs M0+M1), 창 평균 label, 인과 창 L=0.6 m
  - E5 = σ_Δ,max: AUC 손실 ≤ 0.05를 유지하는 최대 포트 시간정렬 오차 (P3)
  - Mechanism M-a: log ε vs log δ 기울기 (S0, 합성)
- **State target / nuisance:** target은 오염 지표의 판별 정보. nuisance: tag yaw·고도각에 의한 LoS 편파비 추세, 안테나 cross-pol, fp tap 전환, 경로 간 정렬오차, 포트 간 이득/위상/시간 오프셋, thermal noise.
- **Null / alternative / 가정 / 예상 부호:**

| ID | Null | Alternative | 가정 | 예상 |
|---|---|---|---|---|
| H1 (S0) | 기울기 ∉ [1.9, 2.1] | ∈ [1.9, 2.1] | 2-path, 대칭 p(t), δ < 0.5/B | 2 (유도식 F2) |
| H2 (P1) | E1 ≤ 0 | E1 > 0 | label은 Full−LoS 차이로 정의 | 양(+), 크기 불확실 — e_s 중 ceiling(δ≈0.1 ns) 몫이 크면 null 가능 |
| H3 (P1) | E2 ≤ 0 | E2 > 0 | — | **부호 미정(sign-free)**: zero-lag 정규화값은 M1과 동치이므로 ≈0 예상 |
| H4 (P2a) | ρ_sep < 0.6 | ρ_sep ≥ 0.6 | Λ_floor/wall 1–2 m, s_LoS 추세 수 m | 혼재 예상(원거리 floor Λ 증가) |
| H5 (P2c) | E4 ≤ 0 | E4 > 0 | H4 PASS 전제 | 양(+) 조건부 |
| H6 (P3) | ε_ρ가 diag 이득에 불변 아님 | 상대 변화 < 1e-12 | 수학적 항등식 | 불변 (수학) |

- **Other plausible causal explanations** (각각 통제): §SCIENCE_SPEC 6장 표. 핵심: (a) LoS 자체의 타원성 → LoS 채널에서 ε≡0 음성대조, (b) yaw/고도각 추세 → LoS 채널로 같은 지표 계산(false-alarm floor) + turn 구간 대조, (c) ceiling 정지 경로 → T4 분해, (d) tap 전환 → W 민감도, (e) 포트 시간 오프셋 → S0/P3 sweep.
- **고정:** Full/LoS H(14개 파일, hash lock), observer 규칙, 궤적, tx=+45, W·L·임계 분위수, 모델 형태(logistic, 무조정).
- **의도적으로 변경:** 지표 집합(arm), P3의 합성 하드웨어 교란.
- **독립적으로 통제 불가:** scene(단일 corridor), 재료, anchor 높이(천장 5 cm 아래 → ceiling 경로 상존), route 기하. 이 셋은 δ·Λ·|a∧b|를 동시에 바꾼다.

## Data and sampling

- Experiment vs baseline: arm M0(|ds1|, log_fp_power) vs M0+M1, M0+M1+M2, M0+M1+M4. 참고 arm d0는 prior 필요로 비교에서 제외(보고만).
- Scene-family/variant/anchor/path: `CORRIDOR_BLOCK_C` 1개 family·1 variant; anchor aA(4,0,2.65)/aB(10,0,2.65); route R2/R4/R5; mount m0(+R2_aA m45).
- Units: δ [ns], tap [0.5008 ns], 거리 [m], s [무차원, −1..1], e_r [m], heading [deg in report], ε [무차원 0..1].
- **Independent sampling unit:** scene variant. 사용 가능 n=1. route·anchor·mount·pose는 반복관측이다. route 간 일치는 **기술적 일관성**이지 독립 반복이 아니다.
- Train/dev/final-test: 기존 corpus 전체는 COMMON_CONTRACT III에 따라 **RETROSPECTIVE/DEV**. LORO는 dev 내부 교차검증. **Final holdout = 없음 → `BLOCKED`**. 확증은 freeze 이후 immutable seed list로 생성한 신규 scene variant(천장고·anchor drop·복도폭·벽재 변경) 또는 라벨 프로토콜이 있는 실측으로만 가능(F-13 예산·사용자 승인 필요).
- Pose field reuse: 같은 XY 재방문(yaw sweep) pose는 같은 RF field. bootstrap block(1 m 주행거리)이 이를 묶는다.
- Frozen calibration: 없음(학습 µ/R 미사용). 분류 임계 q0.80은 train route에서만.
- Provenance: `config/INPUT_LOCK.json` (manifest 대비 불일치 0).

## Mathematics

- 상태·필터: **사용하지 않음** (EKF/R 통합은 범위 밖).
- Observation: SCIENCE_SPEC §2–3. 핵심식
  - J = Σ_{t∈W} h(t)h(t)^H, ε_W = 1−√(1−4detJ/(trJ)²), ε_ρ = detJ/(J₁₁J₂₂)
  - R₊₋(τ) = Σ_t h₊(t)h₋*(t−τ), ρ(τ) = R₊₋(τ)/√(R₊₊(0)R₋₋(0))
  - 소 δ 전개: detJ ≈ δ²|a∧b|²(E_pE_p′−|⟨p,p′⟩|²) [model-truth, 2-path 가정]
- Noise: 저장 H는 noise-free. P3에서만 complex AWGN을 fp SNR 기준으로 추가 [synthetic, known].
- 공분산 학습: 없음. logistic 계수는 learned(train route only).
- Statistical estimator: route별 ΔAUC, 1 m block bootstrap 95% CI (2000회, seed 20261029).

## Implementation & evidence

- Exact commands: 구현자가 `scripts/` 아래 작성. 계약은 입출력만 규정. P0 명령 예: `python research/POL_XCORR_UNRESOLVED_20261029/scripts/p0_preflight.py --lock config/INPUT_LOCK.json --params config/PLAN_PARAMETERS.json --out results_p0/`.
- P0 parity bounds & tolerances: `PLAN_PARAMETERS.json.tolerances_fixed_before_run` (s_fp 1e-9, LoS ε 1e-8, 이득 불변 1e-12 rel, image-method 1 ps, trace 재합성 1e-3).
- Physical canary/budget: RT 실행 없음. 신규 scene 생성은 별도 amendment + 예산 승인 전 금지.
- Expected outputs (P0): `results_p0/P0_CHECKS.json`(check_id, expected, observed, tol, status), `results_p0/TRACE_REALIGN.csv`(tag, path_idx, signature_stored, tau_ns, image_tau_ns, assigned_signature, match_ps), `results_p0/LOS_RANK1.csv`(case, pose_id, eps_W, eps_rho), `results_p0/MANIFEST.json`(COMMON_CONTRACT V 필드 전부).
- Expected outputs (P1–P3, FROZEN 이후): SCIENCE_SPEC §8.
- Fail/stop: P0 항목 하나라도 FAIL → 의존 단계 STOP, 데이터·로그 보존. R-01 FAIL은 T4만 제외(P1–P3 영향 없음)로 사전 규정.
- Acceptance vs scientific verdict: CI/스크립트 PASS는 `TECHNICAL_QA_ONLY`. 과학 판정은 auditor가 `SUPPORTED_RETROSPECTIVE / MIXED / NOT_SUPPORTED / INCONCLUSIVE` 중 하나로만.
- **Forbidden claim language:** "unresolved 다중경로를 완벽히 방어/제거", "유일한 열쇠", "EKF bias 해결", "d0 대체 확정", "일반화", "실측 검증"(P4 없이), "사전등록 성공"(DRAFT 상태), φ≠0 또는 S3≠0을 다중경로 증거로 기술.

## P0_TO_RESOLVE ledger

| ID | 항목 | 해결 방법 | 상태 |
|---|---|---|---|
| R-01 | Path trace `tau`(오름차순)·`signature`(알파벳순) 정렬 불일치, `jones` 축 정렬 미확인 | 1차 경로 image-method 대조 + node 주파수에서 Σpath 재합성 vs 저장 H | OPEN |
| R-02 | observer parity: s_fp 재계산 vs HP_PACKETS `sF_+0` | 1e-9 | OPEN |
| R-03 | LoS 채널 rank-1 수치 floor | ε ≤ 1e-8 | OPEN |
| R-04 | 공통 tap·창 W가 두 포트에 동일 적용되는지 | 코드 검사 + 합성 fixture | OPEN |
| R-05 | SAMPLES(1303) vs timeline(979) 행 수 차이, pose_id↔phase 결합 | pose_id join 검산, 결측 0 | OPEN |
| R-06 | tx 축 index 0 = +45 | `CASES.json` layout 문자열 | **RESOLVED** (`tx(+45,-45)`) |
| R-07 | DW1000 포트 간 fp 정렬 jitter 실측값 | 하드웨어 측정(외부) — P3 해석에만 필요 | OPEN_EXTERNAL |
| R-08 | 홀 VNA 2×2 파일 위치·라벨 조건 | 사용자 제공 | OPEN_EXTERNAL |
| R-09 | root AGENTS router에 POL-XCORR 범위 append 여부 | 사용자 결정 | OPEN_USER |
| R-10 | 독립 auditor 지정 | 별도 세션/사람 | OPEN_USER |
| R-11 | 신규 holdout scene variant 생성 예산 | 사용자 승인 + RT amendment | OPEN_USER |

## Pre-contract disclosure

계약 작성 전에 proposer가 본 것: `PRE_CONTRACT_DISCLOSURE.md`. 요약 — 입력 hash, 기하(image-method) δ/Λ 예측, trace 정렬 결함, 샘플 간격. **M1–M4 지표나 label(e_s, e_r, η)과의 관계는 계산·관찰하지 않았다.**

## Changes and signoff

- Protocol version: v0.1-DRAFT (2026-10-29). 선행 메모 `00_PLAN_KO.md`(v0)는 이 계약으로 대체되며, 충돌 시 이 계약이 우선.
- Pre-run proposer signature/date: _미서명 — 사용자 승인 대기_
- Pre-run auditor verdict/date: _없음_
- Frozen code SHA / amendments: 없음
- 필수 항목 미충족으로 이 문서는 **명시적 P0_PREFLIGHT만** 허가한다. S0/P1/P2/P3 = `BLOCKED_CONTRACT_INCOMPLETE`.
