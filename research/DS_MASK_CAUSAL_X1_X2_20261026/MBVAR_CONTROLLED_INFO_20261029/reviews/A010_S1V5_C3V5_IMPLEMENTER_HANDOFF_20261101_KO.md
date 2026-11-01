# MBVAR-INFO-001 — A010 S1V5/C3V5 구현 인수 보고서 (2026-11-01)

**역할:** IMPLEMENTER, `SELF_REVIEW_ONLY`. **최종 상태:** `DRAFT_PRE_FREEZE`, `DEV3_NOT_RUN`, `HOLDOUT2_NOT_RUN`, `RT_NOT_RUN`. 이 문서는 science contract FROZEN, independent auditor sign-off 또는 G5 science PASS가 아니다.

## 1. 기준 SHA / 증거

- 구현 기준: `research/mbvar-info-001-20261029`, HEAD `7fd49a0b03d9560cdb286162308a21c2dac508a5`.
- 새 구현 브랜치: `research/mbvar-info-a010-canonical-smoke-20261101`. 원본 branch와 기존 A008/A009/C3/C3V4 FAIL 기록은 **미수정**.
- `contracts/AMENDMENT-010-P0.md` FROZEN은 기존 DEV2 사례 4개에 한정. `contracts/AMENDMENT-010.md` 과학 계약은 **DRAFT**.
- Forensic GEN `41269011836`, ABL `41269246996` (구현자 SELF_REVIEW_ONLY).
- 별도 숫자 검산: `audit/mbvar-info-a010p0-indep-20261101` GitHub Actions `41277884578`: canonical 48/48, covariance kernel, 88행 NEES4/C10/modes check PASS_NUMERICAL_RECALC_ONLY. **하나의 AI 세션에서 제안/감사를 겸한 기록**이므로 독립 감사 서명과 구별.
- 신규 canonical loader technical CI `41278153584`: 7 tests PASS.
- 신규 S1V5/C3V5 draft compile/AST/negative fixtures CI `41278588582`: **9 tests PASS**.
- 최신 fail-closed phase routing 포함 CI [#41278769173](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41278769173): **11/11 tests PASS**, `DEV3=NOT_RUN` (code SHA `e2ed82620a0237d486d2873c753658f67a97474c`).
- 본 기술 시험은 DEV3/HOLDOUT2/RT의 입력을 읽거나 실행하지 않는다.

## 2. 생성/수정 파일

| GitHub path | 작업 | 공개 계약과 관계 |
|---|---|---|
| `code/a10_canonical.py` | 신규 | `Lhalf.npy` / 4-key canonical zip SHA 검사, estimator-only 입력(oracle/truth 제외), dtype/shape/array SHA, fail-closed |
| `code/s1v5.py` | 신규 DRAFT | S1V4 MAP 및 objective 그대로, canonical fixed 180-pose field, full covariance `MAT|role|cell` receipt, G2/G4/QA 수정 |
| `code/c3v5.py` | 신규 DRAFT | S1V5 원본 input receipts로 재생, generator-only difference 별도 진단, full 4x4 C10 10개 원소 및 NEES 검증, truth-free best start |
| `code/run_phase.py` | 범위 제한 수정 | S1V5·C3V5 예약 단계 추가. A010 본문 FROZEN 및 DEV3 20–29 확인 전에 planning·run 중단 |
| `tests/test_a10_canonical.py` | 신규 | 데이터 무결성·negative fixture·draft code compilation/AST/contract markers |
| `audit/a10_canonical_smoke.py` | 신규 | 기술 전용 기계 판정 JSON (science/DEV3/HOLDOUT2/RT=NOT_RUN) |
| `.github/workflows/mbvar-a010-canonical-smoke-20261101.yml` | 신규 | git SHA detached sparse checkout, py_compile, 11 tests, artifact upload |

역사적 원본 전체 보존. S1V5/C3V5의 source blobs는 새 SHA로 제안자가 승인한 최종 code-hash lock에 반영해야 한다. **동결 전까지 어떤 DEV3 science run도 허용하지 않는다.**

## 3. 정확한 실행 경계

- S1V5 `lock_v5()`는 `AMENDMENT-010`이 `applied_amendment_locks`에 없으면 `ERR_CONTRACT_DRAFT`로 종료한다.
- S1V5의 primary MAP 알고리즘과 fixed ideal-LoS tap은 S1V4과 동일하다. **Deep polish(τ=1e-9) 및 fixed-grid multi-start는 주 추정기에 채택하지 않았다.** 새 DEV3 과학 결과의 비교 대상은 동일한 측정/추정 알고리즘이다.
- Factor `Lhalf`는 완전한 byte SHA로 확인하고, 180-pose ledger byte SHA와 analytic `Kp` 법칙을 확인한다. `Kp` byte SHA는 CPU `np.exp`/ULP 이식성 문제로 참고 진단만 하며, `LLᵀ≈Kp`는 기존 수학 tolerance로 검증한다.
- S1V5는 `z,x0,ds_m,gy_m,taps`, 추가로 **full** `Sig_true`·모든 `Sig_model`을 저장한다. `C3V5`는 그 **원본 byte receipt**를 사용해 추정하고, 독자적으로 생성한 field/관측은 진단값으로만 보고한다.
- C3V5의 `C*`는 `truth` start를 제외한 truth-free starts에서만 고른다. Truth-start는 오직 `ORACLE_ONLY` 비교로 남는다. Mode ambiguity가 발견되면 `MODE_AMBIGUITY_REPORTED`로 기록하고 `science_release_allowed=false`를 유지한다.
- G2 출력: final E′의 `dec_A_fixed` vs final E′ probe; G4: `multi_excl`이 true면 power 계산하지 않음. G5: 모든 열개 C10 상삼각 원소를 자연 state sd 정규화로 비교, NEES4_C10 재현성도 확인한다.
- 새 구현은 원래 A009 `S1V4` 결과, C3/C3V4의 FAIL, H1/H2 불일치를 소급 변경하지 않는다.

## 4. 미검증 및 필수 선행 작업

**아직 검증되지 않은 것:** S1V5와 C3V5 전면적 FFD end-to-end 실행, DEV3 20–29의 10 independent field 통계, C3V5 1080개 실측/solver/covariance 재현성, 새로운 estimator mode 빈도, 분산 일관성 및 HIT/PASS, HOLDOUT2·RT.

**FROZEN 이전 필수:** (현재 신규 source code 및 run-phase의 실제 10-field end-to-end 실행은 미검증. compile/unit-test PASS만으로 과학적 수용 불가)
1. 독립 감사자가 **구현 diff**를 검토: CSV/NPZ original receipt의 모든 key·dtype·full Sigma의 SHA, source/contract SHA, no-truth-start, G2/G4/G5 fail-closed, pose order와 `Lhalf` identical law.
2. `AMENDMENT-010` full contract와 `PLAN_PARAMETERS.json`의 `run_plan["S1V5"]`, `["C3V5"]`, DEV3 field IDs, source code-hash, permissible outcome/ambiguous-label interpretation, latency budget을 명시해 동결. Deep/fixed-grid candidate primary promotion 금지.
3. Freeze 직전 새 수학/음성-fixture 검증을 수행한 후 별도 감사자 서명. Release gate는 NEW branch SHA를 기록.
4. 그 다음에만 DEV3를 생성·실행하고, 코드·threshold 수정 없이 original receipt로 C3V5 독립 재현; 실패 시 무조건 보존/중단.
5. DEV3 통과 이후에도 **HOLDOUT2는 별도 확증 승인**, P3는 물리 RT 배치·LoS/direct parity·tap·예산 별도 승인 필요.

## 5. 수치적·과학적 판정

`TECHNICAL_CODE_SMOKE=PASS (11/11, CI 41278769173)`; `A010_FORENSIC_NUMERICAL_RECALC=PASS`; `S1V5/C3V5_SCIENCE_NOT_RUN`; `FROZEN_A010=NO`; `DEV3=NO-GO until independent audit/freeze`; `HOLDOUT2=NO-GO`; `P3_RT=NO-GO`.

S0V2 정보 이론 결과는 유지. S1V3/V4 DEV2 H1 LOW POSE_HIGH tan과 H2 tan 부호 역전은 여전히 **관측된 NOT_SUPPORTED 연구 결과**이며, canonical input 구현으로 그 결과를 자동 PASS로 바꿀 수 없다.

> 2026-11-01 정정(구현자, `research/mbvar-info-a010-s1v5-fix-20261101`): 이스케이프된 `\n` 문자를 줄바꿈으로 바꾸고 §2·§5의 테스트 수를 11로 고쳤다. 내용은 바꾸지 않았다. 이 11개 테스트는 D1·D2를 잡지 못했다. 후속 수정과 실행 수준 회귀 테스트는 `reviews/A010_S1V5_C3V5_FIX_HANDOFF_20261101_KO.md`에 있다.
