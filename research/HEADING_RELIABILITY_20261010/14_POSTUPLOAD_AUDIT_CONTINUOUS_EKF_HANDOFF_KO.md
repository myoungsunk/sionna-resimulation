# 14 — 2026-10-11 최신 noisy-probe 업로드 재검증과 Continuous EKF Active Probe 인계

**판정: 자료/수식 기록 감사 완료; 확률 보정·물리적 운영 성능 scientific PASS 아님.**
검증 소스: codex/probe-mixture-reliability-20261010 HEAD 574ccf2e4f1a9ffb4f8ea920292e048afea356d0; 추가 결과 RUN_01a125b3; 독립 감사 실행 https://github.com/myoungsunk/sionna-resimulation/actions/runs/38063380173.

## 1. 업로드 자료의 검증된 범위

- 총 12개 경로×앵커×mount 조합의 기존 legacy Method-B full H manifest가 존재한다. 추가 다섯 개 mount45 케이스는 신규 native full H 및 LoS H 생성 완료. 그러나 서로 다른 legacy/native 전파 solver의 H가 **동일하다**는 정량 parity는 입증되지 않았다. 따라서 두 계통을 묶어 12개 완전 대칭 성능으로 확정하면 안 된다.
- 53,280개 endpoint 실행 결과행, 이전 prior와 wait+yaw 정렬을 거친 신규 prior를 구분한다. 실제 독립 센서 seed는 다섯 개(0~4)이며 53,280회 독립 실험이 아니다.
- 추가 47,160개 trace에서 4,008,600개 covariance stage 수식·PSD 검산 위반 0. 이는 SE2/Joseph 저장 방정식의 검산이지 추정 오차분포의 올바른 NEES/95% coverage 승인이 아니다.
- 같은 정지 XY에서 사전 지정한 true yaw 회전, 측정 gyro/wheel 잡음·slip 및 SNR10/30 수신기 노이즈를 시뮬레이션했다. 실제 바퀴 slip이 참 XY/yaw를 움직이는 plant와 가감속/제동 동역학은 이번 업로드의 정량 실행 대상이 아니다.
- Σ_sr 169 case-station 중 148개의 공간 통계추정 가능, 21개 자료부족; 32회 독립 thermal repeats. **실제 F/H/q_site/q_point filter에는 적용하지 않았고 pose–RF cross-time covariance도 검증되지 않았다.**

## 2. Sensor-v2 정지 회전 Endpoint 결과와 공분산 검산

Nominal SNR30, 기존 원주행에서 회수한 LEGACY_SAVED_POST_ODOM prior 조건의 case×drift×seed 평균 (station endpoint만, full-route 아님):

| Arm | heading RMSE(°) | position RMSE(m) | pose NEES(df3) | coverage95 |
|---|---:|---:|---:|---:|
| A RF off | 3.018 | 0.738 | 3.209 | 91.6% |
| B 3 range | 3.560 | 0.840 | 13.666 | 48.8% |
| C 3 full range + LoS-only s | 1.639 | 0.404 | 955.523 | 54.9% |
| D 3 full range+s | 3.821 | 0.958 | 1003.982 | 38.0% |
| G1 첫 1 range+s | 3.416 | 0.849 | 386.873 | 68.3% |
| G2 첫 2 range+s | 3.822 | 0.952 | 868.391 | 48.4% |

새 대기/정렬 prior 조건의 SNR30: A 3.145°/NEES7.298, B 3.832°/13.772, C 1.986°/12.975, D 3.635°/18.608, G1 3.510°/10.275, G2 3.650°/13.687. **Prior 종류별 결과가 현저히 다르므로 혼합해서 단일 성능으로 주장하면 안 된다.** C의 작은 heading RMSE에도 불구하고 NEES 955 이상인 것은 관측의 공분산 과신 가능성을 제기한다.

## 3. 첫 도착 편파비 재검산

업로드된 FP_CLUSTER_RATIO_existing7.csv를 직접 pair-join하고 양 포트 첫 tap 전력에서 s_FP를 재계산했다. Full/LoS 각 507개 동일 pose, s 수치 parity 최대오차 1e-10 이내.

**명세 간 중요한 차이:** 이전 공통 창은 4/8/16 zero-padded taps로 분석했다. 신규 receiver_existing7.py 구현은 창 끝에 +1 sample을 포함해 명목상 2/4/8ns 창에서 실제 **5/9/17 taps**를 합산했다. 따라서 둘의 편파비 숫자를 관측 정의가 같은 것처럼 직접 비교하지 않는다.

| 업로드한 창 | RMS(full−LoS s_gate) | Pearson(|e_FP|, |e_gate|) | |e_FP|<0.05, |e_gate|>0.1 |
|---|---:|---:|---:|
| 2ns, 실제 5 taps | 0.3313 | +0.800 | 11.6% |
| 4ns, 실제 9 taps | 0.3964 | +0.593 | 23.7% |
| 8ns, 실제 17 taps | 0.4144 | +0.486 | 27.2% |

이는 RF 채널/관측체인의 LoS 대비 mismatch이고 진정한 탈편파도(전체 Stokes DoP) 측정이 아니다. 실제 magnitude-CIR 출력 지원 여부도 여전히 미확인. Cluster를 FP-only LUT의 s 관측으로 직접 대입하려면 동일 창의 clean LoS LUT를 따로 검증해야 한다.

## 4. 핵심 설계 결함 및 최소 보완

1. 기존 HARNESS/body_controls.py의 G1/G2 gate는 s뿐 아니라 range도 1/2개로 제한한다. 따라서 G1/G2와 D 차이를 **편파 정보를 1/2/3개 추가한 효과만**으로 해석하면 안 된다. 보완 대조 G1′/G2′에서는 모든 arm에 range 3개를 동일하게 적용하고 s만 처음 1/2/3개 사용한다.
2. 신규 native full H 5개와 기존 legacy Method-B 7개 간 solver parity, LUT/LoS baseline F01/L1는 미해결이다. 소스 SHA·pose/port/angle convention을 고정하고 동일 주파수/pose의 complex H 비교를 선행한다.
3. site-/point-level latent reliability q_site/q_i, 시점 간 EKF crosscov를 반영한 joint posterior, 실제 full-route 동적 stop/probe/return은 업로드된 RUN_01a125b3에서는 구현/실행하지 않았다.
4. Q/R을 튜닝하여 NEES를 인위적으로 낮추지 말고, origin of range bias, s/range correlation, cross-time P6 및 RF 오염 확률 calibration을 분리 검증한다.

## 5. 연속 EKF를 구현할 수 있는가? 기존 bank 재생 결과

별도의 corrected 기존 RF bank 연속 EKF 검증: GitHub Actions https://github.com/myoungsunk/sionna-resimulation/actions/runs/38054331364, 7case×3drift×8seed×5arm=840개 완결, 평가 t>=30 Tnone (R2 829, R4 592, R5 1265).

| Arm | heading RMSE(°) | pos RMSE(m) | NEES | pose95 coverage |
|---|---:|---:|---:|---:|
| D full RF every tick | 2.873 | .340 | 170.7 | 13.4% |
| E passive confidence | 2.909 | .361 | 156.4 | 19.5% |
| F2 stop+2yaw+resume | 2.820 | .349 | 161.8 | 19.8% |
| F3 stop+3yaw+resume | 2.787 | .344 | 180.4 | 19.3% |
| SHAM same turning, no batch s | 2.838 | .352 | 207.2 | 19.4% |

F3−E heading RMSE -0.122°, but NEES +23.94 worse; seven case unit bootstrap CI contains zero. R2-A mount0 substantially improves; R5-A mount0 worsens. 기존 bank는 54군데 predetermined station과 **즉시 정지**를 가정하므로 arbitrary XY/dynamic slip generalization은 아니다. 그래도 **프로브 결과를 이후 매 시점의 Sensor-v2 EKF 전체 x6/P6로 전달하는 실험이 가능하며 이미 실행됐다**는 점을 입증한다.

## 6. 실제 동적 주행 코드 — 검증 가능한 범위

동적 구동 원형: codex/noisy-probe-ekf-sionna-20261010. 차륜 plant의 motor 속도/가감속 및 물리 slip이 true XY/yaw를 변경하며, streaming gyro/odom, 6state EKF, estimated-heading probe controller, exact-pose native Sionna 호출 어댑터가 연결됐다. 하지만 원 branch는 단일 정지 probe 및 analytical mock test까지였다. 실물 FFD bank/LUT 경로와 native solver 실제 실행은 아직 별도.

신규 codex/continuous-trigger-ekf-bridge-20261011:
- body_active_drive.py: 상시 구동 물리센서+EKF range→RF confidence→좋으면 s update, 낮으면 RF withheld→실제 body stop/2–3각 RF→site joint callback→return→**동일 EKF x6/P6로 주행 재개**. 주행 중 trigger s를 정지 중 첫 probe로 잘못 재사용하지 않는다.
- body_pose_channel.py와 body_probe_loop.py: first-arrival 공통 gate 4/8/16 tap P1/P2, s_gate를 phase 없는 측정 RF packet으로 전달; 각 각도마다 estimated x,y,yaw 및 full P6 저장.
- body_site_mixture.py: 2×2^M site + point clean/dirty hypotheses, 모두의 s를 사용한 full6D Gaussian Joseph posterior와 mode-matched x6/P6, q_site/q_point 산출. **모델 파라미터는 기존 미보정 탐색 가정**, cross-time pose–measurement covariance는 검증되지 않았으므로 추정 성공과 신뢰도 calibration PASS는 구분해야 한다.
- MOCK-only contract tests 27개, GitHub Actions https://github.com/myoungsunk/sionna-resimulation/actions/runs/38064700458 성공. 첫 도착 gate, 모의 RF, 정지→연속 EKF 복귀, 중복 RF 방지, P6 PSD 검증. 실제 native Sionna/로봇 경로 성능으로 해석 금지.

## 7. 다음 과학 검증의 정확한 우선순위

P0: 원데이터 provenance, native/legacy H parity, first-gate 4/8/16 vs 5/9/17 창 정의 하나로 동결, G1′/G2′ full range 유지 대조.
P1: q_site/q_point의 독립 학습/held-out calibration, thermal 시점 공분산과 pose–measurement cross-time P6 정합, RF-수신기 CIR 사용 가능 범위 분리.
P2: 외부 보존된 실제 FFD bank와 LUT를 새 dynamic runner 설정에 연결하고 Native Sionna exact physical pose H를 생성. 12 케이스, mount0/45, control/timeout/stop cost/thermal SNR을 동등하게 비교한다. Trigger-free / passive / SHAM / F2/F3 / q+CIR F/H를 비교하며 scientific_PASS는 독립 검증 전 false.
P3: 복도 폭·벽 재질·앵커 위치 등 신규 geometry 완전 분리 평가. Heading/pos RMSE, NEES/95coverage, harmful update, q calibration Brier/AUROC/ECE, 시간/정지 비용 모두 통과해야 일반화 주장 가능.

**최종 판정:** 데이터 수식·실행 이력 검산 범위는 Ready, 실제 joint reliability 및 physical closed-loop 과학적 채택은 Needs revision. F01/F02 OPEN, L1 FAIL, scientific_PASS=false 그대로 유지.
