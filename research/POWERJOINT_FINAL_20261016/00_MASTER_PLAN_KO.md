# 00. POWER_JOINT 최종 검증·논문화 — 실행 전 동결 문서
날짜: 2026-10-16 (KST)

> **문서 상태: PLAN FROZEN / NUMERIC EXPERIMENTS NOT EXECUTED IN THIS BRANCH.** 다음 요청부터 실행. 이 브랜치는 현재 연구를 과학적으로 감사·재현 가능한 실험으로 준비한 문서/기계 판정 계약만 제공한다. 이전 실험의 실패 결과나 독립 환경 검증 미달을 성공으로 격상시키지 않는다.

## A. 최종 논문 연구 질문

**Single-anchor Dual-LP UWB의 편파 관측 s는 직접 Heading 민감도를 가지지만, Full RF multipath 오염은 Range–s 결합 Innovation을 통해 Heading·Gyro Bias·XY 상태추정에 누적된다. 정상 LoS를 보존하고 state-/geometry-dependent RF 오류와 시간상관을 고려하면, 기존 POWER_JOINT의 정확도 개선을 재현·일반화하면서 상태 불확실도 과신까지 줄일 수 있는가?**

현행 POWER_JOINT는 하나의 복도 R2에서 검증된 **empirical first-path-power-conditioned signed error correction baseline**이다. 통계적으로 일관된 Bayesian posterior correction으로 승인되지 않았다.

상태 $x=[x,y,\psi,b_g]^T$, 측정 $z=[r,s]^T$, $s=(P_1-P_2)/(P_1+P_2)$, 보조 패킷 특징 $q=\log_{10}(P_1+P_2)$, $R(q)=\bigl[\begin{smallmatrix}V_r&C_{rs}\\C_{rs}&V_s\end{smallmatrix}\bigr]$. 범용적으로 $q$와 $s$가 독립이라고 가정하지 않는다.

## B. 기존 증거: 이미 닫힌 검증과 직접 관찰

| ID | 이미 수행한 실험 | 검증된 내용 | 채택하지 말아야 할 결론 |
|---|---|---|---|
| N4-B | 9,519 RF paired residual; POWER joint measurement95=94.51%, NLL=−1.5898 | 전력 조건부 오차 예측이 해당 데이터셋의 RF 잔차를 잘 설명 | EKF Pose95가 95%라는 결론 |
| N4-C | R2 1개 corridor, seed0, 2 Mount×4 Bias×2 Solver; B0 M0 J4 Heading 7.490→1.773°, Bias RMSE .08862→.02160°/s | 해당 동결 시뮬레이션 내 empirical POWER 개선 | 16개 독립 scene 성공, normalized p(z|x), 범용성 |
| N4-Q / Q4-R | Full M45 L2 POWER Heading .727°, Pose NEES 18.58, Pose95 12.3%; 조건부 XY NEES 16.06 | estimator가 과신; 이미 좋던 heading과 위치 covariance 구분 필요 | 단순 P inflation으로 공분산 해결 |
| 기존 Qd | Sensor-v2의 Wheel/Gyro 입력 Q source-matched, 32 independent generator seeds; Qd×64도 M45 condXY 과신 잔류 | 누락된 Wheel white noise Q가 주원인이라는 설명 미지지 | Qd 확대가 새로운 물리 정답 |
| High-Vr | High-power Vr만 상향: M45 L2 XY RMSE 7.86→8.51cm (R0 floor), condXY 16.06→16.21 | 고전력 Vr floor만으로 M45 해결 불가 | High-power Range 분산 축소가 sole cause |
| Exp1 | M45 L2 t95–135s Range LOS vs narrow XY axis | 정렬 0.984, 잔차 평균 +5.47cm, narrow error +6.49cm, condXY NEES 32.97 | 잔류 Range bias가 전체 과신의 유일 원인 |
| Exp2 | 6-way Mean/Cov + C_rs removal, both fixed and natural gate | 모든 Mean+R의 결합 중요; C_rs=0은 M0 Heading 해롭지만 M45 Heading/condXY 개선 | 양의 C_rs가 항상 유익 |
| Exp3 | GT-observed Range low-frequency oracle | M45 L2 t95–135s NEES 32.97→2.46 (10s centered oracle), full path 16.06→8.55; XY RMSE 악화 | 3cm floor만 더하면 covariance 완벽, online correction validated |
| Exp4 | Native LoS R0 vs Full-trained POWER 직접 재귀 | L2 J4 M0 Heading .243→1.517°, XY 2.72→21.76cm; M45 Heading .158→1.129°, XY 4.35→11.70cm | Full-trained POWER의 정상 LoS 적용 안전 |
| Pole | R5 Anchor B pose706 native LoS s −.946821, old LUT −.069205, pole candidate −.945594; 9,519 LoS overall s RMSE .014184→.009616 | 현 FFD/LUT 극점 좌표 특이성과 특정 교정 후보 수치 효과 | FFD-bank regeneration PASS / 모든 LoS interpolation PASS |
| Pole R2 recursive | 기존 R0 Full M0 B0 Pose NEES 2591→356.72; POWER R2는 원본과 동일 | 비물리적 극점 Jacobian이 일부 극단적 NEES에 기여 | POWER의 Pose 과신이 극점 교정으로 해결 |

**추가로 확인한 간과 위험:** LUT 메타의 500점 interpolation gate는 최대오차 0.023972로 설정 허용치 0.01을 초과, passed=false. 극점 5개 수정 후에도 $\theta\ge2^\circ$ LoS–LUT 잔여 최대 오차 0.046651. 상태/P/Gate의 source 재현성과 **관측모델 자체의 물리 정합**은 서로 다른 Gate임.

기존 모델 $R_0$은 실험용 공분산이며 실측 thermal LoS 물리 하한이 아니다. Q4-R에서 바꾼 것은 측정 $R$이 아니라 상태 $P^-$; posterior gain/point-error 왜곡이 있었음을 정확히 구분.

## C. 최종 미해결 가설 8개와 실험 리스트

실험은 임의로 추가·삭제하지 않고 F0–F7로 고정. 기존 대조를 재실행할 경우 source parity/새 모델의 필수 paired baseline에 필요한 경우만 허용.

| 단계 | 실제 검증 질문 | 접근/코드 기반 | 완료할 과학적 산출물 | 시작 가능 |
|---|---|---|---|---|
| **F0 EM/LUT source closure** | 극점 hotfix는 원본 FFD의 물리적 θ→0+ 극한과 같은가? off-pole interpolation/Ranger offset은 올바른가? | 원 hs_lut.py, pattern_apply.py, 관측 O.observe, pole_lut_fix.py, FrozenLut adapter | 신규 source-generated LUT + s/Jacobian/r native LoS 정합 + pole/seam QA | **원 FFD bank 확보 필요** |
| **F1 P2/N4-B 재학습** | R5 극점 오염 레이블이 POWER/G4 RF error 학습·heldout likelihood를 왜곡했는가? | 기존 N4-B weights/folds, 3-bin POWER, source-corrected $h_s$와 Native LoS | contaminated vs corrected train targets, heldout likelihood/coverage, paired source parity | F0 수치 후보로 예비, source PASS 후 논문 |
| **F2 Bias leakage·Dual-LP 인과** | B0 가짜 Gyro Bias와 M0/M45 교차공분산 차이의 실제 기여는? | core.py, N4-C actual J4/SR4, Exp2 fixed prior/fixed gate; Range-only, s-only S4, $4R_0$/gate-only, no-$C_{rs}$ | $K_{b,r}\nu_r$, $K_{b,s}\nu_s$ 기여, 뒤틀린 Heading과 Bias 전이, mechanism-falsification | **기존 자료 예비 즉시 가능** |
| **F3 LoS-safe 물리적 RF correction** | 정상 LoS에서 평균오보정을 차단하며 Full 개선을 유지할 수 있는가? | calibrated $q_\mathrm{LoS}(\hat x^-,m,a)$ vs observed power residual, CIR/FP quality, two-branch likelihood/guard, train-only parameters | Native LoS no-harm + Full-RF correction, signed bias/variance, calibrated risk | F0/F1 완료 후 |
| **F4 Temporal accumulation & state covariance** | correlated residual/site fixed bias/Gate/geometry/state coupling 가운데 무엇이 conditional XY overconfidence를 유발하는가? | Schur NEES/eigenaxis; pre-gate innovations, matched site revisit, batch/colored state models; posthoc report-only PSD as separately validated comparator | condition-XY NEES≈2 / pose≈3 근거, Coverage95 & sharpness, Heading/Bias/XY nondegradation | 기존 자료 예비 가능; 인과 확정은 신규 RF scenes 필요 |
| **F5 G4/FP/gain robustness & two-axis geometry** | pointwise NLL 우세인 G4가 왜 일부 Mount의 recursive consistency에서 뒤지는가? 동적 FP/gain과 기하정보가 원인인가? | G4 vs POWER means/cov cross-swap, $H_\psi$ info, CIR FP tap/window, gain ±3/6dB, port-swap controls | Gain/NIS/Gate/tail cause or falsified; RF-integrity/geometry two axes; hardware-visible features | 기존 실험 입력으로 일부 즉시 가능 |
| **F6 independent full-RF data & generalization** | 모델의 성능이 다른 채널 realization/route/anchor/mount/seed에도 유지되는가? | Sionna native complex Full & LoS, new motion streams, scene-disjoint splits, source FFD | independent scene-clustered confidence intervals, external B0/L2, rare bad cases, no-LUT/GT leakage | **신규 시뮬레이션 필수** |
| **F7 Final locked end-to-end falsification** | F0–F6의 통과 모델이 보정 정확도·신뢰도·LoS 보호를 동시에 만족하는가? | frozen code/weights/thresholds, untouched F6 scenes, paired R0/S4/SR4/POWER/G4/new candidate, independent reviewer | 최종 본문 Figures/Tables/limitations + Git/source/data bundle | F0–F6 PASS 뒤 |

**F6 자료는 F3/F4의 최종 모형 학습 전에 Training/Validation/Test로 선분할.** R2/R4/R5는 기계적 재현·회귀검사와 가설 형성용 기존 scene이며 최종 untouched 시험 아님.

F0에서 source FFD가 없다면 F2·F4·F5의 소스 동결 **진단 대조만 수행**하고, F1/F3 최종 과학적 PASS 및 F7은 입력 대기로 명시한다. 새로운 수치 대신 입력 명세서를 발행하고 다음 독립 실험을 진행.

## D. 이 연구에서 반드시 유지할 주장 경계

- **확정 가능한 좁은 주장:** Dual-LP $s$의 직접 heading sensitivity, B0의 RF 유도 spurious Bias 추정 현상, 하나의 복도에서 POWER 경험적 보정의 상태 RMSE 개선, RF residual95와 EKF Pose95의 격차, 정상 LoS 오보정, 극점 오류의 일부 NEES 원인.
- **추가 검증 조건부 주장:** $\mu_s$의 고유 causal 기여, $C_{rs}$의 Mount별 물리 원인, clean/MP regime identity, temporal residual state bias source, geometrical reliability, independent scene robustness.
- **철회해야 할 주장:** covariance-calibrated Bayesian filter 완성, $C_{rs}>0$ 보편적으로 beneficial, 19개의 독립 물리 변수 학습, 16개의 독립 전파 실험, $P^-$/$R$ 일괄 확대 해결, GT oracle LPF 사용 가능한 online correction, 극점 hotfix=원 FFD 신생성.

**다음 단계는 실행이다.** 본 branch의 코드/데이터/실험 설계 manifest와 RUNBOOK을 고정한 뒤, F0 입력 충족 여부 확인 및 병렬로 가능한 F2·F4·F5 canary를 시작하고 이후 순서대로 진행한다. 재실행 때마다 코드 감사→부정대조→원본 재현→실험→독립 재계산을 요구한다. 패키지/논문 산출물은 새 independent scene이 없어도 완료된 범위만 정직하게 보고한다.
