# R5 거울해 진단에 필요한 데이터

R5에서 독립 잡음으로 처리했을 때 회복된 이유를 확인하려면, 첫 앵커 통과 전후의 참값 기준 편파 잔차와 두 필터의 갱신량을 `pose_id`와 `t`로 맞춰 비교한다. 이 자료는 앵커 B, B0, mount 0°, Full RF seed 10에 해당한다.

| 확인할 항목 | 자료 | 비교할 값 |
|---|---|---|
| 편파와 거리 잔차의 시간 상관 | [D2 패킷별 배열](../../continuation_d2_d3/d2/B_B0_R5.npz) · [D2 구간별 결과](../../continuation_d2_d3/d2/RESULTS.json) | `truth_residual_r_s`, `standardized_truth_residual_r_s`, 수용 순서 기준 자기상관 시간 |
| 느린 성분의 크기와 시간 척도 | [D3 분해 배열](../../continuation_d2_d3/d3/B_B0_R5.npz) · [V8 거리별 분산](../../continuation_ks/run_03/V8.json) | `slow`, `fast`, `decomposition_support`, `arc_m`, `yaw_arc_rad` 및 V8의 R5 donor 예측/측정 분산 비 |
| 첫 통과 전 갱신과 반대쪽 고착 | [느린 상관 trace](run_01/R5_distance.npz) · [독립 잡음 trace](run_01/R5_distance_independent.npz) · [E0-LORO 기준선](../../attempt_02/d5/B_B0_R5.npz) | `V_l_op`, `Reff`, `prior`, `H`, `K`, `nu`, `x`, `P`, `mask`. 참값은 [동결 Release](https://github.com/myoungsunk/sionna-resimulation/releases/tag/fp-sc-original-npz-20261108)의 `R5_B0_Full_10__evaluator.npz`에 있음 |

D2의 첫 0–20초 구간에서 표준화한 편파 잔차의 적분 자기상관 시간은 9.62패킷이었다. V8에서 거리 단독 donor가 예측한 느린 분산은 R5 평가 잔차의 1.5–3 m, 3–6 m, 6–10 m 구간에서 각각 3.12배, 3.08배, 1.57배였다. C5에서 빠른 항과 주변 분산을 유지하며 느린 편파 항을 패킷 간 독립 잡음으로 옮기자 XY RMSE가 45.42 cm에서 4.15 cm로 줄었다. 이 재생 대조는 이식한 상관 모형의 영향을 보여 주며, D2의 잔차에는 시간 상관이 남아 있다.

우선 첫 통과 전 0–45초에서 (y)와 heading에 대한 채널별 갱신량 (K_{j,c}\nu_c), 횡방향 오차 (\hat y-y_{\mathrm{true}}), 편파의 (H_{s,y}) 및 (H_{s,\psi})를 겹쳐 본다. 원래 느린 상관 trace와 독립 잡음 trace는 같은 패킷과 고정 gate를 쓴다. 두 조건에서 편파 갱신량이 갈라지는 시점이 heading 오차 증가와 횡방향 부호 반전보다 앞서는지 확인한다. 이는 앞으로 읽을 비교이며, 위 수치와 별도로 판정한다.

추가로 수집할 자료는 앵커 B 옆을 같은 측면 거리와 heading으로 여러 번 통과하면서 동기화한 두 편파 포트의 원본 CIR, 타임스탬프와 EKF에 독립적인 (x,y,\psi) 참값이다. 같은 자세에서 반복되는 편향과 통과마다 달라지는 잔차를 각각 추정할 수 있다.

## 배포 trace 확인

| 파일 | 원본 실행 기록의 SHA-256 |
|---|---|
| `R5_distance.npz` | `11c5d1057e1cbefc9999732a92ba412838cc5aeff35438907709ba59b0c61025` |
| `R5_distance_independent.npz` | `72543f39045c74f7df2049bb6332c18d142455e302c52a2278ba283629899ec6` |
