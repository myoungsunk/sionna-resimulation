# MBVAR-INFO-001 — C3 실패 분석과 AMENDMENT-010 선택지 (제안자·감사자 결정 요청)

| 항목 | 값 |
|---|---|
| 작성일 | 2026-10-30 (KST) |
| 작성 역할 | IMPLEMENTER. **SELF_REVIEW_ONLY** |
| 대상 실행 | C3 `40992589158` (S1V3 DEV2 run `40981032471`의 재현 검증, AMENDMENT-008 코드, A009 lock) |
| 판정 | **C3 = FAIL** (동결 규칙 기준). 이 판정은 **보존**하며 재분류하지 않습니다. |
| 요청 | AMENDMENT-010의 방향을 제안자·감사자가 결정해 주십시오. 구현자는 결정 전에는 코드·규칙을 바꾸지 않습니다. |
| 현재 상태 | HOLDOUT2 **NO-GO**, 물리 RT **NO-GO**. C3V4 `41005158792` 대기 중, BTAP `40992660047` 실행 중 |
| 진단 자료 | `reviews/c3_diag/` (스크립트와 로컬 출력) |

---

## 1. 결과 요약

C3는 11개 게이트 중 4개에서 실패했습니다.

| 게이트 | 결과 | 관측 최대값 | 허용오차 |
|---|---|---|---|
| INPUT_REPRO | **FAIL** | z 차 1.0e-8 (제어 4.4e-16, Σ fingerprint 1.9e-14) | z ≤ 1e-9 |
| STATE_COST_REPRO | **FAIL** | 상태 0.076·d_ref, cost 6.7e-4 χ² | 1e-6·d_ref, 1e-6 χ² |
| P_REPRO | **FAIL** | C10 대각 상대차 2.5e-3 | 1e-3 |
| STATE_STABILITY_FIXED | **FAIL** | ORACLE 1행 2.21·d_ref | 전 행 ≤ 2·d_ref |
| STATUS_REPRO, NO_WRONG_BASIN, ITER_CAP, PROBE_POWER, LINEAR_EXACT, KINK_FIXTURES, rows | PASS | — | — |

**재현 실패 81/1080행**의 정의: 상태 > 1e-6·d_ref, cost > 1e-6, C10 P > 1e-3, 또는 class 불일치 중 하나 이상.

---

## 2. 실패를 입력 차이 크기별로 나눈 결과

출처: `reviews/c3_diag/c3_rows_breakdown_output.txt`

| 재생성 입력 차 d_z | 행 수 | 재현 실패 | 최대 상태 차 | 최대 cost 차 | 최대 C10 P 차 |
|---|---|---|---|---|---|
| 0 (완전 동일) | 468 | **0** | 5.7e-13·d_ref | 2.8e-14 | 9.3e-13 |
| 0 < d_z ≤ 1e-12 | 372 | **1** | **0.0764·d_ref** | 6.7e-4 | 2.5e-3 |
| d_z ≥ 1e-9 | 240 | **80** | 1.65e-6·d_ref | 6.3e-6 | 3.3e-8 |

- **추정 경로 자체의 비결정성 없음:** 입력이 완전히 같은 468행은 전부 재현됐습니다. 같은 입력에 대해 추정은 결정적입니다.
- **d_z ≥ 1e-9인 240행:** 모두 공간장 cell입니다. 실패 80행은 모두 허용오차를 조금 넘는 수준입니다.
  - 해당 cell: POSE_HIGH, POSE_HIGH_C03 (LOW/HIGH/REV60/FWD60).
- **큰 이탈 1행:** 반올림 수준의 입력 차이(4.4e-15)에서 생겼습니다.

---

## 3. 원인

### 문제 1 — 입력 생성기의 기계 간 비결정성 (INPUT_REPRO, 80행)

- **원인:** 공간장의 제곱근 `Lhalf`는 180×180 world-pose kernel의 eigh(`info_core.psd_sqrt`)로 만듭니다. 이 kernel은 거의 특이합니다(최소 고유값 −1.5e-14, 최대 31.2).
  - 작은 고유값 부분공간의 고유벡터는 CPU·BLAS kernel(OpenBLAS `DYNAMIC_ARCH`)에 따라 달라질 수 있습니다.
  - 그 결과 기계마다 z가 1e-9 – 1e-8 수준에서 달라집니다.
- **세 번째 기계 확인:** 이 작업 환경(Intel Xeon 2.10 GHz, OpenBLAS Haswell kernel)에서 S1V3 receipt와 비교했습니다. 출처: `reviews/c3_diag/regen_vs_receipt_output_local.txt`

  | cell | 공간장 | max \|z_local − z_receipt\| |
  |---|---|---|
  | LOWCORR | 없음 | 0 |
  | TIME_5 | 없음 (시간 OU만) | 8.9e-16 |
  | POSE_HIGH | 있음 | 4.5e-9 – 8.5e-9 |

- **영향:** 상태·cost·P 차이는 1e-6 규모에 그칩니다. 결론에는 영향이 없지만, 동결 허용오차 기준으로는 FAIL입니다.

### 문제 2 — kink에서 LM 정지점의 분기 (STATE_COST_REPRO, P_REPRO, 1행)

- **해당 행:** field 10, LOW, TIME_1, sensor 2, ORACLE_CORR_BATCH. 입력 차는 4.4e-15입니다.
- **무슨 일이 있었나:** 두 기계 모두 LM이 kink 위에서 `NONCONVERGED_LAMBDA`로 멈췄습니다. 그런데 1.5 mm(0.076·d_ref) 떨어진 서로 다른 점에서 멈췄고, cost 차는 6.7e-4 χ²입니다.
  - 두 점 모두 probe 하강이 polish 기준(1e-3 χ²)보다 작았습니다. 그래서 polish가 돌지 않았고 `LOCAL_MIN_CERTIFIED`로 분류됐습니다.
- **로컬 재현 시험:** 이 행의 입력에 1e-14 섭동을 3번 넣었습니다. 출처: `reviews/c3_diag/deep_polish_output_local.txt`

  | polish 정지 기준 | E' 상태 spread | E' cost spread | 행당 추가 시간 |
  |---|---|---|---|
  | 1e-3 χ² (현행) | **0.0764·d_ref** | 6.7e-4 | 0 |
  | 1e-9 χ² (최대 300 step) | 0.00187·d_ref | 6.5e-7 | 약 75 s |

- **해석:**
  - 섭동 1개에서 정지점 분기가 재현됐습니다.
  - 깊은 polish로 cost는 1e-6 아래로 수렴합니다. 그러나 상태는 약 37 µm(1.9e-3·d_ref)에서 멈춥니다. kink 근방의 평평한 방향 때문입니다.
- **설계상 불일치 (구현자 책임):** A008의 STATE_COST_REPRO(1e-6·d_ref = 위치 20 nm)는 기계 간 입력이 bit 단위로 같다는 전제를 둡니다. 하지만 kink 행에서 추정기는 최소점을 1e-3 χ² 정밀도로만 확정합니다. 이 두 조건은 서로 맞지 않습니다.

### 문제 3 — 근접 대안 최소점 (STATE_STABILITY_FIXED, 1행)

- **해당 행:** field 11, REV60, TIME_HIGH_5, sensor 0, ORACLE_CORR_BATCH.
- **내용:** 시작점 격자(psi+2)가 E'보다 0.051 χ² 낮은 점을 2.21·d_ref(4.4 cm) 떨어진 곳에서 찾았습니다.
  - NO_WRONG_BASIN 기준(1 χ²)은 통과했지만 안정성 기준(2·d_ref)은 넘었습니다.
- **해석:** 재현성 문제가 아닙니다. 평평하거나 다봉인 posterior에서 E(multi-start는 misfit 때만 작동)가 격자보다 덜 좋은 점을 고른 경우입니다.
- **참고:** S1V3 G2의 XMODEL 4행(평활 수렴인데 큰 FD step에서 하강이 남음)도 같은 계열의 현상으로 보입니다. 다만 직접 연결하지는 않았습니다.

### 참고 — 이전 C2의 P 차이 (가설, 미검증)

- C2 `40871327417`의 C2-a 실패(20행, P ≤ 1.19 % 차이)도 같은 생성기로 서로 다른 기계에서 입력을 재생성한 결과입니다.
- 그래서 문제 1·2와 같은 원인일 가능성이 있습니다. 다만 당시에는 입력 receipt가 없어 이 가능성을 검증할 수 없습니다.

---

## 4. AMENDMENT-010 선택지

**공통 원칙 (세 안 모두 적용)**
- 기존 C3 `40992589158`의 FAIL은 보존합니다. 진행 중인 C3V4 `41005158792`의 결과도 그대로 판정합니다(같은 원인으로 FAIL이 예상됨).
- 새 규칙은 **결과를 보기 전에** 동결합니다. 새 field로 S1V5와 C3V5를 실행합니다(제안: DEV3 = 20–29, 미사용 ID).
- DEV2(10–19)는 이미 세 번 사용했으므로 재사용하지 않습니다.
- HOLDOUT2와 물리 RT는 결과와 관계없이 독립 재감사 전까지 NO-GO입니다.

### 선택지 1 — 입력 고정 + 깊은 polish + 2단계 허용오차 (구현자 권장)

| 항목 | 내용 |
|---|---|
| R1 입력 | `Lhalf`를 한 번 계산해 hash 고정 입력 파일로 저장합니다(`.npy` 등, LFS 대상 아님). 생성기는 이 파일을 읽습니다. INPUT_REPRO 1e-9는 유지합니다. |
| R2 추정기 | polish 정지 기준을 1e-3에서 1e-9 χ²로 낮춥니다(최대 300 step). A8-2 범위(2·d_ref, 1 χ²)는 유지합니다. |
| R3 허용오차 (사전 등록) | **평활 행** (양쪽 모두 CONVERGED_SMOOTH): 상태 1e-6·d_ref, cost 1e-6, P 1e-3을 그대로 둡니다. **kink 행** (LOCAL_MIN_CERTIFIED): 상태 ≤ 1e-2·d_ref, cost ≤ 1e-5 χ², P ≤ 1e-2로 둡니다. |
| 근거 | 결론은 d_ref 규모의 오차와 ±log 1.5 대역으로 판정합니다. 1e-2·d_ref와 1e-2 P 차이는 이 판정 척도보다 100배 이상 작습니다. |
| 위험 | 실패 후에 허용오차를 바꾸는 것이므로, 사전 등록과 새 field 사용이 필수입니다. kink 행 허용오차 값은 이 1행의 시험(1.9e-3·d_ref, 6.5e-7)을 참고해 정한 것이므로, 감사자의 독립 판단이 필요합니다. |
| 비용 | kink 행(약 35 %)마다 약 75 s가 추가됩니다. S1V5 shard당 약 +45분으로 추정합니다(미측정). |

### 선택지 2 — 완전 결정성 시도

| 항목 | 내용 |
|---|---|
| R1 + R2 | 선택지 1과 같습니다. |
| 환경 | CPU kernel을 고정합니다: `OPENBLAS_CORETYPE` 고정, `NPY_DISABLE_CPU_FEATURES`로 AVX-512 dispatch를 끕니다. 허용오차는 1e-6 그대로 둡니다. |
| 장점 | 기존 허용오차를 바꾸지 않습니다. |
| 위험 | GitHub runner CPU가 달라지면 다시 실패할 수 있습니다. 사전에 검증하기 어렵습니다. 또 bit 결정성이 확보돼도 kink 분기 민감성 자체는 남습니다. 서로 다른 환경(감사자 독립 재현 포함)에서는 재현되지 않습니다. |

### 선택지 3 — 입력 고정만

| 항목 | 내용 |
|---|---|
| R1 | 선택지 1과 같습니다. |
| 나머지 | 추정기와 허용오차를 그대로 둡니다. |
| 예상 | 80행 계열(문제 1)은 해결됩니다. 하지만 문제 2의 분기 행은 남아 FAIL할 가능성이 높습니다. 이 1행은 1e-15 입력 차이로도 재현됐습니다. |

### 세 선택지 모두와 별도로 결정이 필요한 사항

- **문제 3 (근접 대안 최소점):** 현재 E는 cost가 misfit 기준을 넘을 때만 multi-start를 합니다. 선택지는 두 가지입니다.
  - (a) 현 규칙(2·d_ref)을 그대로 두고 FAIL로 기록
  - (b) E에 상시 multi-start를 넣기. 이는 추정기 변경이므로 Option 1 범위를 넘는지 판정이 필요합니다.
- **A009 감사 지적 반영 여부 (`6998e402`):** A010을 만든다면 다음 수정을 함께 넣을지 결정이 필요합니다.
  - G2 카운터 수정 (`dec_A_fixed` 사용)
  - G4: `multi_excl`일 때 power 출력 중단, 분석별 잔여 행·field 수 출력
  - G5: C10 10개 원소와 `nees4_C10` 재현 대조
  - 현재 이 세 항목은 `reviews/posthoc_a009_gate_calc.py`로 사후 계산 중입니다.

---

## 5. 현재까지의 관련 결과 (참고)

| 항목 | 결과 | 출처 |
|---|---|---|
| S1V4 DEV2 `40992623257` | QA PASS (1980/1980). E' 상태 기준 G2 = 0행. A8-5 FAIL 없음, `nees4_C10` LH 4.25 / RV 4.53 PASS. 파일럿 `NOT_SUPPORTED` (H1 LOW POSE_HIGH tan FAIL, H2 tan FAIL) | `results/P2_S1V4_run_40992623257/`, `reviews/posthoc_a009/` |
| G4 (감사 지적 2) | 실제 발생: `EXCLUSION_CHANGES_RESULT`인데도 power n = 60이 출력됨. kink 제외 시 1080 → 723행, 최소 독립 field 5 | `reviews/posthoc_a009/POSTHOC_A009_GATES.json` |
| S1V4 receipt 게시 누락 | publish 패턴이 `S1V3_INPUTS_*.zip`만 포함. workflow 수정(`f934a8f`). C3V4 실행 시 artifact에서 MANIFEST sha256로 검증해 복구 | `.github/scripts/mbvar_recover_receipts.py` |
| C3V4 무효 실행 `41005072382` | 구현자 순서 실수로 receipt 복구 단계 없이 시작됨. GitHub에서 취소됨(cancelled). 유효 실행은 `41005158792` | 커밋 `b2088b4` 메시지 |
| 옵션 C RFRES `40992695655` | 7개 case 모두 BIAS / SCALE (e_mp s sd = σ_s의 4.5–11배) / NON_GAUSSIAN / FP_SWITCH (29–54 %) / CORR_MISMATCH. 탐색적, 게이트 아님 | `results/P2_RFRES_run_40992695655/` |

---

## 6. 결정 요청

1. AMENDMENT-010을 선택지 1·2·3 중 어느 방향으로 할지 (또는 다른 안)
2. 문제 3 처리: (a) FAIL 기록 유지 / (b) 상시 multi-start
3. A009 감사 지적(G2·G4·G5) 수정을 A010에 포함할지
4. 새 field DEV3 = 20–29 사용 승인
5. 진행 중인 C3V4 `41005158792`를 계속 둘지. 같은 원인으로 FAIL이 예상되지만, 감사 권고에 따라 기술 재현 근거로 남기는 것을 구현자는 권장합니다.

결정 전까지 구현자는 코드·규칙을 변경하지 않습니다. 진행 중인 CI는 계속 관찰하고 결과를 보고합니다.
