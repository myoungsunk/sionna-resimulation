# d0 + CIR LoS 복원기의 Heading 정보 보존 — 선행 검증 (사전 고정)

## 목적
현재 \`CIR_PLUS_D0\`가 LoS 편파비의 RMSE는 줄이나, prior heading 변화에 대한 innovation 반응 기울기 G≈0.2인 원인을 최소한의 변경으로 시험한다. 실패 시 복원 RMSE와 heading 민감도의 trade-off를 정량화한다.

## 데이터 격리
- 기존 route-heldout 모델의 저장된 패킷별 예측 \`results_los_bias/LOSC_PACKET_DIAGNOSTIC.csv.gz\` 재사용; 재학습·하이퍼파라미터 최적화 없음.
- LoS oracle innovation은 평가 점수 계산에만 사용한다.
- 세 route는 이미 여러 실험에 사용된 개발용 경로; 새 환경의 독립 일반화가 아님.
- 기준 heading prior는 기존의 **GT±1° 합성 prior**이므로 실제 gyro/odometry 주행 prior나 재귀 EKF가 아님.

## 동결 비교
- BASE: RAW, CIR_ONLY, CIR_PLUS_D0, D0_DIRECT, ORACLE_LOS.
- BLEND_CIR_w: w·s_CIR_ONLY+(1−w)·s_CIR_PLUS_D0, w∈{0,.25,.50,.75,.80,.90,1.00}.
- RESCALE_D0_2X/4X/5X: CIR_PLUS_D0 innovation만 정해진 배율로 확대 (진단용; covariance 보정 아님).
- 매칭된 같은 pose의 +1°/−1° 관측을 사용한다.

## 정량 지표
- LoS 편파비 RMSE; fixed-gain 단일 heading 갱신 RMSE, heading 절대오차 q95/q99/max.
- G=〈ν_clean(+1)−ν_clean(−1),ν_LoS(+1)−ν_LoS(−1)〉/‖ν_LoS(+1)−ν_LoS(−1)‖².
- 사전 성공기준: **동일 arm이 세 route 모두에서 G≥0.8 및 heading 진단 RMSE≤1°**.
- 기준을 통과하더라도 LoS RMSE가 CIR_PLUS_D0 대비 얼마나 악화했는지 반드시 보고하며, 재귀 정확도 성공으로 주장하지 않는다.

## 제외
현재 프레임의 d0를 그대로 빼면 innovation=0이라는 사실은 negative control. 본 pilot은 기존 출력을 결합·재가중하는 최소 진단이며, 과거 d0를 이용한 시간 예측, ±5°/±10° 초기 오차, 실제 Full complex-CIR 직접파 분리, 공분산 교정과 전체 재귀 EKF 검증은 포함하지 않는다.
