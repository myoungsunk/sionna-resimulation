# 7개 기존 Full/LoS RF 채널의 CIR 탐색 분석 — 실제 실행 결과

실행일 2026-10-10. GitHub Actions run: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38038921679  
실행 코드: research/HEADING_RELIABILITY_20261010/run_channel_diagnostics.py  
입력: codex/post-a23-evidence-20261010 @ 047cce2, BLOCK_C, full/LoS H SHA-256 일치.  
완료: 7개 케이스, 9,519 RF pose, 169개의 case×yaw sweep, 독립된 route/XY 측정지점은 74개.  
원본 결과: Actions artifact cir-heading-diagnostics-20261010, 2026-11-09까지 보관. 

## 중요: 무엇을 검증했는가?

직접 측정 label은 e_MP = s_full - s_LoS_direct, 본 분석의 outcome은 |e_MP|이다. fixed LUT의 inverse heading 정확도, sensor-v2의 pre-RF prior를 사용한 operational RF heading 정확도, 실제 angle error 5도 이내의 calibrated reliability 및 filter NEES는 이번에 분석하지 않았다. 이를 혼동하면 안 된다. s 왜곡 proxy |e_MP|>0.1 역시 heading 오차 >5도와 동등하지 않다.

## 거리별 평균, 분산, RMS

| 링크거리 | N | 평균 e_MP | Var(e_MP) | RMS(e_MP) |
|---|---:|---:|---:|---:|
| <5m | 4253 | +0.00254 | 0.001641 | 0.04059 |
| 5–10m | 3605 | +0.03590 | 0.023017 | 0.15590 |
| >=10m | 1661 | +0.05100 | 0.106270 | 0.32996 |
| 전체 | 9519 | +0.02363 | 0.028380 | 0.17011 |

## 특징과 |e_MP| 상관

| 특징 | Pearson | Spearman |
|---|---:|---:|
| 거리 | +0.457 | +0.629 |
| 첫 tap 포트 전력 합계 로그 | -0.405 | -0.574 |
| RMS delay spread | +0.298 | +0.431 |
| s 자체 | +0.301 | +0.427 |
| Early energy fraction | -0.215 | -0.220 |
| 포트 간 JSD | -0.017 | -0.151 |
| 포트 간 16 tap shape L1 | +0.015 | -0.117 |
| 두 포트 peak delay 차이 | +0.138 | +0.050 |

RMS delay spread의 Pearson은 cubic 거리·case·cos2yaw/sin2yaw를 OLS residualize한 후 +0.097로 작아졌다. JSD는 동일 계산 후 +0.099이다. 두 포트 JSD와 오차 Spearman 상관은 7개 케이스에서 부호가 뒤집혀 단일 범용 신뢰도 지표로는 근거가 부족하다.

## 탐색적 예측모델: e_MP 왜곡이 0.1을 넘는지

Leave-one-ROUTE-out (R2/R4/R5, 각 route의 anchor/mount는 같은 fold). AUROC/Brier는 여러 pose의 모델 성능으로, 외부 복도 일반화로 간주 불가.

| 모델 | Brier | AUROC |
|---|---:|---:|
| distance only | 0.14836 | 0.8146 |
| RSS+s only | 0.14128 | 0.8200 |
| classic CIR only | 0.16687 | 0.7090 |
| dual-port shape only | 0.17731 | 0.6133 |
| classic+dual CIR only | 0.16076 | 0.7454 |
| classic+dual CIR + RSS+s | **0.12989** | **0.8521** |
| preceding combination +distance | 0.13169 | 0.8510 |

39개 route/x 약 1.5m 공간 block bootstrap 1200회: full classic+dual+power – RSS+s의 paired Brier 차이 −0.0114, 95% CI [−0.0163,−0.0074]. 샘플들이 같은 복도를 공유하므로 이 CI는 환경 일반화 성능을 나타내지 않는다.

## 1/2/3 yaw 포인트 — matched LoS reference로 계산한 ORACLE 국소 heading 등가오차

169개 case×station 그룹(74 고유 XY). Full/LoS 동일 위치 yaw sweep 16~19개로부터 2psi/4psi Fourier local LoS curve를 fit하고 고정 측정 index [0], [0,2], [0,2,4]를 사용했다. True pose/LoS가 필요한 offline oracle surrogate이며 실제 LUT 역산을 통한 heading accuracy가 아니다. LoS harmonic fit error median 0.0162 s-unit, p90 0.0401.

| 관측점 | Median apparent shift | p90 | RMS | >5deg |
|---|---:|---:|---:|---:|
| 1 | 2.9deg | 14.62deg | 7.34deg | 34.9% |
| 2 | 2.6deg | 9.12deg | 5.98deg | 26.0% |
| 3 | 2.1deg | 8.12deg | 5.66deg | 24.3% |

1→3점의 paired mean |shift| 감소 1.326deg, 74 route/station cluster bootstrap 95% [0.749,1.952]deg. 55.6%는 개선됐지만 38.5% 악화됐다. 각도별 response-shape residual과 3점 apparent heading |shift| Spearman +0.543. 이는 실측 v2 heading improvement의 증거가 아니다.

별도 post-hoc route-heldout oracle-local-heading-risk 분류: passive CIR+power Brier 0.2119/AUROC 0.659, 3점 shape 잔차 추가 Brier 0.2012/AUROC 0.693, 74 그룹 bootstrap ΔBrier CI [−0.0246,+0.0026]으로 0을 포함한다. Probe 신뢰도 향상을 확정할 수 없다.

## 첫 tap UWB range

원 raw range_m - true_distance에는 약 −0.48m 수준의 *공통 30% leading edge detector offset*이 있어 calibration된 range bias로 부를 수 없다. 동일 pose full vs LoS first tap 차이만 재계산하면 거리별 평균 +0.00513m, +0.06098m, +0.14091m; RMS 0.05998m, 0.14740m, 0.22748m.

## 계속 필요한 입력

원 fixed LUT binary (SHA256 711e12...), sensor-v2 RF-disabled pre-RF x/P prior와 동일 pose/timestamp의 original amplitude P1/P2 또는 CIR magnitude; 그리고 독립 환경 장면. 주 사전등록의 actual RF heading correction P(correct <=5deg|features), NEES 및 physically realizable adaptive probe는 이 자료 이후에야 수행할 수 있다. Existing F01/F02 OPEN, scientific_PASS=false 유지. 어떠한 필터/시뮬레이션 운영 코드도 변경하지 않았다.
