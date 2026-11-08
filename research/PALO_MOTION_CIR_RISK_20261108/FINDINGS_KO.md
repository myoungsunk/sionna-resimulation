# PALO — 운동 신뢰도와 first-path 국소 CIR 확산의 실제 저장 데이터 진단

**상태:** R2 실제 저장 시뮬레이션 원본 비교 PASS / 온라인 선택기 폐루프·새 환경 일반화 NOT ESTABLISHED. 
기준: 원시 PALO **8894353b**, 저장된 Full/LoS Sionna H **047cce2**, 분석 코드 **86f6403**, Actions **#42462035988**, 결과 **b7bacb08**.
자료: [분석 원시 결과](runs/42462035988), [실행 소스](run_analysis.py), [Actions](https://github.com/myoungsunk/sionna-resimulation/actions/runs/42462035988).

## 1. 데이터 재현 및 검증 범위

- R2 Anchor B mount0: RF 979프레임; Full/LoS 원시 복소 주파수 응답 1303 pose × 257 frequency × 2RX × 2TX.
- R2 원본의 pose 정합: 최대 위치 4.9982e-7 m, 헤딩 4.8228e-7 deg.
- Hann257, zero-pad1028, IFFT×257, strongest-RX 30% leading edge로 원본에서 s 재생: **Full/LoS 모두 RMSE 0; correlation 1.0**.
- t>=40 s의 DR·S4 × B0/L0/L1/L2 총 **6232개 prior 진단 행** (동일 RF 779개의 재사용이며 독립 표본 6232개가 아님).
- 이 H는 **noise-free 저장된 Sionna RF 배열**이며 로봇 실물 UWB RX의 992-tap raw CIR 실측이 아니다. 실제 하드웨어의 CIR port 제공 가능성 미검증. Zero-padding tap 폭은 물리 분해능이 아니다.
- 참 헤딩, 참 바이어스, Full−LoS 편파 차이는 오프라인 평가·라벨에만 사용. 온라인 특징에 포함하지 않음.

## 2. 네 가지 운동 정보 시험

| 검증 | 결과 | 판정 |
|---|---|---|
| ① 자이로 바이어스 및 S4 bias 공분산 | t>=40s 추정 bias MAE B0 .03599, L0 .03571, L1 .03368, L2 .03004 deg/s; bias sigma RMS 약 .0196–.0205 deg/s | **수치 검증 완료; 공분산 과신** |
| ② 원시 좌·우 엔코더 대 IMU 회전 | PALO 입력엔 ds_odom과 dtheta_gyro만 있으며 독립 좌·우 회전 증분 없음 | **BLOCKED** |
| ③ 정지 시 gyro zero-rate update | 참 위치·헤딩이 모두 정지인 표본 **0**, 온라인 정지 후보 **0**, 연속 2초 정지 구간 **0** | **정지 바이어스 추정 불가능; 편의상 가짜 정지 생성 금지** |
| ④ LiDAR scan-to-scan 상대 회전 | R2 PALO 입력에 raw LaserScan 또는 독립 scan matching yaw 없음 | **BLOCKED** |

### S4 자이로 바이어스의 통계적 불일치

| 실제 바이어스 deg/s | S4 추정 평균 deg/s | MAE deg/s | 95% 포함률 |
|---:|---:|---:|---:|
| 0 (B0) | +.03153 | .03599 | **19.13%** |
| .01 (L0) | +.04124 | .03571 | **19.13%** |
| .05 (L1) | +.07946 | .03368 | **31.58%** |
| .2 (L2) | +.22620 | .03004 | **35.94%** |

S4에서 공분산 수식이 정합하더라도 실제 gyro bias 신뢰구간은 일관되지 않다. 해당 차이가 **다중경로만의 원인**인지는 LoS S4 동일 조건과의 직접 대조 이전에 단정하지 않는다.

## 3. FP 부근 국소 pulse spreading — 전역 delay spread 아님

기본 관측은 기존 strongest-RX k_fp와 양 RX 포트 동일 FP tap의 s=(P1−P2)/(P1+P2)를 유지한다.
Power p_i[n]=|CIR_i[n]|²를 사용하며, FP 국소 범위 **k_fp-4..k_fp+8 (13개 zero-pad tap)**에서 두 RX 각각의 가중 중심·표준편차(σ_FP)를 계산한다.
보조 window: narrow [-2,+4], wide [-8,+16]. RX별 국소 σ의 평균·차이, 형태 JSD, FP 이후 국소 에너지율, 탭 ±2의 Δs를 별도로 기록한다.

**원본 대응 B0/S4, t>=40s 779개 실제 RF 프레임의 독립 재집계:**

| 입력 특징 | 큰 RF 차이 \|sFull−sLoS\|>.10 구분 AUC | 즉시 큰 헤딩 손실 >0.5deg 구분 AUC |
|---|---:|---:|
| FP 국소 폭 13tap | **.678** | **.476** |
| 국소 폭 25tap | .566 | .776 |
| FP ±2tap Δs 절대 최대 | .632 | .308 |
| RX 간 13tap 형태 JSD | .235 (낮은 값 쪽 연관) | .469 |
| LUT \|∂s/∂ψ\| | .536 | .908 |
| 현재 s의 시점차 절대값 | .324 | .901 |

RF 큰 차이 양성 135/779, 헤딩 큰 손실 양성 **11/779**. **심한 헤딩 손실 사례는 매우 소수이고 특정 구간에 집중돼 있으므로 AUC=.776/.908/.901을 일반화·검출 성공으로 주장하지 않는다.** 이 표는 원인적 독립 효과도 아니다.
FP 국소 폭의 중앙값: RF 차이≤.10 그룹 2.055 zero-pad tap(n=644), >.10 그룹 2.125 tap(n=135). FP ±2 Δs 절대 최대 중앙값은 .0466 vs .0908.

**핵심:** FP 근처 waveform 폭은 RF 기하·전파 차이를 설명하는 후보이지만, 해당 측정을 *현재 추정기의 헤딩에 적용하는 것*의 손익과 동일한 라벨이 아니다. RF 품질만으로 수용 결정하지 않는다.

## 4. 동결 구간 공분산 재보정의 진단 — 조건 이동 시 실패

추가 사후 진단 (라벨은 보정과 평가에만 사용, 온라인 입력 금지):
t=40–100s의 S4에서 pooled [B0,L0,L1,L2] `|estimated true-error|/reported sigma` 분포로 95% 경험분위를 맞추는 **단일 σ 배율**을 정한 뒤 t>=140s에 그대로 적용.

- S4 bias σ 배율 **1.507배**. 뒤 구간 bias 95% 포함률 전체 **12.2%** (조건별 B0 13.6%, L0 10.0%, L1 13.3%, L2 11.8%): **목표 95% 미달**.
- S4 Heading prior σ 배율 **1.084배**. 뒤 구간 heading 95% 포함률 **72.2% → 74.3%**: **목표 95% 미달**.

이는 **실제 실측 반복이 아닌 단일 R2 RF 시계열의 탐색적 시간 분할 검산**이다. 통계적 보정 인증 또는 모델 채택은 불가. 공분산만 일률적으로 키우는 방식의 제약을 보여준다.

## 5. 온라인 특징 기반 간단한 선택 규칙 시험 — 채택 불가

동일 R2 안에서 fit 40–100s, calibration 100–120s, gap 120–140s, test >=140s. B0/L0/L1/L2·DR/S4 donor 동일 RF 공유. 현재 상태·LUT 기울기·FP 국소 지표 기반 logistic 모델 세 종류 비교. 임계값은 calibration에서 고정.

- MOTION 단독: DR 4조건 각각 **0/279 수용**.
- MOTION+SLOPE: DR 4조건 각각 **0/279 수용**.
- MOTION+SLOPE+FP: DR 4조건 각각 **1/279 수용**; L1에서 선택한 1건은 >0.5° 헤딩 손실 사례.
- S4 prior는 대부분의 갱신이 수용되었으나 평가 구간에 >0.5° 손실 사건 자체가 없어서 **이 구간의 큰 손실 판별 AUC를 추정할 수 없음**.
- **새 판정기를 정확 폐루프 재귀로 실행하지 않음**; 위는 *저장 prior의 즉시 후보 판단*이며 실제 폐루프 RMSE 개선 결과가 아니다. DR를 사실상 전부 거부하는 방식은 유익한 편파 보정을 확보한 성공으로 볼 수 없음.

## 6. 원인 확인에 필요한 후속 검증

1. **LoS 동일 S4에서 추정 bias와 공분산을 병렬 재계산**하여 Full에서의 bias 오차가 RF 오염 흡수인지, 공통 운동·초기화 오차인지 분리.
2. 과거의 R2/R4/R5 CIR 결과를 참조하되 동일 pose/sensor chain/receiver port가 아닌 데이터를 직접 섞지 말 것. 새 route·RF seed, 주파수별 noise sweep과 다중 장면에서 FP 확산과 실제 보정 손익을 각각 검증.
3. 실제 TB3 raw /joint_states left/right 및 /imu 와 /scan 기록이 확보되면 독립 wheel−gyro·scan−gyro 비교 및 검증된 정지 구간 ZRU를 실시. ROS /odom yaw는 IMU 융합 가능하여 독립 검정에 그대로 사용 금지.
4. 갱신 방향·필요성·손실 위험은 현재 X/P와 IMU 누적오차를 조건으로 판단. RF 확산 품질 특징만으로 수용 가중치 확정 금지.
5. 통계적 calibration, 소수 위험 사건에 대한 독립 route 및 연속 오류 대조, 정확 폐루프 Heading+XY 성능 개선까지 검증 전 모델 채택 보류.

**현재 판정:** MOTION_BIAS_CHECK_PASS / ENCODER_BLOCKED / ZERO_RATE_NO_STATIONARY / LIDAR_BLOCKED / RF_FP_EXTRACT_PASS / ONLINE_SELECTOR_NOT_VALIDATED / SCIENTIFIC_GENERALIZATION_NOT_ESTABLISHED.
