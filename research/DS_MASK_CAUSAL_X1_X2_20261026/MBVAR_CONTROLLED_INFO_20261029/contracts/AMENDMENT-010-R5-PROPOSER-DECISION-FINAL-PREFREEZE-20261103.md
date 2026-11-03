# MBVAR-INFO-001 / A010 — R5 최종 제안자 결정 (PROPOSER DECISION FIXED, PRE-FREEZE)

**결정일:** 2026-11-03. **상태:** `R5_PROPOSER_DECISION_FINAL`, `A010_SCIENCE_DRAFT`, `INDEPENDENT_AUDITOR_SIGNED=false`. 본 결정은 독립 감사 전 과학 동결 또는 DEV3 실행 허가가 아니다.

**원본:** PR #16 @ `ecb6d58199e8fd47d50ba54696b5fbe4b054ee0d`; R1–R4 코드 시험 `6733fb52510e7f4687a8f117f6a01e22b703538e` (42/42, 68/68); K1/K2 2-runner #41562234223 (기술 재현성 범위만).
**승인 주체:** 사용자의 명시적 요청으로 R5의 제안자 설계 결정을 작성. 이는 구현자·감사자의 독립 검산 또는 인적 서명이 아니다.

## R5.1 기본 추정기와 입력 고정 — DECIDED

- **Primary = S1V5 E′**: 기존 `batch_map_v2_ms` + F2 `T.polish`, fixed original z/x0/ds_m/gy_m/taps/Sigma_model/dts, P0/Q, original solver routing and rescue. S1V5의 E′를 진단용 start 중 낮은 cost 해로 교체하거나 고쳐 쓰지 않는다.
- **Truth boundary:** Xtrue·Sigma_true·truth-start는 평가와 표시 전용이다. Nonoracle start, best-start, mode, estimator selection에 사용하지 않는다. ORACLE_CORR_BATCH의 합성 참 공분산은 사전 지정한 synthetic comparator이지 실제 RT 적용 가능한 학습 모델이 아니다.
- 유효한 H1/H2/H3/CAL/H4 본문 표본은 **전부 유지**한다. Ambiguous/fail/capped 행을 유리하게 제외하지 않는다. Science statistics의 독립 표본 단위는 **field**다.

## R5.2 고정 truth-free 진단 start, 최종 목적함수와 종료 정밀도 — DECIDED

- **정확히 9 starts:** `psi−3, psi−2, psi−1, psi0, psi+1, psi+2, psi+3`, `x+1`, `y+1`. Yaw는 initial P0의 표준편차 ±k배, x/y는 각각 prior 1 SD. Nominal initial x0, controls와 process Q는 primary와 동일. No hidden/reselected grid; no truth start in nonoracle set.
- 각 start에 고정된 `FL.batch_map_v2`(기존 `V2_MAX_ITER`), **동일한 F2** `T.polish`(χ² cost descent threshold `POLISH_TOL=1e−3`; 최대 30 steps), 동일 observation objective, original per-row reproducible SHA seed(`DIAG_POLISH|field|role|cell|sensor|arm|start`). **기본 E′도 같은 F2 종료 기준을 따른다.** `E300`은 별도 실패 진단이며 자동 운영 추정기 선택에 사용하지 않는다.
- 단순히 F2를 호출했다는 이유로 모든 해가 같은 최종 정밀도를 달성했다고 주장하지 않는다. **동일 최종 수치 인증 절차**: E′와 9개 후보 모두에서 유한한 final objective·state와 `polish_hit_cap=false`, 그리고 동일한 row-key 기반 `R5_CERT` seed를 사용한 common GN/random probe에서 추가 descent가 χ² `−1e−3`보다 작지 않음을 확인. Probe: old A8 conventions, `GN_ALPHAS=(1,.5,.1,.01)`, random signed directions 8쌍, `rho=0.01`, 동일 P0/Q scaling. Probe 방향을 기준 후보마다 재선정하지 않는다.
- 한 start라도 cap·nonfinite·extra descent가 발견되면 `R5_PRECISION=UNCERTIFIED`, `MODE_IDENTIFIABILITY=UNRESOLVED_PRECISION`으로 보고한다. **최소 비용 또는 non-ambiguous 주장에 해당 start를 조용히 삭제하지 않는다.** R5 precision은 별도 science-scope gate이고 G5 NUMERIC REPLAY 또는 원래 C3 실패를 소급 PASS시키지 않는다.
- 현 DEV2 K2의 5개 근접 start는 **포렌식 관측**이다. 위 인증 결과나 새 규칙의 정당성·임계값을 K2에 맞추어 사후 조정하지 않는다. 인증 미비 시 unique-MAP 주장은 절대 허용하지 않는다.

## R5.3 Ambiguous, 중복 및 식별성 — DECIDED

- 종결점 `s`는 truth-free여야 하며 **`|C_s − C_E′| ≤ 1 χ²` 그리고 `d_ref(x_s,end,x_E′,end) > 2`**일 때 `AMBIGUOUS_START`로 표시한다. `D_ref=(0.02 m, 0.02 m, 0.25 deg, 0.01 deg/s)`이며 psi 차이는 wrap한다.
- **고유 모드 수 clustering을 채택하지 않는다.** 결과에 `n_ambiguous_starts`와 원본 start 이름을 모두 보존하며, 서로 같은 상태에 수렴한 서로 다른 start를 별개의 물리적 해·극소점으로 세지 않는다. 진단 수치 `n_ambiguous_starts=5`는 `n_distinct_minima=5`를 뜻하지 않는다.
- 모든 후보가 정밀도 인증에 통과해도 9-start 검사는 유한 탐색이다. 그 결과는 `GRID_LOCAL_ONLY` 또는 `MIXED`, **global/unique MAP certification은 항상 금지**한다. Ambiguous 행이 존재하거나 precision이 uncertified이면 독립 감사 후 결론 경계/민감도 검토가 필수다.
- 각 arm에 **독립적으로** 기존 전체행과 non-ambiguous 보조집합의 99%≤1 d_ref, 전 행 ≤2 d_ref를 검사한다. Clean 집합의 어느 arm이라도 0행이면 clean gate FAIL; 메인 H/CAL에서 해당 행을 삭제하지 않는다. `STATE_STABILITY_FIXED_LEGACY` 실패도 변경하지 않는다.

## R5.4 사전 등록된 field-paired 민감도·과학적 중요성 — DECIDED

- 각 (field,role,cell,sensor_seed,arm)의 동일 입력에서 운영 E′ 및 **모든** near-cost alternative에 대해 네 상태의 **회전된 제곱오차**(m², m², rad², rad²/s²), 전체 4×4 C10, diag(P), NEES4, logdet(P), Δcost, Δd_ref를 보존한다. 무효(비유한·비SPD) 대안은 `UNCERTIFIED`로 기록, 조용히 제외/정상 취급 금지.
- Field-paired 과학 contrast H1/H2/H3/CAL/H4의 기본 추정·CI는 E′ **전체 유효행**으로 계산한다. 각 field에서 E′↔대안 교체의 **최소–최대 effect envelope**를 산출하고, 재표집은 row/start가 아니라 **field block**, bootstrap B=4000, seed=20261029(기존 S1 측정 계약). 각 field의 반복/arm은 하나의 cluster로 취급하며 start들을 독립 반복으로 세지 않는다.
- 과학적으로 중요한 변화의 **우선 판정(필수)**은 운영 E′ 대비 임의 admissible alternative choice에서 기존 사전 등록 H/CAL 결론의 sign, 95% field-bootstrap CI의 0 포함 여부, 또는 pass/fail/unresolved 판정이 달라지는 경우. 이때 `ALTERNATIVE_CHANGES_CONCLUSION=true`, 과학 release 자동 NO-GO·별도 감사 검토.
- **수치적 경고 임계값(부수 진단):** component normalized squared-error 변화 `|Δe_j²|/D_ref,j² ≥ 1` 또는 `|ΔNEES4| ≥ 0.4`(χ²₄ 기대치 4의 10%) 또는 `|Δlogdet(P)| ≥ ln(1.10)`인 경우 `MATERIAL_NUMERIC_SENSITIVITY=true`; 전체 수치표와 실패 field ID를 보고한다. 이 임계값은 앞선 DEV2 포렌식 관측 이후 사전 지정한 **향후 DEV3 탐색용 기준**이며 DEV2 사례를 confirmatory 검증으로 재해석하지 않는다.
- **통계적 해석:** 모든 admissible 선택에 걸쳐 사전에 고정한 과학적 결론 방향·95% CI verdict가 안정적이어야 단서 포함 제안을 감사자에게 제출할 수 있다. 안정적이라고 해도 R5 코드 단독으로 `SCIENCE_PASS`를 발급하지 않는다. 10개 DEV3 field만으로 power가 낮을 수 있으며 H가 `NOT_SUPPORTED`여도 실패·부정적 결과 자체는 보고 가능하다.

## R5.5 필수 출처·artifact·STOP

- 각 row의 `C_E′`, start별 final cost, best-start, start별 polish steps/cap, common-probe `dmin`, `R5_PRECISION`, d_ref, exact input SHA, full C10, field-paired envelope, NEES4와 적용된 rule version/hash를 MANIFEST로 출력한다. `R5_PRECISION`이 검산되지 않은 과거 SMOKE/DEV2 결과를 새 인증 PASS로 소급 표시하지 않는다.
- `D2 field-qualified Σ`, `D3 RECEIPT_INTEGRITY/GENERATOR_LAW/FULL_C10`, `D4 dual verdict`, `D6 whole S_field`, 등록키·arm gate·비유한값 검사는 변경 없이 보존한다.
- 필수 STOP: 단독 arm FAIL masking, truth leakage, R5 precision 미인증 은폐, 대안해 유리한 선별, 원본 배열 SHA 불일치, 국소 starts를 독립 표본 취급, 기존 FAIL 자동 수정.
- 제안자는 본 R5 설계 선택 **확정**. 그러나 구현 일치 시험, R6 독립 원본 산술 검증, **별도 auditor의 소스·입력·수학 감사 및 proposer+auditor A010-FREEZE 서명 전에는** `AMENDMENT-010.md`를 FROZEN으로 바꾸지 않는다.

## 결정 및 권한

`R5_PROPOSER_DECISION=FINAL`; `R5_IMPLEMENTATION_CERTIFICATION=PENDING_AUDIT`; `A010_SCIENCE_FROZEN=false`; `INDEPENDENT_AUDITOR_SIGNED=false`; `DEV3=NO-GO`; `HOLDOUT2=NO-GO`; `RT=NO-GO`.

**Supersedes** the 2026-11-03 R5 `PROPOSER_DECISION_PENDING` candidate **for prospective scientific decision-making only**; does not mutate/delete the previous draft or historical data.
