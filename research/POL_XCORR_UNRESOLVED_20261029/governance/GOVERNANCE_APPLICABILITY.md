# GOVERNANCE_APPLICABILITY — POL-XCORR-001

`docs/research-governance/*`(governance SHA `250d617a…`)는 MBVAR-INFO-001 전용으로 작성됐다. 이 표는 POL-XCORR-001에 각 규칙을 **APPLY**(그대로), **ADAPT**(대응 규칙으로 치환), **N/A**(해당 없음) 중 무엇으로 적용하는지 고정한다. root `AGENTS.md`의 데이터 보호·claim 규칙은 항상 APPLY.

## COMMON_CONTRACT

| 절 | 규칙 | 적용 | POL-XCORR 대응 |
|---|---|---|---|
| I | 필수 task 필드(role, contract_id, base/governance SHA, contract sha256, scope, input lock, output root) | APPLY | `TASK_HANDOFF_v0.2.md` 헤더 |
| I | DRAFT는 P0_PREFLIGHT만 | APPLY | P0 = source/math/geometry + **label 미사용 측정**(LoS floor, block 수) |
| I | freeze 후 변경은 AMENDMENT | APPLY | `AMENDMENT-POLX-XXX.md` |
| II | 추정량·단위 구분(raw_channel_H, z_s, h_LOS, µ, ε_truth …) | ADAPT | raw H, s, q_W, ε_ρ, R(τ), T1–T4(ORACLE_ONLY) 구분 — SCIENCE_SPEC_v0.2 §1–4 |
| II | 학습 µ/R 상속 금지, Track S/R | N/A | 필터·µ/R 미사용 |
| II | oracle 사용 표기 | APPLY | LoS 채널·label = ORACLE_ONLY |
| III | 독립 단위 = scene variant, anchor/path 반복관측 | APPLY | n = 1, case 공동 block bootstrap |
| III | 기존 Corridor/Office는 retrospective | APPLY | 전체 corpus RETROSPECTIVE/DEV, holdout BLOCKED |
| III | covariance 학습 정규화 | N/A | 공분산 학습 없음 |
| IV | G0–G6 gate | ADAPT | G0 = draft hash + P0 scope, G1 = P0 CORE PASS + freeze, G2 = S0, (G3 N/A), P1/P2/P3 = 계약 v0.2 단계, G6 = 신규 scene(R-11) |
| IV | 상태어 PASS/FAIL/BLOCKED/NOT_RUN과 verdict 분리 | APPLY | + P0 3분류 CORE_FAIL / T4_ONLY_BLOCKED / MEASURED |
| V | MANIFEST 필드, 사전 tolerance, silent clamp 금지 | APPLY | PLAN_PARAMETERS_v0.2, INVALID_WINDOW·NULL_PORT 플래그 |
| VI | 역할 분리, SELF_REVIEW_ONLY 표기 | APPLY | 구현자 검토(IMPLEMENTER_REVIEW_01)는 독립 세션, auditor 미지정 |

## ROLE_IMPLEMENTER

| 규칙 | 적용 | 대응 |
|---|---|---|
| Start contract 필드 | ADAPT | contract_id = POL-XCORR-001 |
| P0: 원본 git source, 행 정렬, s 정규화, noise_var=None | APPLY | R-02, R-04, R-05, H noise-free 확인 |
| P0: MB_VAR replay parity (R4-B, R5-A) | **N/A → ADAPT** | 대신 **G5 feature 재현 parity(R-13)** 와 s_fp·log_fp_power parity(R-02, R-12) |
| P0: repeat pose equality(H, z, h, µ, ε) | ADAPT | 같은 XY·yaw 재방문 시 H 동일성(STATIC_YAW_SWEEP와 timeline 중복 XY 존재 시) |
| P0: LFS·bank sha256 | APPLY | INPUT_LOCK_v2 |
| S0/S1: information ratio 0.526/10, GP field | N/A | S0 = 2-path coherency 법칙(LAW/PHYSICAL) |
| R: RT scene C00–C11, budget | N/A (현재) | R-11 DEFERRED; 신규 scene 시 APPLY |
| Scoring: append-only run 산출물, NOT_APPLICABLE 표기 | APPLY | SCIENCE_SPEC_v0.2 §8 |
| Code review: shape·단위·RNG 결정성 | ADAPT | H (N,257,2,2), W·lag 경계, ns vs tap |

## ROLE_AUDITOR

| 규칙 | 적용 | 대응 |
|---|---|---|
| 독립성 기록, SELF_REVIEW_ONLY | APPLY | R-10 |
| 1D information ratio 재유도 | ADAPT | F2(det J ≈ δ²\|a∧b\|²…)와 q = 4x(1−x) 관계 독립 재유도 |
| GP PSD, 4-state 식별성 | N/A | — |
| 패킷 1개 끝단 추적 | ADAPT | H → CIR → n₀ → J/q_W, R(τ) → label 정렬 |
| 모든 seed·실패 보고 | APPLY | — |

## CI_REQUIREMENTS

설계 문서(DESIGN_ONLY)로 APPLY. POL-XCORR negative fixture: 잘못된 hash, trace 집합 누락 파일, train/test route 중첩, LoS에 포트 시간 오프셋 주입 시 q > 0 검출, 유효창 밖 n₀ clamp 시도.
