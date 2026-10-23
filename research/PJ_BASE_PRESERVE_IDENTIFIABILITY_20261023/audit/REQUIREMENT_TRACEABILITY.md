# 요구사항–구현–감사 대응

이 표는 실제 연구 결과가 아니라 구현 범위 기록이다. 시험 이름과 필수 R01–R20 대응은 `../manifest.json`에서 기계적으로 검사한다.

| 계획 질문 | 구현 | 감사 시 확인/추가한 조건 |
|---|---|---|
| S0 원본 조건을 그대로 재현하는가? | `native.py`, `stages.run_s0` | clean reference SHA, staged input hash, original raw manifest, reference per-step update and full recursive parity, actual x-/P- |
| S1 현재 NOES는 어디에 오차를 추가하는가? | `diagnostics.s1`, `oracle_scoring.residual_table` | raw/all/common/own populations, c1/c2/model mismatch, signed residual strata and persistence; GT bins are diagnostic-only |
| S2 prior와 구분되는 RF 특징인가? | `runtime_features.profile_features`, `diagnostics.s2` | received RF held fixed; x/y/heading/joint perturbations; own/measured FP, invalid taps, finite sensitivity and projector rank; no claim from orthogonality alone |
| S3 잔차 목표와 POWER 조건이 맞는가? | `training.py` | six candidate contracts; original POWER teacher and P0 refit parity; identical P1–P4 labels and augmentation; train-only imputer/Omega/teacher lineage; spatial group OOF |
| S4 측정 개선이 한 번의 상태 개선인가? | `diagnostics.common_prior` | identical x-/P-/H/R and recomputed BASE common gate; actual two updates checked against -K_s c and heading/XY loss identities; angle-wrap cases marked |
| S5 차이가 긴 재귀에서 유지되는가? | `diagnostics.branch_effects`, `replay.simulate` | cloned predicted state, no double prediction; packet/block interventions then BASE suffix; future d0/H/K/P/gate recomputed independently; horizon censoring and fixed-matrix control |
| S6 자연 움직임으로 bias와 heading을 구분하는가? | `temporal.py` | train-only PSD time metric; motion-induced covariance; nuisance constant/linear/free-packet controls; initial-prior contribution separate; nonlinear profile and bias-model forecasting; no new RF yaw samples |
| S7 정확도·꼬리·신뢰도 모두 괜찮은가? | `scorecard.py`, `stages.run_s7` | per-case paired seeds, native LoS, BASE_eta2 update-only comparator, NEES1/2/3/4, coverage deviation, q95/q99/peak/episode duration, missing/failure rows retained, partial scopes explicit |

## 자동 채택하지 않는 사항

단위시험 통과는 실제 데이터 조건의 성공이 아니다. `candidate_adoption=NOT_AUTOMATIC_MECHANISM_REVIEW_REQUIRED`를 남긴다. 최종 선택에는 S3의 절대 residual 예측, S4의 prior-response 보존, S5의 실제 분기 효과와 S7의 전체 case별 결과가 모두 필요하다.

S6는 조건부 확장이다. S6 미실행은 보고서에 표시하며, 해당 결과 없이 temporal filter 또는 heading–bias 분리 성공을 주장하지 않는다.

## 기존 파일 보호

새 `research/PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023/`와 새 launcher만 추가한다. 기존 RF·FFD·LUT·POWER 모델·실험 결과·workflow를 변경하거나 삭제하지 않는다. 원 연구 브랜치에 병합하지 않고 별도 구현 브랜치로 전달한다.
