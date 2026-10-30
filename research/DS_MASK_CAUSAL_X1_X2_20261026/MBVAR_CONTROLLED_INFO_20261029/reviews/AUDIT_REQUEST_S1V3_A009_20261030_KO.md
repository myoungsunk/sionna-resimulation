# MBVAR-INFO-001 감사 요청서 — S1V3 DEV2 결과 및 AMENDMENT-009

| 항목 | 값 |
|---|---|
| 작성일 | 2026-10-30 (KST) |
| 작성 역할 | IMPLEMENTER. §4의 추가 옵션은 사용자 요청에 따라 PROPOSER 관점으로 작성. **SELF_REVIEW_ONLY** |
| 계약 | MBVAR-INFO-001 FROZEN (`68d73bd22bf4…`) + AMENDMENT-003…008. AMENDMENT-009는 **DRAFT(미동결)** |
| Governance SHA | `250d617ad89a4105fa1af546cc83ceed9de98f42` |
| 브랜치 | `research/mbvar-info-001-20261029` |
| 선행 감사 | C2 재감사 `audit/mbvar-info-c2-40871327417-20261030` (`a03cbc1b`) / S1V3 설계 감사 `audit/mbvar-info-s1v3-design-20261030` (`353381b3`, 대상 실행 SHA `c4d84e02`) |
| 현재 상태 | HOLDOUT2 **NO-GO** (미개봉) / 물리 RT P3 **NO-GO** |

---

## 1. 요청 요약

S1V3 DEV2 결과와 AMENDMENT-009 설계에 대한 독립 감사를 요청합니다.

**검토 요청 대상**
1. AMENDMENT-008 하에서 실행된 **S1V3 DEV2 실행 `40981032471`**: 기술 QA PASS, 파일럿 결과 `NOT_SUPPORTED`.
2. S1V3 설계 감사 지적사항(W1–W7)을 반영한 **AMENDMENT-009 초안**: 수정 F1–F4, 옵션 B(tap 강건성), 옵션 C(RT 잔차 탐색), 최종 게이트 G1–G7.
3. 설계 감사가 지적한 수렴 분류 결함(W1)이 실제 DEV2에서 발생했는지에 대한 **G2 사후 점검 결과** (4행 발생).

**감사자 판정을 요청하는 항목**
- S1V3 DEV2 결과의 기술적 유효성.
- AMENDMENT-009를 이대로 동결해도 되는지 여부.
- G2 4행 처리 방식(A008 기록 유지 + 보고)이 적절한지.
- H2 tan 부호 역전을 어떻게 해석해야 하는지 (§3.4).

**아직 실행하지 않은 것:** C3 (S1V3 재현 검증), S1V4, C3V4, 옵션 B, 옵션 C의 CI 실행. 이 요청서는 해당 결과를 포함하지 않습니다.

---

## 2. 감사 대상 커밋·실행·파일

### 2.1 커밋 이력 (시간순)

| 커밋 | 내용 |
|---|---|
| `6aa9bf4` | AMENDMENT-008 DRAFT (post-fit P, class v3, input receipt, S1V3/C3 코드) |
| `0d83032` | **AMENDMENT-008 FROZEN** (E' polish, A8-2 bound, PROBE_POWER, C3 게이트, DEV2 = 10–19) |
| `c4d84e0` | RUN_REQUEST: P2_S1V3 (DEV2 10–19) → 실행 `40981032471` 트리거 |
| `bf17158` | **AMENDMENT-009 DRAFT** — S1V3 결과를 **열람하기 전**에 규칙과 코드를 커밋 |
| `e210236` | (bot) P2_S1V3 결과 게시 `results/P2_S1V3_run_40981032471/` |
| `a4df260` | AMENDMENT-009 DRAFT: §8 상태 기록, Timing 행 수정. **코드 변경 없음**, 미동결 |

### 2.2 실행

| 실행 | Phase | 결과 |
|---|---|---|
| `40981032471` | P2_S1V3 (DEV2 10–19, AMENDMENT-008) | 워크플로 success, MANIFEST `execution_status = PASS` |

보존된 이전 FAIL 실행
- C2 `40871327417`
- C1 `40857100181`
- S1V2 DEV `40864089916`, `40867939262`

### 2.3 주요 파일 (`research/DS_MASK_CAUSAL_X1_X2_20261026/MBVAR_CONTROLLED_INFO_20261029/`)

| 경로 | 설명 |
|---|---|
| `contracts/AMENDMENT-008.md` | 동결 계약 (lock 포함) |
| `contracts/AMENDMENT-009.md` | 초안. §1 W1–W7, §2 F1–F4, §3 옵션, §4 BTAP, §5 RFRES, §6 G1–G7, §8 동결 시점 상태 |
| `code/s1v3.py`, `code/c3_verify.py`, `code/a8_jac.py` | AMENDMENT-008 코드. **이후 미수정** |
| `code/s1v4.py`, `code/c3v4.py`, `code/a9_class.py`, `code/b_tap.py`, `code/c_rfres.py` | AMENDMENT-009 신규 파일 |
| `tests/test_a8_jacobian.py`, `tests/test_a9_class.py` | KINK_FIXTURES, LINEAR_EXACT(H 수준), class v3.1 단위 시험 |
| `results/P2_S1V3_run_40981032471/` | S1V3 DEV2 산출물 전체 (input receipt `S1V3_INPUTS_DEV2_*.zip` 포함) |

### 2.4 재현 경로

- **CI 재실행:** `RUN_REQUEST.json`에 `phase=P2_S1V3`, `split=DEV2`, `field_ids=10..19`, amendments `001…008`을 두고 push하면 됩니다. 실행 커밋 `c4d84e0`과 동일한 코드가 필요합니다.
- **로컬 단일 행 재현:** `s1v3.make_inputs`로 입력을 재생성한 뒤 `s1v3.eval_batch`를 호출합니다. `REFLECT_ROOT`는 `reflect_model/fetch_inputs.sh`(`FETCH_RF=0`)로 준비합니다.
- **입력 대조:** `S1V3_INPUTS_DEV2_<field>.zip`은 NumPy `savez` 아카이브입니다. 키 형식은 `"<field>|<role>|<cell>|<sensor>|z"` 등입니다.
  - git-LFS의 `*.npz` 규칙을 피하려고 확장자를 `.zip`으로 저장했습니다. `np.load`로 그대로 열립니다.

---

## 3. S1V3 DEV2 실행 `40981032471` 결과

모든 수치는 `results/P2_S1V3_run_40981032471/`의 파일에서 그대로 옮긴 것입니다. **DEV2 파일럿이며 확증 결과가 아닙니다.**

### 3.1 기술 QA (`S1V3_QA.json`) — PASS

| 항목 | 값 |
|---|---|
| 행 수 | 1980 / 1980 (fields 10–19 전부) |
| failures / stops | 0 / 0 |
| input receipt 파일 | 10 |
| Mahalanobis 허용오차 | 0.1633 (범위 내) |
| revisit 동일 pose 최대 차 / 시간 성분 최소 차 | 0.0 / 0.0742 |
| class v3 (A008 규칙) | CONVERGED_SMOOTH 712, LOCAL_MIN_CERTIFIED 368, **NOT_CERTIFIED 0** |
| 구 A007 class (보고용) | CONVERGED 712, CONVERGED_NONSMOOTH 367, NONCONVERGED 1 → `ORACLE_CORR_BATCH \| LOW \| POSE_HIGH` 1/30 (구 규칙 기준 셀 실패, 비게이트) |
| primary C10 P PD | 전 행 |
| KINK_P_UNCERTAIN | 0 % |
| rel_spread (q50 / q90 / q99 / max) | 0.0038 / 0.0102 / 0.0240 / 0.0483 |
| A8-2 polish | 11행 적용, 최대 E→E' 0.783 · d_ref, 최대 Δcost 0.0161 χ², cap 도달 0 → 전부 범위 내 |

### 3.2 A8-5 공분산 통계 정합성 (ORACLE arm, C10 P)

| 창 그룹 | kink at E | 상태 | n_runs | mean(e²/P) | 95 % CI | coverage(1.96) | 판정 |
|---|---|---|---|---|---|---|---|
| LH | 아니오 | tan | 202 | 1.133 | 0.905–1.351 | 0.931 | PASS |
| LH | 아니오 | psi | 202 | 0.956 | 0.678–1.245 | 0.955 | PASS |
| LH | 예 | tan | 98 | 1.141 | 0.818–1.490 | 0.939 | PASS |
| LH | 예 | psi | 98 | 1.038 | 0.778–1.315 | 0.949 | PASS |
| RV | 아니오 | tan | 80 | 1.179 | 0.755–1.696 | 0.925 | UNDETERMINED |
| RV | 아니오 | psi | 80 | 0.662 | 0.543–0.821 | 0.988 | UNDETERMINED |
| RV | 예 | tan | 100 | 1.154 | 0.855–1.490 | 0.950 | PASS |
| RV | 예 | psi | 100 | 0.926 | 0.681–1.177 | 0.970 | PASS |

**판정:** CALIBRATION_FAIL 없음. 8개 층 모두 평가 가능하며, 2개 층은 UNDETERMINED입니다.

**참고:** RV 비-kink psi의 점추정 0.66은 C10 P가 실제 오차보다 큰 쪽(보수적)입니다. 이 층은 CI 상한(0.82)도 1.0보다 작습니다.

### 3.3 A8-6 Jacobian 관례 민감도

다음 7가지 조건에서 H1 / H2 / H3 / CAL / H4 판정 목록이 모두 동일합니다.
- A, C03, C10, C30, L, R
- C10에서 KINK_P_UNCERTAIN 행 제외 (해당 행 0개)

결과: `CONSISTENT_ACROSS_CONVENTIONS`.

### 3.4 파일럿 가설 판정 (C10, DEV2 n = 10) — `NOT_SUPPORTED` (결정 아님)

**H1 — IID_BATCH 실현 inflation vs S0V2 정확 예측**

| 창 | cell | 상태 | 실현 | S0 예측 | log 편차 [95 % CI] | 판정 |
|---|---|---|---|---|---|---|
| LOW | LOWCORR | tan | 0.94 | 1.00 | −0.066 [−0.482, 0.255] | UNDETERMINED |
| LOW | LOWCORR | psi | 0.97 | 1.00 | −0.035 [−0.293, 0.184] | PASS |
| LOW | POSE_HIGH | tan | **3.72** | **8.91** | **−0.873 [−1.476, −0.458]** | **FAIL** |
| LOW | POSE_HIGH | psi | 6.49 | 7.40 | −0.132 [−1.274, 0.589] | UNDETERMINED |
| HIGH | LOWCORR | tan | 1.11 | 1.00 | 0.103 [−0.408, 0.476] | UNDETERMINED |
| HIGH | LOWCORR | psi | 0.83 | 1.00 | −0.185 [−0.586, 0.097] | UNDETERMINED |
| HIGH | POSE_HIGH | tan | 11.85 | 5.77 | 0.720 [−0.079, 1.218] | UNDETERMINED |
| HIGH | POSE_HIGH | psi | 12.23 | 11.34 | 0.075 [−0.607, 0.528] | UNDETERMINED |

**H2 — 상관 × 기하 상호작용 (DID)**

| 상태 | 관측 DID [95 % CI] | S0V2 예측 | 판정 |
|---|---|---|---|
| psi (primary) | −0.785 [−1.742, −0.197] | −0.428 | PASS |
| tan | **−0.990 [−1.564, −0.146]** | **+0.435** | **FAIL (부호 반대)** |

**H3 — ORACLE / IID MSE 비 (POSE_HIGH)**
- HIGH tan 0.376 → PASS
- HIGH psi 0.619 → PASS
- LOW tan, LOW psi → UNDETERMINED

**Power:** `n_confirm = 60`이며 `underpowered_at_max = true`입니다. HOLDOUT2를 60 field로 열어도 일부 대비는 결정되지 않을 수 있습니다.

**감사자 판단 요청 — H2 tan 부호 역전.** S0V2는 선형 Gaussian 정확 계산이고, S1은 비선형 MAP(E')입니다.

LOW POSE_HIGH tan에서 실현 inflation이 예측의 약 0.42배이고, HIGH POSE_HIGH tan은 약 2배입니다. 그 결과 DID의 부호가 뒤집혔습니다.

다음 세 가지 가능성을 구현자는 구분하지 못했습니다.
- (a) 선형화(S0V2)가 이 기하에서 유효하지 않음
- (b) 추정기 효과 (polish, multi-start)
- (c) 표본 변동 (n = 10, 넓은 CI)

**구현자는 이 결과를 이유로 규칙을 바꾸지 않았습니다.**

---

## 4. 설계 감사 지적사항 반영 내역

### 4.1 지적 → 반영

| ID | 지적 / 취약점 | 반영 (AMENDMENT-009) | 상태 |
|---|---|---|---|
| W1 | `class_v3`가 analytic decrement ≤ 1e-10이면 probe를 확인하지 않고 `CONVERGED_SMOOTH`를 반환 | **F1** class v3.1: probe 하강 > τ = 0.01 χ²이면 decrement와 무관하게 `NOT_CERTIFIED`. `code/a9_class.py`. 감사자 반례(dec = 0, ΔC = −0.02)를 단위 시험으로 고정 | 코드·시험 완료 |
| W2 | 같은 조건에서 polish가 생략됨 | **F2** polish를 전 행에서 실행하고, probe 하강 ≤ 1e-3 χ²에서 정지. A8-2 범위(2 · d_ref, 1 χ²)는 불변 | 코드 완료 |
| — | 불연속 경계의 좌우 방향 우선 | **F3** x0 각 좌표에 ±ρ_a √P0_jj 편측 probe 추가 (ρ_a ∈ {1e-2, 1e-3}, 16개) | 코드 완료 |
| W3 | `nees4`가 analytic P 사용 | **F4** window-end C10 4×4 전체를 저장하고 `nees4_C10`을 계산. **S1V3(A008) 결과의 결합 정합성 주장은 상태별 A8-5로 한정** | 코드 완료 |
| W4 | `LOCAL_MIN_CERTIFIED`의 의미 | "유한 probe에서 하강을 찾지 못함"으로 한정. 국소·전역 최적성 증명이 아님 | 문서 반영 |
| W5 | EKF(상태 유도 tap)와 batch(참값 tap)의 tap 처리 불일치 | 옵션 B에 `EKF_ORACLE_TAP` 추가 | 코드 완료 |
| W6 | HOLDOUT2는 같은 생성기의 새 난수일 뿐, 독립 RT 장면이 아님 | 청구 범위를 "통제 합성 모델 내 재현성"으로 한정 | 문서 반영 |
| W7 | S1V4/BTAP가 S1V3 열람 이후 DEV2를 재사용 | development 증거로 표기. 확증 합성 집합은 HOLDOUT2뿐 | 문서 반영 |

**보존 원칙:** AMENDMENT-008 파일(`s1v3.py`, `c3_verify.py`, `a8_jac.py`)은 수정하지 않았습니다. 그래서 C3가 S1V3를 A008 코드 그대로 재현할 수 있습니다. 신규 로직은 모두 새 파일에 있습니다.

### 4.2 G2 사후 점검 — W1이 실제로 발생함

S1V3 DEV2 batch 행 중 `newton_decrement ≤ 1e-10`이면서 `probe_min_dcost < −0.01`인 행이 **4개** 있습니다.

| field | 창 | cell | sensor | arm | probe 최소 ΔC (χ²) | 최소화 probe | kink at E |
|---|---|---|---|---|---|---|---|
| 12 | FWD60 | POSE_HIGH | 2 | XMODEL_BATCH | −0.0137 | gn_C30_1 | 0 |
| 19 | REV60 | POSE_HIGH | 1 | XMODEL_BATCH | −0.0121 | gn_C30_1 | 0 |
| 13 | REV60 | POSE_HIGH | 1 | XMODEL_BATCH | −0.0489 | gn_C30_1 | 0 |
| 18 | REV60 | TIME_HIGH_5 | 2 | XMODEL_BATCH | −0.0262 | gn_C10_1 | 0 |

- **기록상 분류:** 4행 모두 A008 규칙으로 `CONVERGED_SMOOTH`로 기록되었습니다. polish는 0 step입니다.
- **원인 해석:** analytic 기준으로는 평활 수렴입니다. 그러나 큰 step의 central-FD Jacobian(C30/C10)이 주는 GN step으로 더 낮은 cost 점이 존재합니다. 즉 E 근방, kink 너머에 더 낮은 점이 있습니다.
- **v3.1 적용 시:** 3개 셀(XMODEL FWD60 POSE_HIGH 1/30, REV60 POSE_HIGH 2/30, REV60 TIME_HIGH_5 1/30)이 셀별 1 % 규칙에서 실패합니다.
  - pooled 4/1080 = 0.37 %는 대체 규칙으로 쓰지 않았습니다.
- **처리:** A008 기록(QA PASS)은 변경하지 않습니다. 이 사실을 AMENDMENT-009 §8에 보고했습니다. 수정은 실패를 추가할 수만 있으므로 소급 PASS는 생기지 않습니다.
- **판단 요청:** "A008 기록 유지 + 보고"가 적절한지, 아니면 S1V3 DEV2 class 게이트를 FAIL로 재판정해야 하는지 감사자의 판정을 요청합니다.

---

## 5. AMENDMENT-009 설계 요약 (사전 등록 규칙)

### 5.1 S1V4 = S1V3 + F1–F4

- 입력, E, post-fit P 관례, A8-5/A8-6 장치는 S1V3에서 import한 것을 그대로 씁니다.
- A8-5는 8개 층을 항상 모두 나열합니다. field가 2개 미만인 층은 `evaluable = false`로 두고 UNDETERMINED로 셉니다.
- A8-6에 제외 민감도를 하나 더 추가했습니다.
  - 기존: KINK_P_UNCERTAIN 행 제외.
  - 추가: E' kink 행 제외.
  - 출력은 `A86_convention_outcome`과 `A86_exclusion_outcome`으로 분리합니다.

### 5.2 옵션 B — tap 강건성 (P2_BTAP, DEV2 민감도, 비확증)

| 조건 | 추정기의 tap 정보 (생성기는 불변) |
|---|---|
| TAP_ORACLE | 참값 tap (현 설계) |
| TAP_ERR_1 | pose의 10 %에서 ±1 detector index 오류 |
| TAP_ERR_4 | 10 %에서 ±4 index (4배 zero-padding 격자의 raw tap 1개) |
| TAP_STATE | tap 관측 없음. 매 평가마다 상태에서 detector tap 재유도 (`world.h_H`) |

- **설계:** DEV2 10–19 × sensor 0–2 × LOW/HIGH × LOWCORR/POSE_HIGH × {IID, ORACLE} × 4 조건.
- **EKF 대조:** `EKF_STATE_TAP` (S1V2 EKF)와 `EKF_ORACLE_TAP`. 기대 행 수는 1200입니다.
- **사전 등록 규칙:** TAP_ERR_1의 H1 / H2 / H3 / CAL 판정이 모두 TAP_ORACLE과 같으면 `ROBUST`, 다르면 `TAP_SENSITIVE`입니다.
  - `TAP_SENSITIVE`는 실패가 아니라 RT 단계의 요구사항이 됩니다 (실제 tap 추출 검증).

### 5.3 옵션 C — 기존 RT 잔차 탐색 (P2_RFRES, 탐색적, 게이트 없음)

- **데이터:** DRIVE_SIM BLOCK_C (커밋 `9bcd5da2`), corridor 7개 case의 Full / LoS-only RT 채널. drive trace의 참값 pose에서 noise-free first-path 관측을 씁니다.
- **잔차 분해:**
  - e_tot = obs(Full) − FFD(truth)
  - e_mp = obs(Full) − obs(LoS)
  - e_los = obs(LoS) − FFD(truth)
- **사전 선언 기술 플래그:**
  - BIAS: |mean| > 0.5 σ_synth
  - SCALE: sd/σ_synth ∉ [0.5, 2]
  - NON_GAUSSIAN: |초과첨도| > 1 또는 |왜도| > 0.5
  - FP_SWITCH: first-path 전환 > 5 %
  - CORR_MISMATCH: 쌍 ≥ 200인 거리 구간에서 |corr_emp − 0.7k| > 0.3
- **용도:** 이미 사용된 데이터이므로 확증으로 인정하지 않습니다. 결과는 pre-P3 계약(G7)의 명시 항목으로만 씁니다.
- **참고 (증거 아님, 코드 경로 확인용 로컬 단일 case R4_aB_m0):**
  - e_mp s의 sd는 σ_s의 6.7배, 초과첨도 7.8.
  - first-path 전환 38 %.
  - e_mp 공간상관은 < 10 cm에서 0.22로, 합성 POSE_HIGH 예상 0.43보다 짧습니다.
  - e_los s의 sd ≈ 0 (FFD와 RT LoS의 s가 일치).
  - 플래그 임계값은 이 확인과 무관하게 정했습니다.

### 5.4 로컬 기술 점검 (SMOKE 900/901, 축소 설계 — 증거 아님)

- **A008 (S1V3 + C3):** S1V3 QA PASS. C3는 전 게이트 PASS (INPUT / STATE_COST / P / STATUS 재현, NO_WRONG_BASIN, 안정성, ITER_CAP, PROBE_POWER 100 %, LINEAR_EXACT, KINK_FIXTURES).
- **A009 (S1V4):** QA PASS, G2 카운터 0, 8개 층 표기, `nees4_C10` 산출, A8-6 두 출력 생성 확인.
- **진행 중:** C3V4와 BTAP 로컬 점검은 이 문서 작성 시점에 실행 중입니다.

---

## 6. 동결 타이밍과 사후 변경 검증 방법

- AMENDMENT-009의 규칙과 코드는 S1V3 결과를 **열람하기 전**인 `bf17158`(S1V3 실행 중)에 커밋했습니다.
- 동결은 S1V3를 열람한 뒤에 이루어집니다. 따라서 열람 후 변경이 없었음을 검증할 수 있어야 합니다.
- **검증 명령:**
  ```
  git diff bf17158 <동결 커밋> -- research/DS_MASK_CAUSAL_X1_X2_20261026/MBVAR_CONTROLLED_INFO_20261029/code \
                                 research/DS_MASK_CAUSAL_X1_X2_20261026/MBVAR_CONTROLLED_INFO_20261029/tests
  ```
  - 현재 `bf17158 → a4df260`에서 위 경로의 diff는 **비어 있습니다**.
  - 계약 문서 diff는 §8(동결 시점 상태)과 Timing 행뿐입니다.
- **A008 코드 불변 확인:**
  ```
  git diff 0d83032 HEAD -- .../code/s1v3.py .../code/c3_verify.py .../code/a8_jac.py
  ```
  → 비어 있어야 합니다.
- **열람 이후 결정 이력:** 기존 두 결정은 모두 DEV2 결과 이전, AMENDMENT-008 동결 전에 내려졌고 AMENDMENT-008에 기록되어 있습니다.
  - polish 도입
  - A8-2 bound를 기존 C3 허용오차(2 · d_ref, 1 χ²)에 연결
  - 둘 다 SMOKE 1행 관찰 이후 결정입니다.

---

## 7. 최종 게이트 G1–G7 현황 (요청서 작성 시점)

| 게이트 | 근거 | 현재 상태 |
|---|---|---|
| G1 DEV2 기술 QA | S1V3 QA (A008), S1V4 QA (A009) | S1V3 **PASS** / S1V4 미실행 |
| G2 수렴 분류 감사 | S1V3 사후 W1 점검, S1V4 G2 카운터 | S1V3에서 **4행 발생** (v3.1 기준 3셀 실패) / S1V4 미실행 |
| G3 공분산 통계 | A8-5 8개 층, `nees4_C10` | S1V3: FAIL 없음, 2층 UNDETERMINED / `nees4_C10`은 S1V4부터 |
| G4 결과 안정성 | A8-6 관례·제외 민감도 | S1V3: 관례 간 일치 / 제외 민감도 확장은 S1V4부터 |
| G5 C3 재현성 | C3 (S1V3), C3V4 (S1V4) | **미실행** |
| G6 독립 확증 | HOLDOUT2 (S1V4 코드, 독립 재감사 후) | **NO-GO** — G1–G5 결정과 재감사 필요 |
| G7 pre-P3 계약 | 복소 채널 + 실제 tap 추출, 공유 C10 판, DIRECT parity, RFRES 플래그, **사용자 숫자 예산 승인** | **NO-GO** — 미서명, 예산 미승인 |

**결론:**
- **HOLDOUT2:** NO-GO. G5가 미실행이고, G2 처리 판정이 필요하며, 독립 재감사가 필요합니다.
- **물리 RT(P3):** NO-GO. G6과 G7이 미충족입니다.

---

## 8. 감사자 검증 요청 체크리스트

**계약·절차**
- [ ] `bf17158 → 동결` 사이 code/tests diff가 비어 있는지 확인 (§6)
- [ ] `s1v3.py` / `c3_verify.py` / `a8_jac.py`가 `0d83032` 이후 불변인지 확인
- [ ] AMENDMENT-009 §1–§6의 규칙이 S1V3 결과로부터 조정되지 않았는지 확인

**S1V3 DEV2 결과**
- [ ] `S1V3_INPUTS_DEV2_*.zip`으로 독립 구현에서 입력(z, 제어, x0, tap, Σ fingerprint)을 재생성해 대조
- [ ] `S1V3_RESULTS_DEV2.csv`에서 A8-5 표(§3.2)와 H1 / H2 / H3 표(§3.4)를 독립 재계산
- [ ] G2 4행에 대해 E를 재실행하고 C30/C10 GN step의 cost 감소를 재현 (θ̂는 행에 저장되지 않으므로 재추정 필요)
- [ ] G2 처리 방식 판정: 기록 유지 + 보고 vs S1V3 class 게이트 재판정
- [ ] H2 tan 부호 역전의 원인 구분에 대한 의견 (선형화 / 추정기 / 표본 변동)

**AMENDMENT-009 설계**
- [ ] class v3.1 (`a9_class.py`, `tests/test_a9_class.py`)이 W1을 완전히 닫는지 확인
- [ ] F2 polish 상시 실행이 Option 1 범위(A8-2)를 넘지 않는지 확인
- [ ] BTAP의 `ROBUST` 규칙과 RFRES 플래그 임계값이 사전 등록으로 타당한지 확인
- [ ] G1–G7 진입 규칙(§7)이 충분한지 확인

**한계와 미실행 사항**
- C3, S1V4, C3V4, BTAP, RFRES CI 결과가 이 요청서에 없습니다. 실행 후 별도로 보고합니다.
- 모든 검증은 SELF_REVIEW_ONLY / TECHNICAL_QA_ONLY입니다. 구현자 자체 시험은 독립 감사를 대체하지 않습니다.
- 합성 결과는 FFD LoS 관측 모델, 알려진 Gaussian 공간장·시간 OU 공분산, 지정된 궤적·앵커 조건 안에서만 유효합니다. 실제 RF 다중경로를 대표하지 않습니다.
- DEV2 n = 10의 파일럿이며, 가설 판정은 결정이 아닙니다.
