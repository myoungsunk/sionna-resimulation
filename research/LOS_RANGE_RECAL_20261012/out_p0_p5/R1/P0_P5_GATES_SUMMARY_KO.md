# LoS first-arrival detector bias 재보정 P0~P5 — 게이트 요약 (R1)

계획서: `PLAN_P0_TO_P5_KO.md`. 각 단계 상세 판정은 `P{0..5}/*_GATE.md|*_DECISION.md`. 이 문서는 요약이며 새로운 결과를 추가하지 않는다.
브랜치 `claude/practical-goodall-wnsjv4`. 과학적 경계 유지: `scientific_PASS=false`, `stage_B_allowed=false`, V02 LARGE FAIL 변경 없음.

## 게이트 표

| 단계 | 판정 | 핵심 수치 | 비고 / 한계 |
|---|---|---|---|
| P0 사전점검 | **PASS** | 16,432행 병합, 12 조건, identity 잔차 3.6e-15 m, V04 평균 재현(1e-9), observer parity 전부 일치 | route 간 공유 XY 1곳 → 사전 선언한 제외 규칙으로 train/valid 분리 |
| P1 LORO 비교 | **KEEP_B_OLD_AND_GO_TO_P2** | 상수/affine 재보정은 B_old 대비 +0.98 % [0.70, 1.27] / +0.52 % [0.36, 0.71] (악화 방향) | 3 route, 1 scene → 탐색적. site 클러스터 2,815 |
| P2 원인 감사 | **PASS (원인 감사이지 성능 PASS 아님)** | tap 전환율 0.394 (V04 일치), flat/FFD/MP identity 최대 오차 0 | tap = 0.1496 m |
| P3 후보 선택 | **E1_on_B** (동결) | LORO site-가중 RMSE B 대비 0.837 (모든 fold 개선); C_const 1.009, C2 1.005는 악화; D1 0.967, D2 0.966 (미채택) | 누수 테스트 all_pass; 동결 후 `predict()` 추가는 `P3_FREEZE_ADDENDUM.json`에 공개; 1차 시도 `P3_attempt1_superseded` 보존 |
| P4 blind 검증 | **WITHIN_SCENE_IMPROVEMENT_GENERALIZATION_NOT_VERIFIED** | noise-free Full RMSE 변화 −17.2 % [−22.5, −13.7] (240 신규 XY 클러스터) | 예측 파일 SHA를 truth 전에 기록; 다른 scene 없음 → 일반화 미검증 |
| P5 EKF replay | **ACCURACY_PASS_DIAGNOSTIC, CONSISTENCY_NOT_ESTABLISHED** | E_COND vs B_OLD 위치 −53.4 % [−59.8, −47.3]; BEST_PLUS_R_IAT −56.0 % [−62.4, −47.4]; B_OLD는 RF 없음(A_DR)보다 +31.8 % [11.2, 50.9] 악화 | 36,864 run, 실패 0; 어떤 arm도 절대 일관성 미확립; innovation lag-1 ACF 0.57~0.75 |

## planned vs executed
- 실행: P0~P5 전부. P5는 개발 seed 5000–5031 → 기준 동결(`P5_CONFIRM_CRITERIA_FROZEN.md`) → 확증 seed 5100–5227 (128 seed × 12 조건 × 3 drift × 8 arm).
- 추가(계획 외): arm `BEST_PLUS_R_IAT` (V05 조건부 IAT 상수 5.8로 R 팽창 — 경미한 정보 누수로 표기).
- 미실행/미충족: P5 사전조건(codex noisy-probe-ekf 브랜치 API/수신기 일치) 미수행; 6상태 전체 NEES; `s` 사용 arm; LARGE prior; 두 번째 scene; per-run trace 미보관(재현은 코드로, chunk/arm SHA는 `P5/P5_TRACE_SHA256_MANIFEST.csv`).

## 결론 (허용되는 주장 / 금지되는 주장)
- 허용: 동일 scene 내에서 조건부 편향 모델(E1)이 고정 오프셋 대비 range/위치 오차를 줄인다. 고정 오프셋(B_old)은 RF를 쓰지 않는 것보다 나쁘다(이 harness·pose-SMALL prior 조건).
- 금지: 다른 scene/실측으로의 일반화, 필터 통계적 일관성(NEES/coverage) 주장, `scientific_PASS` 승격, Native range-only 3점 실험에 대한 주장(harness lineage 상이).

## 다음 분기
1. P4(c)용 두 번째 scene/anchor 기하 확보.
2. BEST_PLUS_R_IAT의 fold-wise IAT 상수(누수 제거).
3. 보정된 range 위에 `s` 갱신 추가(Stage B V06) — Stage C 사용 이전에.
4. 보정 arm에서도 NEES ≫ 3인 원인 조사(A_DR 자체가 불일치: sensor-v2 prior vs generator).

재현 정보: `RUN_MANIFEST.json`.
