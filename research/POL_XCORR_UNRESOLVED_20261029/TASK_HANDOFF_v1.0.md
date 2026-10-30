# TASK_HANDOFF_v1.0 — IMPLEMENTER 작업 지시 (contract v1.0 FROZEN)

## 0. 시작 헤더 (모든 run의 MANIFEST에 그대로 기록)

```
role=IMPLEMENTER; contract_id=POL-XCORR-001; protocol=v1.0 FROZEN (SELF_REVIEW_ONLY audit)
base_git_sha=250d617ad89a4105fa1af546cc83ceed9de98f42
governance_git_sha=d5f84d9d04d28d465f3357e9299352eb184e6bfc
contract_sha256=c36c1c56d4db59d39ea85e1d87c1efe622325730a6b4fbc595fc95e583cde219
contract_v03_body_sha256=39c396c72688d88efa84d0fcb7779ad2b5b693891ab87aaae803bd26793cb76e
science_spec_sha256=5db75dcc0a332833de50d87ba2081bea5ca0cd74e7e093ae00ce987728368450
config_sha256=a16e8226f2766f4188c144228f99276c0102532667eb1e46816c0b4e0ff42658
input_lock_sha256=bddab15801f8d8c653eeb7f825ff71352d48bda7bf7b650f59a2feb300458184
start_from_branch=research/pol-xcorr-freeze-v1-20261030 (새 implementer branch로 분기)
result_label=TECHNICAL_QA_ONLY / SELF_REVIEW_ONLY_FREEZE
```

- 실행 전에 위 sha 5개를 파일에서 다시 계산한다. 하나라도 다르면 `BLOCKED_CONTRACT_MISMATCH`로 멈춘다.
- 읽는 순서: root `AGENTS.md`(POL-XCORR router) → `COMMON_CONTRACT.md` → `governance/GOVERNANCE_APPLICABILITY.md` → 계약 v1.0 → 계약 v0.3 본문 → `SCIENCE_SPEC_v0.3.md` → `config/PLAN_PARAMETERS_v1.0.json` → 이 문서.

## 1. 단계별 권한

| 단계 | 권한 | 조건 |
|---|---|---|
| **S0** | **즉시 GO** | label 없음, 합성 |
| P1 · P2 | **HOLD** | 사용자 명시 진행 지시 또는 독립 감사자 pre-run 서명이 `reviews/`에 기록된 뒤 |
| P3 | P1/P2 이후 | P1/P2에서 살아남은 지표만 |
| P4 · RT · 신규 scene | 금지 | R-08 / R-11 |

S0를 마치면 **반드시 멈추고** 보고한다. P1 trigger를 같은 PR에 넣지 않는다.

## 2. S0 — 합성 법칙과 R-03 판정 (`results_s0/run_<id>/`)

1. **LAW 모드**
   - 모델: H(f) = a·e^{−j2πfτ₀} + b·e^{jψ}·e^{−j2πf(τ₀+δ)}. 실제 257 bin, τ₀ = 20 ns.
   - 관측 체인: v0.3 observer(Hann, 4N IFFT, 30% stronger-port, 공통 n₀) → q_W, ε_ρ.
   - 격자:
     - δ: 0–4 ns, 0.05 간격(PLAN_PARAMETERS `s0_synthetic`). 기울기 적합은 0.05–1.0 ns 구간만 쓰고, δ = 0은 기록만 한다
     - ψ: 16점
     - 정규화 wedge: {0, 0.1, 0.3, 0.6, 1.0}
     - |b|/|a|: {−20, −10, −6, −3} dB
   - 판정: ψ 고정 층별 log q_W vs log δ 기울기 ∈ [1.9, 2.1]. 근접 상쇄 층(|a + b·e^{jψ}| < 0.3|a|)은 표시하고 판정에서 제외한다.
   - **주의:** 실제 4N IFFT tap 격자에서는 n₀가 δ에 따라 바뀔 수 있다. n₀ 전환 지점을 `n0_switch` 열로 기록하고, 전환이 섞인 δ 구간은 기울기 적합을 층별로 나눈다(제외하지 않는다).
2. **PHYSICAL 모드:** ψ = −2πf_cδ(f_c = 6.5 GHz). 기울기 판정 없이 표만 보고한다.
3. **Fixture:**
   - a ∥ b → q_W < 1e-10
   - 주파수 평탄 단일 타원 경로 → q_W = 0, φ_fp ≠ 0, S3 ≠ 0(negative control)
4. **q_ref와 R-03 판정** (계약 v1.0 D6 그대로)
   - q_ref: a = (1,1)/√2, b = 10^(−0.5)·(√0.91·a + 0.3·â⊥), δ = 1.0 ns, ψ 16점 중 근접 상쇄를 제외한 q_W의 산술평균.
   - LoS q95: `results_p0/run_40867521966/LOS_FLOOR.csv` TIMELINE 7,251행.
   - 판정: q95 ≤ 0.1·q_ref → `NEGLIGIBLE`; ≤ q_ref → `NUISANCE`; 그 외 → `REDESIGN_REQUIRED`. 민감도 a = (1, 0.3j)는 보고만 한다.
   - `REDESIGN_REQUIRED`면 M1/M2 계열을 STOP하고 보고한다. 기준을 바꾸지 않는다.
5. **Noise floor:**
   - SNR {30, 20, 15, 10} dB × 포트 시간 오프셋 {0, 25, 50, 100, 250} ps(주파수 영역 e^{−j2πfΔ}을 − 포트에 적용) × seed 0–199(PCG64)
   - LoS 단일 경로의 q_W 분포 q50/q95
6. **출력:**
   - `S0_LAW.csv`: mode, delta_ns, psi, wedge, amp_ratio_db, snr_db, offset_ps, seed, n0, n0_switch, q_W, eps_rho, phi_fp, S3_fp, near_cancel
   - `S0_SLOPES.csv`
   - `S0_QREF.json`(q_ref, 민감도, LoS q95, 판정)
   - `S0_NOISE_FLOOR.csv`
   - `S0_STATUS.json`, `MANIFEST.json`
7. **S0 금지:** label 읽기, Full 채널 지표 계산.

## 3. P1 (HOLD 해제 후) — 정적 감지 (`results_p1/run_<id>/`)

1. **feature:**
   - Full과 LoS 채널, 7 case 전 pose에서 계산한다.
   - G5 17열은 `features.py`를 그대로 쓰고 R-13a parity를 재확인한다.
   - |ds1|, q_W, ε_ρ, u, 4u(1−u), WEAK_PORT, M2(τ*, A1, A2 — SPEC §3 정의·tie 규칙), M3, valid 플래그를 계산한다.
2. **label (ORACLE_ONLY):**
   - T1 = s_Full − s_LoS(자체 observer), T2 = e_r(HP_PACKETS), T3 = η_W.
   - T1과 HP_PACKETS `e_s`의 차이가 ≤ 1e-9인지 확인한다. 아니면 STOP.
3. **표본:**
   - TIMELINE drive가 주 판정, turn은 기술 통계만, STATIC_YAW_SWEEP은 진단만.
   - WEAK_PORT 행은 삭제하지 않는다.
4. **분할·학습:**
   - LORO(R2/R4/R5). held-out route의 모든 case(aA, aB, m45)를 held-out으로 둔다.
   - positive = |T1| ≥ train route(같은 phase) q0.80.
   - sklearn `LogisticRegression(C=1.0, solver='lbfgs', max_iter=1000)`, train 통계로 표준화.
   - sensitivity: `RandomForestClassifier(n_estimators=160, max_depth=6, min_samples_leaf=40, random_state=20261015)`.
   - hyperparameter 탐색 금지.
5. **arm:**
   - E1(M0+[q_W] vs M0) **주 판정**
   - E1b, E1c(all-valid + strong-only, 동일 key)
   - E2(M0+[q_W]+M2 vs M0+[q_W])
   - E1-ctrl / E1-dec(선택)
6. **판정(계약 v1.0 D1·D2):**
   - pooled Δ̄ = Σ w_r ΔAUC_r, w_r = n_r/Σn.
   - B = 2000, seed 20261029. route 내 1 m block을 case 간 공동 resampling, route 간 독립. replicate별로 가중 결합한다.
   - GO = CI 하한 > 0 그리고 ΔAUC_r > 0인 route ≥ 2/3.
   - 판정은 SUPPORTED_RETROSPECTIVE / NOT_SUPPORTED_AT_0.05 / INCONCLUSIVE_UNDERPOWERED 중 하나다.
   - v0.3 route별 규칙은 보조 열로 보고한다.
7. **층별 보고(D3):** phase × mount × WEAK_PORT × range 3분위의 AUC와 n. 판정은 하지 않는다.
8. **LoS false-alarm floor:** LoS 채널 feature로 같은 모델을 평가해 보고한다(label은 Full 기준).
9. **출력:**
   - `P1_FEATURES.csv.gz`(SPEC §8 열 + u, balance, weak_port)
   - `P1_AUC.csv`(heldout_route, arm, phase, stratum, auc, delta_auc, pooled_delta, pooled_lo, pooled_hi, route_rule_go, pooled_go, verdict, n_pos, n_blocks)
   - `P1_BOOT.npz`
   - `DECISIONS.json`, `MANIFEST.json`

## 4. P2 (HOLD 해제 후) — 공간 변동 (`results_p2/run_<id>/`)

SPEC §5 순서를 따른다.
- **P2a:** E3 ρ_sep. high-pass cut은 LoS 채널로 정한다(ORACLE_ONLY 진단). drive segment ≥ 2 m. ρ_sep < 0.6이면 M4a/M4b STOP.
- **P2b:** image-method 예측 Λ와 ±20% 이내로 맞는 비율.
- **P2c:** E4(M0+[q_W]+[M4a, M4b] vs M0+[q_W]). 인과 창 L = 0.6 m, label = 창 평균 |T1|, fold별 q0.80. D1 pooled 판정을 적용한다.
- **P2d:** turn 대조는 기술 통계만.

## 5. P3 — 하드웨어 현실성 (`results_p3/run_<id>/`)

PLAN_PARAMETERS `p3_hardware_arms`를 그대로 쓴다.
- 포트 위상: 패킷마다 U[0, 2π). 이득: N(0, 1 dB).
- σ_Δ {0, 25, 50, 100, 250} ps, SNR {30, 20, 15, 10} dB, DW1000 1.0016 ns 재표본화, seed 1000–1049.
- E5 = AUC 손실 ≤ 0.05를 만족하는 최대 시험 격자점.

## 6. 공통 규칙

- **append-only:** 새 `run_<GITHUB_RUN_ID>/` 폴더만 만든다. 과거 run, 계약, config, 입력은 수정하지 않는다.
- **실행:** GitHub Actions에서 실행한다. 단계별 workflow는 해당 phase 경로만 trigger하게 하고, 결과는 artifact와 commit 둘 다 남긴다.
- **MANIFEST 필드:**
  - §0 헤더
  - execution_git_sha
  - 입력·출력 sha256
  - 명령, package 버전, seed ledger
  - split manifest(route별 train/test key)
  - 실패 기록
- **실패 처리:** 실패도 커밋한다. CORE 실패 시 하류 단계는 STOP하고, 실패를 숨기거나 재시도해서 덮어쓰지 않는다.
- **label 격리:** S0에서 label 읽기 금지. P1부터 label은 ORACLE_ONLY 열로만 쓰고 모델 입력에 넣지 않는다.
- **보고:** 각 단계 후 `reviews/IMPLEMENTER_REPORT_<phase>.md`를 쓴다(만든 파일, 건드리지 않은 파일, 명령, hash, 결과, 실패, 남은 위험, 다음 gate). 과학 판정은 쓰지 않는다. `DECISIONS.json`의 verdict 칸은 "계약 규칙에 따른 기계적 분류"라고 명시한다.

## 7. 감사자가 사후 감사에서 확인할 항목 (미리 공지)

- 패킷 끝단 추적: 무작위 및 극단 key에서 H → CIR → n₀ → J → q_W → label 정렬.
- split 누출 없음(train route 행이 test에 섞이지 않음), threshold는 train에서만.
- WEAK_PORT 행 삭제 없음, strong-only 분석에서 baseline과 비교 arm의 key 동일.
- pooled CI 계산을 감사자가 독립 재계산(B = 2000, seed 같음).
- 모든 arm 결과 보고(유리한 arm만 선택하지 않음), 실패 run 보존.
- 금지 표현 미사용(계약 v1.0, v0.3 목록).
