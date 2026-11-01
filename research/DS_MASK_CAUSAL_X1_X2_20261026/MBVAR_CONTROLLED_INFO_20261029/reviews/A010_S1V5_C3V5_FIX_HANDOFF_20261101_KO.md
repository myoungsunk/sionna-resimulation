# MBVAR-INFO-001 — A010 S1V5·C3V5 초안 수정 인수 보고서 (2026-11-01)

| 항목 | 내용 |
|---|---|
| 역할 | IMPLEMENTER, `SELF_REVIEW_ONLY`. A010 동결이 아니고 과학 판정도 아닙니다. |
| 기준 | `research/mbvar-info-a010-canonical-smoke-20261101` @ `e16e98dc` (수정하지 않음) |
| 새 브랜치 | `research/mbvar-info-a010-s1v5-fix-20261101` |
| 커밋 | `30becc1` 테스트만 추가(수정 전 RED 기록) → `d8a8bd3` 코드 수정 → `f9eb608` CI 로그 요약 출력 → 이 문서 |
| 근거 보고서 | `reviews/A010_S1V5_C3V5_CROSSCHECK_20261101_KO.md` @ `research/mbvar-info-001-20261029` `1c74bce` |
| 기술 smoke CI | 수정 전 [41288591968](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41288591968) **13 failed / 13 passed**. 수정 후 [41288826577](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41288826577)·[41290274463](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41290274463) **26/26 PASS** (e2e 포함) |
| 최종 상태 | `A010 DRAFT / FIX_IMPLEMENTED / TECHNICAL_QA_PASS / SCIENCE_FREEZE_PENDING`. DEV3·HOLDOUT2·RT는 **NO-GO** |

EXP = `research/DS_MASK_CAUSAL_X1_X2_20261026/MBVAR_CONTROLLED_INFO_20261029`. 아래 경로는 EXP 기준입니다.

## 1. 수정 내역 (D1·D2·D5·D6 일부·D7)

게이트의 gating/REPORTED 지위, 허용오차, 주 추정기는 바꾸지 않았습니다. `TOL`, gating 목록 규칙(`"REPORTED" not in k`), `eval_batch`·`estimate`·`probe`·`polish`는 그대로입니다.

### D1 — `lock_v4` NameError
- `code/s1v5.py` `cmd_run`·`cmd_aggregate`: `lock_v4()` → `lock_v5()`.
- grep 결과(`lock_v4`, `S1V4`, `run_plan["S1V4"]`, `PREFIX`): 실행 경로에 남은 잔존 참조 없음. `PREFIX = "S1V5"`는 정상. docstring의 "inherited from S1V4", "E' (v4)"는 추정기 계보 설명이라 그대로 두었습니다. 파일 끝 주석 "re-exported for c3v4"는 c3v5로 고쳤습니다.

### D2 — `MAT|…` 키 중복 → **(a) 키에 field를 넣음**
- `s1v5.mat_key(field, role, cell, arm=None)`, `s1v5.mat_receipt(...)` 추가. receipt 키:
  - `MAT|{f}|{role}|{cell}|Sig_true`
  - `MAT|{f}|{role}|{cell}|{arm}|Sig_model`
- C3V5 조회 키도 `T.mat_key(field, …)`로 바꿨습니다. 각 field는 자기 S1V5 추정기가 쓴 바로 그 bytes로 재생됩니다.
- `c3v5.load_receipts_with_stats(d)`(fail-closed). `load_receipts(d)`는 같은 함수의 receipt 부분만 돌려줍니다.
  - 어떤 키든 두 zip에 있으면 `ERR_C3V5_DUPLICATE_INPUT_KEY`. MAT 키인데 bytes가 다르면 `ERR_C3V5_MAT_CONFLICT`.
  - field 없는 이전 형식 `MAT|{role}|{cell}|…` → `ERR_C3V5_LEGACY_MAT_KEY`.
  - MAT 키의 field가 그 zip의 non-MAT 키 field 집합에 없으면 → `ERR_C3V5_MAT_FIELD_MISMATCH`.
- `C3V5_STATUS.json`에 기록:
  - `receipt_load`: `n_receipt_files`, `mat_keys`, `mat_duplicate_keys`(성공 시 항상 0), `mat_conflicts`(성공 시 항상 0)
  - `MAT_CROSS_FIELD_REPORTED`: 같은 (role, cell, arm) 행렬이 field 사이에서 byte 동일한지. **REPORTED 전용**, gating 아님.

### D5 — MODE_AMBIGUITY를 R4 정의에 맞춤 (REPORTED 유지)
- `c3v5.mode_ambiguity(sol)`: E′를 제외한 모든 non-oracle 해 s에 대해 `|cost_s − cost_E′| ≤ 1`(`TOL["basin"]`)이고 `dref(E′, s) > 2`(`TOL["stab2"]`)인지 검사합니다. truth 시작점은 제외합니다.
- 행별 저장: `n_alt_ambiguous`, `max_alt_dref_within_1chi2`, `alt_ambiguous_starts`.
- aggregate `MODE_AMBIGUITY_REPORTED`: `n_ambiguous`(행 수), `n_alt_solutions`, `max_alt_dref_within_1chi2`, 비교용 `n_ambiguous_best_start_only_legacy`(이전 규칙), `claim_unique_map_allowed=false`. 키 이름에 `REPORTED`가 있으므로 gating 목록에 들어가지 않습니다.

### D6 일부 — `A010_KP_BYTE_MATCH`
- `cmd_run`이 field마다 QA 행(`check="A010_KP_BYTE_MATCH"`)을 남기고, aggregate가 `S1V5_QA.json["A010_KP_BYTE_MATCH"]`(`n_fields`, `n_match`, `all_match`, `per_field`)로 모읍니다. QA `pass` 규칙에는 넣지 않았습니다(진단 전용).

### D7 — 문구
- `c3v5.py` docstring: "compare with the S1V3 receipts", "class v3", "C2 start grid" 제거. 실제 동작(S1V5 receipt 재생, class v3.1, truth-free 시작점 격자)과 실제 gating 목록을 적었습니다. INPUT_REPRO·STATE_STABILITY의 정의·지위는 D3·D4에서 미결이라고 표시했습니다.
- `input_diffs` docstring: S1V3 → S1V5.
- `NO_WRONG_BASIN` note: "E and 10 fixed starts" → "E′와 truth를 제외한 9개 시작점(ψ −3…+3 SD 7개, x+1 SD, y+1 SD). truth 시작점은 ORACLE_ONLY 진단(`truth_gap`)".
- `holdout2_note`: AMENDMENT-009·S1V3+C3 문구 제거 → "AMENDMENT-010 FROZEN, S1V5+C3V5 독립 감사, 별도 확증 승인 필요".
- `preserved` 목록에 C3 `40992589158` FAIL, C3V4 `41005158792` FAIL, G5 FAIL, S1V3/S1V4 DEV2 H1·H2 결과 추가.
- `s1v5.py` docstring의 이스케이프된 `\n` 제거, receipt 키 형식 설명 추가.
- `reviews/A010_S1V5_C3V5_IMPLEMENTER_HANDOFF_20261101_KO.md`: 이스케이프된 `\n` 3곳을 줄바꿈으로 바꾸고, §2·§5의 "9"를 "11"로 고쳤습니다. 끝에 정정 주석을 달았습니다. §1의 "CI 41278588582: 9 tests"는 그 실행의 실제 수라 그대로 두었습니다.

### 파일별 diff·SHA-256 (`e16e98d` → 이 브랜치)

| 파일 | 작업 | +/− | SHA-256 이전 | SHA-256 이후 |
|---|---|---|---|---|
| `code/s1v5.py` | 수정 | +31/−8 | `f1f3a591a0e5ecd6d7fecc728994675cf3104f1b8fb29b4e1661ec5325262a7a` | `4fc96df3986b80449f67b11dc66ea0b1c815817cd2294cb6ca68e95427e465f3` |
| `code/c3v5.py` | 수정 | +111/−24 | `bafba6d0eb2b8e582ffb19d23f21badadcc07068f49fd9c9f192f78e087024c3` | `853dcea51462397a760a0707507a2f5d1442bdf9490eb40fc633d9e75c255a0e` |
| `tests/test_a10_s1v5_c3v5_exec.py` | 신규 | +318 | — | `9d02cb8d8b4c90b354ca22903e68d670d4ad2fdd3504e4efa1cdf4914169fa41` |
| `tests/a10_e2e_smoke.py` | 신규 (e2e driver) | +111 | — | `c163f37bc5feb2e176a72e8c15300236067f5bb81b57256d0386e4bc110d05dd` |
| `.github/workflows/mbvar-a010-s1v5-fix-smoke-20261101.yml` | 신규 | +112 | — | `3a14c3aa21d36c53cb52e9115d5e980728947c09d3adf3dc541719b4b90798ab` |
| `reviews/A010_S1V5_C3V5_IMPLEMENTER_HANDOFF_20261101_KO.md` | 문구 정정 | +9/−4 | `3275603f63ea6f9c104e147409da69f64b9222ed9f20b9336f4aa5099db60490` | `98a73c15671d57ee25caca8129f6dc5d0a40b210f0c87785198eff6975952d02` |
| `reviews/a010_fix/*.txt` | 신규 (로그 발췌) | | — | — |

`MF.code_hashes()`는 `code/`·`tests/`·`scripts/`·`audit/`의 모든 `*.py`를 포함합니다. 따라서 A010 동결 시 code-hash lock은 이 브랜치의 최종 SHA로 새로 만들어야 합니다. 기준 브랜치에서 이미 `s1v5.py`·`c3v5.py`·`a10_canonical.py`가 추가되어 기존 lock과 맞지 않는 상태였으므로, 새 테스트 파일 추가가 새로 만드는 불일치는 없습니다.

## 2. D2 선택: (a) field 포함 키. 근거

권장안 (b)를 쓰지 않은 이유는 DEV3 실행 환경입니다.

1. DEV3는 `n_shards=8`이고, 각 shard는 서로 다른 GitHub runner에서 돌 수 있습니다. `Sig_true`·`Sig_model`은 `IC.k_pose`·`IC.k_time`(`np.exp`)로 runner에서 계산됩니다.
2. 이번 CI가 직접 보여 줍니다. 같은 코드에서 `A010_KP_BYTE_MATCH`(같은 `exp` 기반 `Kp` bytes)가 로컬 Intel Xeon에서는 `true`(2/2), CI AMD EPYC 7763(41290274463)에서는 `false`(0/2)였습니다. 즉 `exp` 기반 행렬 bytes는 CPU에 따라 실제로 다릅니다.
3. (b)는 "모든 사본 byte 동일"을 요구합니다. 그러면 서로 다른 CPU에서 돈 DEV3 shard 사이에서 ULP 차이만으로 `ERR_C3V5_MAT_CONFLICT`가 날 수 있습니다. DEV3 S1V5 결과를 소모한 뒤 C3V5가 시작도 못 하는 경우입니다. 허용오차를 두는 것은 구현자 권한 밖입니다.
4. (a)는 각 field를 **그 field의 S1V5 추정기가 실제로 쓴 bytes**로 재생합니다. R1(정확 입력 재생)의 의미에 더 가깝습니다. field 사이 일치 여부는 `MAT_CROSS_FIELD_REPORTED`로 남기므로, (b)가 검사하려던 가정("공분산은 field와 무관하게 결정적")의 정보도 잃지 않습니다.
5. 비용: zip 하나에 field가 하나면 크기는 같습니다. shard에 field가 2개면 그 shard의 MAT 부분만 2배입니다(120×120 float64 행렬, 행렬당 약 115 KB).

제안자가 (b)를 원하면 `load_receipts_with_stats`의 MAT 중복 분기와 `mat_key`만 바꾸면 됩니다. 그 경우 cross-runner byte 차이를 어떻게 다룰지(허용오차 또는 같은 CPU 강제)를 함께 정해야 합니다.

## 3. 회귀 테스트 목록

`tests/test_a10_s1v5_c3v5_exec.py`의 15개 + 기존 `tests/test_a10_canonical.py`의 11개 = **26개**. 새 테스트는 `s1v5`·`c3v5`를 실제로 import하고 실행합니다.

| # | 테스트 | 잡는 결함 | 수정 전 (CI 41288591968) | 수정 후 |
|---|---|---|---|---|
| i-1 | `test_s1v5_cmd_run_calls_lock_v5` | D1 (`cmd_run`) | FAIL `NameError lock_v4` | PASS |
| i-2 | `test_s1v5_cmd_aggregate_calls_lock_v5` | D1 (`cmd_aggregate`) | FAIL `NameError lock_v4` | PASS |
| i-3 | `test_c3v5_entry_points_call_lock_v5` | C3V5 lock 경로 회귀 | PASS | PASS |
| i-4 | `test_no_undefined_globals_or_stale_v4_names[s1v5]` | D1 계열: 함수가 참조하는 미정의 global, `lock_v4`·`run_plan["S1V4"]` 등 잔존 이름 | FAIL `undefined globals ['lock_v4']` | PASS |
| i-5 | `…[c3v5]` | 같은 검사, c3v5 | PASS | PASS |
| ii-1 | `test_load_receipts_two_shards_same_matrices_pass` | D2: shard 2개, 같은 행렬 → 로드 성공, 중복 0, 충돌 0 | FAIL (`mat_receipt` 없음) | PASS |
| ii-2 | `test_load_receipts_cross_field_difference_is_reported_not_merged` | D2: field 사이 1 ULP 차이 → 실패하지 않고 field별 보존, REPORTED에 계수 | FAIL | PASS |
| ii-3 | `test_load_receipts_duplicate_mat_key_identical_bytes_fails` | 같은 MAT 키 두 번 → `ERR_C3V5_DUPLICATE_INPUT_KEY` | FAIL | PASS |
| ii-4 | `test_load_receipts_duplicate_mat_key_different_bytes_conflict` | 같은 MAT 키, 다른 bytes → `ERR_C3V5_MAT_CONFLICT` | FAIL | PASS |
| ii-5 | `test_load_receipts_non_mat_duplicate_fails` | MAT가 아닌 키 중복 → `ERR_C3V5_DUPLICATE_INPUT_KEY` | FAIL | PASS |
| ii-6 | `test_load_receipts_legacy_fieldless_mat_key_fails` | 이전 형식 키를 조용히 받아들이지 않음 → `ERR_C3V5_LEGACY_MAT_KEY` | FAIL `DID NOT RAISE` | PASS |
| ii-7 | `test_load_receipts_mat_field_outside_its_shard_fails` | 다른 field의 MAT 키가 섞임 → `ERR_C3V5_MAT_FIELD_MISMATCH` | FAIL | PASS |
| D5-1 | `test_mode_ambiguity_counts_any_truth_free_alternative` | D5 fixture: E′ 최저, 다른 해 +0.05 χ²·2.2 d_ref → AMBIGUOUS 1. 1.5 d_ref, 1.99 d_ref, +1.5 χ²는 제외. truth 제외. 이전 규칙(best=E′)은 이 경우를 놓침을 함께 확인 | FAIL (`mode_ambiguity` 없음) | PASS |
| D5-2 | `test_mode_ambiguity_no_alternative` | 대안 없음 → 0 | FAIL | PASS |
| iii | `test_smoke_reduced_end_to_end` | D1·D2 통합: S1V5 run → aggregate → C3V5 run → aggregate | FAIL (S1V5 run `NameError lock_v4`) | PASS |

과제 지시의 (ii) 세 항목과의 대응 (선택 (a) 기준):
- "같은 MAT 키 → 통과" → ii-1. 키에 field가 들어가므로 같은 (role, cell) 행렬이 shard마다 있어도 중복이 아닙니다.
- "다른 MAT 키 → `ERR_C3V5_MAT_CONFLICT`" → ii-4. 같은 field-qualified 키의 bytes가 다르면 충돌입니다. field가 다르면 충돌이 아니고 ii-2처럼 보고만 합니다.
- "MAT가 아닌 키 중복 → `ERR_C3V5_DUPLICATE_INPUT_KEY`" → ii-5.

### (iii) SMOKE 축소 e2e 설계
- driver `tests/a10_e2e_smoke.py`. 실제 `s1v5.cmd_run`·`cmd_aggregate`·`c3v5.cmd_run`·`cmd_aggregate`를 subprocess로 실행합니다. field별·shard별로 병렬입니다.
- 범위: field 900·901, sensor seed 0. S1V5 cell은 `POSE_HIGH`(고정 `Lhalf` factor 사용)와 `TIME_HIGH_5`(시간 kernel)입니다. C3V5는 (900, LH, POSE_HIGH)과 (901, RV, POSE_HIGH)을 돌립니다. 두 field, 두 group, XMODEL 포함 모든 C3V5 arm이 들어갑니다.
- 메모리 안 lock 확장만 사용합니다(디스크 변경 없음):
  - `applied_amendment_locks += ["AMENDMENT-010"]`
  - `run_plan["S1V5"]`·`["C3V5"]` = SMOKE 900·901. S1V4 plan은 상속하지 않았습니다.
  - `code_sha256 = MF.code_hashes()`. 그래서 실제 `M.check_code_lock`이 생략되지 않고 실행됩니다.
  - `B3.lock_v3`를 이 lock을 돌려주도록 바꿉니다. `lock_v5`의 AMENDMENT-010 검사는 그대로 실행됩니다.
  - `canonical_setup`의 cell 축소, `M.SENSOR_SEEDS=(0,)`, `requested_fields=[900,901]`, `C.SPLIT="SMOKE"`.
- D1·D2 우회 코드는 없습니다. `lock_v4` 별칭이 없고 `load_receipts`를 대체하지 않습니다.
- driver는 900·901 외의 field와 DEV3·HOLDOUT2·reserve 범위를 받으면 `ERR_E2E_FIELD_SCOPE`로 종료합니다. AMENDMENT-010이 디스크에서 이미 적용되어 있으면 실행을 거부합니다.
- 판정:
  - S1V5 QA: `qaj["pass"]`의 각 구성 요소를 개별 확인하고, 행 수는 subset 기대값(독립 계산 `expected_s1_rows()` = 44)과 비교합니다. `qaj["pass"]` 자체는 전체 split 기대값(132)과 비교하므로 `false`가 맞습니다.
  - C3V5: `C3V5_ROWS.csv`에서 `rows`를 뺀 모든 gating 조건을 `C3V5_STATUS.json`에 적힌 `tolerances`로 다시 계산합니다. `C3V5_STATUS.status`는 `rows`(10/72) 때문에 `FAIL`이 맞고, 개별 `pass_`도 모두 `allrows`를 포함하므로 false입니다.
  - 출력 파일 존재: `S1V5_INPUTS_SMOKE_{900,901}.zip`, `MANIFEST.json`(S1V5·C3V5), `C3V5_STATUS.json`.
- 테스트 정책: 입력(REFLECT_ROOT)이 없으면 skip합니다. 기술 smoke workflow는 `MBVAR_A010_REQUIRE_INPUTS=1`이라 입력이 없으면 FAIL입니다. e2e는 `MBVAR_A010_E2E=1`일 때만 돕니다. 그래서 `mbvar-info-contract-check.yml`과 `mbvar-info-run.yml` gate job의 `pytest tests`는 영향을 받지 않습니다(입력 없이 61 passed, 15 skipped; contract check CI 41288826635 success).

## 4. 수정 전 실패 로그 (첨부)

- `reviews/a010_fix/PRE_FIX_CI_41288591968_PYTEST_EXCERPT.txt`: 수정 전 CI(`30becc1`, 테스트만 추가) 발췌. **13 failed, 13 passed in 1.21s**. 핵심 줄:

```
FAILED ...::test_s1v5_cmd_run_calls_lock_v5 - NameError: name 'lock_v4' is not defined
FAILED ...::test_s1v5_cmd_aggregate_calls_lock_v5 - NameError: name 'lock_v4' is not defined
FAILED ...::test_no_undefined_globals_or_stale_v4_names[s1v5] - AssertionError: s1v5: undefined globals ['lock_v4']
FAILED ...::test_load_receipts_legacy_fieldless_mat_key_fails - Failed: DID NOT RAISE <class 'SystemExit'>
FAILED ...::test_smoke_reduced_end_to_end - AssertionError: [... s1v5.py", line 206, in cmd_run
      lk = lock_v4(); M.check_code_lock(lk)
  NameError: name 'lock_v4' is not defined. Did you mean: 'lock_v5'? ...]
======================== 13 failed, 13 passed in 1.21s =========================
```

- `reviews/a010_fix/INTERMEDIATE_D1_ONLY_LOCAL_E2E.txt`: D1만 고친 중간 상태의 로컬 e2e(로컬 2코어, 증거 아님). (iii)이 D1과 별개로 D2를 잡는지 확인했습니다. S1V5 run 성공(field당 22행), C3V5 run → `ERR_C3V5_DUPLICATE_INPUT_KEY`. 두 zip이 `MAT|…` 키 22개를 공유했고, 22개 모두 byte 동일했습니다. 교차 검토 보고서의 D2 재현(52개, 전체 cell)과 같은 양상입니다.

## 5. 기술 smoke CI 결과 (수정 후)

`reviews/a010_fix/POST_FIX_CI_41290274463_EXCERPT.txt` 참조. 41288826577(코드 `d8a8bd3`, AMD EPYC 9V74)도 **26 passed (16:11)**. 41290274463(`f9eb608`, AMD EPYC 7763)은 **26 passed (22:12)**.

| 항목 | 41290274463 (CI) | 로컬 (Intel Xeon 2코어, 참고) |
|---|---|---|
| S1V5 run (2 field 병렬) / C3V5 run (2 shard 병렬) | 582 s / 743 s | 642 s / 893 s |
| S1V5 행 | 44 = subset 기대값 44 (전체 split 기대값 132) | 44 |
| S1V5 QA 구성 요소 | FAILED 0, STOP 0, receipt zip 2, revisit pose 차 0.0, revisit time 최소차 0.2347, primary P PD 전부, polish 범위 안, NOT_CERTIFIED 실패 cell 없음, class v3.1 SMOOTH 18 / LOCAL_MIN_CERTIFIED 14 | 같음 |
| `A010_KP_BYTE_MATCH` | **0/2** (진단) | 2/2 |
| C3V5 receipt_load | zip 2, MAT 키 44, 중복 **0**, 충돌 **0** | 같음 |
| `MAT_CROSS_FIELD_REPORTED` | 22 group, byte 동일 22, 차이 0 | 같음 |
| C3V5 행 | 10 (전체 72) → `status=FAIL`(rows만 원인) | 10 |
| INPUT_REPRO 값 | z·ctl·Sig fp 차 0, INPUT_EXACT 전부 | 같음 |
| STATE_COST_REPRO | state ≤ 5.73e-13 d_ref, cost 차 0, best_k 차 0 | ≤ 5.73e-13 |
| P_REPRO | full C10 ≤ 6.86e-13, NEES4_C10 ≤ 1.9e-16 | ≤ 5.60e-13, 0 |
| STATUS_REPRO | class v3.1 차 0 | 0 |
| NO_WRONG_BASIN | gap_E ≤ 6.9e-4 χ², > 1 χ² 0행 | 같음 |
| ITER_CAP | 미수렴 3행, E300 차 0 | 같음 |
| PROBE_POWER | 10/10 NOT_CERTIFIED, rise 1.13–1.96 | 같음 |
| LINEAR_EXACT / KINK_FIXTURES | PASS / PASS | PASS / PASS |
| MODE_AMBIGUITY (R4) | AMBIGUOUS 0, 1 χ² 안 최대 0.81 d_ref, 이전 규칙 0 | 같음 |

C3V5 receipt 재생은 서로 다른 CPU 두 종류(EPYC 9V74, 7763)에서 각각 같은 runner 안 S1V5 → C3V5로 1e-12 수준 재현됐습니다. **같은 runner 안 재생**이므로 runner 간 `SOLVER_REPRO` 증거가 아닙니다. S1V5 aggregate 로그의 "A8-5 fail True"는 2 field·seed 1개 subset에서 나온 값이고 해석하지 않습니다. SMOKE 결과는 과학적 의미가 없습니다.

## 6. 결정하지 않은 항목: 선택지와 영향 (제안자·감사자 결정)

### D3 — C3V5 G5 분해

| 항목 | 선택지 | 영향 |
|---|---|---|
| `INPUT_REPRO` 이름 | ① `RECEIPT_INTEGRITY`로 개명 | gating 동작 동일. 실제 의미(receipt 키 존재 + 재생값 = receipt)를 이름에 반영. `c3v5.py` SHA 변경, 기존 테스트 문자열은 영향 없음 |
| | ② 그대로 | 코드 변경 없음. 재생 구조상 d_z=d_ds=d_gy=d_x0=0이 항상 성립하므로, 생성기 재현 검사로 오독될 위험이 남음. 동결 문서에 "동어반복적 무결성 검사"라고 명시 필요 |
| `GENERATOR_DISTRIBUTION` (field law) | ① 게이트화: 재생성 z와 receipt z의 per-pose 분산·상관을 χ²(분산) 또는 KS(표준화 잔차)로 검정. byte 일치는 요구하지 않음 | 제안자가 통계량, α, 다중검정 규칙, 대상 arm/cell을 동결 전에 정해야 함. runner 간 ULP 차이에 강함. 계산 비용 작음. DEV3 10 field로 검정력이 제한됨 |
| | ② REPORTED로 명시 | 현재 동작(`generator_regen_d_z_REPORTED`)과 같음. G5의 field-law 항목은 검증되지 않은 채 남고, 문서에 그렇게 적어야 함 |
| `FULL_C10_REPRO`의 PSD·condition number | ① 추가: 두 C10의 최소 고유값 > 0, `|Δ log10 cond| ≤ tol` | tol을 제안자가 정해야 함. 현재 10원소 차(≤ 1e-12 수준)가 이미 작아 결과를 바꿀 가능성은 낮음 |
| | ② 계약에서 삭제 | 코드 변경 없음. A010 §1 G5 문구를 실제 구현(10원소 + NEES4_C10)에 맞춤 |

### D4 — `STATE_STABILITY_FIXED`의 지위

| 선택지 | 영향 |
|---|---|
| ① gating 유지 (C3/C3V4와 같음) | "기존 엄격한 기준을 완화하지 않음" 문구와 일치. K2 같은 근접 대안해가 있으면 다시 FAIL이 예상됨(C3V4 G5 FAIL 원인과 같은 구조). 코드: 키 이름에서 `_REPORTED` 제거 |
| ② non-AMBIGUOUS 행에만 gating (예: ≥ 99% ≤ 1 d_ref, 전부 ≤ 2 d_ref), AMBIGUOUS 행은 REPORTED | D5 수정으로 행별 `n_alt_ambiguous`가 있어 구현 가능. AMBIGUOUS 정의가 게이트 대상을 정하므로 R4 정의와 임계값을 DEV3 전에 동결해야 함. 제외 비율 상한도 정해야 선택 효과를 막을 수 있음 |
| ③ REPORTED (현재 코드) | 상태 안정성이 게이트로 검증되지 않음. AMENDMENT-010 본문에 C3/C3V4 대비 완화라고 명시하지 않으면 소급 완화로 보일 수 있음 (현재 초안에는 이 강등이 적혀 있지 않음) |

### D6 — DEV3 split 추가 방식 (`contract_lock.effective_lock`)

현재 규칙은 `lk["splits"].update(v)`, 즉 track 단위 대체입니다. A010 lock에 `{"S_field": {"DEV3": …}}`만 넣으면 `S_field`의 SMOKE·DEV·DEV2·POST_HOC·HOLDOUT2·HOLDOUT2_RESERVE가 모두 사라집니다.

| 선택지 | 영향 |
|---|---|
| ① A010 lock에 `S_field` 전체를 다시 적음 (기존 track + DEV3) | `contract_lock.py` 변경 없음(SHA `899029d4…` 유지). 과거 amendment 조합의 effective lock 불변. AMENDMENT-004·008도 이 방식이었음(둘 다 `S_field` 전체를 다시 적음). 전사 오류 위험이 있으므로 "DEV3 외 track이 A010-P0 effective lock과 byte 동일"을 확인하는 테스트를 함께 두는 것이 좋음 |
| ② merge 규칙을 track 내부 key 단위로 변경 | `contract_lock.py` SHA 변경 → code-hash lock 갱신 필요. **소급 영향 확인 결과:** 규칙을 일괄 변경하면 현재 RUN_REQUEST의 amendment 조합(A001…A010-P0)의 effective lock이 **달라집니다**. 기본 계약의 `S_field.HOLDOUT` track이 다시 살아납니다(AMENDMENT-004가 track 대체로 의도적으로 없앤 것). 따라서 ②를 택하면 새 규칙을 A010 이후 amendment에만 적용하는 명시적 opt-in(예: lock 안 `"splits_merge": "per_key"`)이 필요하고, 기존 조합의 effective lock이 그대로임을 검증하는 테스트가 필요함 |

현재 lock에는 DEV3 split이 없으므로, 어느 쪽이든 정하기 전에는 `cmd_run`의 `lk["splits"]["S_field"]["DEV3"]`가 KeyError입니다. `run_phase.request()`의 FROZEN 확인은 문자열 포함 검사이고, 실제 차단은 `lock_v5`와 `check_code_lock`이 합니다.

## 7. 금지 사항 준수와 보존 사항

- `RUN_REQUEST.json` 변경 0건. 기술 smoke workflow가 sha256 `9e6b8bd7…`을 검사합니다. 연구 workflow(`mbvar-info-run.yml`) 실행 0건(마지막 실행은 이 작업 전인 41269246996).
- 새 workflow는 `contents: read`이고 RUN_REQUEST로 실행되지 않습니다. 결과를 commit하지 않고 artifact로만 올립니다. 마지막 단계에서 작업 트리가 깨끗한지 검사합니다.
- DEV3(20–29)·HOLDOUT2(5000–5059)·reserve(5060–5119)·RT 입력의 생성·읽기·실행 0건. 공개 사항: 코드 탐색 중 frozen effective lock의 `splits` 사전을 한 번 출력했고, 이때 lock JSON에 적힌 HOLDOUT2·reserve ID 목록의 앞 3개가 콘솔에 나타났습니다. 그 ID로 입력을 만들거나 읽거나 실행한 적은 없습니다. 이후에는 track 이름만 출력했습니다.
- 수정하지 않은 것: 기존 `results/`, FROZEN 계약(AMENDMENT-003…009, 010-P0), `AMENDMENT-010.md`(DRAFT 유지), `s1v3.py`·`s1v4.py`·`c3_verify.py`·`c3v4.py`·`a10_p0.py`, 루트 `AGENTS.md`, 기존 workflow, 기준 브랜치. (`git diff e16e98d HEAD`로 확인)
- 테스트는 추정값 선택에 truth나 oracle을 쓰지 않습니다. D5 fixture의 truth 해는 제외 대상인지 확인하는 용도로만 들어 있습니다.
- 보존:
  - C3 `40992589158` FAIL, C3V4 `41005158792` FAIL, G5 FAIL 유지
  - S1V3/S1V4 DEV2의 H1 LOW POSE_HIGH tan FAIL과 H2 tan 부호 역전 유지
  - 소급 PASS 없음. 이 문서와 CI 결과는 어떤 과학 판정도 바꾸지 않습니다.

## 8. 남는 위험

- **runner 간 비이식성(확인됨):** CI EPYC 7763에서 `A010_KP_BYTE_MATCH=false`. S1V5 생성기의 `Sig`·`Lt`·`arm_models`는 runner마다 ULP 수준으로 다를 수 있습니다. (a)는 C3V5 재생을 보호하지만, DEV3 field마다 S1V5가 서로 다른 bytes의 `Sig`로 추정했을 수 있다는 사실은 남습니다. `MAT_CROSS_FIELD_REPORTED`가 그 크기를 보고합니다.
- e2e는 SMOKE 2 field, cell 2개, seed 1개의 축소판입니다. 전체 cell·seed 조합과 8-shard 경로는 실행하지 않았습니다. 같은 runner 재생이므로 runner 간 solver 재현성 증거가 아닙니다.
- 커밋 trailer의 `Claude-Session` 링크는 요청서에 적힌 값(`session_01X1n7vGdtzXNsGwYex2meNS`)을 그대로 썼습니다. 이 작업 세션의 링크와 다릅니다.
- 독립 감사 서명이 없습니다(`SELF_REVIEW_ONLY`).

## 9. 다음 단계

1. 제안자·감사자가 D2 선택((a) 또는 (b)), D3·D4·D6을 정해 AMENDMENT-010 본문에 적습니다.
2. 그 결정을 코드에 반영하고, 이 브랜치의 최종 SHA로 code-hash lock을 만든 뒤 독립 감사를 받습니다.
3. 동결 후에만 DEV3를 실행합니다. HOLDOUT2·RT는 계속 NO-GO입니다.

**최종 상태:** `A010 DRAFT / FIX_IMPLEMENTED / TECHNICAL_QA_PASS / SCIENCE_FREEZE_PENDING`. DEV3·HOLDOUT2·RT: **NO-GO**.
