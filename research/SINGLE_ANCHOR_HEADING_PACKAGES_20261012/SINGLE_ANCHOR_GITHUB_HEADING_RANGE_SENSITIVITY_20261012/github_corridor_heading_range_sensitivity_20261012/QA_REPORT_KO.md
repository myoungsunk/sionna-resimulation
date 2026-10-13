# QA — 실행 및 파일 검증

| 항목 | 상태 | 근거 |
|---|---|---|
| 기본값 재현 | PASS | 기존 GitHub 복도 `methods_summary.csv`와 RMSE/NIS/95% coverage 정합 (오차 1e-6 이내) |
| 500회·100 step / 37 조건 | PASS | all_scenarios.csv 37행, RUN_MANIFEST.json 시나리오 수 일치 |
| heading 관측 기하 점검 | PASS | 가운데 태그 3D 거리 모델에는 yaw 항이 없음; 초기/주행 yaw 오차 설정에서 측정 noise RMS 동일 |
| bias 보정 sanity | PASS | +0.20m 합성 편향을 독립 sample로 보정 후 기준 RMSE 복원 (차이 0.005m 이내) |
| 수치 검사 | PASS | 모든 EKF NIS/NEES/RMSE 값 유한, covariance Joseph-form은 기존 코드 사용 |
| 그래프 생성 | PASS | 5개 PNG 파일 생성 확인 |
| GT 허용영역 위반 기록 | PASS | all_scenarios.csv에 scenario별 비율 기록; 높은 yaw drift는 일부 비현실적 경로 포함 |
| 외부 RF/RT 모델 실재 검증 | NOT RUN | synthetic RF proxy만 사용, 별도 Sionna 실행은 수행하지 않음 |
| 독립적인 실측 데이터 검증 | NOT RUN | 본 실험은 시뮬레이션만 대상으로 함 |

숫자의 물리적 의미에 대한 검증과 코드 실행 성공을 혼동하지 마십시오. 실측 또는 Sionna에서 실제 RF range error가 나오면 가상 오차모델을 교체해야 합니다.
