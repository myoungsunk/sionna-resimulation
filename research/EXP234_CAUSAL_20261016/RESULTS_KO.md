# Exp1–Exp4 R5 재검증 결과 (2026-10-16)

**최종 판정:** Exp1 기존 CSV 분석 PASS, Exp2 6-way+factorial Gate-고정/자연 Gate 재귀 실험 PASS, Exp3 GT Oracle 저주파 Range 개입 실험 PASS (전체 정상화 가설 미충족), Exp4 Native LoS POWER 전이 재귀 PASS (**현재 모델의 LoS 보호 실패 확정**). R4/R5 4-state 실제 동적 재귀 일반화는 입력부족으로 BLOCKED_INPUT.

## 코드·입력·독립 재감사

- 원본 실행 코드/실험: [성공 GitHub Actions Run 38852849031](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38852849031) (source commit d6b72ab837b1c575563c9bbbd170e65689df24c7). [원시 448-arm artifact 12025759278](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38852849031/artifacts/12025759278), ZIP SHA256 **e921b5b19460850be11a3d0fb92f38d09105b1dcac8db7a24b5d9fb0f16666ea**.
- 원본 N4-B / N4-C / R2 / RF SHA와 3D FFD LUT Git blobs를 source audit에서 확인, N4-C SR4 whitening 수학 테스트 후 계산. 실패한 첫 실행은 원시 Exp3 ZERO residual ACF의 undefined를 JSON NaN으로 저장하는 **보고서 형식 문제**; numerical results invalid 판정 및 소스 교정 후 전 단계 source audit부터 다시 성공.
- Exp2 288 재귀 arms +72 동일 prior counterfactual steps, 원 R0/POWER state/P/Gate 원본 parity 32건.
- Exp3 64 GT oracle recursions + 원본 POWER state/P/Gate parity 8건.
- Exp4 96 actual Native LoS recursions + 원 R0 state/P/Gate parity 16건, 실제 Native LoS power P1/P2에서 q 계산하여 정확히 원 s 확인.
- **별도 독립 Python 검증**은 성공 ZIP의 모든 448개 posterior 979프레임 추적을 원래 GT와 직접 비교해 Heading, Bias, XY RMSE, Pose NEES/coverage, 조건부 XY NEES를 다시 계산. 최대 수치차 **9.1e-13(NEES)**, LoS q 차 <1e-15, s 차 정확히 0. 링크된 결과를 외삽 '16회 독립 trial'로 주장하지 않음.

## Exp1 — Range Jacobian과 조건부 XY 좁은 축 정렬

기존 POWER 15,664개 시점 원 CSV + N4-B OOF error에서 GTruth Range 잔차 \`u_r = z_r−h_r(x_GT)−μ_r(q)\`, 좁은 축 Schur-complement \`P_xy|ψ\`, \`e_xy|ψ\`, eigen-axis 투영을 직접 계산.

**Mount45 L2 J4, t=95–135s**:
- mean \`abs(H_r,xy · v_narrow)=0.9840\` (전체 평가 0.8628)
- mean signed \`u_r=+5.471cm\` (전체 +3.256cm)
- mean signed narrow-axis position error \`+6.485cm\` (전체 +2.483cm)
- conditional XY NEES **32.968** (전체 **16.058**)
- raw u_r lag1 autocorr .793, lag25(5s) **−.221** (동일 장면 위치/시간 상관 존재)
- trailing 5s LPF vs narrow axis error Pearson r .435; trailing 10s Pearson .177.

**기전 해석 제한:** Range LOS direction과 오염된 추정기의 좁은 axis는 이 특정 시점에서 강하게 정렬하지만, 이것만으로 시간상관 Range bias의 sole cause 또는 수십 초간 일정한 bias를 증명하지 않음. GT와 전체 데이터로 계산한 실험, 온라인 상태 추정에 입력하지 않음.

## Exp2 — Gate 고정 6-way (+Crs-제거 외 3 factorial) 실제 재귀

동일 frozen POWER Gate mask에 6개 비교군 적용; 아래 L2/J4 Full RF. 원본 POWER의 \`s\`, raw Range, q, FFD, 운동 Q, Sensor-v2, pre/post sensor 99% NIS gate 임계는 고정하고 means and 2×2 R만 ablate. 고정 Mask는 offline counterfactual, 자연 Gate는 별도 144arms.

| 비교 | M0 Heading RMSE ° | M45 Heading RMSE ° | M45 XY RMSE cm | M45 CondXY NEES |
|---|---:|---:|---:|---:|
| R0, fixed POWER gate | 5.415 | 1.529 | 22.71 | 148.74 |
| μr only, R0 | 5.131 | 1.486 | 19.79 | 47.29 |
| μs only, R0 | 3.582 | .978 | 16.67 | 140.89 |
| μr+μs, R0 | 3.223 | .982 | 13.78 | 43.29 |
| POWER cov only | 4.248 | .962 | 13.22 | 53.53 |
| **POWER full** | **1.991** | **.727** | **7.86** | 16.06 |
| Full means and Vr,Vs, **Crs=0** | 2.313 | **.668** | 8.12 | **14.57** |

\`μr\`가 Mount45에서 위치 측위에 해롭다는 가설은 이 시뮬레이션에서 반증: POWER full에서 μr를 빼면 M45 XY 7.86→11.82cm 악화. 그러나 \`Crs>0\`은 모든 마운트에서 이득이라는 주장을 반증: 같은 Gate에 Crs 제거시 M0 Heading 악화(1.991→2.313), M45 Heading 개선(.727→.668), M45 CondXY NEES 개선(16.06→14.57). 2 solvers × 4 biases 조건에서 Heading 결과 방향 일관: M0 full 8/8 우세, M45 full 0/8 우세.

고정 Gate R0와 원본 R0 natural은 다른 정책: L2 M0 5.415 vs 7.521°, M45 1.529 vs .848°. Gate 선택도 Mount 의존 원인. POWER 모델의 Full 이득을 단순 Gate 완화로 환원할 수 없음.

## Exp3 — GT 오라클 저주파 Range 잔차 제거 (Full RF, 실제 재귀)

\`u_r=z_r−h_r(x_GT)−μr(q)\`를 **오프라인 GT**에서 구한 뒤 5s/10s trailing 또는 centered LPF만 \`z_r\`에서 제거. R(q), μ(q), gyro/wheel Q, LUT, NIS gate criterion 동일. 원본 POWER/GT oracle 전체 잔차제거/시간 이동한 5s placebo/전체 평균 제거 대조. 새 state, Jacobian, posterior covariance는 실제 재귀로 달라짐; \`P_k^+\` 불변 실험이 아님.

| L2 M45 J4 | Full-path condXY NEES | 95–135s condXY NEES | XY RMSE cm | Heading RMSE |
|---|---:|---:|---:|---:|
| Original | 16.058 | 32.968 | **7.86** | **.727°** |
| 5s trailing oracle | 13.391 | 4.294 | 14.46 | .913° |
| 10s trailing oracle | 14.679 | 4.900 | 16.98 | 1.097° |
| 10s centered future oracle | 8.554 | **2.459** | 10.09 | .758° |
| 5s LPF shifted 25s placebo | 18.147 | 11.870 | 12.40 | 1.165° |
| Full original residual removed oracle | 5.174 | **2.042** | 9.22 | .804° |

**수정해야 할 Claim:** 95–135s의 극단적 좁은 XY 과신에는 시간 정렬된 Range 잔차의 큰 기여가 강하게 지지된다. 그러나 전체 경로에서 NEES 2에 도달하지 않고 Heading/XY 점추정이 악화되어 'P는 이미 올바르고 3cm floor만 외부 보고하면 완벽히 해결' 가설은 미지지. future-centred 및 GT이용 trailing 모두 실제 온라인 구현 불가능. 독립 RF scene 일반화 불가.

## Exp4 — Full-trained POWER의 정상 Native LoS 안전성 (원본 포트 q)

R2 Native LoS 첫탭 **정말 그 포트의** \`power[N,2]\`에서 q=log10(P1+P2) 계산, s 재현 정확; original R4+R5 M0 train-only R2 fold μ(q), R(q) 계수·cutpoints를 원본 N4B OOF 예측에서 기계정밀도로 재구성. LoS 데이터에 Full q를 사용하지 않음.

| Full-trained model on Native LoS, L2 J4 | M0 Heading RMSE ° | M0 XY cm | M0 Pose95 | M45 Heading ° | M45 XY cm | M45 Pose95 |
|---|---:|---:|---:|---:|---:|---:|
| Clean baseline R0 | **.243** | **2.72** | **96.6%** | **.158** | 4.35 | 65.0% |
| **Full POWER_JOINT** | 1.517 | 21.76 | 8.4% | 1.129 | 11.70 | 7.6% |
| Full mean correction only | 1.970 | 22.02 | 6.2% | 1.689 | 14.50 | 6.0% |
| Full covariance only | .406 | 4.74 | 100.0% | **.150** | **3.28** | **94.9%** |

**Full POWER vs R0:** 두 Mount × B0/L0/L1/L2 × J4/SR4 = **16/16에서 Heading RMSE, XY RMSE, Pose95 전부 악화**. Mean-only에서도 동일 16/16 악화. **Native LoS safeguard FAIL**. 본 모델을 물리적으로 검증된 universal covariance-calibrated estimator 또는 LoS/Full 가변 공동 likelihood라고 주장하면 안 됨.

## Exp4 R4/R5 및 독립 Full RF 장면: 입력 대기 / 명시적 시뮬레이션 사양

원본 R4/R5 P2 ONE_STEP에 t_s/pose_id/Range/s/Native power가 일부 존재하나 시간-동기된 검증 Wheel/Gyro 4-state controls (및 생성 provenance)가 완결되지 않았다. LoS LUT를 야스윕하는 방식으로 Full RF 또는 4-state 동적 재귀 일반화를 꾸며내지 않음. 

추가 시뮬레이션 요청: R4/R5 동시간 \`gt_pose_xyyaw[N,3]\`, \`t_s\`, \`pose_id\`, \`ds_odom_m\`, \`dtheta_gyro_rad\`, \`dt_s\`, \`true_bias_rad_s\` scoring-only, 양 포트의 \`P1,P2,fp_tap\`, Full/Native LoS \`z_r,z_s\` + 원 Full complex \`H[N,257,2,2]\`, Gyro/Wheel sensor-v2 config/seed, Anchor/Mount/FFD revision and SHA256. 새 scene minimum Train/Validation/Test distinct multipath RF layouts, multiple independent RF and motion seeds, unique routes/anchor geometries. 원 R4/R5와 새 장면의 최종 성능/캘리브레이션을 혼동하지 않는다. 별도 전체 상세 사양서는 대화 첨부 Markdown 파일 참조.

**종합:** Signed mean 보정은 한 복도의 Full RF에서는 매우 유익하지만 Native LoS에는 매우 위험하다. \`Crs\`의 개선효과는 Mount 종속. 특정 95–135s의 Range 누적잔차를 oracle로 제거하면 과신이 크게 해소되나, 전체 필터 covariance 또는 점추정 정확도가 자동으로 정상화되지 않는다. 동결 기준선 POWER 유지, 새 LoS/MP 분리 및 geometry-conditioned signed bias 모델과 독립 장면 실험이 필요.
