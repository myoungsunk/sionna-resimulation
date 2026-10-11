# 18 — LUT–LoS, Range 및 RF 시간/각도 상관: 기존 데이터 실행 검증

실행 2026-10-11. GitHub Actions [38112586466](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38112586466) **성공**. 코드: run_lut_los_temporal_cov_audit_20261011.py. 기존 7케이스 9,519개 RF pose의 정답 평가 데이터, Tnone 정상 주행, 고정 FFD LoS LUT 및 169개 3각 프로브 그룹을 사용했다. 새 RF 생성과 필터 Q/R 변경은 하지 않았다.

## 1. Native LoS 대 고정 LUT의 오차

s_full-h_LUT = (s_full-s_LoS)+(s_LoS-h_LUT), 항등식 최대 수치오차 4.44e-16.

| 거리 | N | s_LoS-h_LUT RMS | s_full-s_LoS RMS | s_full-h_LUT RMS |
|---|---:|---:|---:|---:|
| <5m | 4253 | .01690 | .04060 | .04269 |
| 5–10m | 3605 | .01188 | .15590 | .15494 |
| ≥10m | 1661 | .01073 | .32996 | .32898 |

**중요한 예외:** 수직 방향 앵커 아래 수평거리 0.1m 이내 9개 pose에서 LUT 차이 >0.1이 4개 발생했다. R5-B pose706의 수평거리 0.0384m, s_LoS-h_LUT = **−0.8776**, s_full-s_LoS = −0.00008. pose707은 −0.4905. R5-A pose856 및 R5-B pose705는 약 −0.108. 이 9개를 제외한 9,510 pose의 LUT mismatch RMS=.009621, max absolute=.04665. 거의 수직인 방향에서 azimuth atan2와 LUT 극점 보간/Jacobian이 의심되나 원인까지 확정하지 않음. 원 F01/L1 미해결.

## 2. Range pulse offset과 multipath bias를 구분

Filter range_offset 은 **−0.531598390625 m** (LoS pulse/tap detector calibration). Raw measurement minus geometry가 약 −0.5m라는 사실을 multipath NLoS bias로 직접 해석하면 안 된다. 필터가 사용한 offset을 뺀 잔류 모델오차는:

| 거리 | Mean residual m | RMS residual m | empirical RMS² / R_range |
|---|---:|---:|---:|
| <5m | −.00113 | .05848 | .50 |
| 5–10m | +.06485 | .14238 | 2.96 |
| ≥10m | +.13584 | .22251 | 7.22 |

기본 range R=.05²+.05²+.149313²/12=.006858m², sigma=.082812m. 길어진 복도에서 residual은 통계적 측정모델보다 크고 지속적이며, 반복 독립 관측 가정으로 radial XY covariance를 과도하게 축소시킬 수 있다.

## 3. 정상 Tnone 주행 RF 오류의 연속성

7 케이스별 5Hz 정상 주행 RF true residual Pearson ACF 중앙값:

| 오차 | lag .2s | lag 1s |
|---|---:|---:|
| LUT–LoS s | +.511 | +.120 |
| Full–LoS s | **+.866** | +.493 |
| Full–LUT s | **+.871** | +.493 |
| Range model residual | **+.538** | +.264 |

이는 한 corridor 내부 공간·시간에 걸친 deterministic channel error 상관이며, 독립 radio noise ensemble covariance는 아니다.

## 4. 제자리 세 각도의 full RF 측정오차 공간 교차공분산

동일 XY의 169 case-station 그룹, 74 route-unique XY (한 geometry)에서 [r0,r10,r20,s0,s10,s20] 6변수의 공간적인 empirical covariance와 PSD를 계산했다.

- Full–LUT s angular corr (0,10) +.817; (10,20) +.817; (0,20) +.558.
- Range offset residual angular corr (0,10) +.734; (10,20) +.685; (0,20) +.580.
- Same yaw range–s correlations +.437, +.628, +.319. R2에서는 높고 R4에서는 거의 0이나 음수도 있어 일괄 scalar 상관은 부적절.

## 5. Full pose–RF cross-time covariance 판정

**CROSS_TIME_POSE_RF_COV_VALIDATED = FALSE**.

저장된 P6(t_i)는 각 시점의 marginal covariance이고, 필요한 cross-time P6(t_i,t_j)=Cov(e_state_i,e_state_j)는 아니다. Site 169개의 RF bias covariance도 Cov(pose error at i, RF measurement noise at j)를 주지 않는다. 업로드 noisy-probe 반복은 5 sensor seeds/condition과 32 thermal-only repeats라서 고차원 joint covariance calibration에 불충분하다. Representative 7case seed0 pose-error versus subsequent RF true residual correlation은 별도의 descriptive cross-lag 자료로 계산하였지만 cross-time conditional covariance 인증에 사용하지 않는다.

올바른 검증에서는 시간별 full estimated/true x6, P6, F/G/Q, Kalman K, 이전에 수용한 range/s, 추가 yaw actual/measured, 모든 2/3각 RF packet, 다수 독립 gyro/thermal seed 및 여러 물리 scene을 함께 저장해야 한다. 그다음 cross-time predicted S_ij (H_i P_ij H_j^T, R_ij, state–measurement noise cross terms)와 empirical innov covariance, NIS, pose NEES 및 coverage를 검정한다. **현재 데이터로 RF error의 시간 지속성은 입증됐지만 모든 cross-time pose–RF covariance를 검증했다고 주장할 수는 없다.**

관련 결과: artifact zip lut_los_temporal_covariance_audit_20261011.zip. 연구 성능의 scientific_PASS=false, F01/F02 OPEN 유지.
