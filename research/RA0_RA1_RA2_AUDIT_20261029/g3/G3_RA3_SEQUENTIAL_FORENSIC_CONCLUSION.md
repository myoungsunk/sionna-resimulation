# G3 개별 경로 원인 규명 → H 영향 → RA3 재실행 범위 감사

- 감사 범위: 2026-10-07 Snowball R2/R4/R5, anchor A/B, G3 strict 5e-14s 26경로
- 원 G3 소스 `8b693825f46a8a2de64a87de09d48bc50a6e5704`, READ-only 연구 기준 `9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13`, 감사 브랜치 `audit/g3-ray-forensics-ra3-20261029`
- 원 H 해시와 packet 계보는 기존 RA2에서 7/7 검증; 원본 `results/`, `research/DS_MASK...` 값은 불변.
- **역할:** PROPOSER = 경로/반례/허용오차·source SHA 동결; IMPLEMENTER = 원 trace 925개 재구성+원 H 재조립·반사실 지연 민감도·후속 RA3 코드; AUDITOR = 별도 원본 receipt/원 G3 집계·표준 NumPy 논리 비교. **동일 세션의 SELF_REVIEW_ONLY** — 독립 auditor 서명 부재, 과학적 최종 승인 아님.

## G3 원 경로 분모 확인 (6개 그룹)

| case | 위치 수 | ray 수(원 receipt) | strict 초과 ray | 엄밀 판정 |
|---|---:|---:|---:|---|
| R2_aA | 925 | 58,231 | 1 | FAIL |
| R2_aB | 925 | 58,231 | 1 | FAIL |
| R4_aA | 547 | 34,430 | 3 | FAIL |
| R4_aB | 547 | 34,431 | 3 | FAIL |
| R5_aA | 1,343 | 84,553 | 9 | FAIL |
| R5_aB | 1,343 | 84,534 | 9 | FAIL |
| **TOTAL** | **5,630** | **354,410** | **26 (0.007336%)** | **6/6 FAIL** |

신뢰 출처: [5,630 receipt 감사](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40852794655), [과거 수정된 G3 JSON](https://github.com/myoungsunk/sionna-resimulation/tree/9a9f93309d8e07f95c8662991c6b7dc3e4f6d7ad/results/DRIVE_SIM_20261007/SNOWBALL_ROUTE_RUNS/01a11669/g3_recheck_20261008/S2).
6개 그룹 모두 FAIL은 354,410 경로 전체가 FAIL임을 뜻하지 않음. 반대로 0.0073%라고 물리 검증을 통과한 것도 아님.

## 1. R2_aA 원 raw 925위치 직접 재생

[GitHub Actions #40850815112](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40850815112)

- GitHub 원본 `STORED_PATH_TRACES_R2_aA` 925개 `_trace.npz`/receipt, `R2` timeline, 원 SAMPLES 전수 검사.
- 원 G3 `max_residual=5.1090357159952736e-14 s`, `strict_unmatched=1` 정확 재생.
- offending ray: `case=R2_aA, tag=x3.7036_y-0.5204, pose_id=915, ray_index=62, n_paths=63`.
- `tau_raw=2.412728008494014e-7s`, 가장 가까운 이미지 `end_x_max>end_x_min>end_x_max`의 `tau_image=2.4127285193975855e-7s`.
- **병합 이전/이후 잔차가 동일**: `5.1090357159952736e-14s`; 해당 1건에서 **TIE_CLASS_ARTIFACT 반증**.
- raw tau는 float32 roundtrip 정확하지만 차이가 `float32 ULP≈2.84217e-14s`의 약 1.80배. 단순 최종 float32 반올림만으로 해소 불가. Sionna 내부 기하·수치 계산 중 어디서 오차가 생겼는지는 현 증거만으로 분리 불가능.
- 원 trace 좌표와 원 timeline 차이는 최대 마이크로미터 미만; 단순 timeline roundtrip 단독 원인으로 불충분.

## 2. 나머지 25개/23위치의 증거 한계

- [원본 5,630개 receipt](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40850696027)에서 25건 위치 및 원 G3 strict 개수 **모두 보존/재현**.
- [2026-10-07 final + snapshot archive 내용물 감사](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40853663322) — 2개 압축본 각 receipt 5,635개, **원 `*_trace.npz` 0개**.
- GitHub repository tree 전체 11,498개 항목 검색에서 원 `_trace.npz`는 R2_aA 저장 925개뿐이며 다른 5그룹 원 ray 파일 없음.
- 다른 23개 실패 위치 모두 `TIE_S=1e-13s` 병합 때 `5e-14s`보다 큰 class 대표 지연 이동이 가능한 구조가 확인됨. **잠재적 기전이지 실제 25개의 ray-level TIE 원인 증명이 아님**. 해당 ray가 어떤 class와 연결되는지 원 `tau` 필요.
- 원본 source `SNOWBALL_ROUTES_01a11669/S2/traces_*`의 missing 23 key와 각 original `_trace_receipt.json` SHA는 [`G3_23_ORIGINAL_SOURCE_LOCK.json`](G3_23_ORIGINAL_SOURCE_LOCK.json)에 동결. 원본 Snowball volume에서 원 파일을 확보하면 [읽기 전용 collector](g3_25_original_raw_acquisition.py)로 25개 ray 검사. 새 RT로 재생성한 자료는 원본으로 치환 금지.
- 물리학적 최종 원인 판정: **`BLOCKED_EVIDENCE_25_RAW_TAU`**.

## 3. R2_aA 원 H와 지연만 바꾼 반사실 민감도

[검증 실행 #40851669162](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40851669162)

- sha256 고정 원 0/45° FFD bank + Sionna Jones trace에서 저장 H를 다시 합성, 상대오차 `2.37e-17 / 1.57e-17` 로 원 저장 H 패리티 PASS.
- `tau[ray62]`만 이미지 경로 지연으로 바꿨을 때 (\|\Delta H\|_2/\|H\|_2\) = `2.6225575e-7 / 3.0770570e-7` (0°/45°).
- `|\Delta s|=1.0991208e-14 / 2.1774249e-14`, `|\Delta r|=0 m`. 30% leading edge first-path tap 변화 없음; RA2 관측 허용오차 이하.
- 단 **실제 물리 지연을 정정했다고 증명한 것은 아님**. 원 H 파일도, 원 packet도 수정하지 않았으며, 원래 H 생성 코드에 G3 검사 함수를 개입시키지 않는다.
- 이 **1 ray 조건 한정** BB/MB_VAR 재실행 과학적 근거 없음. 나머지 25개에 일반화 금지.

## 4. H→packet→필터 재실행 의존성 및 최대 범위

- G3 checker만 변경: `*_trace.npz`와 `rf_store.assemble`/원 H 불변 → **H/BB/MB_VAR 재실행 NONE**, 단 정정된 G3 verdict 기록 필요.
- 동률 class 이름만 변경: J/τ 원값이 저장 H에 그대로 전달되므로 **H/packet 불변**, 경로 attribution 보고만 재생.
- 실제 ray τ/J/존재 여부 국소 수정: 초과 24개 `(route,anchor,tag)` × 장착 0/45° = **12개 H 저장소의 48개 H행** 우선 민감도 비교. 해당 포즈의 `r,s`·tap·port·수용 gate 재계산 후 변화가 있는 case만 downstream replay. 48행은 **국소 가정 하 최대 후보**, 현재 결함이 확정된 행 수가 아님.
- 원 RF 7개 case × gyro B0/L0/L1/L2 = **28 조건**, `pol_bias_model` 원 점수 14 arms × 28 = **392 rows**. 변경된 관측 및 `mu,R` 재보정이 필요한 경우 **최초 변경 포즈 이전 checkpoint부터 끝까지 BB_ORIG/MB_ORIG/MB_VAR를 재귀적으로 재실행**, 반사 영향이 다른 case의 fitting fold에 퍼지면 해당 fold까지 확대.
- 사후 10월 7일 `S6_routes` 전체를 재생성해야 하는 경우 원래 54,000 score rows가 영향권에 들어갈 수 있으나, **현재 자동 실행·수정 승인 아님**.
- 공통 solver/물리 구현 버그 수정: 48행 가정 무효. RF 전체 검증 절차 및 방법 A/B·G2/G3/L1/L2 등 영향 범위부터 새로 평가. 과거 raw/S6 덮어쓰기 금지.

## 5. RA3 출발 조건 및 상태

- sigma 조회 구현 A: `pol_bias_model/exp_pb.py::run`에서 현재 packet의 motion prediction **이전**, 이전 posterior에서 `rho_hat` 조회. 문서의 `predicted state` 설명과 실행 코드 충돌.
- sigma 조회 구현 B: motion prediction **이후** 현재 prior에서 조회. 같은 BASE 마스크/관측/µ/Q, 단 `R_ss += sigma_b^2`의 조회 시점 차이만.
- [R4_aB/R5_aA × B0,L2 × BB/MB 8-arm canary](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40851671917) 원 implementation state/P parity 정확 재현, sigma lookup 바꾸면 결과 변화: max heading RMSE `0.00549°`, max XY RMSE `0.09075 cm`. 이는 **기존 H에 대한 회귀 비교**이며 G3 25개 H 물리 검증을 대신하지 않음.
- **7 case × 4 bias × MB_VAR/BB_VAR, 28-condition full retrospective audit**: [실행](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40853010911). 과학적 승인 전이므로 기존 BB/MB_VAR 공고 내용을 변경하지 않음.
- G3 물리 출처 gate = `BLOCKED_EVIDENCE`; RA3 기존 packet을 고정한 구현 차이 감사 = `TECHNICAL_QA_ONLY`; 독립 감사 `PENDING_SELF_REVIEW_ONLY`.

## 6. 역할 인계

**PROPOSER:** strict=5e-14 s, relaxed=2e-13 s 원 계약 불변, source SHA lock, 원인 가설 4분리, G3 26경로·H/packet/recursive filter 범위 동결.

**IMPLEMENTER:** original 925 raw 재현, 5,630 receipt 대조, source archives 검색, H counterfactual parity, RA3 비교. 모든 실행은 별도 경로, historic FAIL 결과 보존. `results/` 불변.

**AUDITOR:** 원 자료/JSON·GitHub run/receipt로 분자·분모·24위치 재검산, R2A 병합 기전 반증 및 예외 식별, RA3 소스 semantics 검증. 동일 대화 세션이므로 독립 감수 **불인정**. 최종 `BLOCKED_EVIDENCE` for complete physical G3 cause, `REVISION_REQUIRED` for research release. 25개 원 tau 확보 전 과학적 G3 원인 완결 주장 금지.

## 실행·환경/변경 파일

- 파일: `g3/r2aa_raw_ray_forensics.py`, `g3/r2aa_h_counterfactual.py`, `g3/G3_23_ORIGINAL_SOURCE_LOCK.json`, `g3/g3_25_original_raw_acquisition.py`, `g3/g3_source_archive_inventory.py`; 대응 `.github/workflows/g3-*.yml`; `ra3/ra3_sigma_semantics_28.py`, RA3 workflow.
- 바뀌지 않은 파일: `results/**`, 기존 `research/DS_MASK_CAUSAL_X1_X2_20261026/**`, old G3, 최초 source H, previous 392 score rows.
- 1차 실패도 보존: 초기 925 raw script 로컬 변수 shadowing, H counterfactual 주파수 변수명 오류는 각각 고쳐 재검증됨. 실패 당시 Action을 삭제/덮어쓰지 않음.

**최종 연구 claim:** 과거 G3 strict FAIL을 무효라거나 단순 병합 문제로 다 설명한다고 주장할 수 없음. R2A 실제 ray는 병합 문제 아님. 23개 위치/25개 ray의 물리 근본 원인 미확정. 현재로선 기존 H의 원자료 재현성이 확인된 범위 내에서만 기존 BB/MB_VAR 회고적 수치를 유지하며, 소스 변경 전의 전체 RF/BB 재실행은 승인하지 않음.
