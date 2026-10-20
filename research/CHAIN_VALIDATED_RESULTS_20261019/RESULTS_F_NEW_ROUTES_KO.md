# 새 주로 Mount45 고정 후보 검증 — F 단계

실제 Run 39256517334, artifact 12188722472. 후보를 기존 검증 성능을 보고 교체하지 않고 처음 등록한6개 방법을 그대로 시험했다.

훈련은 기존 R4/R5 Mount0, 원 R2-heldout 학습분할/평균·공분산 적합/시간상관 파라미터를 사용했다. 새 RF의 정답은 센서 생성·평가·입력 LoS 점검용이며 추론에 들어가지 않았다. 새 데이터로 파라미터를 조정하지 않았다.

실제 완료 32 조건 / 192 방법별 점수, 최대 재채점 차이 1.99e-13. 직접 LoS 정합과 누락 RF 시각에서 업데이트하지 않는 것을 검사했다.

## B0 전체 주행 평가 (t>=30s)

| Case | Method | signed° | RMSE° | sigma RMS° | heading95 | NEES |
|---|---|---:|---:|---:|---:|---:|
| C01_A_M45_FULL | JOINT4 | 2.0516 | 2.9693 | 0.9263 | 42.14% | 10.6696 |
| C01_A_M45_FULL | POWER1 | 2.8339 | 4.2692 | 0.9159 | 32.53% | 21.3456 |
| C01_A_M45_FULL | POWER_MEMORY | 0.9333 | 1.7949 | 1.2179 | 77.82% | 2.6405 |
| C01_A_M45_FULL | POWER_MEMORY_NO_CROSS | 1.7949 | 2.8579 | 0.8961 | 41.59% | 11.7744 |
| C01_A_M45_FULL | POWER_SR4 | 2.8458 | 4.2740 | 0.9142 | 32.90% | 21.3442 |
| C01_B_M45_FULL | JOINT4 | -5.8381 | 6.6279 | 1.1430 | 22.92% | 105.1927 |
| C01_B_M45_FULL | POWER1 | -4.4322 | 4.9100 | 0.8273 | 19.96% | 52.5458 |
| C01_B_M45_FULL | POWER_MEMORY | -1.4388 | 2.3504 | 0.8689 | 67.47% | 7.8379 |
| C01_B_M45_FULL | POWER_MEMORY_NO_CROSS | -3.1987 | 3.4687 | 0.7397 | 19.96% | 38.7060 |
| C01_B_M45_FULL | POWER_SR4 | -4.4334 | 4.9037 | 0.8264 | 19.96% | 52.4587 |
| C02_A_M45_FULL | JOINT4 | -1.2053 | 1.7139 | 0.7077 | 57.64% | 5.1384 |
| C02_A_M45_FULL | POWER1 | -1.2705 | 1.9953 | 0.9129 | 61.16% | 4.5184 |
| C02_A_M45_FULL | POWER_MEMORY | -1.2243 | 2.0237 | 1.0999 | 64.15% | 3.1490 |
| C02_A_M45_FULL | POWER_MEMORY_NO_CROSS | -1.8555 | 2.2125 | 0.8394 | 48.68% | 5.7443 |
| C02_A_M45_FULL | POWER_SR4 | -1.3268 | 2.0348 | 0.9127 | 58.70% | 4.6720 |
| C02_B_M45_FULL | JOINT4 | -2.6300 | 3.0761 | 0.7035 | 18.28% | 26.7127 |
| C02_B_M45_FULL | POWER1 | -0.5860 | 1.2699 | 0.5752 | 73.99% | 3.7277 |
| C02_B_M45_FULL | POWER_MEMORY | -0.3966 | 1.0003 | 0.6965 | 78.73% | 1.4599 |
| C02_B_M45_FULL | POWER_MEMORY_NO_CROSS | -0.4807 | 0.9532 | 0.5508 | 74.87% | 2.5128 |
| C02_B_M45_FULL | POWER_SR4 | -0.6151 | 1.2709 | 0.5747 | 73.99% | 3.7456 |
| C03_A_M45_FULL | JOINT4 | 0.0631 | 0.8935 | 0.6866 | 80.15% | 2.1637 |
| C03_A_M45_FULL | POWER1 | -0.0836 | 0.5835 | 0.5915 | 98.98% | 0.7907 |
| C03_A_M45_FULL | POWER_MEMORY | -0.7914 | 1.4643 | 0.7197 | 81.18% | 1.7368 |
| C03_A_M45_FULL | POWER_MEMORY_NO_CROSS | 0.0087 | 0.4505 | 0.5344 | 97.82% | 0.8151 |
| C03_A_M45_FULL | POWER_SR4 | -0.0820 | 0.5856 | 0.5912 | 98.98% | 0.7935 |
| C03_B_M45_FULL | JOINT4 | -0.2445 | 1.2744 | 0.6686 | 49.68% | 5.8946 |
| C03_B_M45_FULL | POWER1 | -0.4834 | 0.7099 | 0.5548 | 63.51% | 3.7949 |
| C03_B_M45_FULL | POWER_MEMORY | -0.2516 | 0.5251 | 0.6838 | 98.46% | 0.7751 |
| C03_B_M45_FULL | POWER_MEMORY_NO_CROSS | -0.3443 | 0.5346 | 0.5371 | 87.71% | 1.9930 |
| C03_B_M45_FULL | POWER_SR4 | -0.4812 | 0.7058 | 0.5569 | 63.51% | 3.7846 |
| O01_O0_M45_FULL | JOINT4 | -0.5515 | 0.7369 | 0.5936 | 85.63% | 2.1220 |
| O01_O0_M45_FULL | POWER1 | -0.2509 | 0.4601 | 0.4744 | 92.38% | 1.0996 |
| O01_O0_M45_FULL | POWER_MEMORY | -0.2825 | 0.4371 | 0.6129 | 99.71% | 0.5708 |
| O01_O0_M45_FULL | POWER_MEMORY_NO_CROSS | -0.0411 | 0.3003 | 0.4450 | 98.83% | 0.4796 |
| O01_O0_M45_FULL | POWER_SR4 | -0.2398 | 0.4550 | 0.4744 | 92.67% | 1.0689 |
| O02_O0_M45_FULL | JOINT4 | -5.2209 | 7.7814 | 0.9456 | 1.50% | 67.9345 |
| O02_O0_M45_FULL | POWER1 | -0.3316 | 2.1205 | 0.8060 | 41.90% | 8.4780 |
| O02_O0_M45_FULL | POWER_MEMORY | 0.0746 | 1.6135 | 0.9867 | 57.86% | 4.4491 |
| O02_O0_M45_FULL | POWER_MEMORY_NO_CROSS | -0.0576 | 1.5718 | 0.7728 | 49.88% | 6.9332 |
| O02_O0_M45_FULL | POWER_SR4 | -0.3361 | 2.1279 | 0.8063 | 42.89% | 8.5299 |

## 전체 Bias 집계

[
  {
    "group": "all",
    "conditions": 32,
    "memory_rmse_improved_gt01pct": 26,
    "memory_rmse_worse_gt10pct": 3,
    "mean_relative_rmse": -0.1012437466621747,
    "median_heading95_base": 0.6357234314980793,
    "median_heading95_memory": 0.7827673805911723
  },
  {
    "group": "corridor",
    "conditions": 24,
    "memory_rmse_improved_gt01pct": 18,
    "memory_rmse_worse_gt10pct": 3,
    "mean_relative_rmse": -0.08561436669858208,
    "median_heading95_base": 0.6357234314980793,
    "median_heading95_memory": 0.7827673805911723
  },
  {
    "group": "office",
    "conditions": 8,
    "memory_rmse_improved_gt01pct": 8,
    "memory_rmse_worse_gt10pct": 0,
    "mean_relative_rmse": -0.14813188655295262,
    "median_heading95_base": 0.6726000248645249,
    "median_heading95_memory": 0.8027731258364352
  }
]

이 통계는 동일 RF 조건에 B0/L0/L1/L2 센서 모델을 적용한 기술통계다. corridor C01/C02/C03은 같은 기존 장면, office O01/O02는 같은 오피스 하나이므로 다섯 개 독립 장면이 아니다. dt=.25s synthetic controls 전체를 예측에 사용하고 지정 RF 시점만 갱신했다. 일부 열화 또는 모델 NO-GO는 삭제하지 않았다. 새 경로의 직선·회전 구간도 EXTERNAL_SCORES.csv에 보존한다.

[Full artifact](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39256517334/artifacts/12188722472)

## 납품·판정 범위

{
  "cases_expected": 8,
  "cases_scored": 8,
  "bias_conditions_expected": 32,
  "method_condition_rows": 192,
  "errors": [],
  "candidate_tuned_on_new_data": false,
  "same_corridor_routes_vs_one_office_scene": "not five independent physical scenes"
}
