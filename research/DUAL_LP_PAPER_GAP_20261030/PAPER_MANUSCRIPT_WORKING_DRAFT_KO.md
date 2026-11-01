# Dual-LP Heading Estimation and EKF Fusion — 논문 원고·근거 통합 작업본

> **원고 상태: WORKING_DRAFT / PROPOSER / 기존 데이터 기반 / NOT_FROZEN**  
> 업데이트: 2026-11-01. 이 문서는 **하나의 누적 원고**이며, 기존 연구 결과를 새로운 검증으로 가장하지 않는다. 구현·신규 RF 생성·EKF 재실행·독립 감사 없음.  
> 고정 데이터 계열: **C0 = 기존 Corridor R2/R4/R5의 동일 Full/Native-LoS RF + Sensor-v2** (MBVAR 실험의 “C0” 단계와 이름이 같아도 다른 용어).  
> 근거 판독 기준: Git commit **6c7200091028fd3f0e55aa83b777d0f10b7cf063** 및 명시한 기존 실행 기록. 추후 다른 원본이 유입되면 **출처와 버전을 추가**하며 본 원고의 옛 수치를 조용히 교체하지 않는다.
>
> **읽는 법:** 각 절의 “논문 원고 초안”은 실제 논문 본문으로 편집·번역 가능한 문장이다. “데이터/소스 위치”에는 GitHub 직접 링크를, “작성 시 유의사항”에는 주장 제한과 미확정 결정을 기록한다. **[미확정]** 및 **[추가 데이터 대기]**는 빈칸을 임의 수치로 채우지 않는다.

## 원고 구성과 작성 상태

| 단계 | 제목 | 이 문서의 상태 |
|---|---|---|
| 1 | Simulation Setup | **기존 데이터 기반 본문 초안 작성** |
| 2 | Dual-LP Heading Concept | **기존 데이터 기반 본문 초안 작성** |
| 3-A | RF Measurement Error Formation | **기존 데이터 기반 본문 초안 작성** |
| 3-B | Conditional Bias and Signed Error | **기존 데이터 기반 본문 초안 작성** |
| 3-C | Heteroscedasticity and Joint Covariance | **기존 데이터 기반 본문 초안 작성** |
| 3-D | Spatiotemporal Correlation and Information Redundancy | **RESERVED: 핵심 연구로 별도 정교화, 원고 보류** |
| 3-E | State-Dependent Utility and Recursive Propagation | **기존 데이터 기반 본문 초안 작성** |
| 4 | Characteristic-Aware EKF | **확정 가능한 공통 수식만; 최종 방식 미정** |
| 5 | Performance Comparison | **검증된 기존 비교만; 누락 비교군 대기** |
| 6 | Limitations | **기존 데이터가 뒷받침하는 한계 초안 작성** |

---

# 1. Simulation Setup

## 1.1. 시뮬레이션 환경과 좌표계

### 논문 원고 초안

본 연구는 단일 앵커의 이중 선형 편파(Dual Linear Polarization, Dual-LP) UWB 관측이 이동 로봇의 heading을 제약하는 능력과, 다중경로로 오염된 관측이 재귀 상태추정에 미치는 영향을 분석하기 위해 동일한 실내 복도 환경에서 생성한 고정 RF 채널을 사용하였다. 시뮬레이션 공간은 길이 **20 m**, 폭 **2.4 m**, 높이 **2.7 m**의 직육면체 복도로 구성하였다. 좌표계는 오른손 좌표계이며 \(z\)축은 상방, 바닥면은 \(z=0\)으로 정의하였다. 로봇에 장착된 UWB 수신 안테나의 기준 높이는 **0.45 m**, 천장에 설치된 앵커의 안테나 기준 높이는 **2.65 m**이다.

기존 RF 데이터에는 앵커 A \((4,0,2.65)\,\mathrm{m}\)와 앵커 B \((10,0,2.65)\,\mathrm{m}\)가 포함된다. 연구의 기본 관측 실험은 **한 번에 하나의 앵커를 사용하는 단일 앵커 구성**이며, 앵커 위치에 따른 결과를 비교하기 위해 A와 B에 대해 별도 RF 사례를 보존하였다. 앵커 안테나의 보어사이트(boresight)는 아래쪽을, 로봇 안테나의 보어사이트는 위쪽을 향하도록 설정하였고, 로봇 안테나 자세는 주행 yaw에 따라 회전한다. 복도 경계의 재질 모델에는 바닥·천장·양 끝벽의 concrete(두께 **0.20 m**)와 양 측벽의 plasterboard(두께 **0.0125 m**)가 사용되었다. 이들은 시뮬레이터에서 지정한 재료 특성이며 실측된 실제 건축 재료의 보증값은 아니다.

### 데이터/소스 위치

- [Corridor scene 및 좌표축/안테나 회전 원본 코드](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/src/qclean_uwb/scenarios/corridor.py)
- [실제 연구의 초기 복도/소재/RT 설정 계획](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/results/DRIVE_SIM_20261007/PLAN.md)
- [재료·앵커·행렬 shape·SHA를 포함한 동결 사례 레지스터](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/CASES.json)
- [환경 3D 도해 예비 파일](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/results/CORRIDOR_SETUP_20261006/corridor_setup_3d.png) — **시각화 전용**, RF 실행 영수증 아님.

### 작성 시 유의사항

- **하나의 복도 장면**에서 A/B와 여러 주행 경로를 바꾼 것이다. 7개 case를 7개의 독립 multipath 환경으로 표현하지 않는다.
- 기존 두 앵커의 **별도 single-anchor 자료**와 세 개 이상의 앵커의 **동시 다중 앵커 관측**은 다르다. 후자는 현재 C0에 확인되지 않아 Section 5에서 **[추가 데이터 대기]**로 남긴다.
- 옛 시각화 구성 파일은 상태가 **SETUP_VISUALISATION_ONLY_NO_RF_RUN**이다. 그림을 재사용하더라도 확정된 채널 물리 구현의 독립 검증으로 쓰지 않는다.
- 실제 전체 채널의 재료·반사 설정과 경로 깊이는 입력 해시 및 원본 RF producer receipt로 재확인해야 한다. LoS 레지스터의 max_depth=0은 LoS 기준 데이터의 설정으로, Full RF에 그대로 옮겨 적어서는 안 된다.

## 1.2. 안테나 편파 구조 및 RF 채널

### 논문 원고 초안

앵커는 \(+45^\circ\) 선형 편파를 송신하는 TX 포트를 사용하고, 이동 로봇의 수신기는 \(+45^\circ\) 및 \(-45^\circ\) 선형 편파를 가지는 두 수신 포트를 이용한다. 수신 안테나의 장착각(mount offset)은 로봇 몸체 yaw와 별도로 정의하였다. 고정 데이터에는 **0°** 장착각이 모든 R2/R4/R5 경로에 포함되며, **45°** 장착각은 R2–Anchor A의 추가 사례로 포함된다. 이상적인 단순 편파 각도식 대신, 각 포트의 3차원 방사패턴과 실제 송수신 방향을 반영하는 주파수별 FFD(Far-Field Data)를 사용하였다.

주파수 영역 채널은 **6.2504–6.7496 GHz**의 **257개 주파수점**으로 저장되어 있으며, 주파수 간격은 **1.95 MHz**, 중심주파수는 **6.5 GHz**, 양 끝 주파수 차이는 **499.2 MHz**이다. 각 포즈의 채널 행렬은 \(H\in\mathbb C^{257\times2_{\rm RX}\times2_{\rm TX}}\) 형태로 보존되며, 실제 단일 송신 구성의 관측값 계산에는 TX index 0(\(+45^\circ\))을 사용하였다. FFD bank의 전계 배열은 포트마다 complex64의 **(257, 181, 361)** 형상으로 확인되었다.

각 포즈에 대해 직접경로(LoS)만 포함된 복소 채널 \(H_{\mathrm{LoS}}\)와 전체 경로를 포함한 \(H_{\mathrm{Full}}\)이 동일한 안테나·포즈 설정으로 저장되어 있다. 두 채널을 같은 \((\mathrm{case},\mathrm{pose\_id})\)에 대응시킴으로써, 전체 관측의 오차와 직접경로 기준 오차를 구분할 수 있다.

### 데이터/소스 위치

- [원본 FFD bank의 파일 크기·SHA256·주파수 축 영수증](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/FFD_P0P3_20261016/SOURCE_BANK_RECEIPT.json)
- [실제 RF 저장 배열의 레지스터](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/CASES.json)
- [Full RF 채널 데이터 폴더](https://github.com/myoungsunk/sionna-resimulation/tree/6c7200091028fd3f0e55aa83b777d0f10b7cf063/results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/FULL_RF)
- [FFD/source 기반 직접경로 재검산 결과](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/FFD_P0P3_20261016/RESULTS_KO.md)

### 작성 시 유의사항

- \(\pm45^\circ\)는 포트의 **명목 편파축**이다. 모든 입사각에서 완전 직교·이상적인 \(s=\cos2\psi\) 동작을 보장하지 않는다. 실제 분석은 주파수별 FFD 작동점에 근거해야 한다.
- FFD bank가 파일 단위로 검증되었다는 사실은 원래 EM 설계·제작 안테나의 물리적 정확도 검증과 다르다. 개별 원시 .ffd export에 대한 재-export 검증은 미실시다.
- LoS와 Full은 서로 대응하는 **동일 정적 RF realization의 두 채널 버전**이다. 상호 독립적인 두 무선 환경으로 세지 않는다.

## 1.3. CIR 변환과 편파·거리 관측기

### 논문 원고 초안

주파수 영역에서 얻은 복소 채널을 CIR(Channel Impulse Response)로 변환할 때 각 포트의 257개 주파수 샘플에 Hann window를 적용한 뒤 **4배 zero-padding(총 1,028개 지연 샘플)**을 사용하여 역 FFT를 수행하였다. 첫 경로 지연 검출은 선택한 TX 열에서 두 RX 포트 중 가장 큰 peak를 갖는 포트를 기준으로, 해당 peak 진폭의 **30% 이상**이 되는 최초 지연 샘플을 선택하도록 정의하였다. 이 첫 경로 인덱스 \(n_{\mathrm{FP}}\)는 두 수신 포트에 **공통 적용**된다.

두 수신 포트의 첫 경로 전력과 정규화 편파 관측값은 다음과 같다.

\[
P_{+}=|h_{+}[n_{\mathrm{FP}}]|^2,\quad
P_{-}=|h_{-}[n_{\mathrm{FP}}]|^2,\qquad
s_{\mathrm{FP}}=\frac{P_{+}-P_{-}}{P_{+}+P_{-}}.
\]

거리 관측은 검출된 첫 경로 지연으로부터 \(r_{\mathrm{FP}}=c\,\tau_{\mathrm{FP}}\) 형태로 구성한다. 저장된 채널의 기본 처리에서는 주파수 간격 \(\Delta f=1.95\,\mathrm{MHz}\)에 의해 zero-padded CIR의 지연 샘플 간격이

\[
\Delta\tau=\frac{1}{1028\,\Delta f}\approx0.49885\,\mathrm{ns}
\]

가 된다. 그러나 4배 zero-padding은 지연축 보간을 위한 것이며, 원래 약 **499.2 MHz**의 대역폭으로 정해지는 물리적 분리능 \(1/B\approx2.003\,\mathrm{ns}\)가 4배 개선되었다는 의미는 아니다.

기존 Conventional EKF는 거리 측정모델에 \(h_r=d+b_{\mathrm{det}}\) 형태의 연속 거리 근사식을 사용했고, 기존 상수는 \(b_{\mathrm{det}}=-0.5315983906250129\,\mathrm{m}\)이었다. 후속 SourceFFD 연구에서는 편파 관측함수 \(h_s\)를 원본 FFD 기반으로 정교화하면서도 비교 공정성을 위해 이 거리 근사식을 유지하였다. 따라서 첫 경로 검출기의 실제 이산 거리 관측과 EKF에서 사용하는 연속형 거리 likelihood가 완전히 일치한다고 가정하지 않는다.

### 데이터/소스 위치

- [Hann/4N-IFFT/30% leading-edge/shared tap 실제 관측기 코드](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/src/qclean_uwb/drivesim/observation.py)
- [기존 EKF3 기준 첫 경로 및 거리 오프셋 계약](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/EKF3_INDEPENDENT_20261013/P0_FREEZE_KO.md)
- [SourceFFD에서 거리 bridge를 그대로 유지한 이력 및 결과](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/FFD_P0P3_20261016/RESULTS_KO.md)

### 작성 시 유의사항

- 수식의 \(r_{\mathrm{FP}}\)는 **측정값**이고 \(h_r=d+b_{\mathrm{det}}\)는 **필터가 사용하는 예측함수**다. 서로 다른 객체를 모두 “true range”로 기재하지 않는다.
- 같은 \(n_{\mathrm{FP}}\)를 써야 정의한 \(s\)가 기존 코드와 일치한다. 포트별 독립 tap, 전체 대역 전력비 및 Jones-based 지표는 별도 특징으로만 표시한다.
- 원 RF \(H\)는 고정된 noise-free 저장 채널이다. RF receiver thermal-noise sweep을 실제로 수행한 실험과 혼동하지 않는다.

## 1.4. 주행 궤적, RF 사례, 평가 모집단

### 논문 원고 초안

로봇은 동일 복도 안에서 세 가지 주행 형태를 수행한다. R2는 왕복 loop, R4는 복도 내 zigzag, R5는 여러 구간을 왕복하는 serpentine 형태이다. 표준 주행 속도는 **0.2 m/s**, 기록 주파수는 **5 Hz**로 설정되어 주행 구간의 시간 간격은 **0.2 s**이다. 방향 전환 구간에는 제자리 회전이 포함되며, 이동·회전 및 별도의 yaw 관측 포즈를 구분한다.

기존 C0는 R2의 세 사례(Anchor A의 mount 0°/45°, Anchor B의 mount 0°), R4의 두 사례(Anchor A/B, mount 0°), R5의 두 사례(Anchor A/B, mount 0°)로 구성되어 있다. 채널 특성 분석에 사용한 저장 RF 포즈 수는 Full/LoS 각각 **9,519개**이고, 이 가운데 주행 시계열에서 대응되는 포즈는 각각 **7,251개**이다. 후자는 동일한 고정 RF를 시간순 센서 입력과 정렬해 EKF 재귀 성능을 평가하는 데 사용한다. 전체 RF 포즈에는 주행 외 yaw 변화를 포함한 정적 진단 포즈가 존재하므로, 두 모집단을 구분한다.

| Route/case | Anchor | Mount | 전체 RF pose/채널 | 주행 시계열/채널 |
|---|---|---:|---:|---:|
| R2_aA_m0 | A | 0° | 1,303 | 979 |
| R2_aA_m45 | A | 45° | 1,303 | 979 |
| R2_aB_m0 | B | 0° | 1,303 | 979 |
| R4_aA_m0 | A | 0° | 922 | 742 |
| R4_aB_m0 | B | 0° | 922 | 742 |
| R5_aA_m0 | A | 0° | 1,883 | 1,415 |
| R5_aB_m0 | B | 0° | 1,883 | 1,415 |
| **합계(각 channel)** | | | **9,519** | **7,251** |

### 데이터/소스 위치

- [R2/R4/R5 궤적 생성기 및 A/B 앵커 배치](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/src/qclean_uwb/drivesim/routes.py)
- [C0 고정 실험 입력 매니페스트 및 사례별 path/shape](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json)
- [Sensor-v2 본 실행의 입력 자료 및 일치성 검증](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/FINAL_REPORT_KO.md)

### 작성 시 유의사항

- “9,519 pairs”는 **9,519개의 동일 pose에 대응한 Full/LoS 한 쌍**을 의미한다. 두 채널을 더한 관측 행 수는 19,038개지만 독립 RF draw 19,038개가 아니다.
- 동일 경로의 A/B/Mount 반복과 센서 시드 반복은 새 독립 환경이 아니다. Route 수준 held-out 분석은 같은 corridor 내 route transfer이지 independent scene validation이 아니다.
- Full 동적 trace는 시간 \(t=0\)부터 계산하고, 주 RMSE 평가구간은 기존 기준대로 **\(t\ge30\,\mathrm{s}\)**로 정렬한다. 동적 결과의 timestamp/pose key 동등성은 원고 확정 전 per-arm로 재확인한다.

## 1.5. 운동 센서, 상태모델 및 대조군 조건

### 논문 원고 초안

이동 로봇의 운동 입력은 wheel odometry의 이동거리와 gyro의 각도 증가량으로 구성하였다. 기존 Sensor-v2 생성기는 로봇의 명목 바퀴 반지름 **0.033 m**, wheelbase **0.287 m**를 바탕으로 gyro 및 wheel 센서오차를 제어하며, 공통 C0 RF 데이터를 유지하면서 제어 입력과 초기오차의 시드·조건을 변화시킬 수 있도록 설계되었다.

본 논문의 단일 앵커 주 상태추정 모델은 \(\mathbf x=[x,y,\psi,b_g]^{T}\)의 **4-State** 모델로 설정한다. 분석된 gyro bias 조건은 실제 bias가 0인 B0, 그리고 **+0.01, +0.05, +0.20 °/s**인 L0/L1/L2이다. 특히 과거 R2 장착각 비교 실험은 gyro/wheel의 대응 white noise를 유지하면서 나머지 체계적 drift, slip 및 bias random walk를 비활성화하여 gyro bias의 영향을 분리한 조건이다. 별도로 수행된 Sensor-v2의 “all” drift 실험과 동일 조건이라고 가정하지 않는다.

기존 Conventional joint 관측의 명목 공분산은

\[
\mathbf R_{0}=\operatorname{diag}(0.0068578637\,\mathrm{m^2},\,0.0081)
\]

이며, 벡터 순서는 \([r,s]\)이다. scalar measurement의 99% NIS gate는 자유도 1의 \(\chi^2=6.6349\), joint Range–Polarization의 99% gate는 자유도 2의 \(\chi^2=9.2103\)을 기준으로 사용하였다. 이는 초기 nominal 모델의 가정이지, 다중경로 조건에서 공분산이 실제로 보정되어 있다는 증거는 아니다.

### 데이터/소스 위치

- [Sensor-v2의 오차항·독립 RNG stream·명목 기하](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/src/qclean_uwb/drivesim/sensor_v2.py)
- [4-State gyro bias 분리, B0/L0/L1/L2 및 반복 평가 원본](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/EKF4_RANGE_S_STAGED_20261014/R2_MOUNT0_45_GYRO_BIAS_B0_L0_L1_L2_RESULTS_20261015_KO.md)
- [기존 4-State 구현 및 상태전이 기준](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/EKF4_RANGE_S_STAGED_20261014/core.py)

### 작성 시 유의사항

- 기존 3-State EKF, 4-State EKF, 6-State calibration EKF의 추정 결과는 서로 다른 모델이다. **EKF3의 '3'은 앵커 수가 아니라 상태변수 수**다.
- 4-State 실험의 최초 상태값·공분산 \((\hat x_0,P_0)\), \(F,Q\), seed 및 gate 패킷 수를 **동일한 frozen 실행 코드**로 확정한 뒤 Table I의 숫자를 완성해야 한다. 3-State의 0.1 m/5° pose prior를 무검증으로 4-State의 모든 요소에 복사하지 않는다.
- 기존 궤적 truth는 legacy-Euler 적분 규약이며, 새 exact-SE(2) arc propagation과 최대 약 **0.000146 m**의 위치 차이를 보인 기록이 있다. 엄밀한 model-consistent truth라고 설명하지 않는다.
- 4-State bias의 직접 측정 Jacobian 열은 0이지만, 운동모델의 covariance 결합을 통해 간접 갱신될 수 있다. 이를 Sensor-v2 센서 정의와 구분하여 Section 2/3-E에 기술한다.

## 1.6. 논문 공통 데이터 사용 규칙과 Table I

### 논문 원고 초안

모든 기존 연구의 결과는 동일한 물리 RF 원본을 사용했는지 여부와, 서로 다른 관측모델·전처리·상태동역학을 사용했는지를 분리해 추적하였다. 원본 \(H_{\mathrm{Full}}\) 및 \(H_{\mathrm{LoS}}\), FFD bank, pose/time 레지스터의 SHA를 논문 데이터 계열 C0의 고정 입력으로 취급한다. 본 연구의 오프라인 GT 위치·Heading 및 Native LoS 채널은 측정오차 분석, 모델 비교의 ground truth, 학습 라벨 구성에만 사용할 수 있고 deployable EKF 업데이트의 입력으로 사용하지 않는다. 데이터의 신뢰도는 입력·연산 재현성에 관한 기술 검증과 독립 장면에서의 과학적 일반화 검증으로 구분한다.

**Table I. Fixed simulation and observation setup (원고용 후보표)**

| 항목 | 현재 확인된 값 / 범위 | 원고 반영 상태 |
|---|---|---|
| Scene | 20 × 2.4 × 2.7 m Corridor | 기존 RF 계열 설정 확인 |
| Coordinate | Z-up, floor z=0 | 확인 |
| TX anchor | A=(4,0,2.65) m, B=(10,0,2.65) m | 확인; 1-anchor case씩 사용 |
| Tag RX height | 0.45 m | 확인 |
| Mount | 0°, R2-A에서 추가 45° | 확인 |
| TX / RX | +45° TX 1포트 / ±45° RX 2포트 | 확인 |
| FFD | 2 bank; complex64; (257,181,361) | 파일/shape 확인 |
| Frequency | 6.2504–6.7496 GHz / 257 points / 1.95 MHz | 확인 |
| CIR observation | Hann; 4× zero-padding; 30% leading edge; shared FP tap | 확인 |
| Fixed RF source | Full 및 Native LoS, paired 9,519 pose/channel | 확인 |
| Motion routes | R2/R4/R5 / 0.2 m/s / 5 Hz | 확인 |
| Recursive state | \([x,y,\psi,b_g]^T\) | 대상 4-State 고정 |
| Bias | B0=0, L0=.01, L1=.05, L2=.20 °/s | 해당 gyro-only 조건 확인 |
| Nominal R | diag(0.0068578637 m², 0.0081) for [r,s] | 기존 joint baseline |
| Evaluation | t≥30 s; filter from t=0 | 확인 |
| Exact 4-State \(P_0,Q,F\), sensor seed | **[최종 동일계열 source lock 필요]** | 미확정 세부 잠금 |
| ≥3-anchor geometry, rate, R | **[추가 데이터 대기]** | 데이터 부재를 숨기지 않음 |

### 작성 시 유의사항

- Table I에는 “실측 장비 스펙”이라는 표현을 사용하지 않는다. 본 절은 **Sionna RT simulation setup**이다.
- Full RF와 LoS는 복제·재가공 결과의 동일성을 숫자로 확인했지만, 기존 LUT와 SourceFFD의 예측 \((h,H)\)이 서로 동일하다고 주장하지 않는다. 먼저 C0 원본 일치 → 이후 모델 차이 표시 순서로 출처를 제시한다.
- 회귀/held-out 결과의 수를 새로운 독립 장면 수로 합산하지 않는다. 이 문서에서 Confirmatory unseen independent scene 수는 **확인되지 않음**이다.
- 추천 도해: *Fig. 1* Corridor 구조(출처: 3D 도해는 layout만 참조), Anchor/Tag 편파축 및 R2/R4/R5 주행 오버레이. 이 Figure는 기존 그림을 결합해 **근거에 맞게 다시 작성**할 수 있지만 현재 새 그림을 만들지 않는다.

---

# 2. Dual-LP Heading Concept

## 2.1. 정적 LoS 편파 응답과 Heading 민감도

### 논문 원고 초안

거리만 사용하는 단일 앵커 UWB 관측은 수신 안테나와 앵커 사이의 위치 관련 제약을 제공하지만, 안테나가 로봇 회전 중심에 동위치하고 lever arm이 없는 경우 단일 시점의 거리 관측함수는 yaw에 직접 의존하지 않는다. 반면, 두 수신 선형 편파 포트가 관측한 첫 경로 전력비 \(s_{\mathrm{FP}}\)는 송신·수신 FFD의 방향성, 입사각과 상대 편파 방향에 의해 로봇 yaw의 함수가 된다. 본 연구는 편파 전력비를 독립적인 절대 heading 측정값으로 역변환하여 사용하는 대신, 상태 \(\mathbf x\)에서의 LoS 관측함수 \(h_s(\mathbf x;\mathbf a,\mathrm{mount})\)로 직접 모델링한다.

\[
\mathbf z=
\begin{bmatrix}r\\s\end{bmatrix},\qquad
\mathbf H =
\begin{bmatrix}
\partial h_r/\partial x & \partial h_r/\partial y & 0 & 0\\
\partial h_s/\partial x & \partial h_s/\partial y & \partial h_s/\partial \psi & 0
\end{bmatrix}.
\]

따라서 \(\partial h_s/\partial\psi\ne0\)인 물리적 작동점에서 Dual-LP는 단일 앵커에서도 **heading-sensitive observation**을 제공한다. 이 관측 민감도는 고정된 상수가 아니라 앵커 방위각, 안테나 고도각, 로봇 yaw, mount offset 및 FFD에 따라 변화한다.

## 2.2. 관측 정보량과 기하적 비구별성

### 논문 원고 초안

이를 실제 FFD 기반 LoS 채널에서 검토한 결과, R2–Anchor A의 동일 위치 집합에서 mount 0°와 45°의 \(|\partial h_s/\partial\psi|\) 중앙값은 각각 **0.51568** 및 **1.63864 rad⁻¹**이었다. 명목 사전 위치 분산을 고려한 기하 기반 heading 정보 지표 \(I_{\mathrm{geom}}\)의 중앙값도 각각 **32.13** 및 **318.48**로 달랐다. 동시에 ±8°–20° 사이 다른 yaw 후보가 명목 편파 잡음 범위 안에서 유사한 응답을 내는 비율은 해당 오프라인 비교에서 mount 0° **76.67%**, mount 45° **29.39%**이었다. 이러한 결과는 Dual-LP 관측이 heading에 직접 민감하더라도, 단일 시점의 응답이 전 yaw 영역에서 단사 함수가 아니며 위치 사전정보와 동역학을 결합하는 재귀 추정이 필요함을 보여준다.

정량 비교에서 사용한 \(I_{\mathrm{geom}}\)은 고정된 nominal 측정 분산과 위치 사전분산에 따른 **국소 기하 지표**이며, Full RF 다중경로 오차나 시간상관까지 반영한 실제 정보량 또는 최종 Bayesian posterior를 의미하지 않는다.

### 기존 데이터/소스 위치

- [N4-Q Q1: 실제 FFD heading Jacobian, mount별 정보량, 비구별률](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/N4_Q_GEOM_RF_20261015/EXECUTION_REPORT_KO.md)
- [N4-B POL-V1: 실제 FFD \(H_{s,\psi}\)·포트 균형 및 NLL 추가 검증](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/R5_N4B_POL_V1_20261015/RESULTS_KO.md)
- [SourceFFD: 복소채널·LoS 전력비·Jacobian 정합 검증](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/FFD_P0P3_20261016/RESULTS_KO.md)

### 작성 시 유의사항

- **\(\partial h_s/\partial\psi\ne0\) ⇒ 유일한 절대 방향을 복원할 수 있음**은 성립하지 않는다. 기하 정보·위치 prior·복수 heading 후보의 구분을 유지한다.
- R2–A mount 비교는 같은 복도에 한정되며 “45° 설치가 일반적으로 최선”이라고 쓰지 않는다. \(I_{\mathrm{geom}}\)은 posterior NEES/실효 독립 정보량이 아니다.
- SourceFFD는 LoS 관측함수 검증 자료이며 최종 다중경로 보정 알고리즘의 독립 실험 성공으로 쓰지 않는다.
- 추천 도해: *Fig. 2* FFD 기반 \(s(\psi)\) 및 \(\partial h_s/\partial\psi\)를 상대 방위·mount별로 비교하고, 유사한 \(s\)를 만드는 yaw 후보의 예를 표시. **기존 저장 결과로만 작성**하며 원시 데이터가 필요한 곡선을 임의 생성하지 않는다.

---


# 3. Characteristics of Dual-LP Measurements Under Multipath

> **현재 작성 범위:** 3-A/B/C/E는 기존 C0 원본의 측정·모델·재귀 진단에서 확인한 결과만 이용한다. **3-D는 가장 중요한 후속 연구로 별도 정교화 예정**이며, 현재 새로운 기전이나 알고리즘의 성공을 주장하지 않는다.

## 3-A. RF Measurement Error Formation and Decomposition

### 논문 원고 초안

Dual-LP 관측에서 발생하는 오차를 분석하기 위해, 동일 포즈에서 계산한 Full RF와 Native LoS RF의 측정값을 대응시켰다. GT 상태 \(\mathbf x_{\mathrm{GT}}\)에서 평가한 편파 관측모델 \(h_s\)에 대한 잔차는 아래와 같이 다중경로 기여와 LoS 모델 불일치로 분리된다.

\[
e_s^{\mathrm{Full}}=s_{\mathrm{Full}}-h_s(\mathbf x_{\mathrm{GT}})
=\underbrace{(s_{\mathrm{Full}}-s_{\mathrm{NativeLoS}})}_{e_{s,\mathrm{MP}}}
+\underbrace{(s_{\mathrm{NativeLoS}}-h_s(\mathbf x_{\mathrm{GT}}))}_{e_{s,\mathrm{model}}}.
\]

초기 2° angular LUT와 달리, 주파수별 원본 안테나 패턴과 실제 기하·관측 tap을 사용한 SourceFFD 모델은 C0의 9,519개 LoS 포즈에서 편파비 RMSE **\(6.592045\times10^{-7}\)**, 최대 절댓값 오차 **\(1.082114\times10^{-5}\)**, 첫 경로 tap 불일치 **0개**를 기록하였다. 따라서 해당 **고정 시뮬레이션**에서는 Full–LoS 편파 차이가 전체 편파 모델 잔차의 지배적 성분이다. 그러나 Range 측정에는 첫 경로 선택·이산 지연 검출·거리 bridge가 추가로 관련되므로, 모든 Range 오차를 순수 다중경로 오차로 해석할 수 없다.

반사 경로를 포함한 별도의 관측모델 연구에서는 정합된 장면에서 높은 예측 정확도가 나타나더라도 벽·바닥의 위치, 재질이 달라지면 예측이 악화하는 경우가 확인되었다. 이는 정확한 장면 정보를 이용한 물리적 재현성과 모델이 불완전한 환경에서의 견고한 상태추정을 구분해야 함을 의미한다.

### 기존 데이터/소스 위치

- [FFD_P0P3: 9,519 LoS 포즈의 SourceFFD·FP tap 대조](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/FFD_P0P3_20261016/RESULTS_KO.md)
- [N4-Q: 관측 혁신의 multipath/LUT/pose 성분 분해](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/N4_Q_GEOM_RF_20261015/EXECUTION_REPORT_KO.md)
- [반사 모델의 설계 및 V0–V3 처리](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/reflect_model/PROTOCOL_REFLECT.md)
- [V3 장면 교란·민감도 측정 원자료](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/reflect_model/results/run_40623954692/v3/V3_ROBUSTNESS.csv)

### 작성 시 유의사항

- SourceFFD 오차가 **거의 0**이라는 확인과 **엄밀히 0**이라는 주장은 다르다. 외부 하드웨어·안테나 오차는 검증 대상이 아니다.
- 오차 \(e_s^{\mathrm{Full}}\)는 사용한 LoS 관측함수에 따라 달라진다. 초기 LUT 기준 결과와 SourceFFD 기준 결과를 섞지 않는다.
- Fig. 3-A 제안: \(s_{\mathrm{Full}}\), \(s_{\mathrm{LoS}}\), \(h_s\) 및 FP tap 전환의 동일 pose 대응 관계. 복소 H 원본과 출력 key를 재확인하여 기존 자료로만 작성한다.

## 3-B. Conditional Bias and Signed Error Structure

### 논문 원고 초안

기존 EKF의 영평균 측정오차 가정을 점검하기 위해, 거리와 편파 관측오차를 부호를 보존한 상태에서 분석하였다. C0 데이터의 \(e_r,e_s\)는 거리·상대 방위·장착각 및 first-path 주변 특성에 따라 조건부 평균이 달라질 수 있다. 따라서 오차의 절댓값이나 분산만으로는 추정기에 누적되는 보정 방향을 충분히 표현할 수 없다.

첫 경로 tap 주변의 추가 편파 정보를 알아보기 위해 \(\Delta s_o=s(n_{\mathrm{FP}}+o)-s(n_{\mathrm{FP}})\)를 정의한 기존 7-case 연구에서, FP 다음 tap의 \(\Delta s_{+1}\) 부호와 Full–LoS 편파 왜곡의 부호가 일치한 비율은 **0.63–0.77**이었다. 부호를 이용한 회귀의 held-route pose 수준 설명력도 \(R^2=0.27\)–**0.46**으로 보고되어, 근접 CIR의 편파 변화가 오염의 signed component에 관한 정보를 지닐 가능성을 보였다.

그러나 오차를 예측할 수 있다는 사실과 예측값을 EKF 관측에서 제거하는 것이 유리하다는 사실은 다르다. \(\Delta s\) 기반 Range 보정 실험에서는 관측 Range 오차가 줄어들어도 Heading 추정이 악화하는 조건이 있었고, 선택된 여섯 조건의 보정강도 개입에서는 Range 평균 보정의 크기가 증가할수록 Heading signed-bias의 **절댓값**이 단조 증가하였다. 따라서 모델의 성공 기준은 단일 패킷의 오차 감소뿐 아니라 재귀 추정에 대한 실제 효용을 포함해야 한다.

### 기존 데이터/소스 위치

- [Signed \(\Delta s\) 및 tap offset별 부호 정보](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/PJ_STEP1_SIGNED_DS_20261021/01_RESULTS_KO.md)
- [Δs X1/X2 기존 비교 및 원시 산출물 범위](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/README.md)
- [E1–E4: 비선형 보정 강도·편파 잔여·Kalman Gain 개입](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/e1_e4/RESULTS_KO.md)

### 작성 시 유의사항

- \(\Delta s_{+4}\)는 해당 실험의 사전등록 1차 지표이며, \(\Delta s_{+1}\) 결과는 보조 분석이다. 둘의 숫자를 뒤섞지 않는다.
- 부호 일치율은 **편파 잔차의 부호**, \(R^2\)는 **오차 예측**에 관한 통계이며, Heading 각도 정확도나 새 장면 성능이 아니다.
- E1–E4에서 고정된 gate와 mean만 바뀌는 개입 및 자연 재귀를 구분한다. Fig. 3-B는 signed 잔차·예측 관계와 보정강도별 Heading bias를 분리하는 것이 바람직하다.

## 3-C. Heteroscedasticity and Joint Measurement Covariance

### 논문 원고 초안

거리와 편파 관측은 공통 RF 채널 및 first-path 검출 과정에서 생성된다. 기존의 고정 대각 공분산 모델과 달리 C0의 잔차는 기하·품질 조건에 따라 분산과 같은 시점의 cross-covariance가 달라질 수 있다. 조건부 공동 오차모델을

\[
\mathbf R(\mathbf q)=
\begin{bmatrix}
V_r(\mathbf q) & C_{rs}(\mathbf q)\\
C_{rs}(\mathbf q) & V_s(\mathbf q)
\end{bmatrix}
\]

로 표현할 수 있으며, \(V_r\)의 단위는 \(\mathrm{m^2}\), \(V_s\)는 무차원 제곱, \(C_{rs}\)는 \(\mathrm m\)이다. **고정된 기존 LUT**를 기준으로 수행한 N4-B 실험에서 R2–Anchor A의 Full RF \(e_r,e_s\) 상관계수는 mount 0°에서 **+0.525**, mount 45°에서 **+0.062**로 관찰됐다. 이는 앵커·경로가 같아도 설치각에 따라 관측오차의 공동 구조가 달라질 수 있음을 나타낸다.

기존 N4-B는 고정 \(R_0\)보다 조건부 평균·공분산 모형에서 패킷 공동 likelihood의 개선을 확인했지만, 비대각 \(C_{rs}\)의 추가가 항상 이득을 제공하지는 않았다. SourceFFD 계열의 별도 Range/s 오차모델 재귀 분석에서도 관측오차 RMS 또는 분포의 적합도가 개선되더라도 Heading RMSE와 posterior coverage가 악화하는 사례가 있었다. 따라서 본 절에서 평가해야 할 대상은 **관측 수준에서의 분산·상관 구조**이며, 후속 EKF 상태성능은 별도의 측정값으로 보고한다.

#### 기존 LUT 기준 N4-B 통계 — 최종 SourceFFD 표로 자동 대체 금지

| Full RF / R2 case | \(\mu_r\) (m) | \(\mu_s\) | \(V_r\) (m²) | \(V_s\) | \(C_{rs}\) (m) | \(\rho_{rs}\) |
|---|---:|---:|---:|---:|---:|---:|
| Anchor A / Mount 0° | +0.05225 | +0.04850 | 0.01708 | 0.03935 | +0.01361 | +0.525 |
| Anchor A / Mount 45° | +0.07187 | +0.00692 | 0.01658 | 0.05234 | +0.00182 | +0.062 |
| Anchor B / Mount 0° | +0.03069 | +0.02274 | 0.00807 | 0.01098 | +0.00090 | +0.096 |

### 기존 데이터/소스 위치

- [N4-B 원시 관측잔차 평균·분산·공분산 및 NLL](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/R5_N4B_REPORT_20261015/RESULTS_KO.md)
- [Physics G0–G5: 관측 품질 특징량과 오차 예측](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/PHYSICS_RS_STAGED_20261015/RESULTS_KO.md)
- [PJ_SEPARATE_RS: SourceFFD 계열 conditional mean/cov 및 EKF 재귀](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/PJ_SEPARATE_RS_20261020/01_EXECUTED_RESULTS_KO.md)
- [MBVAR_PREMODEL: 분산 재적합·cross-route 안정성](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/README_KO.md)

### 작성 시 유의사항

- \(\mathbb E[e^2|\mathbf q]\)는 centered \(\operatorname{Var}(e|\mathbf q)\)와 다르다. Conditional mean을 빼지 않은 error magnitude predictor를 분산 추정기로 부르지 않는다.
- RF 잔차의 NLL/95% 포함률은 EKF Heading/Pose 95% coverage와 다른 객체이다. 같은 시점 \(r,s\) 상관과 시간 간 상관을 구분한다.
- N4-B의 구 LUT 통계와 후속 SourceFFD 통계를 병합하지 않는다. Fig. 3-C에 사용할 SourceFFD 최종 숫자는 같은 C0 원본에서 해당 관측함수로 확인된 경우에만 채운다.
- G3/G5의 주파수·복소 Jones 지표가 기존 상용 UWB 모듈에서 취득 가능한지는 검증되지 않았다.

## 3-D. Spatiotemporal Correlation and Information Redundancy

**[RESERVED — 가장 중요한 항목. 기존 자료 존재, 최종 가설·인과 구분·논문 원고는 별도 설계 후 추가]**

이 분야에는 C0의 시간상관, 공간적 잔차 배치, 정보 과대계산 및 재귀적 분산 신뢰성에 관한 기존 자료가 존재한다. 그러나 lag-1 자기상관만으로 독립적인 temporal sensor drift를 확정하거나, 관측 순서 교란의 결과를 실제 RF correlation-only 인과개입으로 해석할 수는 없다. 이 절의 새 결과·정식 주장은 **현재 작성하지 않는다**.

현재 연결된 별도 제안 기록: [MBVAR controlled-information 기존 계획](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/MBVAR_CONTROLLED_INFO_20261029/PLAN_P0_P6.md). 문서의 존재는 실험이 완료됐다는 뜻이 아니다.

## 3-E. State-Dependent Measurement Utility and Recursive Error Propagation

### 논문 원고 초안

동일 RF 오차라도 EKF가 유지하는 prior-state의 오차, covariance와 Heading Jacobian에 따라 최종 추정에 미치는 영향이 달라진다. 실제 혁신 \(\boldsymbol\nu_k\)는 다음과 같이 RF 측정오차뿐 아니라 prior-state 오차의 관측공간 기여를 포함한다.

\[
\boldsymbol\nu_k=\mathbf z_k-\mathbf h(\hat{\mathbf x}_k^-)
=\underbrace{[\mathbf z_k-\mathbf h(\mathbf x_k^{\rm GT})]}_{\mathbf e_k^{\rm RF}}
+\underbrace{[\mathbf h(\mathbf x_k^{\rm GT})-\mathbf h(\hat{\mathbf x}_k^-)]}_{\Delta\mathbf h_k^{\rm prior}}.
\]

4-State \([x,y,\psi,b_g]^T\)에서 RF 편파비와 Range는 gyro bias를 직접 측정하지 않지만, 운동모델의 \(F_{\psi,b_g}\)와 사전 공분산의 pose–bias 비대각항 때문에 RF innovation이 Kalman Gain을 통해 \(b_g\)를 갱신한다. 기존 B0(실제 gyro bias=0) Full RF 실험에서는 오염된 관측이 가짜 gyro-bias 추정 및 Heading 오차를 유발하는 현상이 기록되어 있다.

또한 Heading 민감도 \(g=\partial h_s/\partial\psi\)가 작은 조건에서는 편파 평균모델의 작은 signed 변화도 대략 \(|\Delta\mu_s/g|\) 크기의 heading 이동으로 확대될 수 있다. 기존 strata 분석은 보정이 실제 heading 상태에 유리한지 판단할 때 민감도뿐 아니라 **기준 필터가 이미 갖는 heading 오차·사전 불확실도**가 중요함을 시사한다. 이는 사후에 확인된 관계로서 온라인 사용 규칙이 검증된 것은 아니다.

관측오차 예측과 전체 재귀 정확도의 차이는 SourceFFD로 재검산된 동일 C0 실험에서 직접 드러났다. R2–A, Full RF, mount 0°, B0 조건에서 G4와 POWER의 같은 패킷 오차모델 공동 NLL은 각각 **−1.696062**, **−1.681675**로 G4가 작았지만, 자연 재귀 Heading RMSE는 각각 **3.131978°**, **1.798910°**로 G4가 더 컸다. 이는 개별 관측의 좋은 likelihood가 이후의 상태·Kalman Gain·Gate 변화까지 고려한 end-to-end 추정 성능을 보장하지 않음을 보여준다.

### 기존 데이터/소스 위치

- [4-State Full/LoS·gyro bias 재귀·동일 prior 결과](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/EKF4_RANGE_S_STAGED_20261014/R2_MOUNT0_45_GYRO_BIAS_B0_L0_L1_L2_RESULTS_20261015_KO.md)
- [SourceFFD P2/P3: 공동 NLL과 재귀 RMSE 역전](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/FFD_P0P3_20261016/RESULTS_KO.md)
- [PJ_SENS_STRATA: 기하 민감도와 평균 보정의 heading 이동](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/PJ_SENS_STRATA_20261021/01_RESULTS_KO.md)
- [N4-A: Pose NEES·Heading/conditional XY Schur 분해](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/R5_N4A_NEES_20261015/RESULTS_KO.md)
- [MBVAR: RF와 prior 오차 분해 및 gate 진단](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/README_KO.md)

### 작성 시 유의사항

- B0의 spurious bias는 관찰된 한 가지 기전이며 모든 Heading·XY 오류를 오직 gyro-bias 추정 하나로 설명하는 것은 아니다.
- Pose NEES의 작은 conditional XY 고유축 집중은 **과신의 위치와 규모**를 알려주지만, 특정 tap이나 gate만이 그 유일 원인임을 증명하지 않는다.
- 위 NLL/Heading 비교는 **같은 SourceFFD 버전**의 값이며 과거 LUT 모델의 공동 NLL 숫자와 합치지 않는다.
- Fig. 3-E 후보는 동일 prior vs 자유 재귀 궤적, \(g\)별 heading 환산 영향, 조건부 XY 예측 분산 대비 오차이며 원본 trace의 시행 단위를 명시해야 한다.

---

# 4. Characteristic-Aware EKF — 최종 통합 모델 미선정

### 논문 원고 초안: 검증된 공통 구조만

본 연구의 추정기는 4-State 운동모델의 예측 단계와 단일 앵커의 \(r,s\) 관측을 결합한다. 고정된 운동 예측은 \(\hat{\mathbf x}_k^-=f(\hat{\mathbf x}_{k-1}^+,\mathbf u_k)\), \(\mathbf P_k^-=\mathbf F_k\mathbf P_{k-1}^+\mathbf F_k^T+\mathbf Q_k\)로 구성된다. Conventional EKF는 \(\boldsymbol\mu=0\)와 고정 \(\mathbf R_0\)를 사용한다. 기초적인 characteristic-aware 갱신을 표현하는 공통 수식은 다음과 같다.

\[
\boldsymbol\nu_k=\mathbf z_k-\mathbf h(\hat{\mathbf x}_k^-)-\hat{\boldsymbol\mu}_k,\quad
\mathbf S_k=\mathbf H_k\mathbf P_k^-\mathbf H_k^T+\hat{\mathbf R}_k,\quad
\mathbf K_k=\mathbf P_k^-\mathbf H_k^T\mathbf S_k^{-1}.
\]

기존 실험에서 mean/covariance 및 기하 의존 가중과 gate가 성능에 미치는 영향을 확인했지만, 이 중 어느 조합을 **최종 M2**로 채택할지는 Section 3-D의 정보량 연구와 독립적 검증을 거쳐 결정해야 한다. 특히 상태 의존 보정 \(\hat{\boldsymbol\mu}(\mathbf x)\)를 관측함수에 포함한다면 그 미분 \(d\hat{\boldsymbol\mu}/d\mathbf x\)을 \(H_{\rm eff}\)에 포함할지, 아니면 사전에 동결한 donor prior의 보정량으로 다룰지를 구분해야 한다. 이 둘은 다른 추정기이다.

### 기존 후보 연구/소스

- [POWER: mean·covariance·Gate 연구용 재귀 baseline](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/POWERJOINT_P0P2P3_20261016/RESULTS_KO.md)
- [PJ_SEPARATE_RS: 별도 Range/s 통계 모델과 공동 \(C_{rs}\)](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/PJ_SEPARATE_RS_20261020/01_EXECUTED_RESULTS_KO.md)
- [MB_VAR: 모델 오류·Jacobian·초기상태·정보행렬 교정](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_e2_e5_revalidation_20261029/README_KO.md)
- [현 단계에서 동결 불가한 항목](https://github.com/myoungsunk/sionna-resimulation/blob/research/dual-lp-paper-gap-proposal-20261030/research/DUAL_LP_PAPER_GAP_20261030/FREEZE_READINESS_KO.md)

### 작성 시 유의사항

- **[M2 최종 구조·파라미터·수치 결과: 미확정]**. POWER/MB_VAR 등을 검증된 최종 알고리즘으로 쓰지 않는다.
- 이분산 모델, mean, \(C_{rs}\), gate 및 확장 상태를 동시에 변경하면 원인 분석이 어려우므로 최종 ablation을 분리한다.
- 위 식은 **같은 시점 관측 갱신의 골격**이다. 시간 간 오차상관을 이용하는 완전한 stacked likelihood의 구현·동치성은 Section 3-D 이후에 결정한다.
- 사용한 \(f,F,Q,\mathbf P_0\)와 Joseph covariance·missing-packet 처리·source SHA·Gate는 실제 최종 구현과 일치하도록 확인한 뒤 본문 수식·표에 반영한다.

---

# 5. Performance Comparison — 검증된 기존 수치만 기입

## 5.1 비교 시스템 정의

### 논문 원고 초안

성능 비교는 RF를 사용하지 않는 4-State Dead Reckoning(M0), 단일 앵커 Range-only Conventional EKF(M1-A), 단일 앵커 Range+Dual-LP Conventional EKF(M1-B), 세 개 이상 앵커의 Range-only Conventional EKF(M1-C), 그리고 단일 앵커 \(r,s\)를 이용하는 최종 특성 반영 EKF(M2)로 구성한다. 상태변수·IMU/wheel 제어 입력·주행·초기조건·평가구간은 일치시키며, 관측 모달리티와 앵커 수의 차이는 명확히 보고한다.

| 방법 | C0 동일 4-State full-recursive 자료 | 처리 |
|---|---|---|
| **M0 DR4** | 확인 | 기존 점수 사용 가능 |
| **M1-A 1A Range-only EKF** | **동일 설정의 4-State 전체 재귀 자료 아직 미확인** | 추가 출처 검색, 없을 때만 기존 C0 replay |
| **M1-B 1A r+s Conventional EKF** | 확인 | J4/SR4의 old LUT와 SourceFFD 버전 구분 |
| **M1-C ≥3A Range-only EKF** | **동일 C0 3개 이상 앵커 RF 미확인** | 동일 scene·동일 궤적 데이터가 입고된 뒤 작성 |
| **M2 1A Characteristic-Aware EKF** | **최종 방법 미선정** | Section 3-D 및 독립 검증 완료 후 작성 |

## 5.2 기존 R2–Anchor A 비교 결과

### 논문 원고 초안

과거 4-State 및 **기존 LUT 관측함수**를 사용한 R2–Anchor A 실험에서 Full RF에 대한 Conventional Joint4의 Heading RMSE는 설치각과 gyro drift에 민감하였다. 실제 gyro bias가 0인 B0 조건에서 DR4의 Heading RMSE는 약 **0.484°**였으나 Joint4는 mount 0°에서 **7.490°**, mount 45°에서 **0.845°**였다. +0.20°/s의 bias가 존재하는 L2에서는 DR4가 약 **24.97°**까지 악화했고, Full RF Joint4는 mount 0° **7.521°**, mount 45° **0.848°**를 기록하였다. 따라서 RF 융합에 의한 결과는 단일 수치의 개선률로 환원할 수 없으며, 기하와 motion-sensor bias 수준에 따라 보고해야 한다.

#### 역사적 old LUT / R2-A 4-State Heading RMSE (deg)

| 조건 | DR4 | Full J4 / mount0 | Full J4 / mount45 |
|---|---:|---:|---:|
| B0 (true bias 0) | 0.484 | 7.490 | 0.845 |
| L2 (+0.20°/s) | 24.97 | 7.521 | 0.848 |

후속 SourceFFD 및 재학습 POWER 실험에서는 B0 Full R2-A의 POWER Heading RMSE가 mount0에서 **old 1.773241° → source 1.798910°**, mount45에서 **old 0.815147° → source 0.982634°**로 바뀌었다. 즉 물리적으로 더 정합한 관측모델을 사용하는 것이 재귀 추정값을 반드시 개선하지는 않으며, 최종 비교표는 모든 모델을 같은 관측함수·센서·시드·평가구간에서 재채점한 자료로 작성해야 한다.

### 기존 데이터/소스 위치

- [R2 Dual-LP 3/4-State, B0–L2, S-only·Joint·순차 재귀 성능](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/EKF4_RANGE_S_STAGED_20261014/R2_MOUNT0_45_GYRO_BIAS_B0_L0_L1_L2_RESULTS_20261015_KO.md)
- [SourceFFD P2/P3 원모델 대비 재귀 정합 결과](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/FFD_P0P3_20261016/RESULTS_KO.md)
- [Range-only 3-State One-step — 4-State 전체재귀 대체 아님](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/EKF3_INDEPENDENT_20261013/P2_ONE_STEP_REPORT_KO.md)
- [다중 Anchor WLS·2D known-Z EKF 코드 — 별도 연구계열](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/rt_cp_uwb_py/localization.py)

### 작성 시 유의사항

- old LUT J4 표와 SourceFFD POWER 표는 **서로 다른 역사적 비교**다. 아직 같은 모델·자료에 대한 완성 M0–M2 횡단 표로 합치지 않는다.
- 기존 EKF3의 3은 **state 수**이지 3개 앵커가 아니다. 세 개 이상 앵커를 처리하는 WLS 코드가 있더라도 C0에서 동시 수신한 3앵커 RF와 4-State EKF 성능이 존재한다는 증거가 아니다.
- M1-C는 센서·패킷 자원을 더 사용하는 비교군이다. 동일 데이터 계열이더라도 앵커 수의 차이를 없애는 공정 비교라고 주장하지 않고, 추가 자원·동시 관측 조건을 명시한다.
- 주 지표는 Heading RMSE/P95, XY RMSE, gyro-bias RMSE, Heading/Pose NEES·95% coverage, Gate acceptance, LoS 비악화 및 업데이트 자원이다.
- **[표/그림의 M1-A, M1-C, M2 값은 추가 데이터 입고 시에만 채움]**. Fig. 5 완성본을 기존 숫자만으로 꾸미지 않는다.

---

# 6. Limitations — 검증된 한계와 미확인 범위를 분리

### 논문 원고 초안

본 연구의 첫 번째 한계는 C0 RF 데이터가 하나의 Corridor 장면에서 생성되었다는 점이다. 앵커·mount·경로·센서 seed의 변화는 결과의 조건부 민감도 분석에 유용하지만 독립된 다중경로 장면을 반복 관측한 것은 아니다. 따라서 현 결과만으로 다른 건물 및 실제 하드웨어 환경에서의 일반화를 주장할 수 없다.

둘째, Full RF에서 학습한 보정기가 정상적인 Native LoS에 손상을 줄 수 있다. SourceFFD/B0 결과에서 SourceR0 대비 sourcePOWER의 LoS Heading RMSE는 mount0 **0.502160° → 2.108206°**, mount45 **0.153262° → 1.356951°**로 증가했다. 그러므로 Full 성능의 개선과 함께 LoS 비악화에 대한 독립적인 평가가 필요하다.

셋째, 관측오차 분포의 likelihood 또는 점추정 RMSE가 개선되어도 posterior covariance의 calibration이 개선된다고 보장할 수 없다. 기존 N4-A에서는 Heading과 XY 점추정 오차가 감소한 특정 모델에서도 조건부 XY 공분산의 작은 고유축을 중심으로 매우 큰 Pose NEES가 관찰됐다. 이는 정확도와 추정 불확실성의 타당성을 별개의 지표로 평가해야 함을 보여준다.

넷째, 초기 상태 오차와 model version에 따른 민감도가 존재한다. MB_VAR의 R5–Anchor B 초기상태/센서 시드 교차 실험에서는 시험 범위에서 큰 Heading 오차가 제어 노이즈보다 초기상태 시드 변화와 더 강하게 연결되었다. 그러나 해당 초기화에는 위치와 yaw 오차가 함께 달라지므로 yaw 단일 원인으로 확정할 수 없다.

다섯째, 안테나 bank와 원시 RF 채널은 시뮬레이션 자산이다. 상용 하드웨어에서 복소 주파수 채널·Jones 특징·모든 CIR tap을 실제로 읽을 수 있는지 검증되지 않았다. 또한 본문에서 비교하려는 ≥3-anchor Conventional EKF의 **동일 C0 자료**는 아직 확인되지 않았으며, 이는 지금 단계의 실험 공백으로 명시해야 한다.

### 기존 데이터/소스 위치

- [POWER 연구의 기존 scientific claim boundaries](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/POWERJOINT_FINAL_20261016/05_PAPER_STORY_KO.md)
- [SourceFFD LoS 악화·pole/crossing 분석](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/FFD_P0P3_20261016/RESULTS_KO.md)
- [N4-A: Pose NEES와 conditional XY 축 분해](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/R5_N4A_NEES_20261015/RESULTS_KO.md)
- [R5-B 초기 상태 seed와 정보행렬 재검증](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_e2_e5_revalidation_20261029/README_KO.md)
- [실제 하드웨어 feature 접근 가능성의 경계](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/HEADING_RELIABILITY_20261010/00_PREREG_CIR_AND_RF_HEADING_KO.md)

### 작성 시 유의사항

- 확인된 **실패**, 추가 자료가 없어 **미검증**, 독립 환경에 **일반화 불가**라는 상태를 명확히 구분한다.
- [Office→Corridor 과거 전이 결과](https://github.com/myoungsunk/sionna-resimulation/blob/research/office-corridor-mount0-45-run-20261027/research/OFFICE_CORRIDOR_POWER_PWIDE_TRANSFER_20261026/run_mount0_45_20261027/README_KO.md)는 C0의 동일 원본 비교가 아니다. 필요하면 별도 *retrospective external-scene stress* 절에서 인용한다.
- Section 3-D가 끝나지 않은 상태에서 **시간상관이 모든 EKF 과신의 유일 원인** 또는 **특정 보정기가 전체 문제를 해결했다**는 주장으로 발전시키지 않는다.

---

# 신규 데이터 입고 시 갱신 규칙

**이 Markdown 파일 하나에만 원고 문장·수치·링크·작성 유의를 누적한다.** 이전 수치를 덮어 쓸 경우 반드시 관측모델/원본 버전·차이 사유를 함께 보존한다.

1. 원본이 **SAME_C0_RAW**, **SAME_C0_RECOMPUTED**, **C0_EXTENSION_NEW_RF**, **EXTERNAL_DATA**, **ORACLE_ONLY**, **MISSING/UNVERIFIED** 중 어디에 속하는지 기록한다.
2. 해당 데이터의 Git commit, 원본·산출물 SHA256, case/route/anchor/mount/pose_id/timestamp, channel, source h, f/F/Q, R/Gate, seed, 평가 단위 및 invalid packet을 명시한다.
3. 같은 원본 RF라도 **old LUT ↔ SourceFFD**, **3/4/6-State**, **one-step ↔ 자유 재귀**, **고정 gate ↔ self-gate**를 동등하다고 하지 않는다.
4. 독립 감사 결과와 구현자의 기술 PASS를 분리한다. 결과 개선 없이도 정확히 검증된 실패는 논문에 포함 가능하나, 보편적인 성공으로 승격하지 않는다.
5. 새 원고 문단을 추가할 때는 같은 절의 **데이터/소스 위치**와 **작성 시 유의사항**, 관련 Table/Figure 후보도 동시에 갱신한다.

## 아직 비어 있어야 하는 항목

| 섹션 | 미확인 항목 | 입고 후 조치 |
|---|---|---|
| §1.5–1.6 | 최종 4-State \(F,Q,P_0\), 전체 seed/관측기 정책의 단일 기준 | Source lock·Table I 보완 |
| §3-D | 시간·공간 상관과 상태별 유효 정보량의 물리/수학적 검증 | 별도 계약·감사 후 원고 작성 |
| §3-A/B/C/E 및 §5 | old LUT와 SourceFFD가 섞인 역사적 비교의 완전 같은 기준 재집계 | 같은 C0 원본으로 필요한 통계만 정합 |
| §4 | 최종 M2 방법의 구현·신뢰성 평가 | 3-D 결과 및 최종 모델 확정 후 작성 |
| §5 | 단일 앵커 Range-only 4-State full-recursive | 기존 증거 검색 후 필요 시 같은 C0 replay |
| §5 | ≥3-anchor 같은 Corridor·pose의 Range RF와 4-State EKF | 동기화 RF·공정한 앵커 자원 비교 확보 후 작성 |
| §6 | 독립 장면 및 실제 측정의 적용성 | 새로운 source 계열을 분리해 추가 |

**문서 상단의 6단계 논문 구조 및 3-D 우선순위를 유지하며, 미입고 수치를 임의로 작성하지 않는다.**
