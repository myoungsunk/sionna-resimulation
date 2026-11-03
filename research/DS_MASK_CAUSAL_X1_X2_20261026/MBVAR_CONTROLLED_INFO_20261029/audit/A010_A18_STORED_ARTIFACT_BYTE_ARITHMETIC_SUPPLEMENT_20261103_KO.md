# MBVAR-INFO-001 — A18 PR #20 원본 artifact 직접 바이트·산술 추가 검산

**기준일:** 2026-11-03 / 원본 tested SHA: `360b496d089c54aaaa488ff1c2a571605547d96b`. 독립 재감사 보고서에서 기술 시정은 `ACCEPT_WITH_BOUNDARIES`로 판단되었지만 GitHub PR에 별도 독립 감사자의 공식 리뷰 서명은 현재 없다.

**이 자료의 성격:** 같은 ChatGPT 대화의 후속 계산에서 작성된 저장 증거의 **구현자 helper 비의존 바이트·산술 확인**이다. GitHub 공식 auditor 서명이나 전역 MAP 유일성 증명으로 사용하지 않는다.

## GitHub 원본 ZIP SHA256 — 직접 내려받아 재계산

| Actions | artifact ID | GitHub digest = 직접 계산 |
|---|---:|---|
| [#41607204271](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41607204271) S1→C3 SMOKE | 13218649296 | `4adaf2f513af509045b20f2d3a6fab2e27afc4a70dfd3799af4054e483848fe1` |
| [#41607204028](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41607204028) 62 formulas | 13216779126 | `e32c13d0d753675474337642b398d258f128f7a031344ef199ea153ff328693d` |
| [#41606839019](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41606839019) archived K1·K2 | 13217795952 | `abfb1bdf1b0a539e6a3547ac9eabad252d52a84f32d96fb2241d3c639641307d` |

## 압축 내부 독립 검산

- S1V5 ZIP 900/901 원본 **128+128=256개** array: `dtype.str + shape + 전체 C-order bytes`를 별도 Python SHA256으로 계산해 **256/256 원본 index 및 manifest와 일치**. 원본 per-field ZIP SHA도 일치.
- C3 저장 10개 등록 키 각각: 저장된 `z,x0,ds_m,gy_m,Sigma_model,dts,taps` **7개 실제 원본 배열**을 SHA 묶음으로 재계산하여 **10/10 `OPTIMIZER_BOUNDARY_INPUT_SHA` 일치**.
- C3 원본행 10개에 대해 고정 `R5_CERT|field|role|cell|sensor_seed|arm`의 60-bit seed 독립 재계산 **10/10 일치**; 저장된 **100개 terminal**의 정책 SHA, seed, 정확한 E′+9 starts, 유한 4D 종료 상태, `polish_hit_cap=False`, `dmin ≥ −0.001 χ²` 모두 통과.
- 원본 C3의 **10개 전체 4×4 C10**을 저장 상삼각으로 복원하여 고유값·Cholesky SPD 검사, `Xtrue`와 Anchor A=(2,2)m의 radial/tangential 회전으로 **NEES4 독립 계산 최대 절대 차이 `5.03774799653911e-11`**.
- 최악의 관찰된 `R5_CERT` 추가 하강 `−0.0005481982243651 χ²`. 최소 C10 고유값 `9.78722614679057e−9`. 동일 10행의 S1↔C3 cost/C10 저장 차이는 각각 `0`.
- DEV2 K1/K2 고정 자료: E′+9개 terminal 인증 `PASS`; K1 near starts=0, K2 near starts=5 (서로 다른 5개 극솟값이 아님).
- [원본 62수식 비교 로그](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41607204028) artifact 텍스트의 29/29 pytest 결과 확인.

## 필수 한계 및 게이트

- 현재 S1V5 `44/132`, C3V5 `10/72`(등록 키 62개 미실행): `C3V5_STATUS=FAIL`, `G5_NUMERIC_REPLAY=FAIL`, `R5_FIELD_PAIRED_CONCLUSION=NOT_EVALUATED_INCOMPLETE`, `science_release_allowed=false` 보존.
- **저장된 대안 C10 행은 실제 SMOKE에서 0개**. A18-03 전체 대안 행렬 검증은 합성 fixture에 대한 수치 증거만 있으며, 이번 SMOKE로 실제 대안 행렬에 대한 새로운 경험적 PASS를 주장할 수 없다.
- 기존 구현의 전체 비선형 MAP solver/Jacobian/Hessian을 독립적으로 재구현하지 않았다.
- 본 바이트 검산은 **같은 대화에서 수행한 별도 계산 경로**로, 별도 auditor 세션·실명·공식 PR GitHub 서명을 보증하지 않는다.
- `A010_SCIENCE_DRAFT`, `INDEPENDENT_AUDITOR_SIGNED=false`, `DEV3/HOLDOUT2/reserve/RT=NO-GO` 유지. Draft PR #20은 merge/approved 상태로 승격하지 않음.

## 로컬 재현 검산 원본

- 검산 스크립트: `a18_independent_artifact_rehash.py` (SHA256 `9d420ee86c406c3cc65beb916a72a165ad3a026195c30cb3e104dbe194f4db49`).
- 세부 case-by-case JSON: `A010_A18_INDEPENDENT_SAVED_ARTIFACT_AUDIT_20261103.json` (SHA256 `f48c0b0c3bc6c7505b51da445419f566abe40997cbcde40ff250e703ce092c4b`).
- 재현시 위 세 원본 GitHub Actions ZIP을 해당 이름으로 배치하고 `python a18_independent_artifact_rehash.py` 실행. **실제 raw artifact SHA는 반드시 재검증**.

**결론:** 기존 독립 재감사의 `ACCEPT_WITH_BOUNDARIES` 기술 수용을 뒷받침하는 저장 원본 증거의 바이트 검사 공백을 메웠다. 다만 PR 공식 독립 감사 서명 및 A010 과학 동결이 자동으로 충족되는 것은 아니다.
