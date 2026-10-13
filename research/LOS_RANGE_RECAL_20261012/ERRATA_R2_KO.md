# ERRATA R2 — R1(P0~P5) 문서의 정정 (R1 파일은 수정하지 않음)

작성: 2026-10-13. 외부 코드 감사 + 직접 코드 대조 결과. 영향 파일: `out_p0_p5/R1/P0_P5_GATES_SUMMARY_KO.md`, `P3/P3_LEAKAGE_TESTS.json`, `P3/P3_DECISION.md`, `P4/P4_GATE.md`, `P5/P5_GATE.md`.

| # | 정정 대상 | 기존 서술 | 정정 |
|---|---|---|---|
| E1 | P3 leakage 테스트 | `all_pass: true` | `fold_params_recorded_for_train_only`는 `loro_fold_params`에 R2/R4/R5 키가 **존재하는지만** 검사한다. "학습 fold에 평가 label이 없다"는 검증은 수행되지 않았고, 스크립트 docstring (4)와 주석의 refit 비교는 미구현. 이 항목은 **UNVERIFIED**. 나머지(predict 서명, 특징명, 라벨 섞기에 대한 예측 불변)는 유효하나, 라벨 섞기 테스트는 입력 H가 같으므로 `predict`가 라벨을 안 읽는다는 것만 보인다 |
| E2 | P3 pooled "site-weighted" | 전역 site 가중 | fold 내부는 (case,site) MSE 평균이나 fold 합산은 pose 수 n 가중(`p3_detector_candidates.py:58`). 전역 site 균등 재계산은 `P3_RECOMPUTE_GLOBAL_SITE_WEIGHT.json`(R2-4a) 참조 |
| E3 | P5 일관성 문구 | "BEST_PLUS_R_IAT … 'not worse than A'" | **철회**. CI가 0을 포함한다는 것은 동등/비열등의 증거가 아니다. 허용 한계를 사전 동결한 TOST 없이는 "A_DR보다 나쁘지 않다"고 쓰지 않는다 |
| E4 | P5 CI의 의미 | bootstrap 95 % CI | 12개 조건을 재표본한 것이며 기하는 단일 scene 3 route다. 이 시뮬레이션 harness 안의 비교 불확실성이지 다른 환경에 대한 일반화 CI가 아니다 |
| E5 | P5 "128 seed" | 128 seed × … = 36,864 run | 12 케이스의 RF 관측 시계열은 케이스당 **고정 1개**(`OBS/<case>_full.npz`, 노이즈 없는 `observe(H,freqs,None,None)`). seed는 센서(sensor-v2 `V.generate`)와 초기 pose 오프셋만 바꾼다. 독립 RF 실현 12개, 독립 range 측정 잡음 0개. 36,864 run은 서로 독립 표본이 아니다. 상세: `P5_AUDIT_R2_1_KO.md` |
| E6 | P4 vs P5 계수 | P5가 P4의 E1을 검증 | P4는 전체 route fit 계수, P5는 route 하나를 뺀 fold 계수. 서로 다른 계수 집합이므로 P5는 "P4 동결 모델의 EKF 성능"이 아니다 |
| E7 | P4 LoS | LoS와 Full 모두 평가 | LoS 열은 B만 채점(`p4_blind_range_eval.py` `if ch=='los': arms=['B']`). chosen(E1)의 LoS 성과는 채점된 적이 없다(R2-4c에서 별도 보고) |
| E8 | P5 입력 | 온라인 E1 | E1 correction은 noise-free H에서 사전 계산(`p5_arm_ranges.py` `det_for`). EKF 수준의 온라인 noisy-feature 성능은 미검증 |
| E9 | BEST_PLUS_R_IAT | 독립 | IAT=5.8은 V05에서 동일 3 route로 추정. 누수(경미). fold-wise 재추정 전까지 "참고용 arm" |
| E10 | 보존 | — | per-run trace와 resumable driver는 원래 미보존. driver(`p5_confirm_driver.sh`)는 R2-1에서 repo에 복사(`tools/`) |

## 고정되는 허용 주장 문구
"동일 scene·동일 3 route 시뮬레이션 harness 안에서, 조건부 편향 모델(E1)은 고정 오프셋 대비 위치/heading 오차를 줄였다. 어떤 arm도 필터 일관성을 확립하지 못했다(RF off인 A_DR도 불일치). 다른 scene·Native EKF·실측으로의 일반화는 미검증."

## 추가 정정 (R2-1/R2-4 계산 후)
| # | 내용 |
|---|---|
| E11 | "B_OLD는 RF 없음(A_DR)보다 나쁘다"는 풀링 평균 결과다. 36 셀(12 RF 시리즈 × 3 drift) 중 B_OLD가 A_DR보다 나쁜 셀은 **23/36**. 모든 조건에서 성립하는 주장이 아니다 (`out_R2/P5_EFFECTIVE_SAMPLE_AUDIT.json`) |
| E12 | E_COND가 B_OLD보다 위치 RMSE가 작은 셀은 **36/36**, BEST_PLUS_R_IAT는 35/36. 방향 일관성은 강하지만, 독립 단위는 4,608 run이 아니라 36 셀(실질 RF 시리즈 12개)이며 run 수준 설계효과(design effect)가 25~68 → 유효 run 수 ≈ 70~190 |
| E13 | P4 LoS-only 채널에서 E1(chosen)을 채점하면 B 대비 RMSE **+36~42 %** (예: noise-free 0.0483→0.0685 m, CI [+30, +53] %). E1은 Full-RF(다중경로 포함) 잔차로 학습된 보정이며 LoS-only 채널에서는 과보정된다(평균 오차 −0.044 m). "E1이 LoS detector 편향을 고쳤다"로 읽으면 안 된다 (`out_R2/P4_LOS_CHOSEN_SCORED.json`) |
