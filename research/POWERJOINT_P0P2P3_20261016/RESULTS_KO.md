# POWER_JOINT P0/P2/P3 — 실행 결과, 2026-10-16

동결 입력 commit: `4c0682a55298ae33f3495a4c7249f3a8c34633ad`.
실행 branch: `research/powerjoint-p0p2p3-execution-20261016`.
사용자의 최종 P0/P2/P3 번호를 사용한다. 계획 문서의 F0/F2와 혼동하지 않는다.

이 파일은 이번 ChatGPT 실행에서 실제 산출하고 별도 산술 검증기로 재검증한 결과 요약이다. **새 실행 코드·모든 CSV/NPZ·입력 SHA와 재현 launcher는 대화에서 제공한 `POWERJOINT_P0P2P3_20261016.zip`의 정본을 참조한다. 이 요약을 게시했다는 이유로 상세 산출물 전부가 GitHub에 업로드되었다고 주장하지 않는다.** 원본 소스·LUT·기존 결과는 덮어쓰지 않았다.

## 실행 범위와 입력 감사

- RF/R2/N4B/N4C ZIP 4개 SHA256/CRC, immutable bundle 120파일, 사용한 동결 소스 7개 git blob, LUT SHA256 확인.
- 같은 prior: 20 arm × 2 prior × 3 gate × 8 조건 = 960개 요약 행.
- 전체 재귀: 15 arm × mount0/45 × B0/L0/L1/L2 = 120개 신규 trajectory. DR4/S4 16개 행은 기존 결과 재채점.
- 각 trajectory 979시점, t>=30s 829시점 평가. B0=0, L0=0.01, L1=0.05, L2=0.20 deg/s.
- 모든 조건은 동일 R2 RF 실현 및 sensor seed0에 기반한다. 독립 RF 반복이나 새 환경을 만든 것이 아니다.
- Python3.13.5 / NumPy2.3.5 / pandas2.2.3, BLAS thread1.

동일 prior 원본 state 최대 차이 9.44e-16. 전체 재귀 POWER 원본 state 차이 4.62e-14 이내, R0 포함 최대 4.39e-8, covariance 최대 3.51e-10. Gate 불일치 0. 비트 동일성이 아닌 사전 허용오차(state1e-7/cov1e-8) 내 재현이다. 독립 산술 지표 차이 최대 1.10e-11. 독립 검증기는 같은 runtime의 별도 산식이며 외부 연구자 검증을 뜻하지 않는다.

## P0: 새로 발견한 off-grid pole 결함

Native LoS 전수 9,519시점. 기존 pole-table patch 전후 s RMSE:

| 범위 | n | 원본 | 기존 패치 |
|---|---:|---:|---:|
| 전체 | 9519 | 0.014184 | 0.009616 |
| theta<2deg | 5 | 0.454941 | 0.001143 |
| theta>=2deg | 9514 | 0.009619 | 0.009619 |

기존 theta0 reindex는 격자점은 맞추지만 두 방위각을 각각 bilinear interpolation하면 같은 physical heading의 pole limit가 off-grid에서 달라진다. Yaw0 s span 약0.001186, yaw90 약0.001193. interpolant FD가 맞아도 물리적 gauge invariance는 보장되지 않는다.

새 numerical-only `pole_sum_chart.py` 후보는 theta0에서 phi_tx+phi_rx 단일 좌표로 보간한다. 6heading×3600방위각 검사 span 최대2.22e-15, gauge derivative 차이0. theta>=2deg 1000점 h/J 차이0, 근접 FD 차이1.62e-8 이내. 원본 FFD 물리 검증이 아니며 학습·재귀 추정에는 사용하지 않았다. 정확한 극점 Cartesian Jacobian은 검증되지 않아 실패하도록 했다.

원본 FFD LFS fetch run38868341083은 제한시간 내 완료되지 않아 취소됨. artifact12033030905에는 pointer와 log만 있고 원본 bank bytes가 없다. Drive에서 두 정확한 bank 파일명 검색도 결과0. **원본이 존재하지 않는다는 뜻이 아니라 이번 실행에 확보되지 않았다는 뜻이다.** P0 원본 EM 검증 BLOCKED_INPUT, P1 재학습 NOT_TESTED.

theta>=2deg Native LoS 잔차 중 |s|>0.01은1859/9514, max0.046651. 이 잔차를 전부 interpolation 또는 multipath로 단정하지 않는다. 거리/first-tap/원 FFD 차이 분리가 필요하다. 원본 F01 metadata의 500점 max0.023972 FAIL은 과거 기록 확인이며 이번 source FFD 재실행이 아니다.

## P2/P3: Heading RMSE [deg]

| Mount | Bias | R0 | POWER | POWER-no-C | POWER-no-mean | Range+POWER-q only | G4 |
|---|---|---:|---:|---:|---:|---:|---:|
| 0 | B0 | 7.4900 | 1.7732 | 2.0358 | 4.3220 | 5.3246 | 2.4928 |
| 0 | L0 | 7.4991 | 1.7567 | 1.8749 | 4.3275 | 5.4942 | 2.4287 |
| 0 | L1 | 7.5399 | 1.7123 | 1.8427 | 4.2145 | 6.2103 | 2.0156 |
| 0 | L2 | 7.5209 | 1.9914 | 2.3146 | 4.2479 | 9.3862 | 1.8450 |
| 45 | B0 | 0.8450 | 0.8151 | 0.7207 | 0.9073 | 10.6247 | 1.1647 |
| 45 | L0 | 0.8444 | 0.8125 | 0.7119 | 0.9096 | 10.8338 | 1.1626 |
| 45 | L1 | 0.8436 | 0.8106 | 0.7078 | 0.9079 | 11.6855 | 1.1583 |
| 45 | L2 | 0.8481 | 0.7274 | 0.6900 | 0.9705 | 15.0577 | 1.1331 |

Range+q를 유지하고 s를 제거하면 현재 8조건 모두 Heading이 악화된다. s의 추가 정보는 SUPPORTED_BUT_LIMITED. B0 DR4 Heading은0.484deg로 POWER보다 좋고 L2 DR4는24.969deg다. RF가 늘 DR보다 좋다는 주장을 하지 않는다.

H[:,b_g]=0, H_r,psi=0. RF bias update는 prior pose-bias cross-covariance를 통해 들어온다. 동일 prior에서 이 cross-covariance를0으로 두면 K_b=0. accepted K_b,r*nu_r + K_b,s*nu_s를 누적해 archived bias 경로를 전 시간 재구성했고 오차8.86e-15deg/s 이내.

B0 mount0 POWER의 누적 Range 기여 -0.102849deg/s와 s 기여+0.104421deg/s가 최종+0.001572deg/s를 만든다. bias RMSE0.021603deg/s, 평가구간 최대 절대오차0.085453deg/s. 이는 같은 실현 경로의 대수적 기여이며 관측 제거 counterfactual과 동일하지 않다.

평균과 covariance, gate는 서로 대체 설명이 아니다. B0 mount0에서 mean+R0는2.830deg, 단순4R0는6.824deg, POWER mask로 고정한 R0는5.399deg로 POWER1.773deg를 재현하지 못한다. fixed mask는 offline counterfactual이다. C_rs 제거는 mount0 네 조건에서 악화, mount45 네 조건에서 개선: C_rs의 보편적 우월성은 FALSIFIED.

같은 POWER prior/mask에서 mount0 B0의 no-mean Heading은1.778779deg로 POWER1.773241deg와 거의 같지만 전체 재귀에서는4.321961deg로 벌어진다. 이후 state/gain/gate 변화가 누적되는 효과를 무시할 수 없다. 시간상관 잡음 하나가 원인이라는 뜻은 아니다.

## G4: 동일 패킷 NLL과 재귀를 구별

평가에 사용한 동일829패킷 NLL(작을수록 좋음): mount0 POWER -1.660902 / G4 -1.718129; mount45 POWER -1.089652 / G4 -0.765506. 따라서 mount45에서는 G4 NLL부터 나쁘다. pooled NLL 우위를 mount45 우위로 옮기면 안 된다.

mount0 B0은 G4 NLL이 더 좋아도 재귀 Heading2.493deg가 POWER1.773deg보다 나쁘므로 진짜 역전이 남는다. 반대로 mount0 L2는G4 1.845deg가POWER1.991deg보다 좋다. G4 mean/POWER covariance 혼합은 mount0 B0 같은-prior1.771616deg, 전체 재귀2.380deg로 국소 이득이 재귀 이득을 보장하지 않음을 확인했다.

## 좁은 conditional XY 축: 여전히 미해결

Schur covariance뿐 아니라 conditional residual도 함께 변환하고 pose NEES=heading NEES+conditional XY NEES를 확인했다. Mount45 B0 POWER: Heading0.815deg, XY0.084934m, bias RMSE0.013260deg/s. narrow error RMS0.041730m / predicted std RMS0.010839m, narrow NEES14.2001, nominal95% 포함률16.4053%. C_rs 제거 후에도 NEES12.1203 / 포함률31.0012%.

정확도 개선이 covariance consistency를 뜻하지 않는다. 위 coverage는 동일 시간경로 기술통계이고 독립 반복 통계 검정이 아니다. P4 LoS 보호, P5 독립 시간상관 검증, P6 최종 source-corrected 모델, P7 환경/하드웨어 일반화는 NOT_TESTED. low-frequency Range 하나가 전체 원인이라는 주장과 calibrated Bayesian estimator라는 주장은 채택하지 않는다.
