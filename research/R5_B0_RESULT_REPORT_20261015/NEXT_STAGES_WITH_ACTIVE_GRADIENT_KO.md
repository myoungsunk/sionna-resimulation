# R5 Full RF Heading: 물리 특징량+Active Gradient 통합 후속 실행 계획 (2026-10-15 수정)

## 0. 목표·평가 원칙
**Primary B0=0°/s true gyro bias**로 Full RF의 체계적 Heading 오류만 분리한다. 동일 4-state `[x,y,ψ,b_g]`에서 초기 bias 추정 자유도는 유지한다. `b_g`를 0으로 고정한 3-state 진단은 별도 Ablation으로 둔다. Gyro Bias L0/L1/L2와 음수 bias는 B0에서 물리 효과와 정보 유용성 검증 후 일반화 확인용이다.

- 동결 기존 기준선: DR4, S4, Joint4, SR4. 2D pose/Heading/gyro bias 에러 및 NEES/95% coverage. RF 원본/LUT/R0에 대한 기존 과학적 주장은 변경 금지.
- RF 품질 목표가 `|s_Full−s_direct_LoS|>.1`인 판별과, 실제 `RF s를 반영하면 Heading이 개선되는가`인 신뢰도/정보량 평가를 분리한다. AUROC 0.86은 정밀도/관측별 확률이 아님.
- R2 / R4 / R5 모두 같은 복도이므로 route heldout의 통계는 외부 장면 일반화가 아니다. 별도 scene/ray/sensor-noise seed가 필요한 단계는 BLOCKED로 표기한다.
- 코드 audit → 문제 수정 → 재감사 → synthetic test → 실제 frozen source test → 독립 score. 같은 packet에서 추출한 Multiple Factors를 독립으로 재사용 금지.

## 1. 이번 실행의 수용 현황 (변경하지 않음)

| 단계 | 대상 | 판정 |
|---|---|---|
| R5-0/R5-1 | 동결 원본 parity 및 zero-bias Heading 실패 분해 | 감사 PASS, 과학 일반화 미검증 |
| R5-2 | Dual LP/CIR 9,519개 오염 프록시 분석 | 완료 |
| R5-3 | Passive proxy held-route Brier / AUROC | 완료; Heading quality 아님 |
| PHY-Rs (기존 b437fd) | 5개 Physics feature groups, R_s only | B0 Full Mount0 개선, Mount45 악화·Pose NEES 문제 |
| **B0 PHY Hard/Soft (Run 38688494790)** | 15 methods B0/Full/LoS/mount0/45 | 계산 PASS, Soft mean+Rs m0 3.362°/m45 1.350°, 전역 채택 HOLD |
| **B0 Harm diagnostic (Run 38689008284)** | MP-risk vs original J4 update Heading harm 3,912 rows | 계산 PASS, MP-proxy Hard gate 정당화 실패 |
| R5-4 yaw full native-LoS oracle | 169 groups 3,133 samples, hypothetical Gradient | 기존 oracle 예비 검증, LoS LUT/gyro/scale 검증 전 |
| R5-5~R5-8 | 물리 Full yaw, Gradient+PHY, Heading factor, 실주행 | 핵심 후속 실행 필요 |

## 2. 업데이트된 연속 단계

### R5-PHY-A. B0의 거짓 Gyro Bias와 Heading 오류 메커니즘 분리
**입력:** 동일 B0 Full/LoS RF·wheel/gyro controls와 3state/4state original code. 
**대조:** DR3 vs DR4, J3 vs J4, S3 vs S4, SR3 vs SR4; b 자유/fixed 구분. 동일 prior pose, gate, 시간 마스크. 
**주요 결과:** B0에서 잘못된 b로 인해 cumulative yaw가 얼마나 악화하는지, RF 관측 자체 heading bias를 얼마나 증폭하는지. 예: b_final, heading signed error, initial/mid/end intervals, K_b × ν, cross-Pψb. 기존 4-state 0-bias spurious b를 physics correction 후 추적.
**PASS:** source-parity/수학 테스트와 offline mechanism 분해. b를 freeze하여 결과가 좋아져도 그 조건만으로 실제 biased sensor 성능을 주장하지 않는다.

### R5-PHY-B. MP-proxy를 Heading harm / 유효 정보 예측으로 교체
**입력:** 기존 R2 B0 harm diagnostic, R4/R5에 B0 motion prior 및 Full RF를 붙인 train/heldout 분리. 정상 LoS false reject도 계량.
**Target 분리:**
- MP proxy: `|e_MP|>.1`
- Heading harm: 원래 RF 업데이트의 `(ψ⁺−ψ_GT)^2−(ψ⁻−ψ_GT)^2>0` (only offline label)
- Expected risk: `E[Δψ_error² | observed q, prior, innovation, geometry]`
- Useful heading information: nuisance 제거 `Iψ|N`, posterior credible likelihood.
**후보 입력:** G0/1/2/4의 패킷 관측가능 지표 + G3/G5 연구용 상한; `ν_r,ν_s`, `Hψ`, (P^-_{ψψ}), anchor geometry, reliability history. GT/post-update loss는 predictor에 포함 금지.
**검증:** Leave-one-route/site/scene split, Brier/ECE/AUROC/risk-coverage/retention; `p_harm`으로 hard gate 할 경우 calibration 후 threshold 사전 고정, random retention control. G5 p_MP보다 p_harm의 추가 순효과가 있어야 다음 단계.
**중단:** LoS 정상 관측 false removal 또는 Heading harm AUROC/Brier가 route heldout에서 개선되지 않으면 Hard Gate 미채택.

### R5-PHY-C. 물리적 평균 편향+공분산의 분리 / Pose NEES 원인 분석
**모델:**
[
z_s=h_s^{LoS}(x)+mu_s(q)+epsilon_s,quad mathrm{Var}(epsilon_s|q)=V_s(q),quad M_2(q)=E[e_s^2|q].
]
[
V_s(q)=max(M_2(q)-mu_s(q)^2,mathrm{floor}),
quad R_{RF}(q)=egin{bmatrix}R_r(q)&R_{rs}(q)\\R_{rs}(q)&V_s(q)end{bmatrix}.
]
- G5 mean vs G5 mean+uncentered (M_2) baseline; centered (V_s) + bias, bias-only, (R_s)-only, (R_{rs})-correlated, (R_r)-only, time-correlated variant ablation.
- (V_s)가 음수로 추정되거나 PSD 실패면 reject model. `R_r`는 원 FP detector common offset과 MP residual 분리하여 정의.
- conditional pose NEES decomposition `Heading + XY|Heading`, time blocks, full covariance calibration. Mean correction의 편향 잔류, covariance bias, G5 Mount45 regression을 strata별 수치로 확인.
- 평가 primary B0 full0, nonharm mount45 및 clean LoS. `Heading RMSE ↓` 하나만으로 채택하지 않음.

### R5-PHY-D. Active Gradient + PHY 결합 (기존 169 Full yaw 그룹 우선)
**기존 자료:** 동일 위치 native Full/LoS 각도 샘플 169 그룹(16/19 yaw)을 사용. 각도별 Full RF를 새로운 실측으로 오표기하지 말 것.
- 원 각도별 `s_full(δ)`, `P1,P2`, CIR early4/8/16, FP 20/30/40% sensitivity, G3 frequency Jones, tap-switch, geometry, direct native LoS reference와 frozen LoS LUT reference를 별도 저장.
- 한 패킷 인접 차분 대신 원 LoS LUT의 **finite difference** `Δh` 대비 `e_g=D(s-h)`; `C_g=D C Dᵀ`에 measurement noise, shared gyro/pose uncertainty, estimated temporal covariance 포함.
- 물리 지표 단독 vs Gradient-only vs Physics+Gradient vs Shape-only. MP proxy/AUROC와 Heading 유해성/conditional information 각각 평가.
- nuisance `a0`, `a0+a1δ`, x/y, yaw prior uncertainty를 추가한 Profile likelihood와 `Iψ|N`; multi-modal/NO_INFORMATION이면 단일 heading factor 금지.
- 기존 large-span 데이터(71.4–90°)를 **Fast11 ±10° 또는 10초/20초 실제 scan 성공으로 주장 금지**. 지원되는 yaw만 관측으로 쓰고, 없으면 Native Sionna 신생성으로 진행.
- G3/G5에서 사용한 복소 채널 특징은 **research-only oracle upper bound**와 하드웨어 가용 측정만 사용하는 방법을 반드시 구분.
**PASS:** model consistency + noise/risk-calibrated selectivity + 비간접 Gradient 개선의 독립 성능; 독립 heading source factor 생성은 이 이후.

### R5-PHY-E. 실제 Full RF active yaw 생성·정보량 검증
동일 고정 RF pose, robot-center yaw, 실제 RX lever arm rotation을 분리. Path amplitude/polarization/phase 및 packet metadata, TP first-path branch/tap, gyro time alignment, LoS/Full matched SHA. Fast11, Wide11(sample count matched), Wide19, Repeat same yaw, reverse scan. Gradient mismatch가 100% MP임을 금지. 수학적 κ/info 및 LoS false rejection, Full quality precision, heading posterior credible reliability 검사.

### R5-PHY-F. Bias-aware 4state 재귀 융합 + scan 정책
- B0 first, L0/L1/L2 and signed bias later; DR4/S4/Joint4/SR4, Physics-only, Gradient-only, Shape-only, combined, matched packet/time count control.
- 정상 RF packet used once: conventional SR4 inside scan raw packet input은 격리하고 scan likelihood와 이중으로 넣지 않음.
- Heading RMSE/NEES/coverage + Pose XY NEES + (b_g) RMSE/bias95 + hard/soft packet retention + wrong-high-confidence fraction.
- 완전히 다른 RF 장면·sensor-noise seed/model uncertainty에서 성능 재검증. B0 DR4가 매우 우수하므로 `모든 RF 제거`만으로 과신을 낮추는 자명한 정책은 B0 검증 PASS가 아님. L2 bias 관측을 유지해야 함.
- 물리적으로 근거 있는 20초 기본/10초 조건부/±10° 정보 부족 시 확장 정책, 회전 시간/오도메트리·충돌 회피·재출발과 주행 총 비용 비교.

## 3. 즉시 다음 실험 Gate 순서
1. **PHY-A** — B0 S3/J3/SR3 vs S4/J4/SR4로 거짓 bias 감도 분해 (기존 원본 trace 재사용, 새로운 RF 필요 없음).
2. **PHY-B** — train-target Heading harmfulness와 signed error risk, Geometry/conditional Fisher 대비 G5 MP target의 한계 수치화.
3. **PHY-C** — G5 signed mean + centered conditional covariance, Range–s coupling, NEES 원인 추적.
4. **PHY-D** — 기존 169 native yaw 그룹에서 Physics+Gradient 결합.
5. PHY-E/F는 native RF/robot yaw/time/actual sensor availability가 갖춰져야 실행. 불가능하면 `BLOCKED_INPUT`, 기존 oracle 결과로 대체하지 않는다.

## 4. 감사 규칙·결과 명명
공통 `PRE_AUDIT.json` GO → regression negative-tests → 원본 hash/observer parity → B0 recursive + paired score → full raw x/P/quality/packet-ID 저장 → `FINAL.json`.
상태: `TECHNICAL_PASS`, `SCIENTIFIC_PARTIAL`, `FAILED`, `BLOCKED_INPUT`. 표본·장면 독립성 및 산출물의 실제 물리적 의미를 반드시 명시한다. 기존 P4 MAP kink/nonsmooth solver 검증은 별도 병렬 트랙.
