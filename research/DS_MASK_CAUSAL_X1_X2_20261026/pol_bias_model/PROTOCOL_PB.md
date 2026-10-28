# 편파 bias 모델링 (분산 · 상태 · sliding window) — 실행 계약

기준 브랜치: `research/ds-x1-x2-results-20261026`. 코드: `pol_bias_model/exp_pb.py`, `aggregate_pb.py`. 입력: `reflect_model/fetch_inputs.sh` (FFD bank, 코드 subset, E1 CONTROL trace B0/L2).

## 조건 (28)
- 경로 7개: R2_aA_m0, R2_aB_m0, R2_aA_m45, R4_aA_m0, R4_aB_m0, R5_aA_m0, R5_aB_m0.
- Gyro bias 4단계: B0 = 0, L0 = 0.01, L1 = 0.05, L2 = 0.20 °/s (`r2_bias_replay.py` 정의, seed 0).
- 패킷(z, μ_B, μ_M, R, 수용 mask A_B, truth)은 bias 단계와 무관하게 동일하다 (B0 대 L2 확인: z 2e-16, μ/R/acc 동일). 단계마다 바뀌는 것은 odometry/gyro 제어 입력뿐이며, 원래 센서 생성기로 다시 만든다. B0/L2는 저장된 trace의 제어와 1e-10 이내 일치, 원 필터 arm은 상태 1e-8 이내 일치를 확인하고 실패하면 중단한다.
- 마운트 45는 R2_aA 한 경로만 있다. 다른 경로의 마운트 45는 μ_M(Δs 학습 보정)·R 생성 파이프라인이 저장소에 없어 이번 범위에서 제외한다.
- L0/L1/L2는 같은 패킷에 제어 입력만 다르므로 독립 환경이 아니다.

## Arm (조건마다 14)
배경 μ: BB = μ_B, MB = μ_M (Δs 보정).
| 이름 | 내용 |
|---|---|
| ORIG | 원래 필터 |
| VAR | R_ss += σ_b(ρ̂)² |
| GM03 | 편파 bias 상태 b_s, 주행 거리 Gauss–Markov L = 0.3 m |
| GM1Y20 | b_s, L = 1 m, yaw 변화 20°로도 상관 감쇠 |
| WIN05Y10 | b_s를 창 안에서 상수로; 0.5 m 또는 yaw 10° 변화 시 창 종료·재초기화 |
| WIN1Y5 | 같은 방식, 1 m 또는 5° |
| ORPOL | oracle: z_s에서 편파 오차 제거 (truth 사용, 상한 기준) |

σ_b(ρ̂) = interp([0, 1.5, 3, 6, 10] m → [0.011, 0.02, 0.05, 0.12, 0.24]), ρ̂는 필터 자신의 예측 상태. 이 표와 창 파라미터는 마운트 0 B0 경로 통계·시험에서 정했으므로 B0 마운트 0 조건에서는 in-sample이다.

## 지표 (t ≥ 30 s)
Heading RMSE, signed bias, XY RMSE, 앵커 거리 RMSE, heading z RMS(오차/보고 σ), heading 95% 포함률, XY NEES, XY 95% 포함률. 상태 arm은 b_s 추정과 실제 편파 오차의 상관·잔차도 기록.

## 사전 판정 (MB 배경이 주 판정, BB는 보조)
- P1 (Δs 실패 해소): heading과 XY가 모두 BB_ORIG보다 나은 조건이 각각 21/28 이상.
- P2 (강건성): 모든 조건에서 heading RMSE ≤ 1.10 × BB_ORIG.
- P3 (불확실성 정직성): heading z RMS 중앙값 ≤ 1.5 그리고 XY 95% 포함률 중앙값 ≥ 0.80.
- 보고: ORPOL까지의 격차 중 줄인 비율 중앙값 (MB_ORIG − M)/(MB_ORIG − MB_ORPOL), bias 단계별·마운트별 중앙값.
