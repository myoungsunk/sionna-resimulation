# 추가 시뮬레이션 명세서 — Mount 0°/45° 완전 대칭 비교 + First-path 편파 응답 불일치
버전: 1.0 | 작성: 2026-10-10 | 실행 상태: SPEC_ONLY / 신규 RF·filter 실행 미완료

**동반 필독:** 06_SENSOR_V2_NOISY_PROBE_FULL_COV_DATA_SPEC_KO.md (전체 P6, noisy 2–3점 프로브, cross-angle/range–s covariance의 상위 필수 데이터 계약).
이 문서는 06의 데이터 계약을 대체하지 않는 **실험 요인·편파 분석·판정 기준 추가 명세서**다.
기존 센서 v2 5,697회와 3점 MIX 분석은 비교 기준으로 보존한다. 본 문서 게시가 신규 0/45 RF 생성 완료를 뜻하지 않는다.

## 0. 고정할 질문과 설계 원칙

R-MOUNT: 45° mount가 0°보다 높은 LUT heading 민감도를 주는 구간에서 multipath에 대한 heading 안정성과 NEES가 함께 개선되는가?
R-POL: 송신 +45° LP / 수신 ±45° LP의 **동일 첫 경로 tap 및 첫 도착 뭉치**에서, 측정한 두 포트 전력비가 clean LoS 기준 전력비로부터 얼마나 달라지는가? 해당 불일치가 실제 heading 오류와 연관되는가?
R-POINT: 2–3개의 yaw 각도에서 일부 측정이 부정확할 때 해당 점의 위험도(q_point)와 측정 위치의 공통 위험도(q_site)를 동시에 추정하고, 모든 점을 확률적으로 가중해 heading 및 불확실성(전체 P6 포함)을 산출할 수 있는가?
R-NOISE: 열잡음에 의한 약전력 변동과 unresolved 반사파 간섭을 구분하는가?

물리 장면과 RF/FDD 입력이 서로 다른 것처럼 표시하지 않는다. 센서 사용 가능 특징은 포트별 first-path amplitude power P1/P2 및 장치가 실제 출력하는 magnitude-CIR까지만 허용한다. 복소 per-port 위상, Jones/path truth, reflected path delay는 **시뮬레이션 정답·진단 전용**이다.

### 중요한 물리적 규약 — "TX +45°이므로 RX +45°만 co"가 아님

현 소스의 안테나-local nominal boresight LP 벡터는 +45°=(x+y)/sqrt(2), −45°=(x−y)/sqrt(2)이다. 천장 TX의 회전은 diag(1,−1,−1), RX의 회전은 Rz(body_yaw+mount)이다.

- 수직 LoS, body yaw 0°, mount 0°의 이상적 직교 LP 극한에서, TX-local +45°는 world 기준 (x−y)/sqrt(2)이므로 **RX-local −45° 포트가 co-like**이고 RX-local +45°가 cross-like이다.
- 동일 극한에서 mount 45°이면 RX 두 포트가 TX 편파를 각각 절반씩 받으므로 P1≈P2, s≈0이 clean LoS에서 **정상**이다. 이때 다른 포트에 전력이 있다고 탈편파로 판정하면 안 된다.
- 로봇 yaw, 입사각, FFD pattern, 편파 누설과 강한 null에 따라 예상 P1/P2가 변한다. 포트 이름 자체를 보편적인 co/cross 명칭으로 쓰지 않는다. co-like/cross-like는 물리적 LoS 기준과 기준좌표를 함께 기록한 **조건부 설명**이다.
- 기존 corridor.py가 위 nominal 벡터를 기록하지만 실제 FFD bank의 해당 방향 Jones readback이 완료된 증거는 아니므로, 0°/45° 전 범위 원 RF 계산 전 **FFD boresight/transverse basis parity 검사**를 필수로 수행한다. 위 이상적 예는 PASS 기준의 방향성 sanity이며 FFD 정확한 수치를 강요하지 않는다.

## 1. 0°/45°를 대칭으로 채울 실험 매트릭스

직전 7개 full-RF/LoS 케이스의 상태는 아래와 같다.

| Route | Anchor A mount 0° | A mount 45° | Anchor B mount 0° | B mount 45° |
| --- | --- | --- | --- | --- |
| R2 (loop) | EXISTING | EXISTING | EXISTING | **NEW** |
| R4 (14-leg zigzag) | EXISTING | **NEW** | EXISTING | **NEW** |
| R5 (serpentine) | EXISTING | **NEW** | EXISTING | **NEW** |

**총 3 route × 2 anchor × 2 mount = 12개 케이스. 기존 7개 재사용, 신규 5개만 생성.**
신규는 R2_aB_m45, R4_aA_m45, R4_aB_m45, R5_aA_m45, R5_aB_m45.
모든 신규 케이스에 paired full-multipath H와 matched native direct LoS-only H를 모두 생성/보존해야 한다. 동일 (route,anchor)의 mount 0°/45°는 정확히 동일한 좌표·body yaw·타임라인·센서 noise seed를 사용하고 달라지는 것은 RX 장착각이다. 앵커는 한 번에 A 또는 B **한 개**만 작동한다. 앵커 위치 A=(4,0,2.65)m, B=(10,0,2.65)m, 로봇 RX 높이 0.45m, TX rotation diag(1,−1,−1).

각 H shape = [n_pose,257,2_RX,2_TX], 실제 관측 TX index0 +45°만 사용. RF pose 수는 R2=1303, R4=922, R5=1883.
신규 full 채널 pose-case 수=1303+2×922+2×1883=6913, 기존 9519와 합치면 총 16432 pose-case. **이는 서로 다른 16,432 위치가 아니다.** Full H 및 LoS H의 2종 SHA·pose-index parity와 12개 complete flag를 보존한다.

- 각도는 antenna_yaw = body_yaw + mount (rad/deg를 혼용하지 않음).
- mount 45°를 가진 R2-A 기존 데이터를 신규 생성하면 안 된다. 먼저 SHA parity 확인하고 재사용한다.
- 단순히 mount 0° RF H의 포트 전력을 재라벨링/교환하거나, yaw angle +45°를 오도메트리 truth에 대입해 mount 45° H를 만든다고 가정하지 않는다. Sionna solver 및 FFD의 동일 위치에서 RX orientation을 실제로 바꾼 RF 채널로 재검증한다.
- LUT 자체는 최초 동결된 공통 2° LoS FFD LUT (SHA 711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079)를 유지하고, h_LUT의 입력에 mount=0 또는45를 넣는다. 신규 LoS-native H와 모델의 F01/L1/L2 기존 FAIL은 새 PASS로 미화하지 않는다.
- ROUTE R2/R4/R5는 동일 복도 geometry(20×2.4×2.7m, plasterboard 양 측벽, 콘크리트 바닥·천장)를 공유한다. 12케이스 역시 cross-environment 반복이 아님.

**불균형 금지:** mount 45°는 이전 프로브 유효 subset에서 R2-A의 물리 지점 두 곳에만 존재했다. 프로브 가능한 전 장소를 두 mount에 대해 대칭으로 만들고 비교의 primary 집합을 두 mount 공통의 paired station으로 고정한다. 예전 RF-off prior 커버리지가 동일할 때 최대 공통 16 물리 지점 ×2 anchor ×2 mount 중 유효 route-specific case-station은 64개까지 가능하지만, 이 숫자는 미리 PASS/표본 수로 주장하지 않는다.

**예산 제약 시:** R2/R4/R5의 앵커 A에서 0/45 paired subset을 먼저 완결하고, 둘 중 45° 결과만 독립적으로 과장하지 않는다. 최종 main analysis는 12-case 완결 후 확정한다.

## 2. First peak / first-arrival cluster 편파비 — 주 분석 지표

delay spread, CIR kurtosis, 전체 CIR의 위치별 late-tail 통계는 주 분석에서 제거하고 **보조 진단**으로만 사용한다. unresolved path가 LoS와 시간상 분리되지 않는 상황에서는 에너지 분포보다 해당 early signal의 편파가 LoS 예상과 달라지는지 직접 검사한다.

### 2.1 First-path power ratio (모듈 최소 관측 가능 계약)

동결 observation.py와 정확히 같은 한 개의 common first-path tap k_fp:
Hann window → 4× zero-padding → IFFT×N → strongest RX branch 30% leading edge → **동일 k_fp에서 양 RX port 동시 power 채취**.

P1_FP=|CIR_RX+45[k_fp]|², P2_FP=|CIR_RX−45[k_fp]|².
s_FP=(P1_FP−P2_FP)/(P1_FP+P2_FP).
R_FP,dB=10log10[(P1_FP+floor)/(P2_FP+floor)].

s와 R_dB는 서로 독립적인 측정이 아니라 같은 두 전력의 변환이다. floor는 실제 수신기 잡음 바닥 또는 사전정의한 양의 수치 floor로만 설정하며 포트간 gain imbalance와 포화는 별도로 기록한다. numerator/denominator의 불안정성이나 first-path 검출 실패는 결측으로 기록한다.

### 2.2 첫 도착 "뭉치" (cluster, 추가 magnitude-CIR가 실제 출력되는 경우만)

두 RX 포트에서 서로 다른 peak/tap를 골라 비교하면 본래 물리적 편파비가 아니므로 금지. 동일 k_fp 기준의 공통 시간창 W_j을 설정한다.

E_i(W)=Σ_{n ∈ W} max(|CIR_i[n]|²−N_i[n],0).
s_W=(E_1(W)−E_2(W))/(E_1(W)+E_2(W)).
R_W,dB=10log10[(E_1(W)+floor)/(E_2(W)+floor)].

- 원 observation의 single-tap s_FP가 primary로 유지된다. first-cluster s_W는 amplitude-CIR가 하드웨어에서도 제공되는 경우에만 deployment candidate이다. 시뮬 complex H를 offline IFFT로 magnitude만 만든 경우에는 **research-only surrogate**라고 명시한다.
- 시험창은 single tap 및 공통 k_fp 기준 폭 약 2 ns / 약 4 ns / 약 8 ns의 세 후보를 사전 등록한다. 복소 CIR의 4× zero-padding sample grid는 실제 4× 지연 분해능을 의미하지 않는다.
- 어떤 cluster window를 primary로 정할지는 held-out heading error를 보기 전에 clean LoS-only 채널의 Hann/IFFT mainlobe 에너지 포집률과 포트간 상대 gain 보존성으로 판단한다. 선택된 구간의 실제 sample 시작/끝, window 및 noise floor는 LUT/reference와 measured 채널에 동일하게 적용한다.
- tap이 mount나 yaw에 따라 튀는 현상은 first-path 검출기의 비선형성일 수 있으므로 k_fp, strongest port, leading edge, peak 위치와 window boundaries를 모두 저장한다. 선택된 tap을 truth로 고정하는 oracle test는 온라인으로 해석 금지.
- 절대 전력 ratio와 cluster 적분은 하드웨어 gain, noise floor, port sensitivity에 영향을 받는다. 반드시 dB 포트 교정/드리프트를 포함한 noise arm을 따로 시험한다.

### 2.3 "수신된 다른 편파"의 증분은 clean LoS reference 대비로 정의

co/cross 포트를 yaw·mount에 무관하게 고정하지 않는다. 각 실험 각도와 입사기하에 대해 정확히 매칭된 LoS-only FFD의 예상 포트 전력을 기준으로 설정한다.

**Oracle 진단(진짜 XY/yaw, online 금지):**
e_MP,FP=s_FP,full_clean−s_FP,LoS_clean.
e_LUT,FP=s_FP,LoS_clean−h_LUT(p_true,psi_true,mount).
e_total,FP=s_FP,full_clean−h_LUT(p_true,psi_true,mount).

**Online 품질평가(사용 가능한 IMU/wheel/range 추정만):**
r_FP=s_FP,measured−h_LUT(p_beforeRF,psi_beforeRF,mount+delta_measured).

Cluster에 대해서도 원 FFD LoS-only 채널을 동일 창과 수신기 모델로 처리해 reference h_W를 **별도로 보정·검증**한다. 기존 single-tap LUT h_FP를 cluster s_W에 그대로 빼는 것은 서로 다른 observation chain이므로 금지. 별도 cluster-LUT가 물리 정합에 실패하면 cluster는 offline distortion 진단까지만 적용.

추가 feature:
- |e_MP,FP| / |e_total,FP| (오직 oracle label), online |r_FP| (predicted pose 오차가 섞임).
- s_FP, |s_FP|, P1+P2 및 R_FP,dB; cluster s_W, |s_W−s_FP|, R_W−R_FP,dB (magnitude-CIR available일 때).
- 두 포트 상대 gain 보정 후 **부호 있는** s와 그 LoS reference residual. |s| 자체는 비정상 편파·탈편파의 증거가 아니다.
- first-lobe 형상 및 port ratio의 yaw 변화량 [s(δ2)−s(δ1)] 같은 **실측 변화량**과 모델 예측 변화량의 차이; 모델이 맞으면 시간적·각도별 shared bias와 heading correction 구분에 도움이 될지 평가.

**물리적 한계:** coherent한 unresolved 반사파는 두 LP 포트에 다른 합성 전기장을 만들어 P1/P2를 왜곡하지만, 측정값 자체에서 LoS와 reflected power를 양의 에너지로 분리할 수 없다. 진짜 탈편파(DoP 저하), 편파 방향 회전, 타원편파는 두 LP 포트 amplitude power만으로 유일하게 구분할 수 없다. 따라서 최종 목표는 **LoS 편파응답 대비 mismatch 및 heading 오염위험도**이고 '절대 탈편파량'이라는 이름을 붙이지 않는다.

## 3. 2–3점 yaw probe와 편파 응답의 연결

로봇 본체 회전 시 ψ_antenna=ψ_body+mount+δ_body; 별도 head mode는 ψ_antenna=ψ_body+mount+δ_head로 분리한다. 직접 전파 계산은 true physical orientation을 쓰되 estimator는 gyro/wheel/head encoder 관측 orientation만 사용한다.

각 i에서 z_i=s_FP(δ_i), model h_i=h_LUT(x_beforeRF,δ_i). 잔차 r_i=z_i−h_i.
2점/3점은 사전 고정한 원 sweep의 [0, 2], [0, 2, 4] 인덱스(약 0,±10,±20°)를 우선 사용한다. 0/45 mount에서 두 점 세트의 상대 회전각과 회전 제어잡음 seed를 똑같이 대응한다. 다만 mount 45°에서 센서가 가파른 관측 구간에 놓이는지 q_slope도 실제 FFD LUT Jacobian으로 함께 기록한다.

임의로 가장 residual 작은 1점만 골라 사용하지 않는다. 점별 오염잠재상태 c_i, 위치 공통 오염상태 M을 둔 robust mixture/batch likelihood로 모든 z_i를 공동 사용한다. 결과에 q_site_bad, q_point_bad_i, heading multimodal posterior, heading mean/credible interval, P6 update, NIS/NEES를 보존한다.
- r_raw max/mean, common heading fit 이후 shape residual, Jacobian condition, angular response modulation depth 등을 특징으로 비교한다.
- 큰 raw r은 정상적인 heading correction 때문에 생길 수도 있으므로 RF corruption label로 직접 사용하지 않는다.
- 3점에서 모두 똑같이 heading 방향으로 이동한 clean-shaped curve는 gyro prior 없이는 true yaw shift인지 effective polarimetric rotation인지 구분할 수 없는 경우가 있다. 확률 보정·abstention/uncertain output을 평가한다.

이상적 균등 이득 직교 LP 수신이라면 s(α)≈(Q/I)cos2α+(U/I)sin2α. 단, body yaw/anchor 입사기하 및 FFD pattern이 모델과 일치한다는 가정하의 진단이다. 3개 yaw에서 Q/I, U/I를 추정할 수 있는가와 **로봇 절대 heading을 구할 수 있는가**는 다른 문제다. 작은 ±10~20° span에서는 선형 조화계수 추정이 불안정할 수 있으므로 설계행렬 condition과 noisy heading prior를 함께 기록한다. 수신 두 LP 포트 power만으로 V/I는 미측정이므로 sqrt[(Q/I)^2+(U/I)^2]를 전체 DoP라고 주장하지 않는다.

## 4. Full covariance + noisy 회전 실험 (06 사양서와 동시 적용)

06번 사양서의 모든 JSON/NPZ field requirement를 그대로 적용한다. 특히 다음을 누락하면 '완료'가 아니다.
- (T,6) 상태 및 (T,6,6) P6를 예측·odometry·range·RF 각 단계에 저장. 기존 pre_rf_cov는 range 전 단계임을 주의.
- 실제 본체 yaw, 명령 yaw, IMU/encoder yaw, slip, 회전 중 XY displacement, 회전/정착/측정/원위치 비용·시간.
- 원래 5Hz v2의 초기화·drift low/mid/high·wheelbase error·noise seed를 0/45 양 mount에 동기화. 독립 thermal noise seed와 realized SNR(제안 30/10dB) 분리.
- 위상 없는 관측 P1_FP/P2_FP, cluster power (available일 때), port gain/noise floor calibration, measurement timestamp.
- Sigma_probe: 같은 station의 2/3점 사이의 off-diagonal s–s covariance, range–s 및 range–range covariance까지 포함. Same H를 다른 gyro seed로 반복한 것은 독립 multipath sample이 아니므로 training covariance 독립표본 수 별도 보고.
- full/LoS channel에서의 관측 parity (same RX index convention, strongest port 30% FP index, shared tap), LUT L1/L2 FAIL 보존.

## 5. 완전 대칭 비교군 및 평가 표

0°와45° 각각 모든 6 route×anchor 조합에서 다음을 같은 RF station, path, seed, clock에 실행:
A = IMU+wheel, RF off.
B = IMU+wheel+single-anchor range.
C = B + matched native LoS-only s (full-route EKF).
D = B + full-multipath first-path s (full-route EKF).
E = 기존 1-point passive quality 정책 (single-angle, 가중/abstention).
G1/G2/G3 = 1/2/3점 naive independent Gaussian (부적절한 독립성 가정의 명시적 대조군).
F1/F2/F3 = 1/2/3점 latent site+point soft-weighting (초기에는 FP s만).
H2/H3 = 2/3점 F + port-power-ratio / calibrated first-cluster feature 기반 learned prior.
Optional S2/S3 = full amplitude-CIR가 실제 장비에서 가능할 때만 first-cluster s로 구현한 joint model.

**다음 두 결과표를 절대 혼합하지 않는다:**
T1: 같은 복도 **전체 주행** 후 A~H의 heading/position RMSE, NEES, coverage, 실제 probe time budget.
T2: 같은 station에 RF-off에서 출발한 **동일 시점 조건부 1/2/3-point correction** (LoS-only vs full RF, 0 vs45 mount). 이 T2는 부분 구간·한 번의 국소 추정이며 전체 주행 EKF 누적 성능이 아니다.
과거 T1 LoS-only C 0.720°, D 2.942°, A 9.893°와 과거 T2 3점 MIX 7.030°를 하나의 RMSE 순위처럼 비교 금지. T2의 동일 prior를 full/LoS·0/45에 공통 적용해 양쪽 모두 실제 재평가한다.

명시적 primary 평가:
- 같은 station에서 mount 45−0의 heading RMSE 차이(°), P95, mount 조건별 good/bad5 비율, distance/yaw/LUT slope stratification.
- first-path/cluster ratio의 LoS reference mismatch vs 실제 RF-only heading error, Spearman/Pearson; 정보 추가가치: distance+Psum 기준선 대비 measured s와 |s| 추가, 그 후 cluster mismatch/cross-angle residual 추가 (label truth는 feature에서 제외).
- q_site/q_point multipath 분류 AUROC/Brier/ECE/false clean; 실제 heading 5° 이내 판별 AUROC/Brier/ECE, risk-coverage; no-match/ambiguity 포함 분모.
- full-route pose-NEES (df=3), 95% pose/heading coverage, post-RF harmful update, long bad wall segments, probe elapsed time and yaw rotation energy.
- LoS-only full-route도 NEES가 3 이론값과 크게 다를 수 있음: 0.720°는 정확도 지표이지 model consistency 승인 아님.

모든 통계는 route/anchor/mount 별 분석, 같은 (route,anchor,station,seed) 내 0/45 paired comparison; 학습·검증은 route 단위로만 나누되 같은 복도라는 사실을 명시하고 완전한 cross-geometry 주장을 보류한다. Station/환경 cluster 기반 bootstrap 1000회(seed20261010). RF/noise seed가 많아도 독립 site 수가 늘지 않는다.

**PASS 최소 조건:** 12개 full+LoS H 입출력 parity와 해시, 실제 FFD co-like sanity, 06 데이터 schema, full-P6 PSD+단위, gain calibration, 포함 가능한 RF evidence, no-truth inference, paired coverage가 모두 통과해야 지표 비교 가능. 개선 주장에 대해서는 mount별 개선량 paired 95% CI, NEES/coverage와 accuracy trade-off, cross-geometry FAIL을 함께 공개한다. 일부에서만 RMSE 좋아도 "일반적인 향상"이라 말하지 않는다.

## 6. 구현 및 보존 단계

Stage 0 [기존자료 확인]: 총 12개 중 7개 존재/5개 없음, timestamp/pose IDs 동일성, TX/RX frame/FDD nominal parity, LoS/native observer parity, 기존 LUT SHA·FAIL 상태 확인. 신규 RF 계산 전 동결 manifest.
Stage 1 [신규 5개 RF]: Sionna full-multipath H와 native LoS-only H 생성; 0/45 동일 station RX mount orientation만 다르게 적용, 원본 절대 덮어쓰기 금지.
Stage 2 [관측 특징 추출]: first-path P1/P2 및 같은 tap s_FP primary; 동일 first-lobe common gate ratio secondary. Clean LoS reference와 full channel 분리, noise/gain controls.
Stage 3 [matched station]: F/G/H 1/2/3점, full 6×6 prior covariance, noisy gyro/wheel body turn, Sigma_probe offdiagonal와 range–s covariance, LoS-only와 full 비교.
Stage 4 [full-route filter]: 실제 수집 시간 포함한 12case×drift×seed 기법 비교, NEES·RMSE·업데이트 안정성.
Stage 5 [외삽 검증]: 복도 폭, 측벽 재질, 앵커 위치, R2/R4/R5 밖의 새로운 위치/방 layout. 이 단계 전 GENERALIZATION_NOT_PROVEN 유지.

반드시 제출할 추가 artifact:
A. MOUNT_CASE_MATRIX.json (12 조합, 5 NEW, full/LoS H SHA, station ids/FFDs).
B. ANTENNA_POL_FRAME_AUDIT.csv/json (actual TX+45 world vector, RX0/1 world axes vs body+mount, expected co-like, FFD Jones parity).
C. FP_CLUSTER_RATIO.csv / NPZ (P1/P2, s_FP, gate window and s_W, receiver gain, LoS prediction and oracle mismatch in separate file).
D. MOUNT_PAIRED_SITES.csv (0/45 same x,y,heading,anchor, RF seed and sensor prior, 1/2/3probe).
E. FIRST_CLUSTER_GATE_CALIBRATION.json (Hann mainlobe, capture fraction, no adaptive test leakage).
F. POL_RATIO_HEAD_ERR_ASSOCIATION.csv (by mount/route/anchor/distance/slope, valid root availability).
G. V2_FULL_COV_NOISY_PROBES.npz + CROSS_ANGLE_COV.npz; 06 document fields remain mandatory.
H. MOUNT_0_45_FILTER_COMPARE.csv, PAIRED_BOOTSTRAP.csv, EXECUTION_STATUS.json, exact source and output SHA256 manifest, failure/partial logs.

Explicit statuses: NEW_H_NOT_RUN, RAW_P6_NOT_BACKFILLED, COV_NOT_VALIDATED, FIRST_CLUSTER_HARDWARE_UNAVAILABLE, NOISE_ARMS_NOT_RUN, ROUTE_FILTER_NOT_RUN, FULL_GEOMETRY_NOT_VALIDATED. Never mark them completed based only on this document.

## 7. 보고용 핵심 표현 (연구 주장 범위)

확인할 가설은 "RX의 어느 하나가 항상 cross-pol이라서 cross power 증가가 직접 탈편파다"가 아니다. 정확한 표현은 **"LoS-only FFD가 예측한 dual-LP first-arrival power ratio 대비, multipath가 실제 합성 편파응답을 얼마나 왜곡하는지; 이 왜곡과 2–3점의 공통/각도별 구조로 single-anchor heading의 정확도·신뢰도를 개선할 수 있는지"**이다.

독립적인 전문 polarimeter 없이 두 LP amplitude만으로 절대 탈편파도(DoP)를 계산했다고 주장하지 않는다. 필요하다면 offline Sionna Jones oracle로 어떤 반사 경로가 port ratio 변화에 기여하는지 검증하지만 estimator inference에는 넣지 않는다. F01/F02 OPEN, scientific_PASS=false는 원문 그대로 유지한다.
