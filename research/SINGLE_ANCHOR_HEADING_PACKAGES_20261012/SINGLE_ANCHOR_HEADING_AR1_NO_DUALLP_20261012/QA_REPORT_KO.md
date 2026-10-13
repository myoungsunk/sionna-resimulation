# 시뮬레이션 QA 및 검증 범위

## 실제 수행한 검사

| 항목 | 결과 | 증거 |
|---|---|---|
| 1,000회·100-step 실험 실행 | PASS | `EXECUTION_LOG.txt`, `all_scenarios.csv` |
| 시간 상관 비교에서 전체 ranging RMS 일치 | PASS | `ranging_temporal_correlation.csv`: ρ별 0.080000m |
| AR(1) 실제 lag-1 자기상관 | PASS | ρ=0/0.5/0.9/0.98에서 0에 근접/0.4993/0.9004/0.9803 |
| x/y 거리 Jacobian | PASS | 유한차분과 분석형 수식 비교 (`qa_checks.py`) |
| 고정 위치에서 yaw에 대한 기하 거리 미분 = 0 | PASS | 3-state 관측 모델에서 3번째 성분 정확히 0 |
| EKF 공분산 PSD | PASS | 작은 별도 실행에서 모든 기록된 P의 최소 고유값 확인 |
| NIS/NEES 수치 유한 및 RMSE x/y/2D 정합 | PASS | `qa_checks.py` |
| Dual-LP/가상 yaw RF bias 사용 여부 | NONE | `study.py`에는 각도 의존 RF 편향이나 Dual LP가 없음 |
| AR(1) aware 대비 naive 비교 | PASS | `ar1_aware_vs_unaware.csv` |
| 같은 seed로 1,000회 완전 재실행한 결과의 byte-for-byte 일치 | PASS | `REPRODUCIBILITY_CHECK.json` 및 재실행 CSV/Bootstrap/geometry 그래프 비교 |
| 이전 GitHub 복도 실험 EKF 코드를 수정 없이 재사용 | PASS | `base_corridor_ekf.py`와 이전 코드 바이트 동일 |

## 수행하지 않았거나 모형의 가정인 사항

| 항목 | 상태 | 의미 |
|---|---|---|
| Sionna RT channel / CIR-to-range | NOT RUN | 벽 반사로부터 time-correlated error를 물리적으로 생성한 실험은 아님 |
| 실제 RF 실측 | NOT RUN | σ=0.08m와 ρ=0..0.98은 민감도 분석 설정값 |
| 알려지지 않은 ρ의 식별/추정 | NOT RUN | AR1-aware EKF는 생성 모델의 ρ, σ를 이미 안다는 이상적 control |
| 물리적 충돌 및 로봇 차체 제약 | NOT ENFORCED | GT가 복도 허용영역을 벗어날 수 있으며 별도 기록함 |
| 지도 기반 heading/횡방향 제약 | NOT INCLUDED | 복도 벽을 EKF 측정 업데이트로 쓰지 않음 |
| 실제 시스템의 절대 yaw 초기 정보 | NOT INCLUDED | 초기 yaw prior를 확률 분포로만 제공 |

**통계 주의:** 1,000개 독립 주행을 bootstrap 단위로 사용함. 같은 주행의 100개 time step을 독립 표본으로 취급해 신뢰구간을 좁히지 않았음. 모델 적합성 가정이 틀렸을 때 NIS χ² 검정을 무조건 통과/실패로 해석하지 않음.
