# 독립 절대 Heading 정보를 Single Anchor + DR/EKF에 융합한 민감도 시뮬레이션

2026-10-12. 완결된 수치 실험. **모든 결과는 합성 데이터**이고, 실제 RF 또는 로봇에서 추정한 Heading 수치가 아니다.

## 1. 검증 가설과 고정 조건

기존 `SINGLE_ANCHOR_MULTIPATH_CORRIDOR_20261012`의 시뮬레이터와 trajectory를 그대로 사용하고 observation update만 추가한다. 이 작업에서 구조를 변경한 것은 heading measurement `z_ψ`의 존재 유무와 분산이며, DR·Ranging·참조 경로·난수 흐름을 동일하게 유지한다. `source_git`는 `myoungsunk/sionna-resimulation`, 브랜치 `codex/range-only-bias-consistency-20261011`, `src/qclean_uwb/scenarios/corridor.py`, Git blob `eba1ab64d5e2117bfd519ceb5cac077b24caf3f8`. 이 파일의 geometry 기본값은 실제 측량값이 아닌 placeholder라고 명시되어 있다.

- 20 × 2.4 × 2.7 m 복도, 앵커 `(4,0,2.65) m`, 태그 높이 `0.45 m`, 안테나와 로봇 중심의 XY 일치
- 4개 경로, 각 10 m, 100 step, `dt=0.5 s`, 각 조건에 동일한 참 궤적/DR 제어/Ranging 관측을 이용하는 독립 반복 1000회
- 운동: 위치 step 오차 `σ_s=0.008 m`, 회전 step 오차 `σ_Δψ=0.23°`; 시작 추정 오차 XY 각 0.10 m, yaw 3°
- Range: Gaussian iid 표준편차 `σ_r=0.08 m` (3D 거리, 높이차 2.2 m)
- Heading: **world-frame 절대 heading 관측** `z_ψ=wrap(ψ_GT+σ_ψ u+b)`; `u~N(0,1)`, DR와 RF의 오차와 독립. 기본 `b=0`, σ_ψ 시나리오 0.5°,1°,2°,3°,5°,10°. 노이즈는 이전 시나리오와 독립적인 난수 시드 `seed+17`에서 발생.
- 모든 baseline 대비 method 변경은 동일 1000개 물리 궤적에서 비교. 훈련·평가 같은 Ground Truth에 맞춘 필터 튜닝 없음.

## 2. 운동, range, heading 수학 모델

### 2.1 상태 및 Prediction

$$\mathbf x_k=[x_k,\ y_k,\ \psi_k]^T.$$

입력 `Δs_k`, `Δψ_k`에서 중간 각도 `φ_k=ψ_k+Δψ_k/2`를 두면

$$x_{k+1}^-=x_k^++\Delta s_k\cos\phi_k,\qquad y_{k+1}^-=y_k^++\Delta s_k\sin\phi_k,\qquad \psi_{k+1}^-=\operatorname{wrap}(\psi_k^++\Delta\psi_k).$$

$$F_k=\begin{bmatrix}1&0&-\Delta s_k\sin\phi_k\\0&1&\Delta s_k\cos\phi_k\\0&0&1\end{bmatrix}.$$

$$G_k=\begin{bmatrix}\cos\phi_k&-\tfrac12\Delta s_k\sin\phi_k\\\sin\phi_k&\tfrac12\Delta s_k\cos\phi_k\\0&1\end{bmatrix},\quad Q_u=\mathrm{diag}(\sigma_s^2,\sigma_{\Delta\psi}^2).$$

$$P_{k+1}^-=F_kP_k^+F_k^T+G_kQ_uG_k^T.$$

### 2.2 Single Anchor Range Update

$$z_{r,k}=h_r(\mathbf x_k)+v_{r,k},\quad h_r(\mathbf x)=\sqrt{(x-4)^2+y^2+(2.65-0.45)^2},\quad R_r=0.08^2\ \mathrm{m^2}.$$

$$H_r=\begin{bmatrix}(x-4)/h_r& y/h_r&0\end{bmatrix}.$$

현재 중간선상의 주행에서는 y에 대한 1차 거리 민감도가 작거나 0이므로 range만으로 yaw 및 횡방향 drift 제약이 어렵다.

### 2.3 독립 Heading 관측 Update

$$z_{\psi,k}=\operatorname{wrap}(\psi_k+v_{\psi,k}),\qquad v_{\psi,k}\sim\mathcal N(0,R_\psi),\qquad R_\psi=(\sigma_\psi\pi/180)^2\ \mathrm{rad^2}.$$

$$H_\psi=\begin{bmatrix}0&0&1\end{bmatrix}.$$

Ranging 업데이트 다음에 적용하는 heading 혁신값:

$$\nu_{\psi,k}=\operatorname{wrap}(z_{\psi,k}-\hat\psi^-_k),\quad S_{\psi,k}=H_\psi P_k^-H_\psi^T+R_\psi,\quad K_{\psi,k}=P_k^-H_\psi^TS_{\psi,k}^{-1}.$$

$$\hat{\mathbf x}_k^+=\hat{\mathbf x}_k^-+K_{\psi,k}\nu_{\psi,k},\quad P_k^+=(I-KH)P_k^-(I-KH)^T+KR_\psi K^T.$$

각도 state는 갱신 후 다시 wrap한다. 코드의 일관성 개선은 heading observation이 세계좌표계 기준 **독립적 절대방향 정보**이기 때문에 가능하다. 상대 gyro 증가량을 `z_ψ`로 그대로 재사용하면 독립 관측이 되지 않는다.

### 2.4 가정한 측정 분산

| Heading 표준편차 `σψ` | 분산 (`deg²`) | 분산 (`rad²`) |
|---|---:|---:|
| 0.5° | 0.25 | 0.00007615 |
| 1° | 1.00 | 0.00030462 |
| 2° | 4.00 | 0.00121847 |
| 3° | 9.00 | 0.00274156 |
| 5° | 25.00 | 0.00761544 |
| 10° | 100.00 | 0.03046174 |

본 실험의 main sweep은 **참 관측 분산과 필터에 입력한 `Rψ`가 동일**하다. 따라서 정확도만 나빠지고 모델은 여전히 통계적으로 올바를 수 있다. 오차분산을 과소평가하거나 고정 편향이 존재하는 경우는 별도 stress case다.

## 3. 결과 — 센서 자체의 기여 구분 (σψ=1°, 매 0.5초)

| 경로 | DR-only RMSE | Range-only RMSE | Heading-only RMSE | Range+Heading RMSE |
|---|---:|---:|---:|---:|
| 직선 | 0.355 m | 0.340 m | 0.152 m | **0.107 m** |
| 네모 | 0.169 m | 0.113 m | 0.153 m | **0.091 m** |
| ㄹ자 | 0.185 m | 0.142 m | 0.151 m | **0.098 m** |
| 지그재그 | 0.337 m | 0.316 m | 0.152 m | **0.099 m** |

직선에서 range-only는 진행 방향 RMSE `0.0432 m`로 작지만 횡방향 `0.337 m`가 지배적이다. Heading-only는 횡방향을 `0.1002 m`까지 개선하나 진행 방향 `0.1148 m` 수준이 남는다. 양쪽 관측을 사용하면 x RMSE `0.0408 m`, y RMSE `0.0993 m`로 상호 보완된다. 일반화하려면 복도 geometry, 센서 상관, 실제 RF heading 정확도를 별도 확인해야 한다.

## 4. Heading 정확도별 2D Localization RMSE

| σψ (°) | 직선 | 네모 | ㄹ자 | 지그재그 |
|---:|---:|---:|---:|---:|
| Range-only (no heading) | 0.340 | 0.113 | 0.142 | 0.316 |
| 0.5 | 0.107 | 0.090 | 0.098 | 0.098 |
| 1 | 0.107 | 0.091 | 0.098 | 0.099 |
| 2 | 0.110 | 0.092 | 0.099 | 0.101 |
| 3 | 0.113 | 0.092 | 0.101 | 0.104 |
| 5 | 0.123 | 0.094 | 0.104 | 0.114 |
| 10 | 0.157 | 0.097 | 0.112 | 0.146 |

동일한 RF 및 DR 조건에서 Heading 관측 정밀도를 높일수록 대부분 위치 RMSE가 감소한다. 직선에서 σ 1°와 0.5° 사이의 개선은 약 0.6 mm로 작다. 1°보다 더 정밀한 sensor가 필수라는 결과는 아니다. 반대로 모든 구간에서 Rψ를 참 분산에 맞추었기 때문에, σ 10°에서도 일관성 지표는 수치적으로 대체로 양호하게 나타난다.

### 4.1 Pairwise Monte Carlo 개선율 신뢰구간

1,000개 독립 run을 반복 단위로 2,500회 paired bootstrap 재표본추출했다. 같은 주행의 `range-only`와 `range+heading`을 함께 선택해 2D RMSE 개선율 분포를 계산한다.

| 경로 | 2D RMSE 개선율 | paired bootstrap 95% 구간 |
|---|---:|---:|
| 직선 | 68.39% | [66.66%, 70.04%] |
| 네모 | 19.60% | [17.42%, 21.68%] |
| ㄹ자 | 30.90% | [28.46%, 33.31%] |
| 지그재그 | 68.75% | [67.04%, 70.40%] |

## 5. 일관성: NEES, NIS, 최종 95% 신뢰타원 포함률

$$NEES_{xy,k}=\mathbf e_{xy,k}^TP_{xy,k}^{-1}\mathbf e_{xy,k},\quad \text{FinalCoverage}_{95}=100\times\frac{\#\{i:NEES_{xy,final}^{(i)}\le5.99146\}}{1000}.$$

2D NEES 기대 평균은 2이며, 상호 독립적인 scalar range 및 heading 혁신의 NIS 기대 평균은 각각 1. 현재 σψ=1° 조건에서 측정된 평균 Heading NIS는 약 0.995, 평균 Range NIS는 약 1.00이다.

| 경로 | 기존 평균 2D NEES → heading 융합 | 기존 최종 95% 포함률 → heading 융합 |
|---|---|---|
| 직선 | 2.414 → 2.044 | 85.9% → 94.2% |
| 네모 | 2.007 → 2.022 | 95.3% → 94.1% |
| ㄹ자 | 2.042 → 2.024 | 92.4% → 95.3% |
| 지그재그 | 2.354 → 1.981 | 86.9% → 94.5% |

95% 포함률은 RMSE와 별도로 봐야 한다. 또한 마지막 coverage가 95% 근처라는 것만으로 모델이 완벽하다는 뜻은 아니다.

## 6. Measurement 주기 및 고정 bias의 효과

### 6.1 주기: σψ=1° 고정

| 관측 간격 | 직선 RMSE | 네모 RMSE | ㄹ자 RMSE | 지그재그 RMSE |
|---|---:|---:|---:|---:|
| 0.5초 (매 1 step) | 0.107 | 0.091 | 0.098 | 0.099 |
| 2.5초 (매 5 step) | 0.110 | 0.092 | 0.100 | 0.101 |
| 5.0초 (매 10 step) | 0.114 | 0.093 | 0.102 | 0.105 |

모든 시나리오는 주행 중 heading 측정이 없을 때 DR 예측으로 진행하고, 관측 시점에만 EKF를 업데이트했다. 0.5초 관측이 필수임을 의미하지는 않는다.

### 6.2 가정된 정확도는 1°인데 보정되지 않은 +2° 또는 +5° 편향이 존재한다면?

| 경로 | bias 0°: 2D RMSE / 종료 포함률 | bias +2° | bias +5° |
|---|---|---|---|
| 직선 | 0.107 m / 94.2% | 0.231 m / 10.8% | 0.520 m / 0.0% |
| 네모 | 0.091 m / 94.1% | 0.101 m / 93.7% | 0.141 m / 92.0% |
| ㄹ자 | 0.098 m / 95.3% | 0.120 m / 75.3% | 0.193 m / 8.6% |
| 지그재그 | 0.099 m / 94.5% | 0.218 m / 5.6% | 0.490 m / 0.0% |

백색 Gaussian의 `σ=1°`와 **고정된 bias +2°**는 서로 다른 오류다. 필터가 영평균 독립 오차만 가정하면 실제 바이어스를 위치 드리프트로 해석하면서 오히려 과신할 수 있다. Heading NIS가 ~1을 유지하는 것은 반복 관측을 따라 잘못된 방향을 추정할 수 있기 때문이며, NIS 하나만으로 위치 일관성을 보장하지 않는다.

## 7. 보조 스트레스: 실제 +5° 누적 yaw drift

100개의 실제 운동 step에만 `0.05°`씩 미모델링 회전을 더해 종료 시 누적 +5°를 만들었다. DR 입력은 기존 명목 회전을 유지하며 절대 heading 센서는 실제 yaw를 관측한다.

| 경로 | Range-only RMSE → heading 융합 RMSE | 종료 포함률 기존 → 추가 |
|---|---|---|
| 직선 | 0.397 → 0.107 m | 74.3% → 94.3% |
| 네모 | 0.119 → 0.091 m | 86.3% → 94.1% |
| ㄹ자 | 0.152 → 0.099 m | 88.1% → 95.6% |
| 지그재그 | 0.369 → 0.099 m | 80.3% → 94.5% |

이는 미모델링 운동오차를 절대 heading 관측이 보완할 수 있다는 합성 결과다. 실제 주행은 보수적 복도 허용 y 범위를 벗어나는 경우가 있으므로 안전·충돌 검증은 아니다.

## 8. 연구적 해석 및 외삽 제한

1. **RF 정보의 추가는 검증하지 않았다**: 그저 world-frame 절대 heading 관측이 주어진다면 어떤 개선이 가능한지를 검증했다. 실제 편파 기반 heading 추정 정확도는 향후 실측 또는 물리 기반 RF 모델로 평가해야 한다.
2. **독립성 전제**: 새 Heading을 range 또는 같은 RF CIR에서 추출한다면 교차 공분산, 공통 NLoS·편향, 시계열 상관관계를 처리해야 한다. 이번 실험처럼 별도 독립 센서로 취급하면 정보량을 과대평가할 수 있다.
3. **Gauge freedom**: 기존 상대 DR + 단일 range만으로는 전체 궤적의 앵커 중심 공통 회전 대칭이 남는다. 별도 절대 heading 관측을 제공하면 해당 대칭을 깬다. 반면 상대 yaw 증분을 또 하나 전달하는 것은 그러지 못한다.
4. **코너·벽**: 직사각형 및 ㄹ자는 이상적인 한 이동 step의 큰 회전을 포함하고, 로봇 바디의 운동역학·충돌 반응은 없다. 기본 zigzag run의 1.4%가 보수적 유효 y 영역을 벗어난다.
5. **실험 종료점의 의미**: 경로별 종료점이 서로 달라, 특히 네모의 큰 정확도는 폐곡선 운동으로 인한 DR 오차 상쇄도 포함한다.
6. **관측률의 영향**: 0.5초마다 독립 백색 heading 오차를 가정했기에 여러 시점 정보를 효과적으로 합칠 수 있다. 현실에서 지속 편향 또는 시간 상관이 크면 결과가 달라진다.
7. **공분산 정합**: 본 실험에서는 Heading 분산을 미리 정확히 알고 `Rψ`에 반영했다. 분산 설정 오류, outlier, calibration drift, lever arm 변경, 비정규 NLoS 오차는 탐구하지 않았다.

## 9. 재현, 검증, 그림

`README_KO.md`의 커맨드와 `heading_fusion.py`, `base_corridor_ekf.py`, `simulate_routes.py`를 사용한다. `qa_artifacts.py`에서 주어진 CSV·메타데이터·이미지 존재·기존 baseline 일치·coverage 횟수 등을 검증한다. 실행의 내부 비교 검사도 성공했다 (`QA_REPORT.json`). 시뮬레이션 출력은 해당 폴더에 작성되며 동일 난수 seed로 재현한다.

- `01_four_routes_heading_fusion.png` — 네 경로 추정 궤적 비교, 경로마다 paired 개선 중앙값에 가장 가까운 사례 1개씩만 시각화
- `02_precision_sweep_rmse_coverage.png` — heading sigma 변화 민감도
- `03_lateral_error_time_series.png` — 횡방향 누적 RMSE
- `04_sensor_ablation.png` — 관측의 종류별 실험
- `05_measurement_cadence.png`, `06_unmodelled_heading_bias.png`, `07_unmodelled_heading_drift.png`
- 정밀한 수치는 각 CSV, `MANIFEST.json`, `QA_REPORT.json`으로 검증 가능
