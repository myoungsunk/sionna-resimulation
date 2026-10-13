# Dual Heading: Heading 1 Bias × Heading 2 표준편차 5×5

경로 4개 × bias 5 × RF sigma 5 = 100개 실험 × Monte Carlo 1000회.

## 주요 파일

- `REPORT_KO.md`: 네 경로의 5×5 × 3개 평가 지표 수치표.
- `bias1_vs_sigma2_all_routes.csv`: 100개 조건의 자세한 수치.
- `unbiased_heading1_reference.csv`: Heading 1 bias=0° 기준선.
- `all_routes_5x5_overview.png`: 4개 경로 × 3개 지표 매트릭스.
- `heatmap_{route}_three_metrics.png`: 경로별 확대 heatmap.
- `precision_vs_dr_bias_all_routes.png`: 표준편차와 bias 효과 곡선.
- `straight_four_corner_trajectory_examples.png`: 네 극단 조건의 예시 궤적.
- `dual_heading_sim_extended.py`: 센서 생성·EKF core, 과거 시뮬레이션에서 동일하게 복사.
- `run_grid.py`: 본 grid 실행 및 결과 생성.
- `CONFIG.json` / `MANIFEST.json` / `qa_checkpoints.json`: 설정·검증·해시 감사.

## 실행

```bash
python -m pip install numpy pandas matplotlib
python run_grid.py --runs 1000 --seed 20261012
```

## 유의 사항

- Heading 2 bias는 모든 실험에서 0°이고, 표에 표시한 0.5/1/2/5/10은 **표준편차**입니다.
- Heading 1 bias는 100 step 전체에 누적되는 미보정 회전 바이어스입니다.
- RF 절대 Heading 관측은 가상 가정이며 단일 앵커가 이를 제공하는지는 검증 대상입니다.
- Dual-LP 또는 Sionna 채널 생성은 사용하지 않았습니다.
- 복도 형상은 GitHub의 비실측 기본 치수를 사용했습니다.