# TASK_HANDOFF — POL-XCORR-001

## 현재 허용 작업 (DRAFT)

```
role=IMPLEMENTER; contract_id=POL-XCORR-001; phase=P0_PREFLIGHT
base_git_sha=250d617ad89a4105fa1af546cc83ceed9de98f42
governance_git_sha=250d617ad89a4105fa1af546cc83ceed9de98f42
draft_contract_sha256=c65f54e4a5782bacf0feea971792650d692fae85bb7e0a3915c2d070d24e33ca
input_lock_sha256=d186f21a00d3a2cf8a012ecd7563c0ed0c99100f595c81a9c9a51ab2da484509
plan_parameters_sha256=e03a04329af4e461bc16c0e5006104ef0ed96d9a3e200ca0adda90ddc96dfeea
intended_scope=R-01..R-05 해결, F1/F3 수치 확인, route별 유효 block 수 산출
output_root=research/POL_XCORR_UNRESOLVED_20261029/results_p0/
```

- 지표–label 관계(AUC, 상관) 계산 금지. P0는 parity·불변성·정렬만.
- 실패해도 출력·로그 보존, 덮어쓰기 금지.

## 구현자 순서 (P0)

1. `config/INPUT_LOCK.json` 전 항목 sha256 재계산 → 불일치 시 STOP.
2. observer 재구현 → `s_fp` vs HP_PACKETS `sF_+0` (|Δ| ≤ 1e-9, 7 case 전부).
3. LoS 채널 전 pose ε_W, ε_ρ (≤ 1e-8) → `LOS_RANK1.csv`.
4. 합성 fixture: 단일 타원 경로(ε=0), diag 이득·위상(ε_ρ 상대변화 ≤ 1e-12), 포트 시간 오프셋 주입(ε>0 검출) — 마지막은 negative fixture.
5. R2_aA trace: 1차 경로 image-method 재할당(≤ 1 ps), node 주파수 Σpath 재합성 vs 저장 H(상대오차 ≤ 1e-3; 안테나 적용 방식은 source_model 확인 필요) → `TRACE_REALIGN.csv`.
6. SAMPLES ↔ timeline pose_id/phase join 결측 0, drive segment(≥ 2 m) 목록과 route별 1 m block 수.
7. `P0_CHECKS.json`, `MANIFEST.json`.

## 감사자 (pre-run)

```
role=AUDITOR; contract_id=POL-XCORR-001; same SHAs as above
```
- SCIENCE_SPEC §2 F2 식을 독립 계산(기호 또는 수치)으로 확인.
- scene n=1, holdout BLOCKED, 판정 상한이 계약에 반영됐는지 확인.
- 구현자 P0 출력은 별도 스크립트로 재계산.
- 같은 세션이면 `SELF_REVIEW_ONLY`.

## 사용자 결정 대기

R-09 router 적용 방식, R-10 auditor 지정, R-11 신규 scene 예산, R-08 VNA 파일, R-07 DW1000 jitter 실측.
