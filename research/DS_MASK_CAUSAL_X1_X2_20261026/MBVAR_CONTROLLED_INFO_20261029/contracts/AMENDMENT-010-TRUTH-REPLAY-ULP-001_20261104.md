# AMENDMENT-010-TRUTH-REPLAY-ULP-001 — USER_AUTHORIZED_NONINDEPENDENT post-DEV3 exploratory correction

**작성일:** 2026-11-04 · **성격:** `PROSPECTIVE_FOR_RERUN_AFTER_DEV3_OBSERVATION` · **독립 감사:** 없음 · **HOLDOUT2 / RT:** 별도 승인

## 1. 원래 실패와 데이터 관찰 여부

- S1V5 source [Actions #41769652106](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41769652106): 1980/1980 rows, source input SHA 및 QA PASS, source SHA `0bd5d706710f172ff6becb562eadd7573b5d3ffd`, 원본 artifact ID 13296915471.
- C3V5 최초 [Actions #41780677692](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41780677692): `ERR_A010_TRUTH_ONLY_REPLAY`; S1 source original과 regenerated truth byte hash가 일부 다름. 1080행 C3/G5 성공 **아님**.
- read-only [#41781114661](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41781114661): 768 배열 대조 중 120 불일치; observed `Xtrue/poses/ds_true/dth_true`, 최대 절대 차이 `8.881784197001252e−16`. 이미 이 결과를 본 후 작성했으므로 **128×machine epsilon 수치 재생 진단은 사후 선택**. PR28에서 그 결과를 원래의 사전등록 확인적 기준이라고 주장하지 않는다.

## 2. 이 amendment의 새로운 사후 탐색적 규칙

1. S1 생성 원본 ZIP 및 per-array source SHA/dtype/shape는 **절대 불변**. 현 C3가 사용한 saved original receipts가 authority이다. S1 manifest `source_git_sha=0bd5d706710f172ff6becb562eadd7573b5d3ffd`, 이전 complete 49-file code hash ledger와 일치하는 경우에만 **source-code diff는 code/c3v5.py 한 파일**인 현재 replay binary를 허용한다. 출처 구별 없이 source_code hash mismatch를 무시하지 않는다.
2. Original S1 truth arrays `TRUTH|field|role|cell|Xtrue,poses,ds_true,dth_true,dts,prior_P0,mu,pose_keys_sha`를 SHA-verified indexed archive에서 로드한다. scoring/coordinate rotation/diagnostic truth-start use source-stored bytes. 절대 C3 regenerated truth를 source truth인 것처럼 주장하지 않는다.
3. Reloaded truth의 `shape/dtype` 모든 field/role/cell 정확 일치. `dts, prior_P0,mu,pose_keys_sha`는 regenerated와 **바이트 SHA 동일**을 필수로 한다. `Xtrue,poses,ds_true,dth_true`는 **사후 탐색적 CPU-float portability diagnostic**으로 별도 `delta_abs`, `delta/(eps×max(1,|source|,|regen|))`를 저장한다. 진단 bound **128** (double eps scaling) 초과 시 중단. 128은 기존 E′/R5/G5 과학 허용오차를 대체하지 않는다.
4. 원래 optimizer 입력 일곱 `z,x0,ds_m,gy_m,Sigma_model,dts,taps`은 exact source bytes SHA를 오직 source original로 비교한다. Q/Prior/9-start grid/forced truth-separation/full 4×4 C10/NEES4/G5 strict replay gates 전부 변경 **금지**. `KINK_CLASS_UNCERTAIN` / no exception / independent unit field 유지.
5. original C3 FAIL 및 원본 SHA mismatch 자체는 기록으로 남긴다. 수정 C3 결과는 `USER_AUTHORIZED_NONINDEPENDENT_POST_OPEN_CORRECTION`로 별도 표시, 진짜 untouched independent-confirmatory DEV3로 간주 금지. 이전 결과를 PASS로 소급 변경 금지.
6. 수정 후 full source byte SHA map 49 entries를 다시 고정해야 한다. 이는 원래 AMENDMENT-010의 역사적 freeze를 소급 변경하는 대신 **추가 lock revision**으로 기록한다. 실행 요청 전 old/new source SHA를 명시하며 기존 `RUN_REQUEST.json`의 `AMENDMENT-010` 경로 조건을 유지한다.
7. Negative controls: corrupted S1 outer ZIP SHA; missing/extra row; truth dtype/shape mismatch; wrong coordinate ≥0.01m; exact invariant 1-bit alteration; tampered port/taps/Sigma; conflicting source code map; any missing 1080 row. Diagnostic can pass only when original S1 entire SHA manifest remains valid. No real Sionna RT or HOLDOUT.

## 3. 단계·중단 조건

`P0` pinned source truth compatibility preflight 10 DEV3 fields (no estimator) → `P1` new code + code_sha256 lock revision + negative fixtures → `P2` 1 field×1 group tiny canary (new source, 3 seeds) → `P3` full 10 fields × LH/RV × 3 seeds 1080 Batch rows, E′+9 × 1080 = 10800 terminal receipts → `P4` original S1 vs new C3 state/cost/P/full C10 + G5/H/CAL separate audit.

**Hard STOP:** immutable S1 SHA mismatch; unexpected code besides C3; any invariant bit mismatch; generated geometry exceeds declared exploratory bound; original estimator boundary mismatch; missing rows; nonfinite or covariance not SPD. Report failures on original conditions; do not tune new tolerance to pass.

## 4. 현재 status

`S1_DEV3_SOURCE=PASS`, `C3_V5_ORIGINAL_ATTEMPT=FAIL`, `POST_OPEN_PATCH=IN_PROVISIONAL_TEST`, `C3_NUMERIC_REPLAY=NOT_CERTIFIED`, `EXTERNAL_AUDITOR_SIGNED=false`, `HOLDOUT2=NO-GO`. **물리적 RT pre-P3 계약은 별도로 관리**하므로 본 C3 코드를 수정하기 위해 RT solver를 실행하지 않는다.
