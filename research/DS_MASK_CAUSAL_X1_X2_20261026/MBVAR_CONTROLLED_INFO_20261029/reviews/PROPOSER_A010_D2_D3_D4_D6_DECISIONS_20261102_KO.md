# MBVAR-INFO-001 — 새 구현자 교체 전 제안자 결정 (2026-11-02)

**문서 유형:** PROPOSER_DECISION / PRE-FREEZE DRAFT. 본 문서는 AMENDMENT-010의 입력 계약이며, **과거 FAIL을 PASS로 변경하지 않는다.** A010 Science FROZEN 및 독립 감사 서명은 미완료.

**기준:**
- `role=PROPOSER`, `contract_id=MBVAR-INFO-001`
- `base_git_sha=af8e0a1b5299ae5e279f9b602afd2f1bb710c4e3`
- `governance_git_sha=250d617ad89a4105fa1af546cc83ceed9de98f42`
- `experiment_contract_sha256=68d73bd22bf467625559f3092433f250cbe91cb2fef011f92151975975b00f34`
- **검토한 수정 HEAD:** `research/mbvar-info-a010-s1v5-fix-20261101@9e0686602b612cd9f948e8a2f9f8e9098facd434`
- 구현자 기술 CI [41288591968](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41288591968) (13 FAIL / 13 PASS, 수정 전), [41288826577](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41288826577) 및 [41290274463](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41290274463) (26/26 PASS, 축소 SMOKE 900/901). 성공 실행의 주 코드·회귀 테스트 Git blob은 수정 HEAD와 동일함을 확인.
- 이전 C3 [40992589158](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40992589158) FAIL, C3V4 [41005158792](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41005158792) FAIL은 변경 금지.
- A010-P0 GEN 41269011836 / ABL 41269246996, 별도 수치 재계산 [41277884578](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41277884578) 수용 범위는 **기존 DEV2 4개 forensic key의 산술/해시 검증**까지다.
- 기존 S1V3/S1V4 DEV2는 H1 LOW–POSE_HIGH tan FAIL 및 H2 tan DID 부호 역전 (S0 +0.435 대 S1 −0.988), Heading H2 부호 일치. 원인 미확정, 새 코드의 기술적 성공이 이를 해결하지 않는다.

## A. D2 결정 — field-qualified full covariance receipt: **ACCEPT option (a)**

유지할 키:
- `MAT|{field}|{role}|{cell}|Sig_true`
- `MAT|{field}|{role}|{cell}|{arm}|Sig_model`

**이유:** C3V5의 재현성은 한 S1V5 실행이 실제 사용한 원본 `z,x0,ds_m,gy_m,tap,Sigma_true,Sigma_model`에 대한 동일 입력 재실행이다. `exp`, `eigh` 등의 CPU별 1-ULP 차이를 무시하고 Field A에 Field B의 다른 행렬을 임의 대입하면 이 목적을 훼손한다. 각 field의 원본 SHA를 보존한다.

**단, D2(a)는 공분산의 field 간 과학적 동일성을 면제하지 않는다.** 이 조건은 D3 `CROSS_FIELD_COV_EQUIVALENCE` 게이트로 별도 부여한다. 동일 (role,cell,arm)의 서로 다른 field 간 `Sigma`는 표본오차가 없는 설계 행렬이므로 다음을 전부 만족해야 한다.

\[
\delta_{\max}=\frac{\max_{i,j}|\Sigma_f[i,j]-\Sigma_{f_0}[i,j]|}{\max_{i,j}|\Sigma_{f_0}[i,j]|},\quad
\delta_F=\frac{\|\Sigma_f-\Sigma_{f_0}\|_F}{\|\Sigma_{f_0}\|_F}.
]

- **예비 승인 후보**: 두 값 모두 ≤ `1e-10`; 대칭성과 양의 정부호 검사 통과. 실제 SciPy/BLAS 차이보다 넉넉하고 과학적 분산 수준보다 매우 작은 *수치적 동등성* 기준이다. 다른 수치 사용 시 **DEV3 이전에 독립 감사 재승인**.
- 각 집단 `n_fields`, 기준 field, `delta_max`, `delta_F`, 최소 eigenvalue, 실패 키를 남긴다. Field ID를 출력했더라도 관측·평가 데이터는 사용하지 않는다.
- 같은 field+role+cell+arm 키가 중복되거나 dtype·shape가 다르면 실패. 기존 D2(a) loader의 Fail Closed 유지.
- 이 검사는 byte 동일성 게이트가 아니다. 원본 byte의 SHA는 여전히 receipt 일치 판정의 하드 게이트이다.

## B. D3 결정 — 세 가지 서로 다른 검증을 분리: **ACCEPT with implementation changes**

### D3-1 `RECEIPT_INTEGRITY`: 하드 게이트

현재 `INPUT_REPRO`는 receipt로 `inp`를 덮어쓴 뒤 같은 receipt와 비교하므로 계산 경로상 대부분 0이다. 새로운 판정 명칭은 `RECEIPT_INTEGRITY`로 지정한다. 기존 `INPUT_REPRO_LEGACY_REPORTED` 값은 호환/역사 증거로 유지하고 명칭만으로 이전 결과를 재분류하지 않는다.

필수 검사:
1. `S1V5 MANIFEST`의 실행 SHA·source/code SHA 및 **각 input ZIP 자체의 SHA256**, 정확한 field 단위 범위, unique `(field,role,cell,sensor,arm)`.
2. `np.load(..., allow_pickle=False)`, array별 dtype / shape / native byte order / float64 finite check, 선언된 `tap` integer와 범위.
3. C3V5가 실제 optimizer에 전달한 `z,x0,ds_m,gy_m,taps,full Sigma_model`에 대해 **receipt 원본과 dtype+shape+전체 bytes SHA** 비교. `Sig_true`는 oracle scoring/생성기 검사용으로만 분리해 저장하고, 비-oracle 추정기에 truth covariance가 유입되는지 감사.
4. `Xtrue,poses,dts,ds_true,dth_true,pose_keys,prior P0,mu`처럼 scoring/재현성과 관련된 입력은 source frozen hash 또는 별도 `TRUTH_ONLY` receipt로 고정·대조. **C3V5가 현재 실시간 생성한 truth를 사용한 경우 이를 노출하고, 전부 canonical replay했다는 주장 금지.**
5. 빠진 키, 중복 키, 1 bit 반전, 다른 field matrix 주입, 입출력 타입 변경, 이중 업로드, SHA 치환 음성 시험은 모두 fail-closed.
6. **`RECEIPT_INTEGRITY=PASS`의 의미는 저장 bytes를 정확히 사용했다는 것**이다. 생성기가 그 bytes를 통계적으로 올바르게 만들었다는 뜻은 아니다.

### D3-2 `GENERATOR_LAW`: 수학적 불변량 하드 게이트 + 표본 진단

실제 `info_core.obs_covariance`의 정의를 독립 계산한다:
\[
K=\alpha_p K_{pose}+\alpha_t K_{time}+\alpha_w I,quad
\Sigma=\mathrm{diag}(\sigma)\,(K\otimes C_{rs})\,\mathrm{diag}(\sigma).
]

- `Lhalf@Lhalf.T ≈ K_{pose,180}`, canonical ledger/pose 중복 키 재현, `K_{time}` OU 정의, `Sigma_true`의 전체 120×120 행렬·대칭·SPD 확인. 정확한 수치 허용오차는 사전에 명시(예: max-abs 정규화 `1e-10`).
- `GENERATOR_REGEN_DIFF`: 다른 CPU에서 새로 생성한 `z`와 receipt의 byte 차이는 **REPORTED만**. 원본 field는 개별 draw이므로 분포가 맞아도 정확한 bytes는 달라질 수 있다.
- 기존 S1V4의 Mahalanobis·재방문·마진 분산 검사는 독립 field 기준으로 보고; n=10에서 KS/분산 검정의 비유의성을 `정확한 분포 입증`이라고 해석하지 않음.
- `CROSS_FIELD_COV_EQUIVALENCE`를 hard gate로 추가한다 (D2).

### D3-3 `FULL_C10_REPRO`: 공분산을 실제로 검증

- 각 end-state의 4×4 C10 `P` 10개 상삼각 원소 및 `nees4_C10`을 원본 vs replay로 검사. 상태별 자연 척도 (D=\operatorname{diag}(\sqrt{P_{ii}}))를 사용해 0에 가까운 교차항 분모 폭주를 방지.
- `P`의 수치적 대칭·SPD·`\kappa(D_{ref}^{-1} P D_{ref}^{-1})`를 두 실행 모두 기록. 같은 입력의 condition number에 대한 `|Δ log10κ|≤1e-3`을 **DEV3 전 확정할 공학 후보**로 제시한다. 이 기준을 적용하기 전 감사자는 기존 DEV2 forensic 환경의 정량 분포를 참고하되 DEV3에는 접근하지 않는다.
- `SPD 및 condition-number 검증 = numerical stability`이며 `실제 posterior calibration`은 field-level NEES/coverage 별도 과학 검증이다.

## C. D4 결정 — 상태 식별성을 재현성과 혼동하지 않는다: **OPTION ② (dual verdict)**

이전 `STATE_STABILITY_FIXED`를 의도치 않게 `REPORTED`로 강등한 사실은 명시적인 계약 변경 사항으로 남긴다. **과거 A008/A009의 STATE_STABILITY_FIXED FAIL은 그대로**이다.

새 C3V5에서는 두 판정을 분리한다.

1. `G5_NUMERIC_REPLAY` (하드 게이트): `RECEIPT_INTEGRITY`, `GENERATOR_LAW`, `CROSS_FIELD_COV_EQUIVALENCE`, `STATE_COST_REPRO`, `P_REPRO`, `STATUS_REPRO`, `ITER_CAP`, `LINEAR_EXACT`, `KINK_FIXTURES`, 행/키 완전성.
2. `G5_MODE_IDENTIFIABILITY` (과학적 범위 게이트): 기존 **전체 행에 대한 `STATE_STABILITY_FIXED_LEGACY`**를 계속 계산해 과거 비교용 보존. 진단 multi-start의 `MODE_AMBIGUITY`는 truth-free 모든 후보를 검사하고 절대 cost gap ≤1χ² 및 상태 >2 d_ref인 경우 기록한다. Ambiguous가 **아닌 집합**에는 기존 `99%≤1d_ref`, 전 행 `≤2d_ref` 기준을 적용하되, 제거된 행 수와 field/role/cell/arm 커버리지도 보고한다.
3. **주 H1/H2/H3/CAL/H4는 전체 유효 표본 사용**, ambiguous 행을 일괄 삭제하지 않는다. Ambiguous가 존재하면 `MODE_IDENTIFIABILITY=MIXED` 및 `UNIQUE_MAP_CLAIM=DENIED`. 반드시 대안해 대체를 통한 state error·MSE·(P)·NEES·로그 과신 지표의 **field-paired 민감도**를 보고한다.
4. 수치 재현이 PASS라도 근접 대안해가 과학 결론을 의미 있게 바꾸면 `SCIENCE_RELEASE=NO-GO / REVIEW_REQUIRED`. 반대로 사전에 등록한 범위 안에서 결과 방향·효과 크기가 안정적이라면 `ACCEPT_WITH_BOUNDARIES`를 별도 감사자가 결정할 수 있다. 기술 출력만으로 자동 승인하지 않는다.
5. `STATE_STABILITY_FIXED_LEGACY` 자체는 소급 PASS하거나 삭제하지 않고, 새로운 D4 지위 변경은 A010의 **전향적 변경**임을 명시한다.

**중요:** 현 `c3v5.mode_ambiguity(sol)`는 여러 후보를 검사하는 방향으로 맞지만, 기존 실행에서 후보 `FL.batch_map_v2`는 E′와 다른 polishing 정확도일 수 있다. `truth-free` 후보는 동일한 solver·수렴 정밀도로 평가하는 **별도 diagnostic arm**에서 검증하고, 해당 시작점 탐색으로 기본 추정기를 몰래 바꾸지 않는다.

## D. D6 결정 — 기존 effective-lock을 절대 변경하지 않는다: **OPTION ①**

- `contract_lock.py::effective_lock`의 현재 `splits`는 track-level `update`다. 이를 전역 per-key merge로 바꾸면 A004에서 삭제했던 구 `HOLDOUT`이 복구돼 실행 스코프가 바뀔 수 있다.
- **선택:** A010 `AMENDMENT_LOCK`에 **현재 effective `S_field` 전체를 복제**하고, 새 `DEV3: [20,21,...,29]`만 추가한다. `contract_lock.py` 코드는 변경하지 않는다.
- 검사: 기존 A009+A010-P0 effective-lock의 `S_field`의 모든 기존 키·배열이 새 lock과 **동일**해야 함(정확한 canonical JSON SHA 또는 딥 동등성); 유일한 추가 track은 `DEV3`. 금지된 과거 `HOLDOUT` 키 재등장=FAIL.
- `run_plan["S1V5"]["fields"]`와 `run_plan["C3V5"]["fields"]` 모두 DEV3 20–29로 일치; `run_phase.request`에 `AMENDMENT-010 FROZEN` 및 개별 code SHA와 exact field set 점검.
- `HOLDOUT2`, `HOLDOUT2_RESERVE`의 기존 key/values를 그대로 보존; **ID 목록을 출력·열람했더라도 그것만으로 outcome leakage는 아니다**. 실제 `z`, 평가 지표, 참값, 잔차·결과를 생성하거나 본 적 없는 상태를 명시하라.
- DEV3는 **새로운 기술 개발 field**일 뿐 최종 confirmatory holdout이 아니다. HOLDOUT2와 P3는 별도 감사/승인 이전에 실행 금지.

## E. 공통 G1–G7 / 결과 허용 범위

- G1: S1V3/V4와 A010 2-field smoke의 기술 결과는 유지; 과거 H1 LOW/POSE_HIGH tan FAIL 및 H2 tan 역전은 보존.
- G2: `dec_A_fixed`와 `probe_min_dcost`를 **같은 E′ 최종 상태**에서 평가.
- G3: C10 4×4 covariance, eigenvalue/condition, 8 strata와 독립 field-based CAL; UNDETERMINED가 PASS가 되지 않음.
- G4: 동일 키의 P 관례 비교 vs kink/ambiguous 집합 제외로 표본이 바뀌는 분석을 구분. `EXCLUSION_CHANGES_RESULT`이면 예전 power가 출력돼도 HOLDOUT2 승인 금지. A010 변경은 전향적.
- G5: 기술 및 식별성/해석 판정 분리. STOP 시 모든 실패행·로그·manifest 보존. SMOKE subset의 `C3V5_STATUS=FAIL`은 전체 n 기대와의 차이로, 그 결과를 전체 G5 PASS로 기록 금지.
- G6: `HOLDOUT2` unopened. *가설 NOT_SUPPORTED는 유효한 과학 결과*일 수 있음. 기술 PASS를 가설 지지로 바꾸지 말 것.
- G7: 물리 RT는 직접파 복소 parity·first-path 실측 추출·재질/솔버·공통 반사판·예산이 독립 동결돼야 함. 기존 RFRES `FP_SWITCH`는 **동일 pose Full/LoS tap 인덱스 불일치율**이지 시간 tap 전환율이 아니다.
- 새 독립 구현자와 과학 감사자는 다른 역할·세션/runner. 구현자는 자신이 작성한 코드를 `INDEPENDENT_AUDITOR`로 서명 불가.

## F. 변경·실행 승인 경계

**NOW GO:** 이 결정을 구현자가 읽고 `AMENDMENT-010.md`의 새 DRAFT 후속안(과거 파일 덮어쓰기 금지), 단위/전체-SMOKE 검사, 위 G5 판정 분리 구현. Handoff 기준 commit SHA를 pin하고 새 구현 브랜치에서만 변경.

**NO-GO:** 원본 구현 브랜치의 frozen A008/A009, 오래된 FAIL 결과, `RUN_REQUEST.json` 무단 변경, DEV3 field 20–29 실행, HOLDOUT2 생성/개봉, 물리 RT. 모두 동결·독립 감사 후 별도 허용.

**최종 상태:** `D2(a)=ACCEPT`, `D3=REVISE`, `D4=DUAL_VERDICT`, `D6=FULL_S_FIELD_REPLACE`, `A010=SCIENCE_DRAFT`, `NEW_IMPLEMENTER_ASSIGNED_BY_USER_REQUIRED`.
