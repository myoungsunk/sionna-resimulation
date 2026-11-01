# MBVAR-INFO-001 — S1V5·C3V5 초안 교차 검토 (2026-11-01)

| 항목 | 내용 |
|---|---|
| 대상 | 브랜치 `research/mbvar-info-a010-canonical-smoke-20261101`, HEAD `e16e98dc`. 기준 `7fd49a0` 대비 8개 파일, +1240줄 |
| 검토자 역할 | IMPLEMENTER (A008–A010-P0 구현 세션). S1V5·C3V5는 이 세션이 쓰지 않은 코드입니다. **독립 감사 서명이 아닙니다.** |
| 실행 범위 | 로컬 전용. SMOKE field 900/901만 사용. 계약 lock은 메모리 안에서만 덧붙였습니다. DEV3(20–29), HOLDOUT2, RT의 ID나 입력은 쓰지 않았습니다. 커밋된 lock·결과·코드는 바꾸지 않았습니다. |
| 결론 | **CHANGES_REQUIRED.** 현재 코드로 DEV3를 실행하면 S1V5 첫 shard에서 즉시 중단됩니다(D1). D1을 고쳐도 C3V5가 receipt 로드에서 중단됩니다(D2). A010 동결 전에 고쳐야 할 결함입니다. |

`TECHNICAL_QA_PASS (11/11)` 자체는 로컬에서도 재현됩니다. 다만 이 11개 테스트는 `s1v5.py`·`c3v5.py`를 import하거나 실행하지 않습니다. 문자열 검사, AST 파싱, `py_compile`만 합니다. 그래서 아래 D1·D2는 이 테스트로 잡히지 않습니다.

## 1. 실행 결과 요약

로컬 머신: Intel Xeon 2.10 GHz, 2코어, BLAS 1 thread. 같은 머신에서 S1V5와 C3V5를 모두 실행했습니다. 따라서 runner 간 `SOLVER_REPRO` 증거가 **아닙니다**.

| 단계 | 결과 |
|---|---|
| `pytest tests/test_a10_canonical.py` | 11/11 PASS (CI 결과 재현) |
| 무수정 `s1v5.cmd_run` / `cmd_aggregate` | **NameError `lock_v4`** (D1) |
| S1V5 run, field 900·901 (별칭으로 우회) | field당 198행, 약 42분. FAILED 0, STOP 0 |
| S1V5 aggregate (SMOKE) | 아래 S1V5 aggregate 표 참조 |
| `canonical_setup` | 180-pose ledger SHA 일치, `Lhalf` SHA `b09450fa…` 설치. 이 CPU의 `eigh` factor와 고정 factor의 원소 차이는 최대 1.48e-7, LLᵀ 차이는 4.1e-14. Kp bytes 일치 |
| 무수정 C3V5 run | **`ERR_C3V5_DUPLICATE_INPUT_KEY`** (D2). 900·901 zip이 `MAT|…` 키 52개를 공유하며, 52개 모두 byte 동일 |
| C3V5 run (중복 허용 loader, 축소 subset) | 아래 C3V5 subset 표 참조 |
| C3V5 aggregate | `FAIL`. 원인은 `rows` 하나뿐입니다(10/216). subset 실행이므로 예상된 결과입니다. 나머지 gating 값은 subset 안에서 모두 허용오차 이내였습니다. |

**S1V5 aggregate (SMOKE)**

- QA:
  - `pass=True`, 396/396행, receipt zip 2개
  - `NOT_CERTIFIED` 실패 cell 0, G2 위반 0
  - class v3.1: SMOOTH 150, LOCAL_MIN_CERTIFIED 66
  - primary P PD: 전부
  - polish: 전부 범위 안(최대 1.25 d_ref), cap 0
- A8-5 FAIL 없음, 평가 불가 stratum 0
- A8-6: 관례 간 일치, 그러나 `EXCLUSION_CHANGES_RESULT`. 그래서 power는 계산되지 않았습니다. G4 규칙이 의도대로 동작했습니다.

**C3V5 subset (중복 허용 loader)**

- 범위: field 900 · {LH×LOWCORR, RV×TIME_HIGH_5} · sensor seed 1, 총 10행
- 결과:
  - state 차 ≤ 5.7e-13 d_ref, cost 차 ≤ 2.8e-14
  - full C10 차 ≤ 9.0e-13, `nees4_C10` 차 ≤ 2.1e-16
  - class v3.1 10/10 동일
  - `gap_E` ≤ 4.6e-4 χ², AMBIGUOUS 0
  - PROBE_POWER 10/10
  - ITER_CAP: 미수렴 4행에서 차이 0
  - LINEAR_EXACT, KINK_FIXTURES PASS

해석: D1·D2를 우회하면 S1V5 → receipt → C3V5 → aggregate 경로는 끝까지 동작합니다. 같은 머신에서 receipt를 재생하면 수치가 1e-12 수준으로 재현됩니다. 이것은 **파이프라인 기술 확인**일 뿐입니다. SMOKE 2개 field의 결과는 과학적 의미가 없습니다.

## 2. 결함 (동결 전 수정 필수)

### D1 — `s1v5.py`에서 `lock_v4()` 미정의 → NameError (BLOCKER)

- `s1v5.py`는 `lock_v4`를 `lock_v5`로 이름을 바꿨습니다(51행). 그런데 `cmd_run`(206행)과 `cmd_aggregate`(301행)는 여전히 `lock_v4()`를 호출합니다.
- `s1v5`는 `s1v4`를 import하지 않으므로 이 이름이 없습니다.
- 로컬 재현 결과:

```
UNPATCHED cmd_run -> NameError name 'lock_v4' is not defined
  File ".../code/s1v5.py", line 206, in cmd_run
    lk = lock_v4(); M.check_code_lock(lk)
UNPATCHED cmd_aggregate -> NameError name 'lock_v4' is not defined
```

- 영향:
  - A010을 동결하고 DEV3를 열면 모든 S1V5 shard가 즉시 FAILED로 끝납니다.
  - 그러면 DEV3 RUN_REQUEST와 실행 기록이 결과 없이 소모됩니다.
  - 그 상태에서 코드를 고치면 새 code-hash lock이 필요합니다.
- 수정: 두 호출을 `lock_v5()`로 바꿉니다.
- 회귀 테스트: 테스트가 `s1v5`를 실제로 import하고 `cmd_run`이 `lock_v5`를 호출하는지 확인해야 합니다. 예: `monkeypatch`로 `lock_v5`를 대체하고, 호출되는지 확인합니다.
- 이후 단계는 로컬에서 `T.lock_v4 = T.lock_v5` 별칭을 둔 채 진행했습니다(우회책, 공개).

### D2 — `MAT|role|cell|…` 공분산 키가 shard마다 중복 → C3V5 `ERR_C3V5_DUPLICATE_INPUT_KEY` (BLOCKER)

- S1V5 `cmd_run`은 full `Sig_true`·`Sig_model`을 `MAT|{role}|{cell}|…` 키로 저장합니다. 이 키에는 field가 들어가지 않습니다.
- shard 하나가 zip 하나를 만들고, DEV3는 `n_shards=8`이므로 zip이 8개 생깁니다. 같은 MAT 키가 모든 zip에 들어갑니다.
- C3V5 `load_receipts`는 키가 둘 이상의 zip에 있으면 무조건 `ERR_C3V5_DUPLICATE_INPUT_KEY`로 종료합니다.
- 따라서 shard가 2개 이상이면 C3V5는 계산 전에 항상 중단됩니다.
- 로컬 재현: SMOKE 900·901 zip 2개가 키 52개를 공유합니다. 모두 `MAT|…` 키이며 byte 단위로 같습니다. 무수정 C3V5는 계산 전에 `ERR_C3V5_DUPLICATE_INPUT_KEY`로 종료했습니다.
- 수정안 (택1, 동결 문서에 명시):
  - (a) MAT 키에 field를 넣습니다: `MAT|{f}|{role}|{cell}|…`. 데이터 크기는 늘어납니다.
  - (b) MAT 키만 중복을 허용하되, 모든 사본이 byte 단위로 같을 때만 허용합니다(`np.array_equal` + dtype·shape). 값이 다르면 fail-closed입니다.
- (b)는 "공분산은 field와 무관하게 결정적"이라는 가정을 검사로 바꿉니다. 그래서 수용 가능합니다.

### D3 — C3V5 `INPUT_REPRO` 게이트가 동어반복

- C3V5는 receipt의 `z, x0, ds_m, gy_m`로 `inp`를 덮어씁니다. 그 다음 `input_diffs(rec, kb, inp, …)`로 같은 receipt와 비교합니다.
- 그래서 `d_z = d_ds = d_gy = d_x0 = 0`이 항상 성립합니다. `INPUT_EXACT`는 receipt 키가 있는지만 검사합니다.
- R1(정확 입력 재생) 설계로는 의도된 동작입니다. 그러나 G5 분해의 다른 두 항목이 게이트로 구현되지 않았습니다:
  - `GENERATOR_DISTRIBUTION`(field law): 재생성 입력과의 차이 `generator_regen_d_z_REPORTED`만 보고합니다. 판정 규칙이 없습니다.
  - `FULL_C10_REPRO`의 PSD·condition number: A010 §1 G5에 적혀 있지만 구현되지 않았습니다. C3V5는 10개 원소 차이와 `nees4_C10`만 비교합니다.
- 요청: 동결 문서에서 셋 중 하나를 정합니다.
  - `GENERATOR_DISTRIBUTION`을 법칙 검정으로 게이트화합니다. 예: 재생성 field의 per-pose 분산·상관을 χ² 또는 KS로 검정합니다. `z`의 byte 일치를 요구하지 않습니다.
  - 또는 REPORTED로 명시합니다.
  - 그리고 PSD/cond를 추가하거나 삭제합니다.
- 이름도 `INPUT_REPRO` 대신 `RECEIPT_INTEGRITY`로 바꾸기를 권고합니다. 실제 의미가 그것입니다.

### D4 — `STATE_STABILITY_FIXED`가 게이트에서 REPORTED로 바뀜 (계약 결정 필요)

- C3/C3V4에서 `STATE_STABILITY_FIXED`는 gating이었습니다. 이것이 G5 FAIL의 한 원인(K2 근접 대안해)이었습니다.
- C3V5에서는 `STATE_STABILITY_FIXED_REPORTED`로 이름이 바뀌었고 gating 목록에서 빠졌습니다. `"REPORTED" not in k` 규칙 때문입니다.
- 근접 대안해를 `MODE_AMBIGUITY`로 분리하는 R4의 방향과는 맞습니다. 하지만 제안자 문구("기존 엄격한 재현성 기준도 완화하지 않습니다")와 충돌할 여지가 있습니다.
- AMENDMENT-010 초안 본문에는 이 게이트 강등이 적혀 있지 않습니다.
- 요청: 동결 문서에 다음을 명시합니다.
  - `STATE_STABILITY_FIXED`의 지위(gating 또는 REPORTED)
  - 그 대신 무엇이 gating인지. 예: "AMBIGUOUS가 아닌 행에서는 ≤ 1 d_ref 99% / ≤ 2 d_ref 항상"
- 코드만 바꾸고 계약에 적지 않으면 소급 완화로 보일 수 있습니다.

### D5 — `MODE_AMBIGUITY` 계수가 R4 정의보다 좁음

- R4 정의: truth-free 해 중 **어느 하나라도** Δcost ≤ 1 χ²이고 끝 상태 거리 > 2 d_ref이면 AMBIGUOUS입니다.
- C3V5는 최저 cost 시작점 `best` 하나만 E′와 비교합니다(`gap_E ≤ 1 & E_vs_best_dref > 2`).
- 놓치는 경우: E′가 최저이고, 다른 시작점이 +0.05 χ²에 2.2 d_ref 떨어진 해를 찾았을 때. 이 경우 `best = "E"`이고 거리는 0이므로 AMBIGUOUS로 세지 않습니다. K2와 같은 쌍이 순서만 바뀐 경우입니다.
- 수정: 모든 non-oracle 해 `s`에 대해 `|cost_s − cost_E′| ≤ 1`이고 `dref(E′, s) > 2`인지 검사합니다. 그 수와 최대 거리를 저장합니다.

### D6 — 계약·lock 구조 관련 주의 (동결 시 반영)

- `contract_lock.effective_lock`은 `splits`를 track 단위로 `update`합니다. 그래서 A010 lock에 `{"S_field": {"DEV3": …}}`만 넣으면 기존 `S_field` track 전체(SMOKE, DEV, DEV2, HOLDOUT2 등)가 **대체**됩니다.
  - DEV3 추가는 전체 `S_field` 사전을 다시 적는 방식이어야 합니다. 또는 merge 규칙을 바꿔야 합니다.
  - 현재 lock에는 DEV3 split이 없습니다. 그래서 `cmd_run`의 `lk["splits"]["S_field"]["DEV3"]`는 KeyError가 됩니다.
- `run_phase.request()`의 동결 확인은 문자열 포함 검사입니다(`'"status": "FROZEN"' in text`). 실제 차단은 `lock_v5`와 `check_code_lock`이 합니다. 문서에 이를 명시하면 됩니다(결함은 아님).
- `canonical_setup`은 `A010_KP_BYTE_MATCH`를 계산합니다. 하지만 행, QA, manifest 어디에도 기록하지 않습니다. 진단으로 쓰려면 `QA.json`에 넣어야 합니다.

### D7 — 문서·문구 (경미)

- `c3v5.py` docstring에 C3V4 문구가 남아 있습니다. "regenerate one field's inputs, compare with the S1V3 receipts", "class v3", `input_diffs`의 "S1V3 receipt", aggregate의 `holdout2_note`(AMENDMENT-009, S1V3+C3) 등입니다.
- `NO_WRONG_BASIN` note는 "best of E and 10 fixed starts"입니다. 실제로는 truth를 뺀 9개 시작점(ψ −3…+3 SD 7개, x+1, y+1)과 E′입니다.
- `s1v5.py` docstring과 인수 보고서 §1·§2에 이스케이프된 `\n` 문자가 그대로 들어가 있습니다.
- 인수 보고서 §5의 "9/9"는 최신 CI 11/11과 맞지 않습니다.

## 3. 확인된 양호 사항

- `a10_canonical`:
  - factor 파일 SHA, dtype·shape·finite 검사, LLᵀ ≈ Kp(1e-10 상대) 검사가 fail-closed입니다.
  - canonical zip은 단일 멤버와 정확한 키 집합을 요구합니다. pickle은 금지합니다.
  - estimator 입력과 truth 입력이 분리되어 있습니다.
  - 음성 fixture(1 ULP, 1 byte 손상, 누락 키, 미등록 case)는 모두 검출되었습니다(로컬 11/11).
- `canonical_setup`:
  - 180-pose ledger 순서가 `s1v2.setup`의 key 순서와 같습니다.
  - `pose_ledger_sha256`가 GEN lock과 일치합니다. 일치하지 않으면 `ERR_A010_WORLD_LEDGER_MISMATCH`로 종료합니다.
  - 그 다음 `Lhalf`만 교체합니다. 로컬 CPU에서 새로 계산한 `eigh` factor는 고정 factor와 원소 단위로 최대 1.48e-7 다릅니다. 반면 LLᵀ 차이는 4.1e-14입니다. 즉 고정 factor는 null-space basis의 기계 의존성을 의도대로 제거합니다.
- 주 추정기는 S1V4와 동일합니다. `s1v4.py` 대비 diff는 lock 이름, PREFIX, `canonical_setup`, MAT receipt뿐입니다. deep polish와 고정 시작점 격자는 채택되지 않았습니다. 제안자 결정과 일치합니다.
- C3V5의 `C*`와 `best`는 truth 시작점을 제외하고 고릅니다. truth 시작점은 진단(`truth_gap`)으로만 남습니다.
- `run_phase`:
  - `P2_S1V5`·`P2_C3V5`는 A010 본문 동결, `split=DEV3`, field 정확히 20–29 조건을 모두 만족해야 계획됩니다.
  - 다른 phase는 바뀌지 않았습니다.
  - HOLDOUT2·RT phase는 추가되지 않았습니다.

## 4. 남는 비이식성 (보고 사항)

- S1V5 생성기에서 공간장 factor는 고정됩니다. 그러나 시간 커널 `S["Lt"] = psd_sqrt(k_time)`도 `eigh` 기반이고, `arm_models`의 공분산도 runner에서 계산합니다.
- C3V5는 receipt 재생으로 이 문제를 우회합니다. 그래서 solver 재현성에는 영향이 없습니다.
- 다만 "같은 seed → 같은 z"는 runner 간에 보장되지 않습니다. `generator_regen_d_z_REPORTED`가 0이 아닐 수 있으며, 이것은 예상된 값입니다. D3에서 정할 field-law 기준이 이를 다뤄야 합니다.

## 5. 동결 전 체크리스트 (구현자 권고)

1. D1·D2를 수정하고, `s1v5`·`c3v5`를 실제로 import·실행하는 회귀 테스트를 추가합니다. SMOKE field, 축소된 cell·seed 조합이면 충분합니다.
2. D3·D4·D5를 AMENDMENT-010 본문에서 결정합니다. 게이트 목록, REPORTED 목록, AMBIGUOUS 계수 규칙을 적고, 그대로 코드에 반영합니다.
3. D6의 splits overlay 방식을 정하고 `run_plan["S1V5"]`·`["C3V5"]`를 확정합니다. 그 다음 code-hash lock을 새 SHA로 만듭니다.
4. 수정된 코드로 SMOKE e2e를 CI에서 한 번 실행합니다. S1V5 → C3V5 → aggregate까지이며, 이것은 기술 증거이고 과학 증거가 아닙니다. 그 다음 독립 감사 서명을 받습니다.
5. 그 다음에만 DEV3를 실행합니다. HOLDOUT2·RT는 여전히 NO-GO입니다.

## 6. 보존 사항

- C3 `40992589158` FAIL, C3V4 `41005158792` FAIL, G5 FAIL을 유지합니다.
- S1V3/S1V4 DEV2의 H1 LOW POSE_HIGH tan FAIL과 H2 tan 부호 역전을 유지합니다.
- 이 문서는 어떤 PASS도 소급하여 부여하지 않습니다.
- A010은 DRAFT이고, DEV3·HOLDOUT2·P3는 NO-GO입니다.
- 로컬 실행 산출물은 증거로 커밋하지 않습니다. 로컬 실행 스크립트만 `reviews/a010_crosscheck/`에 둡니다.
