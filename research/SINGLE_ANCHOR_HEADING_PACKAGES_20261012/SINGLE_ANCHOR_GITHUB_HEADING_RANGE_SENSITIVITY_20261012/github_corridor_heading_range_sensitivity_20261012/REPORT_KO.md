# GitHub 복도 단일 앵커 Range-only + DR/EKF: Heading 및 Ranging 오차 민감도

## 실험 환경

- 출처: `myoungsunk/sionna-resimulation`의 `src/qclean_uwb/scenarios/corridor.py`, `codex/range-only-bias-consistency-20261011` (원본 수치 자체가 실측이 아닌 placeholder).
- 복도 20×2.4×2.7m, 앵커 (4,0,2.65)m, 태그 z=0.45m, 로봇 (4,0)→(14,0) 10m 직진.
- 0.1 m/step, 100 step, 0.5s/step, Monte Carlo 500 independent runs, seed 20261012.
- 초기 heading sigma=3°, 상대 DR yaw sigma=0.23°/step, 이동 sigma=0.008m/step, ranging noise sigma=0.08m (기본값).
- **RF 측정 전파/다중경로는 계산하지 않음.** 자의적인 angle-bias 함수는 설명용 가상 proxy임.
- Range EKF는 기본적으로 `R=(0.08m)^2`를 가정, `R1`만 실제 Gaussian 표준편차에 맞게 R 조절.
- 복도 벽은 시각화 및 위반 확인 용도로만 활용함(충돌/운동 제약 미구현).
- 모델 공분산 기준: 평균 NIS 1, 평균 2D NEES 2, 2D 95% coverage 목표 95%.

## A. Heading -> ranging / localization

중앙 태그 위치에서 **기하 거리**는 heading에 직접 의존하지 않음: $r=\sqrt{(x-4)^2+y^2+2.2^2}$, 따라서 $\partial r/\partial\psi=0$ (고정 위치). Heading 오차는 DR 이동을 통해 위치를 변경하여 간접적으로 측정 거리와 위치 오차에 영향을 줄 수 있음. 추가 RF 효과는 검증되지 않은 angle-bias proxy로 독립 분리.

### A1. 초기 heading prior 표준편차 변화

| description                   |   range_rmse_m |   ekf_rmse_2d_m |   ekf_nees_xy_mean |   ekf_nis_mean |
|:------------------------------|---------------:|----------------:|-------------------:|---------------:|
| initial heading sigma=0.5 deg |          0.080 |           0.167 |              2.017 |          1.005 |
| initial heading sigma=1 deg   |          0.080 |           0.189 |              2.030 |          1.005 |
| initial heading sigma=3 deg   |          0.080 |           0.351 |              2.524 |          1.005 |
| initial heading sigma=6 deg   |          0.080 |           0.651 |              8.034 |          1.005 |

### A2. 상대 heading의 매 스텝 Gaussian 오차

| description                 |   range_rmse_m |   ekf_rmse_2d_m |   ekf_nees_xy_mean |   ekf_nis_mean |
|:----------------------------|---------------:|----------------:|-------------------:|---------------:|
| heading sigma/step=0.05 deg |          0.080 |           0.330 |              2.406 |          1.005 |
| heading sigma/step=0.1 deg  |          0.080 |           0.334 |              2.424 |          1.005 |
| heading sigma/step=0.23 deg |          0.080 |           0.351 |              2.524 |          1.005 |
| heading sigma/step=0.35 deg |          0.080 |           0.377 |              2.701 |          1.005 |

### A3. 필터가 모델링하지 않은 누적 DR yaw bias

| description                                      |   range_rmse_m |   ekf_rmse_2d_m |   ekf_nees_xy_mean |   ekf_nis_mean |
|:-------------------------------------------------|---------------:|----------------:|-------------------:|---------------:|
| actual heading drift=0 deg/step (model omits)    |          0.080 |           0.351 |              2.524 |          1.005 |
| actual heading drift=0.01 deg/step (model omits) |          0.080 |           0.354 |              2.566 |          1.005 |
| actual heading drift=0.03 deg/step (model omits) |          0.080 |           0.374 |              2.780 |          1.005 |
| actual heading drift=0.05 deg/step (model omits) |          0.080 |           0.408 |              3.181 |          1.005 |

### A4. **가정**한 RF 방향별 거리 편향 함수

$b_{RF}(\psi,\beta)=A(d_{xy}/r)\cos[2(\psi-\beta)]$. A는 물리적으로 측정된 값이 아니며, Sionna나 DW1000 수신기의 추정 곡선이 아님.

| description                                 |   range_rmse_m |   ekf_rmse_2d_m |   ekf_nees_xy_mean |   ekf_nis_mean |
|:--------------------------------------------|---------------:|----------------:|-------------------:|---------------:|
| illustrative RF angle-bias amplitude=0 m    |          0.080 |           0.351 |              2.524 |          1.005 |
| illustrative RF angle-bias amplitude=0.05 m |          0.090 |           0.357 |              6.676 |          1.007 |
| illustrative RF angle-bias amplitude=0.1 m  |          0.116 |           0.369 |             16.540 |          1.014 |
| illustrative RF angle-bias amplitude=0.2 m  |          0.186 |           0.408 |             53.452 |          1.039 |

## B. Ranging -> localization

### B1. Gaussian white ranging noise (R 정합)

| description                               |   range_rmse_m |   ekf_rmse_2d_m |   ekf_nees_xy_mean |   ekf_nis_mean |
|:------------------------------------------|---------------:|----------------:|-------------------:|---------------:|
| Gaussian ranging sigma=0.03 m (matched R) |          0.030 |           0.351 |              3.540 |          1.005 |
| Gaussian ranging sigma=0.08 m (matched R) |          0.080 |           0.351 |              2.524 |          1.005 |
| Gaussian ranging sigma=0.15 m (matched R) |          0.150 |           0.351 |              2.251 |          1.005 |
| Gaussian ranging sigma=0.3 m (matched R)  |          0.301 |           0.354 |              2.087 |          1.005 |

### B1b. 실제 ranging noise에 비해 EKF가 R을 과소평가

| description                                          |   range_rmse_m |   ekf_rmse_2d_m |   ekf_nees_xy_mean |   ekf_nis_mean |
|:-----------------------------------------------------|---------------:|----------------:|-------------------:|---------------:|
| Gaussian ranging sigma=0.15 m but EKF assumes 0.08 m |          0.150 |           0.354 |              3.890 |          3.421 |
| Gaussian ranging sigma=0.3 m but EKF assumes 0.08 m  |          0.301 |           0.368 |              9.585 |         13.544 |

### B2. 비보정 상수 range bias

| description                |   range_rmse_m |   ekf_rmse_2d_m |   ekf_nees_xy_mean |   ekf_nis_mean |
|:---------------------------|---------------:|----------------:|-------------------:|---------------:|
| constant range bias -0.2 m |          0.216 |           0.427 |             61.809 |          1.475 |
| constant range bias +0 m   |          0.080 |           0.351 |              2.524 |          1.005 |
| constant range bias +0.1 m |          0.128 |           0.396 |             23.607 |          1.102 |
| constant range bias +0.2 m |          0.215 |           0.485 |             81.894 |          1.372 |
| constant range bias +0.5 m |          0.506 |           0.867 |            498.262 |          2.965 |

### B3. 거리 비례 scale bias

| description                         |   range_rmse_m |   ekf_rmse_2d_m |   ekf_nees_xy_mean |   ekf_nis_mean |
|:------------------------------------|---------------:|----------------:|-------------------:|---------------:|
| range scale bias +1% of 3D distance |          0.101 |           0.361 |              9.739 |          1.016 |
| range scale bias +3% of 3D distance |          0.202 |           0.413 |             56.271 |          1.100 |
| range scale bias +5% of 3D distance |          0.320 |           0.493 |            145.941 |          1.269 |

### B4. 시간적 상관 AR(1) noise

| description                                               |   range_rmse_m |   ekf_rmse_2d_m |   ekf_nees_xy_mean |   ekf_nis_mean |
|:----------------------------------------------------------|---------------:|----------------:|-------------------:|---------------:|
| AR(1) temporal correlation rho=0, nominal sigma=0.08 m    |          0.080 |           0.351 |              2.524 |          1.005 |
| AR(1) temporal correlation rho=0.9, nominal sigma=0.08 m  |          0.079 |           0.366 |              7.234 |          0.594 |
| AR(1) temporal correlation rho=0.98, nominal sigma=0.08 m |          0.077 |           0.371 |             10.251 |          0.267 |

### B5. 양의 이상치(no gating)

| description                            |   range_rmse_m |   ekf_rmse_2d_m |   ekf_nees_xy_mean |   ekf_nis_mean |
|:---------------------------------------|---------------:|----------------:|-------------------:|---------------:|
| positive outliers p=1% amplitude=0.5 m |          0.094 |           0.352 |              2.904 |          1.351 |
| positive outliers p=5% amplitude=0.5 m |          0.137 |           0.358 |              5.374 |          2.769 |
| positive outliers p=5% amplitude=1 m   |          0.236 |           0.374 |             12.433 |          8.035 |

### B6. 독립적인 상수 bias calibration (1000 sample)

| description                                                                  |   range_rmse_m |   ekf_rmse_2d_m |   ekf_nees_xy_mean |   ekf_nis_mean |
|:-----------------------------------------------------------------------------|---------------:|----------------:|-------------------:|---------------:|
| 0.20 m bias, 1000 independent calibration samples; 4-state residual-bias EKF |          0.080 |           0.351 |              2.506 |          1.005 |

## 전 조건 상세 수치

`all_scenarios.csv`의 33개 시나리오에 `RMSE_x`, `RMSE_y`, 전체/최종 `RMSE_2D`, NIS, NEES, 95% coverage, GT 복도 허용범위 위반률을 수록. 전체구간 RMSE에는 step 1~100, 최종은 step100만 포함.

## QA

{
  "baseline_match": true,
  "heading_independent_geometric_ranging": true,
  "calibration_sanity": true,
  "finite_metrics": true,
  "plots_computed": true
}

## 재현

```bash
python3 -m pip install -r requirements.txt
python3 sensitivity_study.py --runs 500 --seed 20261012
```

`../github_corridor_sim/corridor_sim.py`의 원본 EKF 함수를 직접 import. 패키지로 독립 실행하려면 `github_corridor_sim/corridor_sim.py`를 현재 폴더와 같은 상위 디렉터리로 풀거나, 아래 ZIP에 포함된 패키지용 폴더 계층을 그대로 유지.

## Heading 경로 굴곡과 기하 거리 변화 (동일 난수 구동)

|   gyro_bias_deg_per_step |   accumulated_bias_deg |   final_xy_shift_rms_m |   final_geometric_range_shift_rms_m |   overall_geometric_range_shift_rms_m |   final_geometric_range_shift_mean_m |
|-------------------------:|-----------------------:|-----------------------:|------------------------------------:|--------------------------------------:|-------------------------------------:|
|                 0.000000 |               0.000000 |               0.000000 |                            0.000000 |                              0.000000 |                            -0.000000 |
|                 0.010000 |               1.000000 |               0.087210 |                            0.000637 |                              0.000259 |                            -0.000121 |
|                 0.030000 |               3.000000 |               0.261611 |                            0.002177 |                              0.000877 |                            -0.001106 |
|                 0.050000 |               5.000000 |               0.435961 |                            0.004388 |                              0.001746 |                            -0.003081 |

복도 충돌·맵 기반 제약은 미사용. 위 최종 위치 변화는 heading bias가 없는 실제 GT와 비교한 값이며 EKF 오차가 아님.
