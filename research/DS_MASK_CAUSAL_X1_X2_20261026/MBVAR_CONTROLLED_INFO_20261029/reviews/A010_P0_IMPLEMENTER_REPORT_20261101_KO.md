# MBVAR-INFO-001 — A010-P0 forensic 결과 보고 (구현자) · 독립 감사 요청

| 항목 | 값 |
|---|---|
| 작성일 | 2026-11-01 (KST) |
| 역할 | IMPLEMENTER, **SELF_REVIEW_ONLY** |
| 근거 지시 | 제안자 인수 지시서 `PROPOSER_A010_IMPLEMENTER_HANDOFF_DRAFT_20261030_KO.md`, Phase A010-P0 (감사 브랜치 `audit/mbvar-info-c3-a010-proposal-20261030`, `ef0b707c`) |
| 실행 lock | `contracts/AMENDMENT-010-P0.md` (FROZEN, 커밋 `0cb5b5f`). forensic 전용이며 과학 규칙이나 허용오차는 담지 않음. **AMENDMENT-010 본문은 DRAFT** |
| 실행 | GEN `41269011836` (커밋 `a55edb4`) → ABL `41269246996` (커밋 `12b359b`, 4 key × 복제 2, job 8개) |
| 결과 위치 | `results/P2_A010P0_GEN_run_41269011836/`, `results/P2_A010P0_ABL_run_41269246996/` |
| 상태 | G5 FAIL(C3, C3V4) 유지. DEV3 미개봉. HOLDOUT2 **NO-GO**. 물리 RT **NO-GO** |

---

## 1. 결론 요약

1. **입력 byte를 고정하면 추정 결과는 기계 간에 엄격 기준으로 재현됩니다.**
   - CPU 모델 5종에서 같은 canonical 입력을 replay했습니다(Intel Xeon 8573C / 6975P-C, AMD EPYC 9V45 / 9V74 / 7763; 7763은 AVX-512 없음).
   - 결과는 bit 단위로 같거나 최대 cost 6e-13, C10 1.3e-12 차이였습니다. 원래 S1V4 실행 결과와 비교해도 상태 차이는 ≤ 5.7e-13·d_ref입니다.
   - 따라서 C3·C3V4의 재현 실패(문제 1)는 **입력 재생성** 문제였습니다. 추정기 비결정성이 원인이 아닙니다.
2. **공간장 생성 행렬(eigh)은 기계 의존적입니다.**
   - EPYC 7763에서 직접 계산한 `Lhalf`는 동결본과 원소 최대 1.0e-7만큼 다릅니다. 다른 CPU에서는 차이가 0입니다.
   - 원인은 180개 고유값 중 114개가 최대값의 1e-10 미만이라, 거의 퇴화한 고유 부분공간의 고유벡터가 유일하게 정해지지 않는다는 점입니다.
   - 그래서 동결 `Lhalf` 파일(R1)이 필요합니다.
3. **K1 kink 정지점:** 깊은 polish(τ = 1e-6, 1e-9)는 기본 E'보다 cost가 6.7e-4 χ² 낮은 점으로 결정적으로 수렴합니다(상태 이동 0.073·d_ref, C10 tan 변화 −5.6e-4). 이 점은 C3에서 갈라졌던 다른 쪽 점과 같은 위치입니다.
4. **K2 근접 대안 최소점은 실제로 존재하는 식별성 문제입니다.**
   - 서로 떨어진 **평활 국소 최소점 두 개**가 있습니다(둘 다 `CONVERGED_SMOOTH`, Δcost = 0.0511 χ²).
   - E는 높은 쪽을 고릅니다. 깊은 polish로는 바뀌지 않습니다.
   - 사전 정의 규칙상 `AMBIGUOUS_STATE_IDENTIFICATION = true`입니다.
5. **음성 시험 3종을 모두 탐지했습니다:** z의 1 bit 반전, 배열 누락, `Lhalf` 1 ulp 변경.

---

## 2. GEN — 생성 행렬 lock과 canonical 입력 (`41269011836`, PASS)

| 항목 | 값 |
|---|---|
| 생성 runner | AMD EPYC 9V45 96-Core, numpy 2.3.3, scipy-openblas 0.3.30 (DYNAMIC_ARCH, Haswell kernel) |
| `A010_LHALF_WORLDPOSE_V2.npy` | 180×180, `<f8`, little-endian, sha256 `b09450fad48dc9f7c4eea6b59f5fe40995d7544c851ee2ea7daad7a28fc78fca`. git-LFS 대상 아님(실제 byte로 커밋) |
| LLᵀ 검증 | \|LLᵀ − K_psd\|max / \|K\|max = 3.3e-16, \|LLᵀ − K\| = 5.4e-15, diag 오차 5.4e-15 (허용 1e-10). 최소 고유값 −2.2e-15, 최대 31.2, 1e-10·max 미만 고유값 114개 |
| canonical 입력 | `A010_CANONICAL_INPUTS.zip`: 4 key의 z, x0, ds_m, gy_m, taps (S1V4 receipt를 byte 그대로 복사), 그리고 poses, Xtrue, Σ_true, Σ_model 전체 배열. 배열별 sha256은 `A010_INPUT_CANONICAL_SHA.csv` |
| S1V3 vs S1V4 receipt | K2에서 max \|z_S1V3 − z_S1V4\| = 8.9e-15. 같은 생성 코드라도 실행마다 미세하게 다릅니다 |

---

## 3. ABL — 같은 입력에서의 replay (`41269246996`, 8/8 job, MANIFEST PASS)

### 3.1 G5 분리 판정

| key | runner CPU (A / B) | INPUT_EXACT | 기계 eigh `Lhalf` vs 동결본 | FORWARD_FFD 동일 | rep A vs B (E'의 상태·cost·C10 전체) | vs 원래 S1V4 실행 |
|---|---|---|---|---|---|---|
| K1 (10/LOW/TIME_1/s2/ORACLE) | Intel 8573C / AMD 9V74 | PASS / PASS | 0 / 0 | 예 | 0 / 0 / 0 | 5.7e-13·d_ref |
| K2 (11/REV60/TIME_HIGH_5/s0/ORACLE) | AMD 9V74 / AMD 7763 | PASS / PASS | 0 / **1.0e-7** | 아니오 (ULP 수준) | 0 / 6.1e-13 / 1.3e-12 | 2.0e-13·d_ref |
| K3 (10/LOW/LOWCORR/s1/IID) | Intel 8573C / Intel 6975P-C | PASS / PASS | 0 / 0 | 예 | 0 / 0 / 0 | 5.7e-13·d_ref |
| K4 (15/REV60/POSE_HIGH/s1/ORACLE) | AMD 9V45 / AMD 9V45 | PASS / PASS | 0 / 0 | 예 | 0 / 0 / 0 | 0 |

**해석**
- **SOLVER_REPRO:** 같은 입력 byte에서는 A008 엄격 기준(상태 1e-6·d_ref, cost 1e-6, P 1e-3)을 **약 6자릿수 여유**로 만족합니다.
- **kink 행 이식성 기준:** 관찰상 R3의 kink 행 완화 기준은 canonical replay에 필요하지 않습니다.
- **K4:** 두 job이 같은 CPU 모델에서 돌았으므로, K4의 기계 간 비교는 원래 S1V4 실행과의 비교만 해당합니다.

### 3.2 polish 정지 기준 τ sweep (복제 A·B 결과 동일)

| key | τ = 1e-3 (기본, ≤30) 대비 τ = 1e-6 | τ = 1e-9 | 소요 시간 (1e-9) |
|---|---|---|---|
| K1 | 상태 0.0708·d_ref, Δcost −6.72e-4, 5 step | 0.0732·d_ref, −6.72e-4, 10 step, C10 tan −5.6e-4 | 81 s |
| K2 | 변화 없음 (평활 최소점) | 변화 없음 | 7 s |
| K3 | 변화 없음 | 변화 없음 | 8 s |
| K4 | 0.0243·d_ref, −4.38e-4, 6 step (E 대비 0.110·d_ref) | 동일, C10 tan +1.1e-4 | 37 s |

- 모든 polish 경로에서 cost는 단조 감소했고, cap(300 step)에 도달한 경우는 없습니다.
- **해석:** kink 행에서 기본 E'(τ = 1e-3)는 최소점이 아니라 그보다 최대 7e-4 χ² 높은 plateau 위에 멈춰 있습니다. 깊은 polish는 그 아래 점을 결정적으로 찾습니다.
- 깊은 polish를 쓰면 추정값이 0.02–0.07·d_ref 바뀝니다. 따라서 **새 추정기**로 취급해야 합니다(인수 지시서 R2).

### 3.3 섭동 fixture (z + 1e-14·N(0, 1), seed 1–3)

| key | τ = 1e-3 state / cost spread | τ = 1e-9 state / cost spread |
|---|---|---|
| K1 | 2.5e-11·d_ref / 2.8e-11 | 9.4e-8·d_ref / 2.6e-11 |
| K2 | 1.0e-12 / 1.9e-11 | 1.0e-12 / 1.9e-11 |
| K3 | 2.9e-12 / 9.6e-12 | 2.9e-12 / 9.6e-12 |
| K4 | 3.1e-11 / 1.4e-11 | 3.1e-11 / 1.1e-11 |

- 이번 CI runner들에서는 K1 정지점 분기가 생기지 않았습니다.
- 반면 C3(4.4e-15 입력 차)과 로컬 Intel 기계(seed 2)에서는 분기가 생겼습니다. 따라서 이 분기는 **특정 기계·섭동 조합에서만 나타나는 취약한 현상**입니다.
- **결함 기록:** τ = 1e-9 행 요약은 aggregate JSON에서 빠졌습니다. CSV에 기록된 1e-9가 `9.999999999999999e-10`으로 다시 읽혀 float 비교(`==`)가 실패했기 때문입니다. 위 표는 완전한 원본 `A010_DEV2_ABLATION.csv`에서 사후 계산한 값입니다. 동결 코드는 수정하지 않았습니다.

### 3.4 K2 — 근접 대안 최소점 (`A010_MODE_PROFILE.csv`, 복제 A·B 동일)

| 시작점 (깊은 polish 후) | 도달 해 | cost | Δcost vs E' | 거리 (d_ref) |
|---|---|---|---|---|
| psi0 (E 기본), psi−2, y+1 | A (= E') | 121.7815 | 0 | 0 |
| psi−1, psi+1, psi+2, psi−3, x+1 | **B** | 121.7304 | **−0.0511** | **2.21** |
| psi+3 | 잘못된 basin | 3288.1 | +3166 | 101 |
| truth (`ORACLE_ONLY`, 선택 불가) | B | 121.7304 | −0.0511 | 2.21 |

- **A와 B의 차이:**
  - 좌표별 d_ref: x 2.21, y 0.70, ψ 1.25, bg 0.81
  - posterior SD 기준(E'의 C10): rad 0.18, tan 0.51, ψ 0.28, bg 0.14
  - 최대 성분은 x(2.21·d_ref ≈ 4.4 cm)입니다.
- **두 해 사이 cost profile (θ 공간 직선):** 높은 쪽 끝점보다 **0.069 χ² 높은 장벽**이 있고, 단조가 아닙니다. 직선상에서는 두 basin이 분리되어 있습니다. 다만 직선 profile 하나로 분리를 증명할 수는 없습니다.
- **판정:** `AMBIGUOUS_STATE_IDENTIFICATION = true`입니다. 참값을 쓰지 않는 해 18개(시작점 9 × raw/deep) 중 10개(시작점 5개)가 Δcost ≤ 1 χ²이면서 거리 > 2·d_ref 조건에 해당합니다.
- **과학 판정 영향:** 이 1행을 B로 바꾸면 H4_REPRO(REV60 / TIME_HIGH_5 / ORACLE, 30행)의 log inflation이 tan −0.020, ψ −0.006 변합니다. tan 변화는 제안된 |Δlog| ≤ 0.02 기준과 같은 크기입니다.
- DEV2 전체에서 이런 행이 얼마나 자주 나오는지는 **측정하지 않았습니다.** 이번 분석은 4개 key만 대상으로 했습니다.

---

## 4. G7 교정 — tap 지표 분리 (`reviews/A010_G7_TAP_METRICS/`)

| case | 같은 pose의 Full–LoS 불일치 | 시간적 변화 Full | 시간적 변화 LoS | 불일치 지표의 시간 변화 | 불일치 시 Full이 더 이른 비율 |
|---|---|---|---|---|---|
| R2_aA_m0 | 0.379 | 0.228 | 0.195 | 0.314 | 0.16 |
| R2_aB_m0 | 0.292 | 0.240 | 0.190 | 0.317 | 0.31 |
| R2_aA_m45 | 0.535 | 0.226 | 0.192 | 0.245 | 0.06 |
| R4_aA_m0 | 0.457 | 0.269 | 0.136 | 0.239 | 0.15 |
| R4_aB_m0 | 0.383 | 0.281 | 0.131 | 0.251 | 0.17 |
| R5_aA_m0 | 0.352 | 0.240 | 0.204 | 0.257 | 0.20 |
| R5_aB_m0 | 0.306 | 0.233 | 0.198 | 0.277 | 0.27 |

- 기존 RFRES `FP_SWITCH`(29–54 %)는 **같은 pose의 Full–LoS 불일치**입니다. 시간적 전환율이 아닙니다.
- 불일치할 때 index 차이의 중앙값은 1(4배 zero-padding 격자)이고, 대부분 Full이 LoS보다 늦습니다.
- 시간적 tap 변화(0.2 s 간격)는 LoS-only 채널에서도 13–20 %입니다.
- 기존 RFRES 출력은 변경하지 않았습니다.

---

## 5. A010-FREEZE 결정을 위한 구현자 의견 (결정은 제안자·독립 감사자)

1. **C3V5 구조:** canonical 입력 replay를 주 시험으로 두고, A008 엄격 기준을 그대로 유지할 것을 권합니다(근거 §3.1). 생성기 법칙 검사(`GENERATOR_DISTRIBUTION`)는 동결 `Lhalf`를 기준으로 따로 둡니다.
2. **kink 행 이식성 완화 기준(R3):** 이번 증거로는 canonical replay에 필요하지 않습니다. 기하학적 kink 분류기도 아직 정의되지 않았습니다(`KINK_CLASS_UNCERTAIN`). 구현자는 이 기준을 **채택하지 않는 쪽**을 권합니다.
3. **깊은 polish(R2):** 결정적이지만 추정값을 바꿉니다(kink 행 0.02–0.07·d_ref). 따라서 S1V5에 넣는다면 새 추정기로 공시해야 합니다. kink 행(약 33 %)마다 30–80 s가 추가됩니다.
4. **mode 모호성(R4):** 실제로 존재합니다. S1V5에 고정 시작점 격자(진단 후보)를 넣을지, `MODE_AMBIGUITY`를 보고 항목으로만 둘지는 제안자가 결정할 사항입니다. 어느 쪽이든 DEV3에서 발생 빈도와 과학 판정 영향을 함께 집계해야 합니다.
5. **과학 판정과의 분리:** 이번 결과는 H1(LOW POSE_HIGH tan)과 H2 tan의 불일치를 설명하지 않습니다. 감사 판단과 같이, 그 불일치는 수치 문제와 분리된 과학적 결과로 남습니다.

---

## 6. 결함과 한계

- **aggregate 결함:** τ = 1e-9 섭동 요약이 float 비교 때문에 JSON에서 빠졌습니다(§3.3). 원본 CSV는 완전하며, 동결 코드는 수정하지 않았습니다.
- **같은 CPU 모델에서 실행된 복제:** K4는 두 job이 같은 CPU 모델에서 돌았습니다. 기계 간 비교는 원래 S1V4 실행과의 비교만 해당합니다.
- **표본 크기:** 이번 분석은 4개 key의 forensic입니다. DEV2 전체 빈도와 통계적 결론은 없습니다.
- **자체 검증만 수행:** 모든 검증은 구현자 자체 검증입니다. 인수 지시서 요구대로, 독립 감사자가 **별도 실행**으로 원본 입력·코드·수학을 확인해야 합니다.

## 7. 독립 감사 요청 항목

- [ ] `A010_LHALF_WORLDPOSE_V2.npy` hash와 LLᵀ·Kp 검증 재현
- [ ] canonical 입력 hash(`A010_INPUT_CANONICAL_SHA.csv`)와 S1V4 receipt의 byte 일치 확인
- [ ] 별도 환경에서 같은 canonical 입력으로 K1–K4 E' replay (SOLVER_REPRO 재현)
- [ ] K2 두 mode의 cost와 상태, 장벽 재계산, 그리고 식별성 판정
- [ ] §5 의견에 대한 판단과 AMENDMENT-010 동결 여부. 동결 후에만 DEV3(20–29) 개방
