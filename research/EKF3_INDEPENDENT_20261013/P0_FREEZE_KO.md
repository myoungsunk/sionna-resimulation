# 독립 3-State EKF — P0 동결 조건과 근거 (2026-10-13)

## 현재 상태
- **실행한 작업:** 새 브랜치 생성, 기존 자료 Git tree 확인, 기존 감사 SHA-256 값 및 정확한 입력 경로를 `P0_INPUT_MANIFEST.json`에 고정.
- **아직 하지 않은 작업:** 바이너리 파일의 현행 SHA-256 직접 재계산, Tnone–RF pose_id 일치 검사, 신규 observer parity, 독립 3-State 구현 및 A/B/C 실행.
- **판정:** `P0_SPEC_FROZEN; INTEGRITY_GATE_NOT_RUN; scientific_PASS=false`. 과거 source parity PASS를 새 P0의 실행 PASS라고 쓰지 않는다.

## 비교를 왜 이렇게 설계했나?
- 독립 비교군 **D0**는 IMU+Wheel만 이용. **A**는 D0+UWB 다중경로 편파값 `s` 한 개, **B**는 D0+Range 한 개, **C**는 D0+(`s`, Range) 공동 측정.
- RF에서 절대 방향을 추정하지만 원래의 `s` 역함수는 `x,y,ψ`에 의존하고 이전 DR prior를 이용해 root를 선택할 수 있다. 그러므로 최초 공식 실험에서 **direct-s**를 사용한다. 독립적 절대각 관측 `H=[0,0,1]`을 이미 확보했다고 가정하지 않는다.
- 동일 소스, 경로, 시드, Motion `Q`, 초기화, 3×3 `P`로 **측정 구성만 다르게** 한다. D0를 유지해야 RF heading-only 성능을 정확히 해석할 수 있다.
- 기본 비교에는 **한-step 동일 prior 복제 실험**과 **전체 경로 posterior 재귀 실험**을 모두 넣는다. 전자는 측정의 순간 정보, 후자는 미래 운동 예측으로의 전달을 검증한다.

## 입력 선택과 이유
- 데이터: 기존 확증 Sensor-v2의 저장된 **7 case** Full/LoS `H` (R2_aA_m0, R2_aA_m45, R2_aB_m0, R4_aA_m0, R4_aB_m0, R5_aA_m0, R5_aB_m0); 원본 Tnone 시계열(R2 979, R4 742, R5 1415 sample), RF case-pose 9,519건. **모두 한 corridor**로 환경 간 일반화를 주장할 수 없다.
- 원본 `H`는 **동결된 noise-free RF realization**으로, 센서 seed가 새 RF 실현이나 새로운 물리 사이트를 생성하지 않는다.
- 257-bin, TX0(+45 LP), RX±45 LP, Hann→4N IFFT→30% leading-edge→공통 tap `s=(P1-P2)/(P1+P2)`를 바꾸지 않는다. 기존 observer/LUT 구현에 대한 결과와 수학적인 공정 비교를 위해서다.
- 앵커 A=(4,0,2.65)m, B=(10,0,2.65)m; 태그 높이 0.45m. LoS LUT와 first-arrival offset **−0.5315983906250129m**를 R0 기준으로 고정한다.
- 원 Tnone truth는 legacy-Euler에 정확히 맞고 Sensor-v2 exact-SE2에 아주 작은 불일치가 있다. **truth를 수정하거나 이를 무시하지 않고** W0의 모델 정합 실험과 별도로 기록한다.

## State·초기값·잡음 조건과 이유
- 상태 `[x,y,yaw]`, IMU `dtheta_gyro`와 Wheel `ds_odom`만 Motion Prediction 입력으로 사용한다. `dtheta_odom`는 처음에는 기록·진단만 하여 Wheel yaw 관측의 추가 효과와 RF 효과를 혼동하지 않는다.
- 초기값은 동일 세계 좌표계; `P0=diag(0.1²,0.1²,(5° in rad)²)` 및 동일 seed의 실제 초기오차를 4개 arm 모두에 재사용한다.
- W0: 이상적인 수학 모델 검증. W1: 저장 LoS + `noise_pair` 운동 잡음. W2: 저장 Full RF + `noise_pair`, 이후 `all` low/mid/high drift 스트레스.
- `noise_pair` 우선은 3-State에 **의도적으로 빠진** gyro bias/scale, wheel asymmetry 등의 체계적 오차와 기본 EKF 구현 문제를 분리하기 위함이다. 실제 sensor-v2 모드 `all`은 오차가 존재한다; 3-State가 모른다고 이를 참세계에서 0으로 취급해서는 안 된다.
- 개발 seed 0–19, 독립 확증 seed 10000–10049를 사전 지정하고 모든 arm에서 paired로 사용. 이는 고정 RF 채널을 여러 차례 보면서 센서·초기오차를 바꾸는 실험이지 70개 독립 RF 사례가 아니다.

## Covariance와 Gate (R0 진단 기준선)
- Prediction: SE(2) Jacobian `F,G`와 Sensor-v2 Wheel 이동거리·Gyro 입력분산으로 `P^- = F P F^T + G Q_u G^T`; `Q_model=0`은 **noise-only 모델 정합 점검에 한함**, 드리프트 모델 적합을 보증하지 않는다.
- A: `H_s=[∂_x h_s,∂_y h_s,∂_ψ h_s]`, `R_s=R_thermal+0.09²`.
- B: `H_r=[(x-a_x)/d,(y-a_y)/d,0]`, `R_r=0.0068578637 m²`, 기존 검출기 offset은 측정 평균 모델에서 별도 보정.
- C: `H=[H_s;H_r]`, `R=[[R_s,0],[0,R_r]]`의 **R0 독립성 가정**에서 출발. 이는 물리적인 RF 독립성이 검증됐다는 의미가 아니다. 사후 R1(조건부 평균/분산) → R2(동시 `s/r` 상관) → R3(시간상관) 비교를 사전 고정한다.
- Scalar gate 99% χ²(1)=6.6349, Joint gate 99% χ²(2)=9.21034. pre-gate NIS를 반드시 저장하며 같은 관측이 빠진 A/B/C에는 억지로 값을 채우지 않는다.
- 앵커 직하부 추정 수평거리 ≤0.1m는 관측 불안정 **플래그**로 별도 기록. 진짜 `x,y`를 이용해 온라인에서 제외하는 truth leakage를 막는다.

## 통계 및 실패 경계
- 원래 Tnone의 t≥30s만 주 RMSE 구간이지만 EKF는 t0부터 실행. 보정 학습이 필요해지면 R2/R4/R5 **leave-one-ROUTE-out**, 중복 XY 누수 제거 후 동결 계수를 사용한다.
- 기존 6-State에서 Range-only는 DR-only보다 위치 RMSE 1.007→1.285m로 악화, NEES≈1285. 실제 Range/편파 `s` residual에는 평균 편향과 시간 지속성이 있어 **오차 분산 축소를 성능 성공으로 판단하면 안 된다**.
- 최근 LoS 조건부 보정 E1은 Full RF 동일-scene RMSE에 유리하지만 LoS에 과보정; 후속 ERRATA E1–E13이 존재한다. 이 계수는 R0에 섞지 않고 분리 참조한다.
- 공분산 PSD, innovation, NIS/NEES, 95% coverage, heading/위치 RMSE 및 반경/접선 방향 오차를 함께 확인한다. 기존 6-State 숫자를 신규 3-State 결과로 인용하지 않는다.

## P0 완료 정의
1. `P0_INPUT_MANIFEST.json` 기록 및 Git 입력 경로 존재: 완료.
2. `p0_verify_inputs.py`를 원본 바이트가 있는 checkout에서 실행해 SHA-256, 파일 크기, numpy shape, RF pose_id–Tnone 정렬: **NOT_RUN**.
3. observer parity 및 실제 3-State 독립 EKF: P1 이후 단계, **NOT_RUN**.
4. `scientific_PASS=false`; 기존 F01/F02 및 new-scene gate를 승격시키지 않는다.

### P0 무결성 확인 명령
```bash
python research/EKF3_INDEPENDENT_20261013/p0_verify_inputs.py
```
출력의 `status`가 `PASS_LOCAL_SHA256_SHAPE_POSE_PREFLIGHT`가 되기 전에는 후속 P1 실행에 대한 입력 무결성 PASS를 선언하지 않는다.
