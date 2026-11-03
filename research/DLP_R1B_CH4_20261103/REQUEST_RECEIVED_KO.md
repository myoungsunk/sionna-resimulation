# DLP-R1B-CH4-001 — R1 직선 왕복 경로·Anchor B 관측오차 및 4상태 EKF 독립 검증 요청서

**작성일:** 2026-11-03  
**대상:** `myoungsunk/sionna-resimulation`  
**요청 역할:** IMPLEMENTER (생성·검산) → INDEPENDENT AUDITOR (독립 승인)  
**기준 참조 SHA:** `9e9133ecb46f96d88ee14652d42f43525fdd1b29` (과거 원고·기본 자료 조회 기준일 뿐, 새 실행 SHA는 별도 동결)  
**우선순위:** Chapter IV를 위한 **보정 전 관측오차 + LoS/Full 동일 4상태 EKF 비교**. 제V·VI장 모델 비교는 별도 하위 단계로 구분.

## 0. 요청 목적 및 필수 연구 질문

R1 직선 왕복 주행의 기존 참 궤적을 보존하고 **Anchor B `(10,0,2.65) m`**, **태그 높이 `0.45 m`**, **mount `0°`** 조건에서 Full/LoS 관측을 일대일 생성·검증한다. 그 결과를 동일한 4상태 SourceFFD EKF에 적용해 다음 질문에 실제 데이터로 답한다.

1. **IV-A — 발생:** 직접경로와 반사 경로의 포트별 중첩·검출 tap 변화가 거리 `r` 및 signed 정규화 전력차 `s=(P_+-P_-)/(P_++P_-)`를 어떻게 변화시키는가? 
2. **IV-B — 보정 전 오차:** `e^0=z_FULL-h(x_GT)`와 `Δz=z_FULL-z_LOS`, `e_LOS=z_LOS-h(x_GT)`가 어떻게 구성되는가? 거리·위치·방위각·왕복 구간별 오차의 평균, RMS, 중심화 표준편차를 산출한다. **기존 보정 평균을 빼기 전**의 값을 Chapter IV 주 분석으로 사용한다.
3. **IV-C — 상태 전달:** 사전 상태오차의 관측공간 투영 `δh=h(x_GT)-h(x^-)`과 관측오차 `e^0`가 `ν^0=e^0+δh`를 형성하고, 상태 갱신 `Kν^0`에 어떻게 기여하는가? 실제 packet 단위 분해와 집계가 대수적으로 일치하는가?
4. **IV-C 최종 결과:** 동일 조건의 일반 **4상태** EKF에서 `LoS-only → Full`로 바꾸면 Heading 및 XY RMSE는 어떻게 변하는가? 악화·개선 결과를 모두 보고한다. **악화가 반드시 발생한다고 가정하지 않는다.**
5. **제V장 연계(별도 승인 가능):** 동일 관측에서 기존 평균 `μ^B`와 EXDS 평균 `μ^M`을 적용할 수 있는지, 적용 시 잔차 `e^0−μ`의 변화가 어떤가? 평균 보정이 일부 구간에서 오차를 증가시키는 경우도 기록한다. **보정 모델의 예측값·적용 가능성이 검증되지 않으면 별도 결과로 표시하고 Chapter IV 완료 판정과 혼합하지 않는다.**

## 1. 동결할 비교 계약

| 항목 | 계약 |
|---|---|
| 장면 | 기존 C0 corridor 장면·재질·안테나 bank·좌표계. 각 입력 SHA 기록. 장면을 새로 만들었으면 C0 파생 장면으로 명시 |
| 앵커 | **B `(10,0,2.65) m`만**. 과거 Anchor A `(4,0,2.65) m` RF·보정값을 B인 것처럼 변경 사용 금지 |
| R1 궤적 | 우선 `results/DRIVE_SIM_20261007/S1/timeline_y0.35_Tnone.csv`를 **바이트 해시 동결**하고 시점 순서 그대로 사용. 원본 917 시점(5 Hz, 0–183.2 s), `drive_out/turn/drive_back` 포함. R1은 완전한 기하학적 직선이 아니라 4°의 scripted 방향 흔들림과 끝단 180° 회전을 포함한다. 별도 R1 y0 후보는 선택적 민감도 분석으로만 사용 |
| y0 선택 이유 | y0=0.35 m는 앵커 수직축을 지나는 y0=0 중심 경로보다 축상 퇴화 위험이 작다. **Anchor B 기준 실제 최소 수평거리는 코드로 재계산**하고 기록 |
| 태그·장착 | 수신 ±45° 두 포트, TX +45° 한 포트, 태그 z=0.45 m, mount=0°, lever arm=0; world/body/antenna yaw의 부호·단위 검증 |
| RF 관측 | 동일 pose에서 **Full**과 **Native LoS-only** 각각 생성. 동일 주파수 그리드·창·IFFT·관측기. 원래 detector의 strongest-port 30% leading-edge, 양 포트 공통 tap으로 `r`·`s` 산출. Full과 LoS는 **각각 tap 검출**. 예전에 저장한 6상태용 LUT 결과를 Native LoS 대체물로 선언하지 않음 |
| 관측모델 | **현재 논문과 동일한 4상태 SourceFFD** `h=[h_r,h_s]^T`, Jacobian `H=∂h/∂x`. 범위 예측은 기존 continuous detector offset bridge를 보존. 실제 first-edge 거리 확률분포를 새로 학습한 것으로 표현 금지 |
| 상태·입력 | `x=[x,y,ψ,b_g]^T`, 기존 4상태 `f,F,Q`, 동일 `x0,P0`, 동일 gyro·wheel 제어열 및 seed를 LoS·Full에 재사용. 옛 R1의 **6상태** `[x,y,ψ,b_g,SF_g,ε_d]` 필터 출력 사용 금지 |
| 일반 EKF 기준 | 두 주행의 오차 평균 `μ=0`, 추가분산 0, 동일 고정 `R0`과 동일 4상태 알고리즘. R2/R4/R5의 동결 conventional 비교에서 사용된 `R0=diag(0.0068578637 m²,0.0081)`과 검출 거리 오프셋 `−0.5315983906250129 m`의 R1 적용 가능성을 **먼저 source·단위·기준 계약으로 확인**. 적용 불일치 시 임의 대체하지 말고 `P0_HOLD` |
| 갱신 규칙 | 유한 두 성분에 대해 각 arm의 **공동 NIS χ²₂(0.99)=9.210340371976184** self gate. Joseph covariance, yaw wrap. LoS/Full 자체 gate가 달라도 고정 threshold와 계산법을 바꾸지 않음 |
| 평가 | 전 기간 결과 보존, 주 평가 `t≥30 s` 모든 시점에서 Heading wrapped RMSE(°), XY RMSE(cm). **관측이 거절된 시점도 점수에 포함**. phase별 및 거리별 수치는 별도 보조 결과 |
| 불변 조건 | 사실 검증·원시 RF 생성·필터·후처리 사이의 실행 SHA, 패키지 버전, 설정·코드·입력 해시 추적. 시험 도중 재튜닝 금지 |

**중요한 선행 사실:** 기존 R1의 `Snowball` 실행은 6상태 필터·기존 LUT 및 Anchor A를 사용했으며, 당시 Sionna/LUT 관련 게이트 중 L1·L2 FAIL이 기록되어 있다. 그러므로 R1의 기존 실험은 **궤적과 기존 현상 진단의 원천**이지, 새 Anchor B·4상태 SourceFFD 평가에 대한 과학적 승인 근거가 아니다.

## 2. 사전 점검 및 중단 조건 — P0 (RF 계산 전에 수행)

1. **입력 계보 잠금:** 참 궤적 CSV의 실제 `sha256`, `n`, `t_s`, phase, 각 pose `(x,y,ψ)`를 확인하고 `pose_id` 정합표를 생성. 기존 manifest와 비교. 선택 `y0.35/Tnone`가 달라지면 중단하여 차이 보고.
2. **RF 데이터 가용성:** 동일 R1·Anchor B에 대해 필요한 `H_FULL/H_LOS` 및 path metadata가 이미 있는지 파일별로 조회. 있으면 원본 hash·채널 shape·pose hash·TX/RX 순서·생성기 SHA 확인. **B RF가 없으면 기존 Anchor A H를 재해석하지 않고 신규 RF 생성 계약**으로 진행.
3. **SourceFFD 실행 복원:** 동결된 4상태 코드와 안테나 bank/FFT·FP 검출 소스를 식별. Anchor B에 대한 SourceFFD 입력 위치·편파축 변환, `h_r` 오프셋, `H` 수치미분, 전 시점 pre-gate 기록 가능 여부 확인.
4. **실행기 사전 동결:** LoS/Full RF에서 사용하는 동일 4상태 알고리즘, `Q/R0/x0/P0`, gyro/wheel 입력 생성법(참값은 진단 및 synthetic sensor 생성기에 한정), NIS, 측정 단위, 결측/거절 규칙을 JSON 계약에 기록한다.
5. **환경/비용 점검:** 원본 요구 버전 `sionna-rt 2.0.1`, `mitsuba 3.8.0`, `drjit 1.3.1` 및 LLVM 사용 가능 여부를 점검하고 소수 pose에 대한 CPU/메모리·수행 가능성을 확인한다. 생산 실행 비용과 작업 방식은 **P0에서 실제 측정값으로 보고**한다.

**즉시 HOLD 조건:** (i) 동일 pose·TX/RX·검출 규칙이 증명되지 않음, (ii) 4상태 SourceFFD가 복원되지 않음, (iii) Anchor B geometry/bank 대응 불일치, (iv) NaN/누락을 임의 0이나 다른 pose로 대체해야 함, (v) 장면과 4상태 비교 계약을 맞추지 않고 결과를 섞을 위험, (vi) Sionna 구현 동등성 canary 불합격. HOLD 시 본 실행을 하지 않고 원인·필요 데이터·수정 제안을 보고할 것.

**기존 L1/L2 FAIL 처리:** 기존 R1 자료에서 발생한 검증 실패를 무시하지 않는다. 새 실행에 적용한 SourceFFD와 Native LoS/Full이 그 오류에서 자유로운지 별도 canary로 확인해야 한다. 통과하지 못하면 `RF_UNVERIFIED`, 따라서 `SCIENTIFIC_HOLD`로 판정한다.

## 3. 신규 RF 생산과 물리 관측 검증 — P1

### 3.1. 두 채널의 생성

- 모든 R1 pose에 대해 `Full(max_depth=기준설정, 저장 시 정확한 값 기록)`과 `LoS-only(max_depth=0)` 복소 응답을 생성한다. Full 구성에서 직접경로가 실제로 존재하는지 표시하며, 동일 scene·antenna·pose에 대해 다른 설정은 변경하지 않는다.
- 최소 보존: 주파수 축 `freq_hz`, `H_full`, `H_los`의 복소 채널 텐서(안테나 포트 축 정의 포함), 시점·pose 목록, 경로별 지연·복소 기여·반사/편파 변환이 지원되는 경우 해당 metadata, detector 입력 CIR·두 포트 선택 tap·거리·`P±`·signed `s`, 직접파 존재/검출 flags.
- path별 데이터가 필요한 물리 설명과 단순 총 H 재생을 구분한다. path별 정보 불가 시 ‘ray 원인 독립 분해’는 미검증으로 표시하고, 총 채널과 동일 tap 간섭항의 대수적 관계는 별도로 검증한다.
- 저장 파일이 너무 크면 입력·SHA·detector 출력·선택 예시를 GitHub에 보존하고 원본 H는 체크섬과 다운로드 가능한 영속 저장소로 별도 전달한다. `H` 존재 없이 전체 검증 완료 선언 금지.

### 3.2. RF canary 및 동일성 검사

- 앵커 수직축에서 충분히 떨어진 pose, 축에 가장 가까운 pose, outbound/inbound 및 180° turn 각 1개 이상을 포함한 **최소 8개 canary pose**를 사전 지정한다.
- 동일 pose에서 `H_LOS`와 `SourceFFD` 직접경로 모델의 정규화 전력차 및 detector branch·tap을 비교하고 complex H의 축/주파수 위상 정합을 점검. 허용오차는 R2/R4/R5 기존 SourceFFD 재현 계약을 **먼저 조회하여 그대로 사용**하며, 미확인 시 숫자를 만들어 통과시키지 않고 `P0_HOLD`로 돌린다.
- `P±≥0`, `−1≤s≤1`, 공통 tap, 주파수 길이 및 단위, LOS/Full pose 완전 일치, 원래 총 H 재구성 합계 및 FP 선택 parity 확인.
- 기존 257-bin/R1 LUT 체인을 그대로 쓸지 새 SourceFFD detector를 쓸지 하나로 확정. 서로 다른 FFT, tap 규칙, 관측함수 출력을 섞은 hybrid 금지. 이전 `R1 LUT` 검증 통과만으로 SourceFFD parity를 대체하지 않음.

## 4. Chapter IV-B용 **보정 전** 관측오차 특성 — P2

### 4.1. packet별 정의 및 저장 (GT는 오프라인 분석 전용)

\[
\begin{aligned}
\mathbf e_k^{0}&=\mathbf z_k^{Full}-\mathbf h(\mathbf x_k^{GT}),\\
\Delta\mathbf z_k&=\mathbf z_k^{Full}-\mathbf z_k^{LoS},\\
\mathbf e_k^{LoS}&=\mathbf z_k^{LoS}-\mathbf h(\mathbf x_k^{GT}),\\
\mathbf e_k^0&=\Delta\mathbf z_k+\mathbf e_k^{LoS}.
\end{aligned}
\]

각 식을 거리(`m`)와 편파(`무차원`)에 대해 계산. 위의 `e^0`는 **기존 BB/EXDS 평균을 빼지 않은 값**이다. 동일 기준 `h_r` 오프셋의 효과와 detector 오차는 별도 기록한다.

### 4.2. 집계

- 주 집계: `t≥30 s` 전체 유한 packet **pre-gate**. 별도로 전 기간, `drive_out`, `turn`, `drive_back`, 수평거리 구간, angle/`|H_{sψ}|` 안정 구간을 집계.
- `n`, mean, RMS, centered std, signed mean, median, 5–95% 분위, first-tap mismatch rate, direct-ray visibility, 관측 `s_full−s_los` 및 `r_full−r_los`의 부호·크기. **표본 수와 packet mask를 모든 그래프에 명시**.
- 수평거리 bin은 분석용 GT 좌표로 구하고, 미래 온라인 추가분산의 추정 위치 기반 lookup과 구분. 특정 구간에서 오차가 커지는 현상이 거리만의 단독 인과효과라고 주장하지 않는다.
- 조건부 평균의 원칙: `E[e|φ]`는 이론적 대상이며, 실제 단일 결정적 주행에서의 bin mean은 **표본 조건별 평균의 추정치**다. 이론적 영평균 잔여 변동을 실험으로 증명했다고 쓰지 않는다.
- **비교 (필수):** `FULL−LOS`와 `LOS−h(GT)`를 분리 표시. 필요한 그림의 물리적 원인이 `tap mismatch`, 동일 tap에서 포트별 복소 중첩, 기존 모델의 관측 불일치 중 어느 쪽인지 구분한다.
- **선택:** 시간 자기상관은 Chapter IV-B 주 논리에는 불필요. 관련 원자료는 저장하되 논문 본문의 시간상관 수치·그림은 별도 연구/제VII장 한계 항목으로 넘긴다.

### 4.3. P2 필수 QA

- `max|e^0−Δz−e_LoS|`를 실제 float64 산술 수준에서 검사하고 임계값을 사전 기록. 단위·시점·full/los 각각의 tap selection 준수.
- 공통 조건에서의 관측 오차 분산과 단순 `R0`의 적합성을 **진단으로만 제시**. 실제 `R`이 무조건 과소라는 가정으로 분산 보정 도입 금지.

## 5. Chapter IV-C용 4상태 LoS/Full 재귀 비교 — P3

**두 필터는 동일 `f,F,Q, x0,P0, seed, controls, h,H, R0`, 나머지 상이한 것은 `z_LOS` 또는 `z_FULL`이다.** 각 arm은 동일 NIS threshold로 자체 gate를 적용한다. Packet 수용 집합이 달라지는 것은 자연스러운 필터 결과이며, 원인 분해와 혼동하지 않도록 별도 저장한다.

필터는 `z − h(x^-)` 혁신 및 공동 2차원 갱신으로 실행. 각 패킷 pre-gate에 대해:

\[
\begin{aligned}
\boldsymbol\delta\mathbf h_k&=\mathbf h(\mathbf x_k^{GT})-\mathbf h(\hat{\mathbf x}_k^-),\\
\boldsymbol\nu_k^0&=\mathbf z_k-\mathbf h(\hat{\mathbf x}_k^-)=\mathbf e_k+\boldsymbol\delta\mathbf h_k,\\
\Delta\hat{\mathbf x}_k&=\mathbf K_k\boldsymbol\nu_k^0
=\mathbf K_k\mathbf e_k+\mathbf K_k\boldsymbol\delta\mathbf h_k.
\end{aligned}
\]

- LoS에서는 `e_k=e_LoS`; Full에서는 `e_k=e^0` 사용. `h(GT)`와 상태 비교에만 GT를 사용하고 실제 추정 입력에는 사용하지 않는다.
- `x^-`, `P^-`, `h(x^-)`, `H`, `z`, `e`, `δh`, `ν`, `S`, `K`, `NIS`, `accepted`, `x^+`, `P^+`, yaw wrap, `K e`, `K δh`를 시간순 보존. `ν=e+δh`, `Δx=K e+K δh` 재검산.
- Heading 갱신 `Δψ=K_{ψr}ν_r+K_{ψs}ν_s` 및 위치 갱신을 같은 packet에서 검증. 관측오차의 성분별 상태 전달을 signed 값으로 분석하고, `K e`가 항상 상태오차를 악화시킨다고 선언하지 않음.
- 관측 수용/거부 이벤트와 자체 gate 후의 posterior를 함께 보존. NIS accepted count, 최대 관측 공백, 숫자적 공분산 대칭성·PSD, `H` 수치미분, 초기화·입력 동일성 검사.

### 5.1. 평가 지표

\[
\mathrm{RMSE}_\psi=\sqrt{\frac1N\sum_{k:t_k\ge30}\operatorname{wrap}(\hat\psi_k-\psi_k^{GT})^2},\quad
\mathrm{RMSE}_{XY}=\sqrt{\frac1N\sum_{k:t_k\ge30}\left[(\hat x_k-x_k^{GT})^2+(\hat y_k-y_k^{GT})^2\right]}.
\]

`ψ`는 논문 표에서 degree, `XY`는 cm로 표시. 동일 평가 시점 사용, gate rejected 포함. LoS→Full의 Heading/XY 차이와 증감률을 둘 다 표기하며, B0는 필수, L2는 보조 강건성 검증(같은 입력 seed 계약). B0 외 사용 bias L0/L1은 **선택**; 새 관측 데이터/잡음 생성보다 원본 4상태 실행과 동일 입력 보존을 우선.

### 5.2. 인과 해석과 분리된 보조 검증

- **필수:** 실제 self gate 전체 재귀 결과. **보조:** LoS 수용 mask 고정/동일 prior shadow를 이용해 `RF 변화 → innovation/gain/update`의 국소 기여를 구분.
- 실제 두 recursive arm의 prior는 서로 달라지므로 `Full−LoS` 결과를 한 번의 갱신에서 특정 ray가 만든 인과효과로 축약하지 않음.
- 가능하면 RF-on vs RF-off 4상태 DR를 동일 컨트롤로 추가하여 모델오차가 오히려 DR을 악화시키는 조건을 진단. 핵심 LoS/Full paired 비교의 대용으로 사용하지 않음.

## 6. 제V–VI장 연계 확장 — P4 (분리된 결과, 필수 P3를 가리지 않음)

- 기존 `BB_ORIG`는 **보정이 이미 적용된 기준선**이며 무보정 conventional과 다르다. R1에 적용할 `μ_r^B, μ_s^B, R^B`, `μ_r^EXDS`가 현재 R1·Anchor B·동일 detector/pose에 대해 실제로 존재하는지 먼저 확인.
- 없으면 보정 평균을 다른 경로에서 임의 복사하거나 GT로 생성하지 않는다. R1에 신규 학습이 필요하면 학습 route/공간 구간/평가 분리 계약을 별도 제안하여 승인받기 전 학습/성능을 보고하지 않는다.
- 사전 승인된 frozen prediction이 있는 경우 다음 두 분석을 명확히 구분:
  1. **오프라인 잔차:** `η^B=e^0−μ^B`, `η^M=e^0−μ^M`, packet별 개선/악화, 조건별 signed mean·RMS·std, 동일 패킷 mask. 평균 보정 자체의 효과만 분석.
  2. **재귀 평가:** `BB_ORIG`, `MB_ORIG`, `BB_VAR`, `MB_VAR`를 동일 4상태·동일 관측 체인에서 자체 gate 재실행. 이것은 평균·분산·gate feedback의 결합 효과이며 오프라인 잔차 감소와 구별.
- 이론적 관계 `E[(e−μ)^2|φ]=Var(e|φ)+(E[e|φ]−μ)^2`를 제V장 설명에 활용. 개별 패킷은 `η²−e²=μ²−2eμ`가 양수이면 평균 보정으로 오히려 악화.
- 편파 추가분산 조회는 원 구현대로 **motion prediction 직전 저장된 posterior 상태에서 산출한 수평거리** 사용; 값과 모델 수치가 검증되지 않으면 R1 성능 개선 결과를 구성하지 않음.

## 7. 산출물 계약 — 반드시 파일로 제공

다음 구조로 새 디렉터리를 생성한다. 기존 결과와 Obsidian 원고를 덮어쓰지 않는다.

```text
research/DLP_R1B_CH4_20261103/
  00_REQUEST_CONTRACT_FROZEN.json
  01_P0_PROVENANCE_AND_FEASIBILITY_KO.md
  02_INPUT_HASH_MANIFEST.json
  03_RF_CANARY_QA.json
  data/
    pose_timeline.csv
    channel_full_and_los_manifest.json
    rf_observations.csv              # z_full/z_los, common-tap detector, P+,P-, fp flags
    raw_observation_errors.csv       # e0, delta_z, e_los; NO mean subtraction
    raw_error_distance_bins.csv
    raw_error_phase_bins.csv
    raw_error_summary.csv
    ekf_packet_log_los.csv           # x-,P-,H,S,K,nis, accepted, x+,P+, nu, e, delta_h
    ekf_packet_log_full.csv
    ekf_scores_los_full.csv          # B0 mandatory, L2 optional
    optional_mean_correction.csv     # only if P4 approved and predictions verified
  figures/
    R1_GEOMETRY.png
    R1_FULL_LOS_OBSERVATIONS.png
    R1_RAW_ERROR_DISTANCE_PHASE.png
    R1_HEADING_XY_TIME_AND_RMSE.png
  04_P1_RF_GENERATION_REPORT_KO.md
  05_P2_RAW_ERROR_REPORT_KO.md
  06_P3_4STATE_REPLAY_REPORT_KO.md
  07_P4_OPTIONAL_MODEL_EXTENSION_KO.md
  08_QA_PARITY_AND_LIMITATIONS.json
  09_INDEPENDENT_AUDIT_REQUEST_KO.md
  10_FINAL_RESULT_AND_MANUSCRIPT_USE_KO.md
  SHA256SUMS.txt
```

원시 `H_FULL`/`H_LOS`와 필요한 경로별 배열은 별도 영속 파일로 기록해 상대경로·bytes·SHA-256·열람 절차를 명세할 것. 논문용 그림은 PNG 외에 벡터 PDF/SVG와 입력 CSV를 제공하고, 각 그림에 보정 전/후, true-state/offline vs online-estimated, gate/mask를 명시한다.

**원고에 필요한 최소 그림:** (a) R1 경로와 Anchor B, (b) 동일 pose에서 LoS/Full 거리·편파 관측과 tap 불일치 위치, (c) 보정 전 거리·편파 오차의 구간별 평균·RMS, (d) 무보정 4상태 EKF의 LoS vs Full Heading·XY 궤적/주 RMSE. 개별 케이스 숫자는 그림·표에 두고, 논문 본문에는 수식 기반의 인과 관계만 기술.

## 8. 사전 지정 PASS/HOLD 판정

| Gate | PASS 조건 | 실패 시 |
|---|---|---|
| P0 source/pose | 원본 R1 궤적의 pose·hash·전 단계 실행 SHA/설정 확보, 기존 4상태 동결 계약 확정 | `HOLD_SOURCE_OR_CONTRACT` |
| G1 RF canary | Native Full/LoS 동일 pose 완전 정합, 동일 관측기·SourceFFD 정합 허용오차 충족, 파형·tap·포트 순서 검증 | `HOLD_RF_PARITY` |
| G2 raw errors | `e0=Δz+e_LoS` 전 packet 재검산, GT only offline, 무보정 오차와 BB 보정 후 잔차 파일 분리 | `HOLD_OBSERVATION_ACCOUNTING` |
| G3 EKF replay | 동일 control/state/Q/R/initial/seed, pre-gate 혁신·갱신 항등식 및 Jacobian/gate/Joseph parity, 모든 시점 출력·점수 | `HOLD_FILTER_PARITY` |
| G4 independent | 별도 실행자/감사자가 raw 소스·로그·해시·임의 추출 packet을 독립 재계산 | `AUDIT_PENDING` 또는 `AUDIT_FAIL` |

- 각 gate의 정량 허용오차는 **기존 동결 검증 계약을 찾아 인용**하여 생산 실행 전에 확정할 것. 기존에 허용오차가 없으면 canary 재현성과 수치미분으로 근거를 제출하고 **사전 승인**받을 것. 최종 결과에 맞춰 문턱을 변경할 수 없다.
- `TECHNICAL_PASS`와 `SCIENTIFIC_SUPPORTED`를 별도 판정한다. 기존 H 검출/SourceFFD 불일치나 재료·solver 조건의 실패가 있으면 기술 수치가 좋아도 과학적 판정은 HOLD.
- 결과가 예상과 달라도 삭제하지 않는다. LoS보다 Full이 좋거나 평균 보정이 악화한 경우도 동일 표와 그림으로 보고한다.

## 9. IMPLEMENTER에게 전달할 최종 실행 지시문

> 당신은 `myoungsunk/sionna-resimulation`의 **DLP-R1B-CH4-001 IMPLEMENTER**다. 첨부 요청서의 §0–8을 순서대로 수행하라. **P0 점검과 계약·허용오차·비용 동결을 먼저 완료**하고, G1 canary를 통과한 뒤에만 R1(기존 y0.35/Tnone, 917시점)·Anchor B·mount0의 Native Full/LoS RF를 생성하라. 동일 `z=[r,s]`, 4상태 SourceFFD `h,H`, 동일 `f,F,Q,x0,P0`로 평균 보정이 없는 LoS/Full EKF를 쌍으로 실행하라. IV-B의 오차 `e0=z_FULL−h(GT)`와 `FULL−LOS`, `LOS−h(GT)`를 **보정 이전에** 계산하고, IV-C의 혁신 `ν=e+δh`, signed 상태 갱신과 Heading/XY RMSE를 재현 가능하게 보존하라. 모델 보정 비교(P4)는 R1에 대응하는 frozen 평균·분산 데이터가 검증된 경우에만 별도로 수행하라. 기존 Anchor A RF, R1의 6상태 결과, BB 보정 후 잔차를 R1B 무보정 증거로 대체하지 마라. 중단 조건에 해당하면 즉시 STOP하고 근거와 해결 요청을 보고하라. 모든 결과는 새 디렉터리에 로그·CSV·그림·SHA-256·실행 SHA와 함께 저장하고, 독립 감사자가 재계산할 수 있도록 하라. **실행 완료와 과학적 승인 및 원고 반영을 동일시하지 마라.**

## 10. 확인된 GitHub 근거 — 기준 SHA `9e9133e`

- R1 원본 궤적: `results/DRIVE_SIM_20261007/S1/timeline_y0.35_Tnone.csv` (917 time steps), `S1/TRAJECTORY_MANIFEST.json`.
- R1 생성기: `src/qclean_uwb/drivesim/trajectory.py` — outbound / 180° turn / inbound, 5 Hz, wobble.
- 원본 R1 6상태 실행 및 기존 RF: `results/DRIVE_SIM_20261007/SNOWBALL_RUNS/01a11582/final_B_20261007T1017Z/README.md` — 당시 L1/L2 FAIL 및 raw H 미동봉 명시.
- R2/R4/R5 Anchor B 4상태 conventional 비교: `research/DUAL_LP_PAPER_GAP_20261030/OBSIDIAN_CHECKPOINT_20261102/paper/figures/conventional_ekf_20261102/README_KO.md` — fixed R0·range bridge·NIS·평가 정의.
- SourceFFD/과학 계약: `research/DUAL_LP_PAPER_GAP_20261030/SCIENCE_SPEC_KO.md`.
- 최근 물리–EKF 교차 검증: `research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_LINK_REAUDIT_READINESS_20261102/03_PHYSICS_TO_RESULTS_USE_KO.md`.

**범위:** 본 문서는 실행 요청서다. 신규 RF 생산, 4상태 재귀 실행, 독립 감사는 현재 이 요청서 작성 과정에서 수행되지 않았다.
