# Single Anchor + DR/EKF — 독립 절대 Heading 관측 추가 연구

**실제 실행 완료: 2026-10-12, NumPy 합성 시뮬레이션, 각 조건 Monte Carlo 1,000회.** 실측이나 Sionna RF 채널 기반 추정이 아닙니다.

## 한눈에 보는 결과

GitHub 복도 `(20, 2.4, 2.7) m`, 앵커 `(4,0,2.65) m`, 로봇 태그 z=0.45 m. 기존 주행 4개(직선·네모·ㄹ자·지그재그)를 **변경하지 않고**, world-frame 절대 heading 측정을 각 0.5초마다 추가하여 `DR`, `DR+range`, `DR+heading`, `DR+range+heading`을 비교했습니다.

- UWB ranging: `σ_r=0.08 m` (독립 백색 Gaussian)
- DR 이동 오차: `σ_Δs=0.008 m/step`, 상대 회전 오차 `σ_Δψ=0.23°/step`
- 초기 pose prior: xy 각각 0.10 m, heading 3° 표준편차
- 가상 **절대** heading 관측: `z_ψ=wrap(ψ_GT+v)`, `v~N(0,σ_ψ²)`. 기존 DR·range noise와 독립
- 정확도 조사: `σ_ψ={0.5,1,2,3,5,10}°` 및 **필터 Rψ도 그에 맞게** 설정
- 추가 조사: heading 관측 주기 0.5/2.5/5.0초, 미보정 +2/+5° sensor bias, 실제 운동에 미모델링 +5° yaw drift

| 경로 | Range-only RMSE | +절대 Heading σ=1° RMSE | 개선 | 최종 위치 95% 포함률: 기존 → 추가 |
|---|---:|---:|---:|---:|
| 직선 | 0.340 m | 0.107 m | 68.4% | 85.9% → 94.2% |
| 네모 | 0.113 m | 0.091 m | 19.6% | 95.3% → 94.1% |
| ㄹ자 | 0.142 m | 0.098 m | 30.9% | 92.4% → 95.3% |
| 지그재그 | 0.316 m | 0.099 m | 68.7% | 86.9% → 94.5% |

**주의:** 이 결과는 새로운 heading 센서가 독립적인 절대방향 정보를 실제로 제공한다는 **가정** 하에서 얻은 성능입니다. Dual-LP, RF heading 또는 range에서 heading을 추론하는 센서는 포함하지 않았습니다. 특히 오차의 고정 편향·시간 상관·DR과의 오차 상관이 있으면 결과가 달라질 수 있습니다.

## 필수 그림

- `01_four_routes_heading_fusion.png`: 4개 경로 GT / DR / Range-only / Range+Heading 비교. 각 경로의 1,000회 중 paired RMSE 개선의 **중앙값에 가장 가까운 실행**을 시각화 대상으로 선택했습니다. 선정된 run ID는 `illustrative_run_selection.csv`에 공개합니다. 이 그림의 단일 실행을 Monte Carlo 성능으로 해석하지 마세요.
- `02_precision_sweep_rmse_coverage.png`: 0.5–10° heading 정확도에 따른 RMSE_y, RMSE_2D, Heading RMSE, 종료 coverage
- `03_lateral_error_time_series.png`: 경로별 1,000회 기반 RMSE_y 시간적 누적
- `04_sensor_ablation.png`: DR / range / heading / combined 기여 분리
- `05_measurement_cadence.png`: heading 관측 간격의 영향
- `06_unmodelled_heading_bias.png`: heading bias가 정확도와 coverage를 무너뜨리는 위험
- `07_unmodelled_heading_drift.png`: 실제 미모델링 yaw drift 5° 스트레스 결과

## 주요 데이터

- `heading_precision_sweep.csv`: σ=0.5°, 1°, 2°, 3°, 5°, 10° 및 range-only/DR 기준 모두 포함
- `method_ablation.csv`: σ=1°에서 네 가지 필터 분리 평가
- `heading_update_cadence.csv`: 1/5/10 step마다 측정
- `heading_persistent_bias.csv`: 0°/+2°/+5° 고정 bias
- `unmodelled_heading_drift.csv`: 실제 주행이 5° 휘어지는 경우 range-only vs 융합
- `paired_bootstrap_summary.csv`: 동일 물리 주행의 paired 95% bootstrap RMSE 개선 신뢰구간
- `final_coverage_per_run.csv`: 4개 경로 × 2개 방법 × 1000회 최종 GT, 추정값, P, NEES, 포함 여부
- `sample_trajectories_run0.csv`: 사전 결정 run #0 4개 필터
- `illustrative_selected_paths.csv` / `illustrative_run_selection.csv`: 경로 그림에 사용된 대표 실행 및 선택 기준

## 실행

```bash
python3 -m pip install -r requirements.txt
python3 heading_fusion.py --runs 1000 --seed 20261012
# 검증 CSV만 재계산해 확인하고 PNG 재생성은 생략
python3 heading_fusion.py --runs 1000 --seed 20261012 --skip-plots
python3 qa_artifacts.py
```

재현성 검증은 `qa_artifacts.py`, `QA_REPORT.json` 및 `MANIFEST.json`을 참조하세요. 기존 환경 소스 스냅샷(`base_corridor_ekf.py`,`simulate_routes.py`)도 동봉했습니다.

## 해석 범위

- Heading 측정은 **세계좌표 기준 절대값**이며, gyro 적분과 다른 정보입니다. 절대 heading 없이 동일한 DR yaw를 다른 이름으로 이중 입력하면 결과를 재현할 수 없습니다.
- 원래 GitHub `CorridorSetup`의 치수는 측량값이 아닌 시각화용 placeholder입니다.
- 네모와 ㄹ자는 방향 전환·반복 주행으로 오차가 상쇄될 수 있어, 단순 최종 RMSE만으로 관측가능성 개선을 주장하지 않습니다.
- 코너는 이상화된 동작이며 주행 중 충돌 반응·벽 위치 제약은 없습니다. 정상 지그재그 GT 1.4%, +5° drift에서는 직선 7.7%와 지그재그 17.9%의 run이 보수적 로봇 통행 영역을 벗어납니다.
- **95% 최종 포함률**: 독립 run 1,000개에서 최종 2D NEES `e_xyᵀ P_xy⁻¹ e_xy ≤ 5.991`를 만족하는 비율입니다. 높은 포함률 하나만으로 높은 위치 정확도를 뜻하지 않습니다.

자세한 수식과 연구상 해석은 `REPORT_KO.md`를 참고하세요.
