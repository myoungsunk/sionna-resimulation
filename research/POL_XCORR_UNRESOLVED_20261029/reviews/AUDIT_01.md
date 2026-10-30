# INDEPENDENT_AUDIT — POL-XCORR-001 / AUDIT-01 (P0 + P0V3 runs, pre-freeze design)

Status: **COMPLETED — independent calculation executed.** Independence label: **`SELF_REVIEW_ONLY`** (§Identity). Verdict: **`REVISION_REQUIRED`** (§Verdict).

## Identity / independence

| 항목 | 값 |
|---|---|
| auditor actor/session | Claude (Opus 5.5), session `session_01X1n7vLtVgpf8CKd7wVoL2f` |
| 같은 세션의 이전 역할 | v0.1·v0.2 계약/SPEC 작성(PROPOSER), `PROPOSER_RESPONSE_01/02`, P0 실행 패치(`reference_parity`)와 `pol-xcorr-p0-preflight.yml` 작성 |
| implementer actor/session | 별도 세션(commit `51bf023`, `df0c64d`, `d47dd70`, `82e4506`, `e119917`) |
| v0.3 proposer decision | 별도 세션(commit `d5f84d9d` … `cd6e7e43`) |
| shared code/helpers | **없음.** 감사 코드는 저장소 모듈을 import하지 않는다. 정의(30% leading edge, G5 식)는 `features.py`·SPEC에서 읽었다 → **정의 수준 의존은 남음** |
| independent executable | `audit/audit01_recompute.py` (sha256 `591aca17a9b6ae3c4bd71e3ecb97ba8ab36a843881038e148d9be2575b7323ec`) |
| 독립 경로 | 자체 observer·G5 재작성, `jones_diversity`는 2×2 closed-form 고유값(eigvalsh 미사용), 30개 패킷은 np.fft 없이 명시적 DFT 합산으로 재추적, 구현자와 다른 Python/numpy/pandas 버전 |
| execution | Actions run [40982122546](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40982122546) (head `8726e9df`, Python 3.12.15 / numpy 2.2.6 / pandas 2.2.3) + 로컬 재실행(Python 3.13 / numpy 2.x) 동일 판정 |
| 실패 run 보존 | run [40981740739](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40981740739): 감사 코드 G 단계에서 pandas 2.2.3 Spearman의 scipy 의존으로 중단. 부분 출력 `results_audit01/run_40981740739/` 보존 |
| full governance commit | `d5f84d9d04d28d465f3357e9299352eb184e6bfc` |
| contract sha256 (v0.3 DRAFT) | `39c396c72688d88efa84d0fcb7779ad2b5b693891ab87aaae803bd26793cb76e` (파일 재계산 일치) |
| config / spec (v0.3) | `c9ffef3e…6d9c` / `5db75dcc…8450` |
| audited heads | implementer `e11991721a79e7e7c37ba25002abb44670658e22`, P0 `06ac7bdf`, decision `cd6e7e43` |
| input lock | `config/INPUT_LOCK_v2.json` (32 자산 + trace 925×2) |

**`SELF_REVIEW_ONLY`인 이유:** 감사 세션이 v0.1·v0.2 설계와 P0 참조 대조 패치를 직접 작성했다. ROLE_AUDITOR 규칙상 이 보고서는 **R-10/F-14(독립 감사 서명)를 충족하지 않는다.** 계산 결과는 증거로 쓸 수 있으나, FROZEN 승인 근거가 되는 독립 서명은 별도 세션이 필요하다.

## Pre-run design correctness

| Test | Expected | Recomputed observed | Result | Evidence |
|---|---|---|---|---|
| (ADAPT) 소 δ 법칙 det J ≈ δ²\|a∧b\|²(E_pE_p′−⟨p,p′⟩²) | 비율 → 1, log–log 기울기 2 | 연속 Gaussian 펄스(계약 S0의 Hann 대역·q_ref 아님): 비율 0.99999(δ=0.02)→0.99716(δ=0.32), 기울기 **1.9991**; 평행 Jones ε_ρ = 0 | PASS | `I_MATH_SMALL_DELTA_LAW` |
| 항등식 q = 4u(1−u)ε_ρ, q = 4x(1−x) | 기계 정밀도 | 무작위 PSD 2×2 20,000개: 4.4e-16, 3.7e-16 | PASS | `I_MATH_IDENTITIES` |
| 단위·축 | Δt = 1/(1028Δf) | 0.4988526 ns | PASS | `dt_ns` |
| arm 중첩 구조 | E1 ⊂ E2/E4 기준 일관 | v0.3: E1 = M0+[q_W] vs M0, E2·E4는 M0+[q_W] 위 증분, ε_ρ는 E1c(secondary) | PASS | `PLAN_PARAMETERS_v0.3.models` |
| train/test 분리 | LORO route, holdout 명시 | LORO dev-only, final holdout BLOCKED, scene n = 1 명시 | PASS(경계 포함) | 계약 v0.3 §Data |
| 사전등록 순서 | label 관측 전 freeze | label·AUC 미계산 확인(코드·출력 열 검사). 단 v0.3 결정은 LoS P0 측정 이후 — 공개됨(#12, v0.3 disclosure) | PASS(공개 조건) | `J_LABEL_ISOLATION_OUTPUTS`, disclosure |
| freeze 산출물 | 계약 sha 기록·서명 | v0.3 계약 본문 `Contract SHA256: PENDING…`, proposer 서명 없음, F-11 없음 | **FAIL(미완)** | 계약 v0.3 L13, checklist v0.3 |

## Run correctness

| Test | Expected | Independent recomputation | Result | Ref |
|---|---|---|---|---|
| 입력 hash | 32 자산 + trace 집합 일치 | 불일치 0, 집합 `6c2a4998…` 재계산 일치 | PASS | `A_INPUT_LOCK` |
| R-02 s_fp vs HP `sF_+0` | ≤ 1e-9, 9,519 1:1 | 9,519/9,519, max 1.1e-16 | PASS | `B_R02` |
| R-12 log_fp_power vs HP | ≤ 1e-9 | max 1.8e-15 | PASS | `B_R12` |
| R-13a G5 Full vs UM (17열) | ≤ 1e-9, NaN 패턴 동일 | max 7.1e-15, NaN 불일치 0 | PASS | `C_R13a` |
| R-13b G5 Full+LoS vs run 39376076166 artifact | ≤ 1e-9 | 19,038/19,038, max 7.1e-15; artifact sha256 `6a69a36a…6fe4` | PASS | `C_R13b` |
| R-04 tap/branch (LoS) vs 구현자 P0V3 | 불일치 0 | 9,519행 n₀·branch 불일치 0 (두 run 모두) | PASS | `D_IMPL_LOS_*` |
| R-04 tap (Full) | 저장 참조와 일치 | range_m = n₀·Δt·c의 R-13a parity로 Full n₀가 저장 결과와 정확히 일치 | PASS | `C_R13a.range_m` |
| R-14 u, q_W, ε_ρ vs 구현자 | ≤ 1e-12 | max 2.8e-16 / 1.0e-15 / 1.2e-15; WEAK 3,492 = 3,492 | PASS | `D_IMPL_LOS_*` |
| 패킷 끝단 추적 (DFT) | FFT 경로와 일치 | 무작위 24 + 극단 6(최대 ε_ρ, 최소 u, 최대 q_W, 최소/최대 n₀, u≈0.5): n₀·branch 불일치 0, q·ε 상대오차 ≤ 5.8e-13 | PASS | `AUDIT01_PACKET_TRACE.csv` |
| 같은 pose 재방문 H 동일성 | 동일 | 7 case 모두 정확히 반복된 (x, y, yaw) pose 없음 | N/A | 감사 로그 |
| 실패·무효 관측 보존 | 묵시적 삭제 0 | LoS 9,519 VALID, u ≥ 0.499 13행은 역산 검사만 건너뛰고 행은 보존 | PASS | `F_WEAK_PORT_COUNTS` |
| 출력 무결성·append-only | manifest hash 일치, 과거 run 무수정 | P0 2개·P0V3 2개 run 전 파일 일치, 과거 run 폴더는 생성 commit 외 변경 없음, P0V3 두 run 공통 8파일 동일 | PASS | `H_OUTPUT_INTEGRITY` |
| 보호 경로·범위 | POL-XCORR 외 변경 없음 | base `250d617a`→HEAD 변경: POL-XCORR 폴더, workflow 2개, AGENTS.md(삭제 0줄, append만) | PASS | git diff |
| label 격리 | 참조 표 usecols, 출력에 label 열 없음 | 구현자 코드 `usecols` 확인, 출력 CSV에 e_s/e_r/eta 계열 열 없음 | PASS | `J_LABEL_ISOLATION_OUTPUTS` |

## Scientific claims

- **Supported exactly (TECHNICAL_QA, 과학 아님):** 관측 체인, G5 baseline, LoS J·q_W·ε_ρ·u가 저장 참조와 구현자 출력에서 기계 정밀도로 재현된다. 소 δ 전개식은 이상화된 연속 2-path 모델에서 맞다.
- **Rejected exactly:** 없음.
- **Mixed / unresolved:**
  - WEAK_PORT 비율이 mount 0°에서 54–67%, mount 45°(R2_aA_m45)에서 1.0%, R4에서 8.5–8.9%다. 약포트는 이상치가 아니라 **편파 배치에 따른 구조적 상태**다. R-14(d)(일괄 제외 거부)는 정당하다.
  - mount 45°는 case가 하나뿐이므로, mount 효과는 route·anchor와 분리할 수 없다.
- **Alternative explanations:** LoS floor(q95 ≈ 0.006)와 방향 의존성은 주파수 의존 포트 응답(F1′)과 일치한다. q_ref 판정 전에는 다중경로 증거로 쓸 수 없다.
- **Inadmissible extrapolations:** 소 δ 법칙 PASS는 실제 채널이나 Hann 대역 S0의 확인이 아니다. R-13a와 R-13b는 같은 upstream이므로 독립 반복으로 세지 않는다. 두 P0V3 run의 일치는 같은 코드의 재실행이다.

## Auditor findings

| ID | 심각도 | 내용 | 필요 조치 |
|---|---|---|---|
| AF-1 | BLOCKING | v0.3 계약 본문에 contract sha256이 `PENDING`이고 proposer 서명이 없다. FROZEN 산출물(package manifest)이 없다 | proposer: sha 기록·서명·manifest |
| AF-2 | BLOCKING | F-11 label 없는 검정력 시뮬레이션이 없다. block 수(drive R2 40 / R4 35 / R5 58)로 감지 가능한 최소 ΔAUC 미기록 | implementer 또는 proposer: 사전 기록 |
| AF-3 | BLOCKING (R-10) | 이 감사는 SELF_REVIEW_ONLY | 제안자·구현자와 다른 세션의 감사자가 서명 |
| AF-4 | 기한 있음 | R-13b artifact가 **2026-11-19T05:41Z에 만료**된다. 이 감사에서 sha256 `6a69a36a…`와 내용 일치를 확인했다 | 만료 전에 보존. 권장: key+G5 열만 추출한 파일을 커밋하고 원 파일 sha256 기록 |
| AF-5 | 중간 | governance commit `d5f84d9d`가 research branch 3개에만 있고 main에는 없다. rebase나 삭제 시 추적이 끊긴다 | tag(예: `gov/pol-xcorr-router`) 또는 main 반영 |
| AF-6 | 권고 | 약포트 비율이 mount에 따라 구조적으로 갈린다 | P1 결과를 mount(0°/45°)·WEAK_PORT 층별로도 보고하도록 freeze 전 명시(label 미사용 결정) |
| AF-7 | 철회 | 감사 세션이 앞서 제기한 "q_W의 포트 균형 교란" 우려(E1-ctrl/E1-dec 요구)는 LoS 측정으로 약화됐다. var(log q_W) 중 균형 항 기여 **−2.1%**, ε_ρ 항 **102%**. 창 균형 4u(1−u)와 M0의 1−s_fp²는 Spearman **0.994**로, M0가 이미 균형 정보를 담고 있다 | **FROZEN 필수 요건에서 철회.** E1-ctrl은 저비용 secondary 대조로만 선택 사항. Full 채널 확인은 FROZEN 이후 P1에서 |
| AF-8 | 정보 | 구현자 P0V3는 P0 모듈(제안자 패치 포함)을 import하지만, 사용한 `independent_observer`는 구현자 작성분이다. 이 감사의 자체 재작성으로 교차 확인했다 | 없음 |
| AF-9 | 정보 | 이 감사 branch에 push할 때마다 기존 `powerjoint-separate-rs-model-validation.yml`이 실행되어 실패한다(POL-XCORR와 무관한 기존 workflow) | 해당 workflow의 trigger 정리는 별도 작업 |

## Verdict

**`REVISION_REQUIRED`**

- **근거:**
  - 기술 실행은 유효하다. P0·P0V3의 모든 CORE 항목을 독립 코드 경로로 재현했다.
  - 수학적 무효나 train/test 누출은 없으므로 REDESIGN은 필요 없다.
  - 다만 AF-1(계약 sha·서명 미기록), AF-2(F-11 미수행), AF-3(독립 서명 부재) 때문에 FROZEN으로 갈 수 없다.
- **Blocking defects와 담당:**
  - AF-1 → proposer
  - AF-2 → implementer 또는 proposer
  - AF-3 → 사용자(별도 감사 세션 지정)
  - AF-4 → 만료일(11/19) 전 누구나
- **Permitted claim-register promotions:** 없음. SELF_REVIEW_ONLY이므로 PX 항목의 상태를 바꾸지 않는다.
- **P0V3 기술 판정 수용:** R-04·R-14의 `CLOSED_TECHNICAL`을 감사 측 재계산으로 확인했다(독립 서명은 아님).
- **Auditor signature/date:** Claude (Opus 5.5), session `session_01X1n7vLtVgpf8CKd7wVoL2f`, 2026-10-30 KST — **SELF_REVIEW_ONLY, R-10 충족하지 않음**.
