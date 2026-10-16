# 논문 스토리라인과 Claim Boundary — Single-Anchor Dual-LP UWB (2026-10-16)

**논문 저술 계획 초안. 새로운 검증이 아직 끝나지 않은 기여를 완료된 사실로 쓰지 않는다.** 
연계 검증 프로토콜: [01_VALIDATION_PROTOCOL_KO.md](01_VALIDATION_PROTOCOL_KO.md).

## 1. 한 문장짜리 연구 중심 명제

**단일 앵커에서 Dual-LP 편파비가 제공하는 Heading 정보는 다중경로의 부호 있는 오염을 통해 약관측 Gyro Bias 상태까지 잘못 갱신시킬 수 있다. First-path total power에 조건화한 경험적 Range–편파 오차 보정은 한 동결 복도 시뮬레이션에서 이 상태 오염과 Heading/Bias RMSE를 크게 완화했다. 하지만 단일 패킷 잔차 정합은 재귀 EKF posterior 신뢰도 정합을 보장하지 않는다.**

필수로 구분할 것:
- **안테나/편파의 핵심:** $s=(P_1-P_2)/(P_1+P_2)$가 $H_{s,\psi}\ne0$인 측정으로 Heading을 제약. Range에는 direct Heading Jacobian이 0이나 dynamics로 간접 Heading 제약이 가능함.
- **보정기:** $q=\log_{10}(P_1+P_2)$는 같은 packet에서 얻는 scalar quality covariate이고 Heading 측정을 대체하는 별도 독립 센서가 아님.
- **State coupling:** $b_g$ 직접 관측 열은 0이나 KF state cross covariance와 motion model 때문에 $\Delta b_g=K_{b,r}\nu_r+K_{b,s}\nu_s$ 경로가 존재. 실제 기여의 부호와 크기는 RV1–RV2로 검증해야 함.
- **주의:** $C_{rs}>0$ 또는 '19 파라미터라서 물리적'이라는 사실만으로 모델 일반성을 주장할 수 없음.
- **가장 강력한 이미 관찰된 사례:** B0 Full m0 J4 Heading RMSE 7.490→1.773°, spurious Bias RMSE 0.08862→0.02160°/s. Bias 추정 시간평균 R0 −0.05841°, POWER −0.00537°/s; RMSE는 시간평균 부호 있는 Bias가 아니다.
- **가장 강력한 미해결 한계:** N4-B POWER의 heldout RF error 95%≈94.51%지만 N4-C posterior Pose95은 Full L2 m0≈45.7%, m45≈12.3%, B0 m45≈9.4%; 외부 환경 성능 미검증.

## 2. 제목: 증거 수준별 두 후보

**현재 완료된 결과만으로 방어 가능한 안전한 제목**

Power-Conditioned Correction of Dual-Polarized UWB Observations for Single-Anchor Heading and Gyroscope-Bias Estimation

**RV1–RV2에서 bias leakage 및 $C_{rs}$ 기여가 독립 입증된 경우에만 사용 가능한 더 강한 제목**

Multipath-Induced Gyroscope-Bias Leakage in Single-Anchor Polarimetric UWB Localization: Signed Error Mitigation and Range–Polarization Coupling

어느 경우에도 'Consistent Bayesian Covariance Calibration', 'Fully Robust', 'Universal Multipath Suppression'은 현재 사용 금지. 추후 별도 독립 scene과 state covariance consistency가 해결되면 제목 수준을 재평가.

## 3. 서론 문단·논리적 순서

1. **Sparse-anchor 필요성:** UWB ranging은 위치 기하에 유익하지만 한 시점의 range Jacobian에서 Heading에 대한 직접 편미분이 0이다. 반면 Gyro dead reckoning은 시간 누적 Bias가 발생. 최소 앵커 환경에서는 RF에서 Heading 정보를 추출하는 것이 필요.
2. **안테나의 물리적 기여:** 2포트 LP 수신의 상대 전력비 $s$가 실제 3D FFD 기하에서 Heading에 의존한다. Mount 0/45, LoS LUT의 $H_\psi$와 유한 yaw 변화량 및 다중해로 '정보가 존재하는 조건' 자체가 크게 변함.
3. **새로운 실패 질문:** Full RF에서 LoS-model 기반 $s$의 multipath error가 EKF innovation으로 들어오고, recursiveness와 $P_{\psi b}$ cross coupling을 통해 오염이 Heading만 아니라 Gyro Bias·XY로 전이될 수 있다. B0에서 실제 Gyro Bias=0인데 spurious Bias RMSE ~0.089°/s를 관찰한 현상이 핵심 출발점.
4. **경험적 완화:** 복잡한 coherent Jones G5가 아니라 두 포트의 first-path power sum으로 조건화한 작은 signed mean+full covariance map을 원래 s/r measurements에 적용. 한 동결 복도의 B0/L2 Mount0/45에서 Heading/Bias 개선. 교차항의 독립 물리 효과는 요인분해 전에는 'joint-model candidate'로만 기술.
5. **남은 과학적 모순:** packetwise conditional residual NLL/coverage가 좋아졌어도 recursive Pose NEES/95%는 매우 나쁠 수 있다. 시간상관은 주요 후보지만 state-conditioned likelihood, biased prior, high-power R narrowing, gate/process mismatch도 후보임. 본 논문이 확률적 consistency까지 해결했다고 주장하지 않음.
6. **연구 경계:** Native LoS에 Full correction 적용하면 정상 s/r을 오보정하는 현상이 확인됨. 한 복도의 Mount0-only training으로 Mount45를 외삽했으므로 new-scene/hardware generality를 제한. 다음 실험이 검증하면 claim 확대, 아니면 실제 적용 범위로 축소.

## 4. 논문에 쓸 Contribution의 단계

### 현재 이미 작성 가능한 좁은 기여

C1. 실제 LoS FFD에 기반한 Dual-LP $s$의 mount/geometry-dependent Heading sensitivity와 single-anchor heading의 직접 측정 기하 제시.

C2. B0 Full RF의 spurious Gyro Bias and Heading degradation을 정량 보고하고, 원 R0 대비 power-conditioned **empirical** signed mean/full $R_{rs}$ model이 해당 고정 환경에서 Heading/Bias/XY error를 줄인 paired simulation 결과 제시.

C3. RF **measurement residual coverage**와 recursive **Pose posterior coverage** 사이의 체계적 차이, 정상 Native LoS 오보정, RF/Gyro Bias coupling 위험을 공개하는 consistency diagnosis.

### RV1–RV6 통과 전 사용하면 안 되는 기여

X1. '원인이 정확히 $C_{rs}>0$라서 B0 false Bias가 발생했다' (Crs-off 대조 미실행).
X2. 'POWER는 s 오염에 대한 complete robustness restoration' (LoS harm / Pose NEES 과신 반례).
X3. 'G4 gain spikes 때문에 recursive failure' (G4 K/NIS trace matched analysis 미완료).
X4. 'High power variance narrowing이 직접적인 sole root cause' (High-only $R$ PSD floor 반증 미실행).
X5. 'temporal covariance가 posterior consistency gap의 유일한 원인' (독립 scene/colored noise fit 전).
X6. '16 statistically independent successes' (실제 하나의 RF scene와 같은 seed).
X7. '19 trained physical parameters' (실제 19 effective scalar descriptors: q slopes 2+bin mean offsets 6+bin covs 9+two quantile cuts 2).

## 5. 논문 Figure 및 Table의 스토리보드

| 본문 순서 | 과학적 역할 | 필요한 Figure/Table | 증거 상태 |
|---|---|---|---|
| Fig. 1 | 안테나가 왜 필요한가? | Anchor TX +45 LP, RX ±45 LP, r/s definition, actual FFD Hψ vs mounting angle with LoS physical geometry | 기존 N4-Q/POL 증거 있음 |
| Fig. 2 | 왜 단일 앵커에서도 Gyro Bias에 RF 오염이 전이되는가? | State transition Fψb, Hsψ, Pψb, Kr/Ks; B0 b_g truth=0 vs inferred signed trajectory and Heading RMSE | 식과 원 B0 trace 있음, 경로별 attribution RV1 필요 |
| Fig. 3 | 실제 최소 보정기의 역할 | q-log FP sum, three learned conditional means/covariances, expected port balance, LoS vs Full residuals | N4-B 원 모델 있음. RV2로 μr/μs/Crs 독립 기여 입증 필요 |
| Fig. 4 | 주 결과: Bias/Heading 동시 개선 | Joint4/SR4 R0 vs POWER B0/L2 vs no-s/only-s, matched two mounts, time-course bias and heading | 원 R0/POWER 있음, 누락 ablations RV1/RV2 |
| Fig. 5 | 왜 packet NLL이 recursive 일관성을 보장하지 않는가 | N4B conditional NLL/measurement95 vs N4C Pose NEES/Pose95; G4 vs POWER, Gain/NIS timeline | 성능 수치 있음, G4 상세 기전 RV5 필요 |
| Fig. 6 | 가장 중요한 반례와 수정 동기 | Native LoS distance/s overcorrection; q gain+3/-3dB and power-bin jump; high-power covariance floor | LoS 관측 수준·jump 근거 있음, recursive floor/RV3–RV4 미완료 |
| Fig. 7 (조건부) | 외부 일반화 | Fresh Full RF scenes/curved/reverse routes and LoS protection tests | RV7 독립 data 필수; 없으면 Figure 미수록 |

**Fig. 2/4의 Gyro Bias trace는 제곱평균(RMSE), 부호 있는 평균, 최종값을 분리해서 표시한다.** Fig. 5의 measurement vs state 95%는 표본 정의/DOF가 다르다는 캡션을 반드시 쓴다.

## 6. 핵심 그림 제목과 Takeaway 예시

Fig. 1: Dual-polarization provides heading-sensitive RF information not directly available from single-epoch ranging.
Fig. 2: Multipath-distorted polarization innovations coincide with spurious gyro-bias estimation under zero true bias (causal gain attribution pending).
Fig. 3: A compact received-power-conditioned empirical map predicts signed range/polarization corrections and cross-covariance in the tested environment.
Fig. 4: Corrected polarimetric observations reduce heading and gyro-bias errors in the tested corridor; mechanism-specific ablations are required.
Fig. 5: Good packetwise RF error calibration does not imply consistent recursive pose covariance.
Fig. 6: Unconditioned Full-RF bias corrections distort native-LoS observations and signal limited transportability.

캡션에서 'corrects fully', 'physically universal', 'proved AR1 noise', 'Bayesian calibrated'와 같은 과장 어휘는 금지.

## 7. 현재 증거 기반 English abstract draft — conservative and review-safe

Single-anchor ultra-wideband (UWB) ranging provides limited direct information about heading, motivating the use of dual-linearly polarized antennas as an additional orientation-sensitive measurement. However, multipath can distort the polarization power ratio and contaminate a recursive UWB–inertial estimator, including its weakly observed gyroscope-bias state. This study investigates that coupling using a frozen three-dimensional antenna-pattern lookup table and paired line-of-sight and full-multipath channel simulations. We evaluate a compact first-path-power-conditioned empirical correction for the signed errors and joint covariance of range and polarization observations. In one simulated corridor with zero injected gyroscope bias, the correction reduces heading root-mean-square error from 7.49° to 1.77° and bias root-mean-square error from 0.0886°/s to 0.0216°/s. The improvement is also observed across the tested gyroscope-bias conditions and antenna mounts; these configurations share a channel environment and are not independent propagation trials. Importantly, accurate held-out modeling of individual RF residuals does not ensure consistent recursive state uncertainty: pose coverage remains far below the nominal level, and applying the full-multipath correction to native line-of-sight measurements can be harmful. These findings motivate explicit separation of heading observability, RF integrity, and temporal or geometry-dependent contamination. The present correction is an empirical simulation baseline rather than a fully calibrated Bayesian observation model.

위 초록은 원 데이터가 지원하는 범위로 작성된 provisional draft. RV1/RV2에서 독립 물리 기여가 확인되면 기전 표현을 강화하고, 그 전에는 'demonstrates that covariance coupling blocks propagation' 같은 강한 어구로 교체하지 않는다.

## 8. G4 역전과 NEES gap의 학술적 가치

N4-B pooled likelihood: G4 NLL −1.7038 vs POWER −1.5898; N4-C L2 J4 M0 Heading G4 1.845° vs POWER 1.991°이므로 G4가 M0 Heading에서 나쁜 것은 아님. M45는 G4 1.133° vs POWER 0.727°, M0 Pose NEES는 G4 33.36 vs POWER 12.89. 논문의 명제는 **pointwise residual NLL 최적이 recursive estimator performance와 uncertainty 최적을 보장하지 않는다**이지 'G4 항상 inferior'가 아니다.

RF residual temporal correlation은 이미 관찰됐으나 동일 scene/trajectory의 deterministic geometry trend를 별도로 제거하지 않은 상태라 인과적으로 colored noise라고 확정 불가. Pointwise-vs-recursive gap이 잔류 Bias, selection/heteroscedasticity, state endogeneity, covariance floor, temporal persistence 중 어느 요소에서 왔는지 RV4–RV6로 단계별 반증한다.

## 9. 투고 전략과 최종 Claim 상승 규칙

**현재 자료로 제출한다면**: 좁은 simulation demonstration + dual-LP heading sensitivity + empirical correction + candid consistency/LoS limitations; consistency achieved 혹은 cross-scene validity라는 문구는 절대 사용하지 않는다. 추정기 기여를 핵심 novelty로 내세우려면 RV2 및 RV7 없이 강한 주장 불가.

**RV1/RV2 성공 시**: Spurious gyro-bias leakage mechanism and signed range/polarization correction contribution를 Figure 2/4의 주 메커니즘으로 강화하되 실제 positive C_rs 역할이 추가 확인된 경우에만 Cross-Correlation Coupling을 제목 및 abstract contribution에 사용한다.

**RV4/RV6/RV7 성공 시**: posterior uncertainty consistency, temporal colored bias suppression, independent-scene robustness 등의 확장 Claim을 별도 성과로 채택 가능. Q4-R 실패는 기존 연구의 음성 대조로 보존한다.

연구실의 안테나·전자기학 정체성은 실제 3D FFD $H_{s,\psi}$, TX/RX polarization geometry, two-port signal processing and FP stability를 중심에 놓고, q는 그 물리 관측을 부호 있는 오차에 대해 보정하는 보조 feature로 위치시키는 방식으로 유지한다.
