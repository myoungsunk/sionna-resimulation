# MBVAR-INFO-001 — 신규 구현자 인계 계약 / START HERE (2026-11-02)

**이 문서는 신규 세션·신규 구현자용 단독 작업 요청서다.** 과거 구현자의 대화·가정을 암묵적으로 이어받지 않는다. 현 구현자의 `SELF_REVIEW_ONLY`는 인계 후에도 독립 감사 서명으로 승격되지 않는다.

## 0. 역할·고정 출처·현재 상태

- **Role**: `IMPLEMENTER` (new actor/session), **contract_id**: `MBVAR-INFO-001`. 구현자 스스로 `AUDITOR` 서명 금지.
- **기존 source base**: `af8e0a1b5299ae5e279f9b602afd2f1bb710c4e3`.
- **Governance SHA**: `250d617ad89a4105fa1af546cc83ceed9de98f42`.
- **Frozen original experiment contract SHA256**: `68d73bd22bf467625559f3092433f250cbe91cb2fef011f92151975975b00f34`.
- **실제 수정 소스**: `research/mbvar-info-a010-s1v5-fix-20261101@9e0686602b612cd9f948e8a2f9f8e9098facd434`. 이 commit을 확인하고, handoff branch `handoff/mbvar-info-a010-new-implementer-20261102`에서 **새 개발용 브랜치**를 분기한다. 기준 구현 코드가 다른지 Git blob별로 검증한다.
- **읽기 순서:** 루트 `AGENTS.md` → `docs/research-governance/COMMON_CONTRACT.md` → `ROLE_IMPLEMENTER.md` → `ROLE_PROPOSER.md` → `ROLE_AUDITOR.md`(서명 권한이 아닌 감사 체크리스트) → 본 디렉터리 `contracts/EXPERIMENT_CONTRACT_MBVAR-INFO-001.md`, `AMENDMENT-008.md`, `AMENDMENT-009.md`, `AMENDMENT-010-P0.md`, `AMENDMENT-010.md` → `reviews/PROPOSER_A010_D2_D3_D4_D6_DECISIONS_20261102_KO.md` → 이전 구현자 `reviews/A010_S1V5_C3V5_FIX_HANDOFF_20261101_KO.md` → 구현 및 회귀 테스트.
- **실행상태:** A010 전면 과학 계약은 **DRAFT**. 기존 C3/C3V4 `FAIL`; A010-P0 forensic 기술 재현/수학 검산 PASS. 신규 fix smoke 26/26 PASS, 그러나 **전체 S1V5·C3V5 실행/독립 감사 아직 없음**.
- **금지:** 기존 연구·실패 결과 덮어쓰기, 과거 FROZEN threshold 변경, 참값으로 mode 선택, `RUN_REQUEST.json` 임의 변경, DEV3 20–29 입력 생성/분석/실행, HOLDOUT2 5000–5059 혹은 reserve 5060–5119 사용, 신규 RT. 허용되지 않은 field를 함수에 전달해서는 안 됨. 이 문서만으로 science freeze/실험 실행 권한이 생기지 않는다.

## 1. 왜 새 구현자로 변경하는가 / 무엇을 재사용하는가

이전 구현자의 **D1, D2(a), D5, D6 일부, D7 수정은 유지**한다:
- `s1v5.py`의 `lock_v5` 정정 및 기존 S1V4 MAP/probe/polish 동일성;
- field-qualified `MAT|{f}|{role}|{cell}|...` + 중복/충돌/legacy key fail-closed;
- 모든 non-oracle 대안해 검사(D5);
- `A010_KP_BYTE_MATCH`는 CPU별 `exp` ULP에 민감하므로 REPORTED;
- 기존 regression tests 및 2 field 축소 e2e(26 PASS)를 변경 전 기준선으로 보존.
- **이전 구현자의 `Claude-Session` trailer는 실제 세션을 나타내지 않는다.** 새 세션은 자신이 수행한 commit/workflow SHA만 사용하고, 정확한 세션 URL을 모르면 기록하지 않는다.

이전 CI에서 2field/2cell/1sensor의 `S1V5 44행`, `C3V5 10행` 재생, state 차 ≤ 5.7e-13 d_ref / full-C10 ≤ 6.9e-13. 성공한 26개 테스트가 전체 10-field 과학 QA를 의미하지 않는다. `C3V5_STATUS=FAIL`은 축소 `rows=10/72`에 의한 의도된 차이로 처리하되, 실패를 전체 G5 PASS로 재표기 금지.

## 2. 구현 범위 — 단계별 상세 명령

### NI-0. 인수/추적

1. 새 브랜치·base full 40-hex SHA·source diff·file blob 목록을 README/manifest에 기록.
2. 기존 성공 CI [41288826577](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41288826577), [41290274463](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41290274463)와 실패 CI [41288591968](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41288591968)의 출처·테스트 집합·원본 로그를 검토하고, 먼저 **수정 전 26/26** 재현.
3. 기존 `code/run_phase.py`의 `P2_S1V5/C3V5` 연구 실행 게이트는 science FROZEN 및 지정 DEV3 field가 아니면 fail-closed 상태로 보존한다.

### NI-1. D2(a) 수용 후 field-equivalence 보호 구현

**계약 결정문 A항을 그대로 따른다.** 기존 field-qualified MAT key 유지. `C3V5`에서 `MAT_CROSS_FIELD_REPORTED`에 현재 최대 상대오차뿐 아니라 **두 독립 비교** (`delta_max`, `delta_F`)·검사 field 수·동일 집단 수·matrix SPD·exact schema·충돌 유형을 기록한다.

- 동일 (role,cell,arm)에서 field 간 `delta_max ≤ 1e-10` AND `delta_F ≤ 1e-10`을 **새 `CROSS_FIELD_COV_EQUIVALENCE` 하드 게이트 후보**로 구현한다. 사용 시 숫자를 science contract에 먼저 기록한다.
- `MAT` 원본 각각의 byte SHA는 해당 field의 zip/MANIFEST와 일치해야 한다. 다른 field matrix로 바꾸면 FAIL. Field 간 ULP 차이는 허용되지만 수치적 비교가능성을 초과하는 차이는 FAIL.
- 음성 fixture: field-qualified 키 중복(같은/다른 bytes), 잘못된 field, 전형식 MAT, 1 ULP 변형(원본의 integrity 검사 실패), 유의미한 1e-7 covariance 변형(equivalence FAIL).

### NI-2. D3 — RECEIPT / GENERATOR / SOLVER / FULL-P 분리

**D3-1 `RECEIPT_INTEGRITY`**: `INPUT_REPRO`라는 동어반복 명칭은 새 프로토콜에서 중단하거나 legacy-only로 재명명. ZIP 파일 자체, 내부 arrays 각각의 SHA256(dtype,shape,bytes), full `Sigma_true`·`Sigma_model`·taps·prior 등을 검사. 모든 `C3V5` estimator에 들어가는 값이 저장 receipt와 **byte 단위로 일치**했음을 명시적으로 기록한다.

- `C3V5`가 현재 S1V5 receipt에서 가져오지 않고 생성 코드로 재계산하는 `Xtrue,poses,dts,ds_true,dth_true`는 **TRUTH_ONLY/geometry receipt의 별도 검증 대상**이다. 필요 시 S1V5 새 포맷에 저장·manifest 해시를 추가한다. scoring truth와 estimator 입력을 섞지 않는다.
- `source input model`, `target dataset`, `oracle reference`로 사용되는 Sigma를 명시적으로 분리. XMODEL arm에서도 `Sigma_true`를 oracle 선택에 노출하지 않는다.
- 누락·중복·전치·0행·shape mismatch·dtype/endianness mismatch·SHA 치환을 유발하는 음성 시험 필수.

**D3-2 `GENERATOR_LAW`**: `info_core.k_pose`, `k_time`, `obs_covariance`와 다른 독립 계산 경로에서 `Lhalf@Lhalf.T`·`K_pose`(180×180)·`K_time`·표본의 `Sigma`(120×120)·r/s 상관을 재계산한다. 정해진 수학적 불변량 및 대칭/PSD/동일pose 재사용/OU 시간 계산은 하드 게이트, 실제 10 field 표본의 Mahalanobis 등 stochastic 검사는 통계적 오차범위와 독립 field count를 보고. **새 z vs 원본 z byte 일치 요구 금지**.

**D3-3 `SOLVER_REPRO`**: 같은 frozen receipt를 물리적으로 **서로 다른 두 runner job**에 제공해 state 4D, cost, best-start, class, full C10과 NEES의 원래 엄격 허용오차를 검증. `S1V5`와 `C3V5`를 항상 동일 runner에서 바로 이어 수행한 SMOKE만으로 다중 runner 재현을 선언하지 말 것. 최소 기존 DEV2 K1, K2 forensic key를 사용해 미사용 DEV3를 열지 않은 상태에서 교차-runner e2e 시험 가능.

**D3-4 `FULL_C10_REPRO`**: 10개 상삼각 C10 원소를 자연 state SD로 정규화해 비교; `P` 대칭·SPD·정규화 condition number와 상대 차이를 기록, `NEES4_C10` 재계산. 배치 `P`가 Gaussian 근사라는 한계를 유지하고 최종 field-level calibration과 구분한다.

### NI-3. D4 — 이중 verdict 설계 구현

- 옛 `STATE_STABILITY_FIXED` 결과를 `STATE_STABILITY_FIXED_LEGACY`로 **모든 결과 행에** 재계산/보존. 이전 C3/C3V4의 FAIL은 원본 그대로.
- 신규 `G5_NUMERIC_REPLAY`(입력 재현/solver/covariance hard gates)와 `G5_MODE_IDENTIFIABILITY`(대안해·상태 정보 비유일성)를 반드시 분리한다.
- 모든 truth-free 시작점 s와 E′를 **같은 solver objective와 비교가능한 수렴 정밀도**로 평가. E′보다 cost가 높은 대안해도 `|C_s-C_E′|≤1`, `d_{ref}(x_s,x_E′)>2`이면 ambiguity로 기록. START=truth는 candidate selection에서 영구 제외.
- `MODE_AMBIGUITY` 행의 발생 비율은 전체 1,080 batch row 및 독립 field·role·cell·arm별로 기록. **전체 H1/H2/H3/CAL/H4 분석에서 해당 행을 제거하지 않는다**. 대안해 대체가 주요 로그-정보량·RMSE·NEES·판정에 미치는 영향을 별도 쌍 비교로 보고한다.
- `STATE_STABILITY_FIXED`의 G5 총합 격하를 자동 PASS로 해석하지 않는다. Mode ambiguity가 과학 결론을 바꾸면 `SCIENCE_REVIEW_REQUIRED`, 기술 재현이 PASS라도 독립 연구 승인은 보류한다.
- 우발적인 `REPORTED` 접미사만으로 gating 여부가 변하지 않도록 **명시적 gate-ID allowlist**를 새 계약에 선언. 기존 `gating=[k for k in crit if "REPORTED" not in k]`는 신규 G5에서 제거/퇴역한다.

### NI-4. D6 — split overlay, lock 및 실행 불변성

- 현재 `contract_lock.effective_lock`의 track-level `splits.update()` 보존. 새 `AMENDMENT-010` 계약의 `resolved.splits.S_field` (실제 JSON상 최상위 `splits.S_field`)에는 기존 **전체 S_field** + `DEV3=20..29`만 추가.
- 현재 effective lock과 신규 후보 lock을 비교하는 fail-closed `diff` 테스트 구현: 기존 track의 모든 key/value가 100% 동일; 구 HOLDOUT track이 되살아나지 않음; 새 DEV3 유일 추가; 기존 reserved/historical field를 삭제·변경하지 않음. HOLDOUT 값은 채팅/로그에 불필요하게 출력하지 않고 해시·키 이름만 요약한다.
- `run_plan.S1V5/C3V5.fields`, `RUN_REQUEST`의 `split=DEV3`, 원본 source code SHA; `A010 full AMENDMENT_LOCK` 및 사용자·제안자·독립 auditor 서명 이전에 `ERR_A010_UNFROZEN_NO_DEV3` 또는 그에 동등한 fail-closed.
- **기존 `AMENDMENT-010-P0`와 `AMENDMENT-008/009`의 FROZEN hash는 수정 금지**, `AMENDMENT-010.md` DRAFT를 새 버전/추가 annex로 갱신 후 review. 코드 수정 후 최종 SHA 계산. **절대로 science freeze 이전에 run plan을 실제 DEV3로 전환하지 않는다.**

### NI-5. 사전등록 기술 시험

1. 기존 26 테스트 + 새 음성 fixture/허용오차·분할·gating 테스트.
2. SMOKE 900/901로 실제 `S1V5→C3V5` 축소 e2e. `C3V5_STATUS=FAIL`(rows subset)는 기술 검증에서 expected로 설명하며, science G5 PASS로 보지 않는다.
3. A010-P0 archived K1/K2 2-runner **exact-input** 비교 및 complete C10/NEES 계산. CPU 환경과 BLAS·thread config 기록. 같은 CPU 모델이면 독립 물리 CPU 비교라고 주장 금지.
4. 실험 중 root 계약, 결과 원본, `RUN_REQUEST.json` 변형 여부를 SHA 검사. `py_compile/AST`만으로 완료 주장 금지.
5. 아래 GO/NO-GO 체크리스트로 독립 감사 의뢰. DEV3 입력은 열지 않는다.

## 3. 새 구현자의 산출물 명세

필수 문서/결과:
- `IMPLEMENTER_CHANGE_REPORT.md`: 새 구현자 세션/actor, 변경 파일·diff, 소스 SHA, original preserved, commands, negative fixtures.
- `A010_DRAFT_REVISED_FOR_AUDIT.md`: D2/D3/D4/D6의 수치·추정기·분할·gate-ID 정의, 과거 FAIL/결과 열람 공개. *FROZEN이라고 쓰지 말 것.*
- `A010_CONTRACT_DIFF.json`: 원래 effective lock vs 신규 후보, old S_field keys unchanged, reserved field ID list 미열람 확인, source/contract SHA.
- `A010_RECEIPT_INTEGRITY.json`, `A010_GENERATOR_LAW.json`, `A010_CROSS_FIELD_COV.csv`, `A010_FULL_C10_REPRO.csv`, `A010_MODE_IDENTIFIABILITY.csv` (SMOKE 및 기존 forensic 범위 한정).
- `MANIFEST.json`에 code SHA, governance SHA, input hashes, output hashes, positive/negative tests, float64 dtype/shape, CPU/BLAS.
- `AUDIT_REQUEST_A010_FREEZE_KO.md`: 독립 감사자가 직접 확인할 6항목(입력/수학/분할/대안해/CI/주장 경계).

## 4. 상태별 승인

| 단계 | 현재 | 진입 조건 |
|---|---|---|
| 기존 26/26 smoke | PASS | 새로운 구현자 기준 smoke baseline |
| D2/D3/D4/D6 계약 및 코드 보완 | GO | **새 브랜치 / 과거 결과 불변** |
| A010 새 코드 독립 감사 | PENDING | 전체 코드·데이터·수학·음성 시험 |
| A010 전체 science FROZEN | NO-GO | 독립 감사자의 승인 + proposer 승인 + full code/input/contract SHA |
| DEV3 20–29 S1V5 | NO-GO | A010 FROZEN 후 별도 run authorization |
| C3V5 1,080 row | NO-GO | S1V5 DEV3 receipt SHA 검증 후 |
| HOLDOUT2 / 물리 RT | NO-GO | 후속 G5+과학 감사와 G7 별도 서명 |

## 5. 첫 번째 응답(새 구현자가 제출)

자유 서술 대신 아래 정확한 8개 항목을 보고한다: `BASE_SHA`, `NEW_BRANCH`, `CODE_BLOB_PARITY`, `D2_ACCEPTANCE`, `D3_DESIGN`, `D4_TWO_VERDICTS`, `D6_SPLIT_DIFF`, `TEST_PLAN`.

이 단계에서 과학적 `SUPPORTED`·`HOLDOUT_GO`·`RT_GO`를 주장하면 계약 위반이다. **새 구현자에게 할 일은 실패를 없애는 것이 아니라, 실패의 위치와 의미를 독립적으로 검증할 수 있게 구현하는 것이다.**
