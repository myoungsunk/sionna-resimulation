# 01. Hypothesis Ledger: 검증·미확정·반증 가설과 논문 주장 경계

버전 1.0 / 2026-10-16. 이 문서의 PASS는 인용된 *기존 실험 범위에 한해서만* 인정한다. 확정 현상(Observation), 인과 가설(Causal hypothesis), 물리 모델의 외삽 가능성(Generalization)을 혼합하지 않는다.

## 1. 기존 실험으로 닫힌 질문 (다시 독립 가설로 반복하지 않음)

| H-ID | 주장 | 이전 데이터 및 정량값 | 상태 / 다음 행동 |
|---|---|---|---|
| C01 | 하나의 Full RF 복도 R2에서 POWER는 R0 대비 Heading/Bias RMSE 개선 | M0 B0 J4 7.490→1.773°, Bias RMSE .08862→.02160°/s; M45 L2 .848→.727° | OBSERVED. 원본 baseline freeze, 다른 RF scene에서 독립 반복 전 일반화 금지 |
| C02 | M45 Pose의 핵심 잔여 NEES는 조건부 XY 좁은 축 | L2 J4 Pose 18.580=Heading 2.522+condXY 16.058, 좁은 eigen axis 13.774 | OBSERVED. covariance PSD + Schur identity를 항상 검사 |
| C03 | Original Sensor-v2 입력 Q와 필터 Wheel/Gyro Q 구조가 동일 | 독립 seed32 wheel normvar .98579, Gyro .99230; x/y를 GQG^T로 전파 | VERIFIED IN SIMULATOR. 물리 하드웨어 Q 정합 주장 금지 |
| C04 | Qd×64로 M45 narrow XY 과신과 위치 정확도가 모두 개선되지 않음 | M45 L2 XY .0786→.1416m, condXY 16.06→14.19 | CONTRARY to sole-Q-inflation solution |
| C05 | High-power Vr-R0 floor 단독은 M45 개선 해법 아님 | M45 L2 XY 7.86→8.51cm, condXY 16.06→16.21 | CONTRARY. Range Jacobian/bias/temporal evidence 우선 |
| C06 | M45 t95–135s Range 잔차 및 좁은 XY축 기하정렬 | alignment .984, residual +5.47cm, narrow error +6.49cm, NEES 32.97 | OBSERVED CORRELATION, cause not established |
| C07 | R2 GT residual low-pass oracle가 95–135s 급등을 줄임 | centered 10s: conditionalXY 32.97→2.46 on selected window but full 16.06→8.55; XY RMSE 7.86→10.09cm | CAUSAL *OFFLINE INPUT INTERVENTION* for that dataset only, not online validated |
| C08 | Mean, covariance, cross-correlation effects differ across mount | Gate fixed M0 L2 C_rs removal Heading 1.991→2.313° (worse), M45 .727→.668° (better), conditionalXY 16.06→14.57 | UNIVERSAL C_rs benefit **FALSIFIED**; geometry-dependent effect suspected |
| C09 | Current Full RF-trained signed mean damages Native LoS | L2 LoS M0 heading .243→1.517°, XY 2.72→21.76cm; M45 heading .158→1.129°, XY 4.35→11.70cm | NEGATIVE TRANSFER CONFIRMED, must have no-harm guard |
| C10 | Original LUT theta=0 azimuth collapse creates artificial near-pole s/H | R5B pose706 LoS error .877616→.001226, theta<2° RMSE .454941→.001143, source trig collapse | ROOTCAUSE SUPPORTED; candidate only, no FFD source rebuild |
| C11 | Candidate theta0 source fix changes only 6/48 original R2 filter pairs, but significant P covariance effect | R0 Full M0 B0 Pose NEES 2591→356.7; POWER R2 unchanged | SOURCE-SPECIFIC OBSERVATION; not Full RF covariance solution |
| C12 | Off-pole LUT remains imperfect | 500-point F01 interpolation gate max .023972 > .01 (FAIL), remaining LoS residual tail max .046651 | **UNRESOLVED SOURCE QUALITY GATE** |

## 2. 미해결 원인 가설 — 다음 실험에서 반드시 반증 가능한 형태로

| H-ID | 현재 지위 | Null/counter-explanation | 직접 실행에 필요한 반증 실험 | 해당 F 단계 |
|---|---|---|---|---|
| U01 Zero-bias leakage | B0 false Bias inference 관찰, 자세한 인과 기여 미확정 | Bias는 Range-only/Gate/프로세스 cross-cov만으로도 상당 부분 설명될 수 있음 | 같은 x-/P-/packet/Gate에서 δb=K_brνr+K_bsνs, zero-s/zero-r/s-only/R-only, clean vs Full 통제 | F2 |
| U02 Signed μs 본원 기여 | Exp2 μs-only M0 Heading 3.582°, Full 1.991°, 추가 결합 필요 | μs 단독은 충분하지 않고 μr·Gate 변화가 주효할 수 있음 | μs/μr/Crs 2×2 요인 + same prior/NIS + natural recursion, anchor/mount holdouts | F2, F6 |
| U03 Power q의 state confounding | q–거리 강상관과 LoS damage 확인 | 이득이 MP signature가 아니라 특정 거리/패턴의 평균 식별 때문 | $\Delta q=q-\mathbb E[q_\mathrm{LoS}|\hat x^-,m,a]$, distance/pattern residual, gain-shift/mount controls | F3, F5 |
| U04 Two-port polarimetric information is essential | s has Hsψ, single anchor heading observed in LoS, but pure no-s in comparable Full RF not complete | q+range+DR만으로 대부분 개선될 수 있음 | DR4, Range-only, s-only S4, q+Range(no s), matched gate/filter/seed; rank/information | F2, F6 |
| U05 Conditional C_rs role is physical & geometry-specific | M0 positive, M45 removal better on R2 | Fitted Crs captures corridor-specific artifacts or q-feature confounding | same μ,Vr,Vs covariance swaps, anchor/mount/material reflectors, sign symmetry/port swapping | F2,F3,F6 |
| U06 'LoS-safe POWER' feasible | Old Full μ catastrophically harms Native LoS | even good q-quality AUC may not identify LoS under constructive MP and geometry | clean-first baselines, FP/CIR q-excess or latent regime, calibrated risk, natural recursive and LoS 0 correction control | F3,F6 |
| U07 Temporal colored noise sole driver of pose overconfidence | Range residual autocorr .79–.94 and oracle reduction seen | fixed geometry/mean/trajectory deterministic bias or gate/linearization/process model mismatch dominates | paired scene revisit/different RF realization, after fixed site/geometry detrending, innovation whiteness, shift-placebo, batch-vs-AR | F4,F6 |
| U08 Posterior report PSD floor can fix NEES without filter degradation | P-only inflation sometimes increases coverage; no independent trained floor | mean tracking error remains and arbitrary P inflation gives nominal coverage by dilution | learn floor ONLY separate train scenes, reported-P-only vs internal, heldout calibration/sharpness/scoring | F4,F7 |
| U09 G4 pointwise NLL advantage arises from bad gain spikes | G4 NLL −1.7038 vs POWER −1.5898; M45 Heading G4 1.133 vs POWER .727; M0 G4 1.845 < POWER 1.991 | Gate/time-sequence/mean structure/mount shift rather than spikes | fixed prior, compare eigen R/K/NIS/gates, G4/POWER mean↔cov swap, FP detector stratification | F5 |
| U10 FP single tap robust enough for hardware | Original 30% stronger RX tap, first-edge threshold; gain scale sensitivity | tap switching, group delay, port gain drift and AGC invalidate q/s | 20/30/40 threshold, 1/3/5-tap power/window, gain ±3/6dB, delay/port imbalance, LOS/Full | F5,F6 |
| U11 FFD-bank pole regeneration matches hotfix and analytic Jacobian | theta0 candidate observation and R2 canary PASS | 0° tensor/gauge ambiguity and off-pole F01 interpolation could invalidate physical extrapolation | direct complex FFD synthesis at epsilon theta and Cartesian basis, seam/pole finite differences & native channel | F0 |
| U12 P2/N4B corrupted by wrong polar labels | R5 five old LoS labels huge and source heldout calibration tail | rarity means global POWER coefficients might barely change | same train fold & seeds OLD vs SOURCE-CORRECTED labels, paired 9519 packet OOF, no R2 retuning | F1 |
| U13 True independent Full RF generalization | 1 corridor and R4/R5 same scene/M0 training | model memorizes existing corridor geometry and LoS/Mount0 mean | independent scenes/materials, opposite direction, unseen Mount/anchor, new RF seeds; scene clustered interval | F6 |
| U14 A formally normalized measurement likelihood is feasible | p(e|q) fitted same packet q does not prove p(r,s|x) normalization | empirical q-conditioned correction only decision heuristic | compare normalized p(q,r,s|x) and strictly specified conditional model vs heuristic protected update, heldout proper scores | F3,F7 |

## 3. 경쟁 원인과 Negative Controls를 빼먹지 않기

### State and covariance
- Pose $\mathrm{NEES}_3=\mathrm{NEES}_\psi+\mathrm{NEES}_{XY|\psi}$ 정확한 identity; 주변 XY NEES와 Heading NEES는 일반적으로 더할 수 없음.
- $P_{XY|\psi}=P_{XX}-P_{X\psi}P_{\psi\psi}^{-1}P_{\psi X}$. 가장 좁은 eigen-axis 위치오차 및 signed error를 점추정 분산과 분리.
- Bias의 마지막 시점 추정값, 시계열 signed mean, Bias RMSE, 상태 cross covariance, Bias95을 별개로 출력. Zero true Bias B0에서 측정된 .08862°/s는 **RMSE**, 특정 양의 고정 Bias가 아님.
- Nominal NEES means: 1/2/3/4 for Heading/conditionalXY/Pose/all4; chi-square 95% coverage quantiles are distribution checks, time-frame 829 count를 독립 샘플 829개로 가정한 confidence interval 금지.

### Physics and measurement
- $q$와 $s$는 같은 FP tap 두 LP port에서 결정, 독립 계측치 아님.
- RF Range 관측에는 고정된 신호처리 bias $B_\mathrm{OLD}\approx−0.53159839$m가 LoS h에 포함. R0=diag(.0068578637,.0081)이나 이는 실험적 설정이지 실제 hardware thermal floor 아니므로 clamp가 문헌상 물리법칙이라는 주장 금지.
- FFD pole correction은 코드 AST/shape/periodicity/centered finite-diff와 직접 complex LoS를 모두 확인; original NPY byte-identical 보존.
- Full/LoS 같은 pose/time/anchor/mount/tap 조건 대응; q-from-Full을 Native LoS 성능 점검에 가져오는 누수 금지.
- Distinct *motion noise seed* without regenerated Full RF complex channel is independent sensor noise but **NOT** independent multipath realization.

## 4. 어떤 결과가 나오면 주장을 수정하는가?

- F2 Range-only/no-s가 기존 Full 모델 효과 대부분 재현 → Dual-LP marginal Heading contribution 재측정, 제목 강도 축소.
- F2 C_rs 제거가 모든 새 장면에서 비열등 → correlation term은 선택적 보정이며 핵심 필수 mechanism에서 철회.
- F3 Normal LoS no-harm 실패 → 논문은 Full RF case study로만 제한; 방법을 범용 deployable estimator로 명명 금지.
- F4 Scene-level heldout Pose95가 명목 95%에 접근하지 못함 → "posterior covariance consistency" claim 금지, 문제제기 결과만 논문에 보존.
- F6 Mount45/새 Anchor에서 성능 반전 → training geometry/domain shift 한계를 본문에 공개, scene-specific 보정 전략 또는 기하 조건부 모델 필요.
- F0 원 FFD-bank direct response가 theta0 candidate와 안 맞음 → candidate hotfix REJECT, 정확한 global Cartesian basis에서 새 관측모델 구현.
