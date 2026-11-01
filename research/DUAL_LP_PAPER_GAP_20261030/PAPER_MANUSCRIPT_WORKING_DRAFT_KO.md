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
