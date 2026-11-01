# 별도 구현 객체 인계서 — 목적과 불변조건부터 구현

역할: 수신자는 `IMPLEMENTER`, 현재 작성자는 `PROPOSER`다. 계약 `DLP-PHYS-BRIDGE-012-001`. 이 문서는 실행 스크립트가 아니며 새로운 시험은 아직 없다.

## 1. 시작 순서와 허용 범위

1. root AGENTS, 이 커밋의 COMMON_CONTRACT, ROLE_IMPLEMENTER, 본 폴더 01/02/CONFIG/SOURCE_REFERENCE_LOCK을 읽는다.
2. `role, contract_id, base_git_sha, governance_git_sha, draft_or_frozen_contract_sha256, numeric_config_sha256, input_lock_sha256, allowed_phase, output_root`를 receipt에 쓴다. base/governance는 원고 v4의 full SHA다. source lock과 파일 체크섬이 없으면 scientific run을 하지 않는다.
3. 명시적 후속 위임이 PB0 source audit만 허용했다면 원본 확인·테스트 스캐폴딩까지만 한다. FROZEN 계약과 독립 pre-run review가 준비되지 않았는데 PB1–5의 결과를 계산하지 않는다.
4. 새 구현 브랜치를 만들어 원본 source/evidence를 read-only로 유지한다. 이 제안자의 문서 제출 브랜치에서 production filter를 변경하지 않는다.

**검증 목적은 기존 MB_VAR의 물리적 설명이다.** 더 좋은 알고리즘 탐색, 5상태, SUB3, sub-tap, 새 앵커, 실제 RT, 원고에서 R4-B 제거는 과업이 아니다.

## 2. 모듈별 책임 — 실제 구현은 후속 객체가 작성

| 권장 모듈 | 입력→출력 | 필수 경계 |
|---|---|---|
| `source_inventory` | source refs→materialized hash/pose-time ledger | 다른 H/LoS 계열 대입 금지 |
| `legacy_trace_adapter` | 원본 4-state runtime→x/P/μ/R/gate/lookup snapshots | 관측·filter arithmetic 변경 금지 |
| `physical_response_audit` | Full/Native LoS/SourceFFD→power,s,J,branch,잔차 | truth-only diagnostic namespace 분리 |
| `matched_prior_shadow` | 하나의 prior+lookup snapshot→4 shadow update | shadow가 원 재귀 상태를 덮어쓰지 않음 |
| `variance_policy_control` | source-route lookup traces→상수/현재/0 비교 | 상수 산식과 denominator는 사전 설정 그대로 |
| `correlation_projection` | 원시·cross-fit 잔차와 gain→상관/투영 통계 | time lag와 physical spatial kernel을 동일시하지 않음 |
| `claim_export` | immutable outputs→12조건 표/claim ledger | 좋은 결과만 선택하지 않음 |

각 모듈이 원본 source helper를 공유한 범위와 새로 계산한 범위를 기록한다. 공유 wrapper로 같은 결과를 두 번 얻은 것을 독립 검증으로 표시하지 않는다.

## 3. source preflight에서 확정할 파일

- 원고 v4, D2/D3 및 RA4 score의 immutable git/artifact refs.
- Full/Native LoS H, samples/pose/time, fgrid, LP±45 bank, 관측 extractor.
- SourceFFD h/H, f/F/Q, sensor controls, 초기 x/P, μB/μM, RB, original BASE mask.
- EXDS 학습 route/fold, feature order/normalizer, 가중치·예측파일, 저장 예측의 복원식.
- 참고 manifest: `research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json` 등. 기존 manifest를 실제 bytes 없이 신뢰하지 말고 선택 case의 SHA를 materialize해 대조한다.

raw SourceFFD와 D2 replay runtime이 서로 다른 reference commit일 수 있다. 이를 임의 최신 코드로 통합하지 말고 각 의존성을 잠금표에 기록한다. 원본 packet μ가 lookup state와 무관한 저장예측이라는 사실도 그대로 기록한다.

## 4. 단계별 정확한 완료/중단 기준

| 단계 | 기술 QA 완료 조건 | 중단 조건 |
|---|---|---|
| PB0 | 3 case×4 gyro, 입력 hashes, pose/time/port 일치; 원본 h/z/μ/R 및 score provenance | 해시/포트/timestamp 누락, 중복, source family 혼합 |
| PB1 | native r/s replay, power-ratio derivative 식, branch별 FD/출력 전체 분모 | 의미 없는 denominator, 관측 부호 오류, stable J tolerance 실패 |
| PB2 | common prior+previous-posterior lookup 동일성, Joseph update, 4-arm 항등식, full 96 trace parity | source x/P/mask 비일치, shadow feedback, truth leakage |
| PB3 | train-only variance 상수 재계산, 144 protocol trajectories/48 신규 상수 대조, 동일 control/window | 평가 route로 상수 fitting, best-γ 사후 선택, baseline 변경 |
| PB4 | raw/cross-fit 분리, pair count·시간 key 보존, 한 장면 한계 | packet을 독립 RF로 계산, 불가능한 time/space 식별 주장 |
| PB5 | 독립 감사 raw 재계산, 모든 12조건과 실패, claim-to-evidence matrix | 독립 감사 미실행, source 없는 수치, 누락 case |

### 수치 QA (결과 보기 전 고정)

- byte SHA256와 pose/time/channel identifiers: exact equality.
- native r replay: max absolute ≤1e-9 m; s replay ≤1e-12; tap/port/valid exact.
- unchanged source h/source Jacobian replay: 기존 동일 입력 연산을 exact source에서 비교. state/P parity `atol=1e-10, rtol=0`; yaw는 같은 wrap convention. 원 mask exact.
- 6 significant-digit D2 표 대조와 원본 고정밀 score 대조를 구분: 고정밀 canonical score `atol=1e-8` deg/cm; D2 출력은 기존 formatting 후 string 또는 반올림 범위로 대조. 이를 물리 tolerance로 사용하지 않는다.
- gain 축소/mean 교체/Σ basis/zero σ/μM=μB identities: max scaled error ≤1e-10.
- R/S/P symmetry `≤1e-12+1e-10*maxabs`; PSD/PD는 natural units와 normalized condition을 함께 기록. 음의 eigenvalue나 singular solve를 조용히 diagonal jitter로 구조 복구하지 않는다.
- PB1 active branch FD: 02 명세의 componentwise tolerance. 진짜 detector discontinuity는 별도 층으로 보고하되 source 오류를 discontinuity라고 처리하지 않는다.

지표가 악화한 것은 위 QA 실패와 다르다. 기술 상태 `PASS/FAIL/BLOCKED/NOT_RUN`와 과학 해석 `SUPPORTED/MIXED/NOT_SUPPORTED/INCONCLUSIVE`를 두 필드로 쓴다.

## 5. 최소 출력 스키마

공통 행 키:

`run_id,contract_sha256,source_sha,case,route,anchor,mount,bias,sensor_seed,packet_id,pose_id,t_s,denominator_id,reference_arm,mean_arm,variance_policy,gate_policy,truth_role,source_field_id`.

### PB1_PHYSICS_PACKET.parquet/csv

`Pplus_Full,Pminus_Full,Pplus_Direct,Pminus_Direct,s_Full,s_Direct,h_s_GT,h_s_prior,H_sx,H_sy,H_spsi,rho_true,rho_prior,relative_bearing_true,relative_bearing_prior,tap_Full,tap_Direct,tap_model,port_*,peak_*,margin_*,branch_stable,FD_valid,FD_error,e_prop,e_model,epsilon_B,epsilon_M`.

GT와 prior 열은 이름부터 구분한다. 모든 유효·무효 packet count 및 invalid reason을 별도 ledger로 남긴다.

### PB2_SHADOW_UPDATES.parquet/csv

`xprev_post_lookup,rho_lookup,sigma_lookup,lambda,xprior,Pprior,z,mu,R,H,S,K,nu,NIS,would_accept,dx_range,dx_pol,xpost_forced,Ppost_forced,xpost_policy,Ppost_policy,heading_sq_error_before_after,XY_sq_error_before_after`.

모든 matrix는 shape/unit metadata를 제공한다. 실제 recursion과 local shadow 결과를 같은 arm 이름으로 합치지 않는다.

### PB3_VARIANCE_CONTROLS.csv

`held_route,calibration_routes,calibration_count_per_route,constant_lambda,lookup_policy,mean_arm,gate,bias,heading_RMSE_deg,XY_RMSE_cm,bg_RMSE_deg_s,heading_coverage95,XY_coverage95,NEES,NIS,n_valid,n_used,n_rejected,mask_sha,first_divergence_packet`.

원래12조건과 factor96조건의 재현 표, 상수 신규48조건을 분리한다.

### 공통 산출물

`MANIFEST.json`, `INPUT_LOCK.json`, `CONFIG_LOCK.json`, `SOURCE_LEDGER.csv`, `SPLIT_LEDGER.csv`, `BASELINE_PARITY.json`, `QA.json`, `FAILURE_LEDGER.csv`, `CLAIM_EVIDENCE.csv`, `FIGURE_MANIFEST.json`, `RESULTS_SUMMARY_KO.md`, raw trace 또는 그 immutable artifact link.

manifest에는 모든 input/output SHA256, 실행 commit, environment, 실제 command, timestamp UTC, role/session, source model/controls/observer hashes, independent_scene_count=1, RF_sequences=3를 포함한다. SHA ledger 자신의 hash를 자기 목록에 넣는 순환 참조를 만들지 않는다.

## 6. 구현자 완료 보고 형식

(1) 변경 파일 (2) 이동/삭제 파일 (원칙상 없음) (3) 그대로 둔 원본 (4) 명령·환경 (5) parity/negative tests (6) 12조건 및 부정적 결과 (7) claim 범위 (8) 다음 gate와 blocker.

수정이 필요하면 실패 run을 보존하고 새 commit/run으로 재실행한다. 연구 의미가 바뀌는 수정은 제안자 amendment와 auditor review가 선행되어야 한다. CSV/JSON 출력 오류 수정과 관측정의·mask·허용오차 변경을 구분한다.

## 7. 별도 구현 객체에게 전달할 시작 지시문

> 역할 IMPLEMENTER로 이 패키지를 읽고 source preflight부터 진행한다. 사용자에게 승인받은 allowed_phase와 계약 SHA를 receipt에 먼저 기록한다. 원고 v4의 R2-B/R4-B/R5-B 12조건, 원래 4-State MB_VAR와 pre-predict lookup을 보존한다. source lock을 완성하고 unresolved input 및 source 계보를 보고한다. 독립 pre-run 감사와 FROZEN revision 전에는 scientific comparisons를 실행하지 않는다. 이후 PB1→PB2→PB3를 우선 수행하고 모든 성공·악화·미확정 결과를 04의 규칙으로 전달한다. 원본 데이터·원고·타 계약을 덮어쓰지 않는다. 이번 제안자에게 구현/독립 감사 완료 서명을 대신 맡기지 않는다.
