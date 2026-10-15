# N4-Q 실행 보고 — Heading 관측가능성과 RF 오염의 분리 검증 (2026-10-15)

## 최종 판정

**Q0: PASS / Q1: 물리 기하 검증 PARTIAL / Q2: 오프라인 오염 분해 PASS / Q3: 2×2 기술 PASS·과학 PARTIAL / Q4: 수치 실행 PASS·온라인 신뢰도 보정 FAIL / Q5·Q6: 계획상 단계 게이트 차단 / Q7: 독립 Full RF 장면 입력 부재로 BLOCKED.**

원본 Joint4/SR4, N4-C POWER_JOINT, LoS 2° FFD LUT, Range·s RF 관측기, 원래 상태 x=[x,y,ψ,b_g], R0, 원 Sionna RF 데이터, 오도메트리 및 gyro stream 모두 변경하지 않았다. GT pose와 Native LoS paired RF는 오프라인 물리 원인·label·score 계산에만 사용하고 온라인 센서 정보인 것처럼 취급하지 않는다.

## 실제 GitHub 실행과 원시 결과

- [Q0–Q3 최종 성공 Run 38724429046](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38724429046), [원시 결과 artifact 11967575965](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38724429046/artifacts/11967575965), ZIP SHA256 748b7d1b91e06b1825fdd49bc10bf387fae3786aebd63eac18f194e275170d67.
- [Q4 최종 성공 Run 38725307645](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38725307645), [원시 결과 artifact 11967961466](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38725307645/artifacts/11967961466), ZIP SHA256 599267063f87546ca76cf6f7c755977c74c8b298c18fbb89e73066dd34be3164.
- [Q4 독립 재감사 Run 38725929604](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38725929604), [artifact 11967647952](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38725929604/artifacts/11967647952). 26,528개 Q4 원본 시점과 32개 그룹의 평균·진단 결과 독립 수치 재계산 PASS. 온라인 보정의 과학적 게이트는 FAIL.
- Q0–Q3 source commit af461ff5b9ea26019b55eda877119523c42c5ed9; Q4 source 2fa9a8fb013b65d437a2d0e945cbb401f9c7ff6f; Q4 독립 재감사 7c31016069f684ede14915ec476ea7bafa4947ec.
- 감사: 동결 입력 자산 22개 SHA, 14채널 Full/Native LoS original 14,502개 Range·s 관측 parity, FFD 실제 Jacobian·finite yaw difference, 원 R2 979 pose/timestamp ID 정합 PASS.
- 실패 시행(판정값으로 사용하지 않음): Q3 Pandas eval-mask 참조, R2 별도 yaw-sweep 샘플과 motion GT 차이에 의한 3항 분해 실패, Q4 결과 저장 함수, 독립 CSV bool reader. 각각 수정 후 사전 감사부터 재실행해 최종 PASS. 문제를 무시하거나 기존 데이터를 수정하지 않았다.

## Q1 — 실제 LoS FFD Heading 정보량과 비구별 조건

진짜 Heading 기하정보 축은 동일 고정 R0_s=.0081 및 동일 nominal P0=(0.1m,0.1m,5°) covariance로 계산해 Full MP contamination에 종속되지 않도록 했다. Hψ 및 유한 ±2°/5°/10° LUT 관측차, 2° angular knot/seam, ±20° LoS 단일 s의 대안 Heading 비구별성 proxy 검사.

| R2 AnchorA, 1303 pose | Mount0 | Mount45 |
|---|---:|---:|
| Median abs FFD Hψ (rad−1) | 0.51568 | 1.63864 |
| Median nominal Igeom | 32.13 | 318.48 |
| Median maxabs Ds at ±10° | 0.1522 | 0.3156 |
| ±8°–20°에 차이가 σ_s=.09 이내인 다른 yaw 존재 비율 | 76.67% | 29.39% |
| R4/R5 train-only Igeom median=70.2076 아래 비율 | 64.54% | 30.24% |

동일 복도에서의 1차 정보 부족 메커니즘을 확인했다. 76.7%는 실제 multi-modal posterior 확률이 아니라 단일 LoS s의 비구별성 진단이다. Mount0가 항상 낮은 정보량이라는 외삽은 금지. 다른 trajectory/mount에서 기하가 역전될 수 있다.

## Q2 — Full−Native LoS RF 오염과 LUT·Pose 오차

동일 pose/anchor/mount Native Full/LoS를 9,519쌍 매칭. eMP=zFull−zLoS_native, eLUT=zLoS_native−h(x_GT), ePose=h(x_GT)−h(x_prior), 따라서 original J4 prior에서 Full Innovation=eMP+eLUT+ePose. 원 R2 motion truth/time/poseID 좌표와 일치시켜 이 identity를 정밀 검사 통과.

R2 AnchorA에서 train-only Igeom cutoff 70.2076를 적용한 Full−Native LoS 오염:

| Mount | Igeom | n | μmp,r (m) | μmp,s | Vmp,s | ρmp,r,s | abs(eMP,s)>.1 |
|---|---|---:|---:|---:|---:|---:|---:|
| 0° | 낮음 | 841 | +.0485 | +.0578 | .03605 | +.579 | 19.62% |
| 0° | 높음 | 462 | +.0638 | +.0434 | .04636 | +.362 | 37.01% |
| 45° | 낮음 | 394 | +.0926 | +.0547 | .08105 | +.364 | 48.48% |
| 45° | 높음 | 909 | +.0775 | −.0149 | .03874 | −.155 | 31.46% |

FP tap/strong RX branch 변화도 원 observer로 재계산해 보존. MP label은 Native LoS가 필요한 **offline oracle**이며 실제 DWM1000에서 직접 관측되는 값이 아니다.

## Q3 — 2×2 분리와 기존 Joint4 Heading 위해성

R2 AnchorA Full RF의 원본 1,303 pose씩 4영역:

| Mount | 저정보·저오염 | 저정보·고오염 | 고정보·저오염 | 고정보·고오염 |
|---|---:|---:|---:|---:|
| 0° | 676 | 165 | 291 | 171 |
| 45° | 203 | 191 | 623 | 286 |

R2 AnchorB m0에도 네 조합 모두 존재 (692,125,367,119). 위치 샘플은 동일 scene/연속 trajectory로 상관돼 있으므로 표본 개수가 곧 독립 검증 수를 뜻하지 않는다.

기존 Joint4/L2에서 RF를 원래 수용한 한-step update의 Heading squared error 증가 비율:

| 조건 | Mount0 | Mount45 |
|---|---:|---:|
| 낮은 정보 + 낮은 RF 오염 | 45.94% | 57.14% |
| 낮은 정보 + 높은 RF 오염 | **56.76%** | **70.59%** |
| 높은 정보 + 낮은 RF 오염 | **8.20%** | **36.69%** |
| 높은 정보 + 높은 RF 오염 | 26.15% | 51.38% |

이는 original J4의 acceptance-selected 사후 관측결과다. 정책을 변경했을 때 같은 결과가 나온다는 인과 증거는 아님.

R4/R5 훈련 → 완전 R2 평가의 편파 MP 프록시 예측:

| 입력 | AUROC | Brier |
|---|---:|---:|
| RF power/CIR/FP | .86887 | .13167 |
| GT oracle geometry only | .62402 | .19536 |
| RF+oracle geometry | .87009 | .13134 |

Geometry를 무조건 오염 분류기에 추가해도 증분은 매우 작다. RF-only는 훈련 LoS 거짓경보율 5% 목표로 정한 경계를 R2 LoS에서는 7.65%로 초과했다. Oracle geometry only는 온라인 사용 불가.

## Q4 — 실제 RF 갱신 직전 원 DR4/Joint4 prior와 불확실도

Frozen R2 DR4/J4 prior x−,P−, B0/L0/L1/L2×Full/LoS×Mount0/45 26,528개 평가시점. 실제 frozen FFD를 통한 6점 3D cubature와 fixed reference Igeom vs actual pre-RF P-conditioned information 분리.

### Full RF J4 prior

| 지표 | M0 B0 | M0 L2 | M45 B0 | M45 L2 |
|---|---:|---:|---:|---:|
| Prior Heading absolute error mean (°) | 6.086 | 6.154 | .709 | .716 |
| Claimed prior Heading sigma mean (°) | .859 | .847 | .408 | .406 |
| High/low Igeom oracle label mismatch | 18.94% | 19.30% | 2.05% | 2.17% |
| 6-point cubature Brier of Igeom class | .1789 | .1835 | .0181 | .0175 |
| **LoS expectation inside predicted geometry-only 95% band** | **30.76%** | **32.21%** | **53.68%** | **53.80%** |

같은 LoS J4 (고정 FFD)에서는 예상 LoS geometric band 포함률이 99.9–100%. DR4 control은 M0 B0 σψ~12.53°/err~0.478°/geometry band~100%, M0 L2 err~23.04°/sigma~12.53°/band 98.91%. 따라서 Full RF J4 posterior의 Heading 오차 대비 **사전 공분산 과신**이 새 geometry-quality head의 근본 장애.

Cubature는 잘못 과신한 P를 입력받으면 그 과신을 바로잡지 못한다. 이 LoS-expectation coverage는 Bayesian posterior 명목 coverage와 다른 진단적 지표지만 같은 estimator의 LoS vs Full 반례는 강하다.

Q4 independent original 32 groups and 26,528 rows metric parity PASS, 과학적 진행 기준 **Q4_highconfidence_calibration_PASS=false**로 고정.

## 5. 다음 단계 게이트/중단 원칙

| Stage | Numerical status | Scientific decision |
|---|---|---|
| Q0 | PASS | frozen sources secured |
| Q1 | PASS | Local LoS information geometry PARTIAL, full profile multimodality not proven |
| Q2 | PASS | Oracle RF contamination decomposition confirmed |
| Q3 | PASS | 2×2 physical distinction and conditional original-J4 harm PARTIAL; independent scenes absent |
| Q4 | PASS | Online prior geometry uncertainty **CALIBRATION FAIL** |
| Q5 | NOT RUN | **BLOCKED_STAGE_GATE**: do not fit/deploy new two-head harmful-Heading score from an invalid online geometry confidence model |
| Q6 | NOT RUN | **BLOCKED_STAGE_GATE**: no new Joint4/SR4 RF factor before validated Q5; preserve frozen POWER_JOINT |
| Q7 | NOT RUN | **BLOCKED_INPUT**: independent multipath/noise scenes, curved/reverse trajectories and Mount cases not present |

계획에 따라 Q5/Q6는 Q4 검증이 실패한 상태에서 성공인 양 강행하지 않는다. Q5의 분리 모델의 오프라인 탐색은 독립 과제로 가능하나 본 계획의 정상 통과 결과가 아니다.

## 6. 정확한 후속 연구 문제

1. RF 독립의 Dead Reckoning prior와 Full J4/POWER_JOINT prior의 **Heading/P covariance 과신**을 분리해 보정하고 실제 LoS response probability가 95% nominal에 도달하는지 검증.
2. Qgeom의 분류를 단일 Hψ 점값 대신 credible yaw interval에서 실제 FFD finite difference, profile multimodality, angle grid/seam/kink를 유지해 산출.
3. MP proxy classifier를 Heading harm 확률에 대입하지 말고, 이미 확인된 low-I/high-MP 위해 관측과 high-I/low-MP 관측을 별도 risk/utility 레이블로 독립 검증.
4. R2 m45 외삽과 LoS false rejection 및 N4-C POWER_JOINT 기준의 Pose NEES/95% coverage를 동시에 개선하는 경우에만 Q5/Q6 재개.
5. 실제 Q7 independent Full/native-LoS scene을 준비하지 않고 한 복도의 반복 샘플을 일반화 결과로 주장하지 않는다.

## 원시 산출물 이름

Q0-Q3 artifact에는 Q0_PRE_AUDIT.json, Q0_Q3_FINAL.json, Q1_GEOMETRY_INFORMATION.csv.gz, Q2_FULL_VS_NATIVE_LOS_RF_ERRORS.csv.gz, Q2_PRIOR_INNOVATION_THREE_TERM.csv.gz, Q3_2X2_CONFUSION.csv, Q3_LABELED_EXAMPLES.csv, Q3_HELDOUT_RF_RISK.csv.gz, Q3_HEADING_HARM_DIAG.csv 등이 있다.
Q4 artifact에는 Q4_PRE_AUDIT.json, Q4_PRIOR_GEOMETRY_FULL_RECORDS.csv.gz, Q4_PRIOR_VS_ORACLE_STATS.csv, Q4_FINAL.json이 있다. 독립 검증에는 Q4_STAGE_GATE.json, Q4_DR4_VS_J4.csv가 있다.

**최종 요약:** 기하 정보량의 부족과 다중경로 오염은 실제로 서로 구별되는 축이다. 그러나 오염된 Joint4의 과신 posterior로 만든 온라인 geometry quality는 제대로 calibrated되지 않는다. 현재는 두 축 분리의 물리적 근거는 얻었으나 새 융합 정책의 재귀 성공에 필요한 검증은 아직 없다.
