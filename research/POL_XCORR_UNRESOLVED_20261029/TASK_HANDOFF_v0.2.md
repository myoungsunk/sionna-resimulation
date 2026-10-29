# TASK_HANDOFF — POL-XCORR-001 (v0.2)

v0.1 `TASK_HANDOFF.md`를 대체한다. P0는 아래 v0.2 draft hash로만 착수한다.

## 현재 허용 작업 (DRAFT v0.2)

```
role=IMPLEMENTER; contract_id=POL-XCORR-001; phase=P0_PREFLIGHT
base_git_sha=250d617ad89a4105fa1af546cc83ceed9de98f42
governance_git_sha=250d617ad89a4105fa1af546cc83ceed9de98f42   # PENDING_REPIN_AFTER_R09
draft_contract_sha256=468249a7b32c9699c20a3227fc0241eef3ab92773d00bc52a981a32cf6e56ddb
science_spec_sha256=0beeab98c28e3a2933845069172bb8288ac91809325437549d0c4d9d7733efa1
input_lock_sha256=bddab15801f8d8c653eeb7f825ff71352d48bda7bf7b650f59a2feb300458184
plan_parameters_sha256=c73a5e7fe36eb5922854e1382e0f8f916672b76fcb395fdc59139f41e3f70d3a
governance_applicability=research/POL_XCORR_UNRESOLVED_20261029/governance/GOVERNANCE_APPLICABILITY.md
intended_scope=CORE(R-02,R-04,R-05,R-12,R-13, invariance fixtures), T4_ONLY(R-01), MEASURED(R-03 LoS q floor, block counts)
output_root=research/POL_XCORR_UNRESOLVED_20261029/results_p0/
```

- 금지: 지표(q_W, ε_ρ, R(τ), M3, M4)와 label(e_s, e_r, η)의 관계 계산·출력. LoS floor는 LoS 채널만 사용.
- 실패해도 출력·로그 보존, 덮어쓰기 금지.

## 구현자 순서 (P0)

1. `INPUT_LOCK_v2.json` 전 항목 재계산(trace 925+925 개별·집합 hash 포함). 불일치 → CORE_FAIL(trace 집합은 T4_ONLY).
2. Δt = 1/(1028·Δf) 런타임 계산 기록.
3. observer 재구현 → s_fp vs HP_PACKETS `sF_+0`(≤ 1e-9, R-02), log_fp_power 밑·정의 parity(R-12), `features.py` G5 출력 재현(R-13) → `G5_PARITY.csv`.
4. 합성 fixture: 주파수 평탄 단일 타원 경로(q = 0, φ ≠ 0), diag 이득·위상(ε_ρ 상대변화 ≤ 1e-12), negative fixture(포트 시간 오프셋 주입 → q > 0, 유효창 밖 n₀ → INVALID_WINDOW).
5. LoS 채널 q_W, ε_ρ, jones_diversity를 timeline + STATIC_YAW_SWEEP 전 pose에서 측정 → `LOS_FLOOR.csv` (판정 없음).
6. R2_aA trace 재정렬(image-method ≤ 1 ps)·node 재합성(≤ 1e-3) → `TRACE_REALIGN.csv`.
7. pose 층 분리·주행거리·1 m block·turn block → `POSE_ALIGNMENT.csv`, route·phase별 block 수.
8. `P0_CHECKS.json`(CORE/T4_ONLY/MEASURED 분류), `MANIFEST.json`, `IMPLEMENTER_REPORT.md`.

## 감사자 (pre-run)

```
role=AUDITOR; contract_id=POL-XCORR-001; same SHAs as above
```
- F2(ψ 독립)와 q = 4x(1−x) 관계 독립 재유도, R-03 규칙의 q_ref 정의 점검.
- baseline M0 = G5 + |ds1| 적정성, case 공동 block bootstrap 확인.
- 구현자 P0 출력은 별도 경로로 재계산. 같은 세션이면 `SELF_REVIEW_ONLY`.

## 사용자 결정 대기

R-09 router append(문안: `governance/AGENTS_ROOT_APPEND_PROPOSAL.md`), R-10 auditor, R-08 VNA 파일, R-07 DW1000 jitter. R-11은 DEFERRED.
