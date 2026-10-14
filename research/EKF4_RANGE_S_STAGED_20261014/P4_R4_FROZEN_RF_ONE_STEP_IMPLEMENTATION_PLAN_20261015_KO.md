# EKF4 R4 P4 구현·실행 계약 — Frozen RF 동일 prior One-Step 융합 (2026-10-15)

> **계획 문서 전용:** 이번 커밋에서는 P4 수치코드·RF·LUT·P2/P3 source를 수정하거나 P4 실험을 실행하지 않는다. 현재 \`P4=NOT_RUN_ON_R4_P3_BRANCH\`, \`scientific_PASS=false\`.
>
> **기준 HEAD:** \`research/ekf4-r4-p3-frozen-rf-20261014\` commit \`71e3cb21881664f24635f42f01b1c4a9fd5e138a\`. **실제 P3 검증 소스**는 \`b244c2e399d9d105972a09ce35a2516c71f7e514\`; 이후 \`71e3cb2\`는 결과 문서 추가. P3 Run [38583064582](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38583064582), artifact [11904127597](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38583064582/artifacts/11904127597), ZIP SHA256 \`de40cbbef664b064b6c24ac679ffb7238738ceab36995ee4fa156bb99699428b\`. **원 RF 입력** EKF3 Run [38331588521](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38331588521), artifact \`11782748118\`, ZIP SHA256 \`88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63\`.

## 1. 질문·완료 범위

**P4 핵심 질문:** 원본 DR-only 3-state predicted prior \`(mu3,P3)\`를 매 시점 동일하게 복제하고 원본 LoS/Full \`z=[r_raw,s]\`를 각 한 번 사용했을 때, (a) joint vs frozen-linear sequential의 수학적 일치, (b) range-first 비선형 재선형화의 추가 변화, (c) 고정 original prior에서 수렴한 local MAP가 EKF와 어떻게 다른지를 분해한다.

- **P4는 one-step counterfactual**: 각 다음 시점의 prior는 다시 동일한 archived DR-only prior에서 시작한다. One-step posterior를 다음 시점의 motion prior로 누적 전달하지 않는다. 따라서 gyro bias 개선의 최종 재귀 효과, 종단 RMSE 또는 posterior multimodal reference를 주장하지 않는다.
- **P4의 1차 기술 가설(H0):** 동일 선형화·동일 Gaussian likelihood·동일 사전분포에서 Joint EKF = R-first frozen sequential = s-first frozen sequential (숫자 오차 이하), 차이 자체가 실험 성능 이득이 아님.
- **P4의 2차 진단 질문(H1):** r 갱신 뒤 s Jacobian을 재계산하거나 local MAP를 사용하면 LoS/Full에서 상태·covariance·signed error가 얼마나 달라지는가? **개선 방향은 미리 가정하지 않는다.**
- **P4가 검증하지 않는 것:** R0 likelihood의 물리적 calibration, 새로운 RF scene 일반화, 실제 다봉 posterior/G3 위치적분 TV, 4-state 재귀 gyro bias 추정의 효과, Full 다중경로가 DR보다 항상 좋은지 여부.

## 2. 기존 증거 감사: 재사용과 한계

1. **P3** 7 case × LoS/Full = 14 trace, 전체 14,502 시점에서 canonical \`[range,s]\`의 h/H, R, innovation, S/K/NIS 및 gate parity PASS. 39 P0 frozen assets/7 case/3 Tnone routes SHA 및 pose match는 원 변경 없는 증거로 재사용한다. **P4 새 소스가 P3 과거 Git SHA와 다르다는 이유만으로 무효 처리하지 않는다**: P3 당시 저장된 파일별 SHA256와 현 P3 파일 hash/원 archived input ZIP을 대조한 후 \`REUSED_VERIFIED\`를 발행한다. P3 파일 변경 시 관련 parity 다시 실행해야 한다.
2. 이전 P4 [Run 38562745996](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38562745996)는 14 trace에 대한 archived 3-state fixed linearization joint parity를 PASS했다. **새 R4 4-state, range-first nonlinear, MAP 성공을 증명하지는 않는다.**
3. 이전 P4 [Run 38557692205](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38557692205), source \`9826b2cc09863728ca580e2aac1ea7774d6f1919\`: **R2_aA_m0/LoS·Full 각각 t>=30의 12개 시점**. Joint=frozen sequential parity LoS \`8.8818e−16\`, Full \`2.2204e−16\`; 이전 solver는 LoS t=30.0,180.4 및 Full t=30.0,180.4에서 local MAP 미수렴(각 채널 2). **이전 P4가 독립 4-state DR prediction으로 prior를 만든 반면 본 P4는 P3 archived 3-state prior를 block-augment한다**. 따라서 같은 (case,time)인 것만으로 byte-identical 실패 fixture라고 부르지 않는다. 이전 \`mu,P,z,R\`를 정확히 회수·검증한 경우에만 별도 \`EXACT_OLD_FIXTURE\`, 아니면 \`MATCHED_TIME_DIAGNOSTIC\`으로 명기한다.
4. 기존 EKF3 [one-step Run 38331588521](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38331588521)에서는 같은 DR prior 대비 Full joint RF C가 악화된 사례가 있으므로, Full 악화를 hidden failure로 가리지 않고 별도 보고한다. P4를 성능 좋아 보이는 case만 선택하여 PASS시키지 않는다.

## 3. 불변 입력·상태·관측 계약

- frozen case 7: \`R2_aA_m0\`, \`R2_aA_m45\`, \`R2_aB_m0\`, \`R4_aA_m0\`, \`R4_aB_m0\`, \`R5_aA_m0\`, \`R5_aB_m0\`; 각각 LoS/Full \`noise_pair, seed0\`. 전체 14,502 시점; \`t>=30s\` 평가창 LoS 6,201 + Full 6,201 = 12,402 시점. **총 1 corridor/기하학적으로 연관된 7 case**; 시간·seed를 독립 환경으로 세지 않는다.
- 매 시점 \`mu3=trace.prior_x[k]\`, \`P3=trace.prior_P[k]\` (world \`[x_m,y_m,yaw_rad]\`). \`mu4=[mu3, b_0=0 rad/s]\`, \`P4=blockdiag(P3, sigma_b²)\`, \`sigma_b=(0.1°/s)*π/180\` (따라서 variance 단위 \`rad²/s²\`). \`P4_{pose,b}=0\`을 기본 zero-cross prior로 **명시**. \`mu4[:3],P4[:3,:3]\` 원본 일치 확인. P3 archived DR prior는 실제 4-state bias를 전파한 공분산이 아니다.
- 채널 관측 \`z=[r_raw_m,s]\`, \`h(x)=[rho_xyz(x)+B_old,s_frozen_LUT(x,y,yaw)]\`, \`B_old=−0.5315983906250129m\`, \`H_4∈R^{2×4}\`, \`H_4[:,3]=0\`, \`R0=diag(0.0068578637m²,0.0081)\` ([r,s]). 실제 \`S=H P H^T+R\`의 비대각 성분은 유지한다. \`R_rs=0\`은 **미검증 가우시안 독립성 R0 control**.
- 기존 joint gate \`χ²_2(0.99)=9.210340371976184\`. **모든 arm은 업데이트 전 동일 3/4state prior에서 계산한 단일 common NIS/mask** 사용. \`detected=false\`이면 missing, \`NIS>gate\`이면 rejected: 전 방법 동일 prior를 그대로 반환. 경로별 gate가 달라지는 실험은 부가 연구로 분리; 성능이 좋아지는 마스크를 truth로 고르지 않는다. P3 원본 기준 **Full 316건 rejected, LoS 0건**, t≥30 창에서는 **Full 304건 rejected, LoS 0건**을 사전 parity 대조. 전체 gate-eligible \`14,502−316=14,186\`.
- \`truth_for_offline_scoring_only\`는 추정기 입력 \`FrozenRFTrace\`/모델로 넘기지 않는다. inference를 끝내고 원본 출력 저장·해시 생성 이후 **별도 scoring reader**에서만 사용한다. 원 자료 legacy-Euler vs SE2 source mismatch 유지.
- 원 \`core.py\` R4 stable-objective MAP, \`max_iter=80\`, \`gradient_tol=1e−8\`(prior-whitened coordinates) 변경 불가; original P2/P3 pass receipt 보존. LUT, H, RF noise, bias prior, Q/R, offset, tag height, anchor·mount, angle wrapping은 고정한다.

## 4. 수학적 알고리즘 비교군

먼저 \`NIS=(z-h(mu))^T(HPH^T+R)^{-1}(z-h(mu))\`로 공통 gate를 고정한다. 성공 시 모든 arm은 **동일한 (mu,P,z,R)**를 독립 복제받는다. 검사에서는 angle seam 차이를 wrap한다.

| ID | 모델 | 목적과 핵심 구현 |
|---|---|---|
| D0 | DR-only frozen prior | RF 미사용. 기준 상태 \`mu3,P3\`, 4-state 표시 때 pose 동등성만 사용 |
| J3 | 3-state Joint EKF | 이전 archived original joint C와 상태/공분산·gate를 비교. Joseph form |
| J4 | 4-state Joint EKF | \`mu4,P4\`, H 마지막 bias 열=0. J3와 pose 및 pose-cov가 같아야 함 |
| SF4-R | 4-state Range→s **frozen linearization** | \`h0,H0,R0\`를 원 \`mu4\`에서 단 한 번 평가. posterior range correction을 s innovation에 반영하되 \`H_s\` 재계산 금지. J4와 정확한 Gaussian posterior parity |
| SF4-S | 4-state s→Range frozen linearization | 순서 불변성 음성 대조. 실제 covariance \`R_rs≠0\` synthetic SPD 테스트 시 정확 conditional whitening 사용 |
| SR4 | 4-state Range→s **relinearized** | 최초 original prior의 Range만 한 번 업데이트, 그 posterior에서 \`s_LUT,H_s\` 재계산 후 s만 한 번 업데이트. R0=diagonal이므로 적절. Range 관측 재사용 금지 |
| M4-R | 4-state local joint MAP, Range-first initialization | Range-only는 **초기점 생성**에만 사용. 최종 objective는 원 prior + 원 z_r,z_s 각각 한 번. R4 solver의 80/1e−8 원 수치 계약 유지 |
| M4-P | 4-state local joint MAP, prior initialization | M4-R과 **동일** 목적함수의 초기값 차이만 대조. mode 차이·chart discontinuity 기록, \`solver.success\`만으로 PASS 금지 |

**MAP 비용(원래 고정 Gaussian prior):**

\`J(x)=1/2 (x−mu)^T P^{-1}(x−mu)+1/2(z−h(x))^T R^{-1}(z−h(x))\`,

\`r\`와 \`s\`는 각 **한 번**. MAP의 최종 \`P\`는 local GN Hessian 기반 근사이지 multi-mode posterior covariance가 아니다. MAP만 반복 중 **prior 자체를 갱신하지 않는다**. M4-R과 SR4는 이름이 비슷하지만 수학적으로 다른 모델이다.

**단일 시점 4-state Bias 불변성(필수):** R0 관측에서 \`H_b=0\`, \`P_{pose,b}=0\`이면 \`K_b=0\`. 따라서 J4 Bias mean/cross-cov 변화 0; **pose mean/covariance J3=J4**. 고정 prior MAP 목적함수도 b에 대해 분리되어 M4-R/M4-P의 stationary b는 원래 0이다. 이 테스트가 실패하면 코딩 오류(HARD). Bias가 이 P4에서 학습되지 않는 것은 과학적 반증이 아니라 설계의 정확한 한계.

**별도 수학 대조:** 인위적으로 작은 비영 pose–bias 교차항을 갖는 SPD 4×4 prior를 만들면 \`K_b=P_{b,pose}H_{pose}^T S^{-1}\`로 bias 간접 갱신이 가능함을 확인한다. **실제 frozen RF P4 데이터에 삽입하여 효과 측정하지 않는다**. 별도 P6 재귀 prior 검증의 참고용이다.

## 5. 실행 전 코드 감사와 단계별 실행 (순차 gate)

| 단계 | 구현·실행 범위 | 통과/중단 규칙 |
|---|---|---|
| **P4-A. Audit first** | exact SHA sparse checkout, prior P3 \`P3_ADAPTER_INDEX.json/P3_FINAL.json\` source SHA 및 원 11904127597 ZIP SHA, original 11782748118 ZIP·LUT SHA, P2 R4 solver fingerprint, code/AST·truth flow·unit/order/gate/cost once, output manifest·실패전파. \`pytest\` 이전에 실행 | audit \`GO\`, fatal 0. P3의 historical \`GITHUB_SHA\`를 P4 \`GITHUB_SHA\`와 잘못 비교하지 않음. SHA mismatch면 해당 실행 HARD BLOCK |
| **P4-B. Math & stored-reference regression** | 독립 선형 Gaussian 수식 (3/4state, correlated R positive definite), Joseph covariance, exact frozen sequential R→s/s→R vs joint, posterior local chart, likelihood count, rejection no change, bias zero-cross 불변, negative controls | 최대 wrapped pose diff ≤1e−9 (m/rad 원소별), covariance max diff ≤1e−9; P3 14 trace archived 3-state original C 결과 재현. NaN inactive scalar row를 강제 finite로 취급하지 않음 |
| **P4-C. Nonlinear canary + historical failures** | 7case×2채널 각 시작/\`t=30\` 직후/중앙/마지막 및 Full gate 극단, LUT knot 근방, R2_aA_m0 t=30/180.4 **matched-time**. Joint/Seq/MAP 각 branch의 NIS, J, stationarity, step history·mode 차이 검사 | 진짜 MAP 미수렴은 해당 estimator-case \`CASE_RESULT_INVALID_NUMERICAL\`, 다른 J3/J4/SF/SR 비교까지 전면 중단하지 않음. 4개 이전 실패가 새 R4로 해결됐다고 먼저 주장하지 않음 |
| **P4-D. 전체 fixed-linear 14,502시점** | 모든 channel/pose에서 common gate 재생(316 Full reject/LoS 0), D0/J3/J4/SF4-R/SF4-S/SR4; prior memory no carryover. gated/ungated 후보를 분리 저장, accepted 14,186 프레임 별 trace·cov·mask 출력 | J3 vs original one-step, J3=J4 pose, J4=SF4-R=SF4-S 판정, NaN/PSD·finite 검사. Joint/seq는 strict parity gate |
| **P4-E. MAP 확장** | C단계에서 모든 관련 MAP numerical regressions 검증 후 M4-P/M4-R. 전체 accepted 14,186을 모델별 분모로 저장; 완주한 frame만으로 주장하지 않고 failed counts 보존. 필요 시 stage별 checkpoint/resume 가능하나 고정 source/input identity 준수 | stationarity \`||∇_y J||∞≤1e−8\`, \`iter≤80\`, independent J/gradient/covariance re-eval. 실패에서는 last iterate/raw mu,P,z,R, previous/next step, \`s\` LUT cell/gradient, accepted/rejected fractions 보존. Retry는 별도 감사·수정 커밋 |
| **P4-F. Offline scoring 및 report** | 모든 추정 출력 완료·고정 후 read-only scorer에서 truth 읽기; \`t>=30\` per-case/channel/alg RMSE 위치·heading, NEES, heading95/pose95, gate rate, signed range residual·\`s\` residual, delta J·cov eigenvalues, mode branch·MAP failure count. LoS/Full 공통 mask 5,897개/채널 결과도 별도로 표기 | one-step descriptive 결과와 technical/physics/generalization verdict 분리. 시간 샘플을 독립 bootstrap unit으로 취급하지 않음 |

**실행 예산:** P4-B 작은 선형 fixture→P4-C canary→P4-D 전체 빠른 선형 비교→P4-E 고비용 MAP→P4-F offline scoring. 전 14,502 점에서 MAP가 실패한다면 해당 실패를 남기되 유효 EKF/순차 분석을 끝내고 수치 진단으로 분기한다. 무조건 전체 재시도 루프나 시간/리소스 예산에 맞추기 위한 수렴 기준 완화는 금지.

## 6. MAP failure에 대한 독립 수치 진단 (solver 변경 전 감사 필수)

기존 소수 사례 t=30/180.4의 실패가 R4에서 재현된다면 먼저 고정 \`mu,P,z,R,case,pose_id\` 저장, 정확한 prior와 solver 버전 대조 후 아래를 조사한다.

1. 원래 canonical LUT trilinear 보간에서 **phi/theta cell 경계와 yaw periodic seam** 근접성을 계산. cell 내부 해석 \`H\`와 finite difference를 비교하고 knot를 가로지르는 중앙차분과 one-sided derivative를 구분. 매끄러움/미분 불연속이 있는 경우 "진짜 smooth stationary gradient" 통과만으로 성공을 단정하지 않는다.
2. \`gradient_inf\` 변화, GN 방향 \`gᵀd\`, stable residual objective \`ΔJ\`, float64 cost subtraction, true-gradient integral, line-search fraction, candidate objective at *same frozen prior*를 분리. Need 시에 80자리 고정 입력 reference와 정확 Hessian 국소 검산; 기본 P4 모든 step에 고정밀 불필요.
3. \`range_first\` vs prior-init, exact scipy reference의 **독립 J/gradient**(SciPy \`success\`는 주장 근거 아님), 동일/다른 local mode, nonfinite or outside chart인지 구분.
4. 솔버 결함은 \`CASE_RESULT_INVALID_NUMERICAL\`, LUT 불연속에 의한 최적화 기하학은 수치 모형 한계, RF 악화는 실제 모델미스매치로 구분. 어떤 결함도 \`gradient_tol\` 상향, \(R\) 임의 증가, truth 기반 gate 변경, 가짜 fallback으로 덮지 않는다.

## 7. 별도 공분산·통계·물리 이슈

- fixed affine Jacobian에서 joint/sequential local Gaussian covariance 동등성이 **기술 PASS**. MAP local GN covariance가 더 작거나 크다는 사실만으로 물리 coverage 우위를 주장하지 않는다.
- R0 \`R_sr=0\`이나 Full RF residual에는 관측 모델 bias 및 시간 상관이 있을 수 있으며, P4는 교정 수행 단계가 아니다. LoS/Full 성능 차이가 발생하면 range signed bias/heading 분해를 **결과로 보고**, LoS에 맞춰 Full 수용 mask나 분산을 조정하지 않는다.
- \`P4\`의 one-step trace는 물리적으로 같은 corridor/seed0의 반복 계산이다. case/route grouping과 통계적 독립을 구분한다. 14,186 accepted frame을 14,186 independent RF scenes로 과장 금지.
- P5/G3 position-integrated posterior numerical TV 기존 \`0.387065 > 0.001\` 미수렴 기록을 유지. P4의 local MAP 수렴이 P5 레퍼런스 성공을 뜻하지 않음.
- P6는 별개 recursive input/motion/time model 검증이 요구됨. P4 technical parity 또는 MAP one-step 원점근방 성능만으로 \`scientific_PASS=true\` 불가.

## 8. 파일 구성·P5/P6 인계

**새 P4 branch 예정:** \`research/ekf4-r4-p4-frozen-onestep-20261015\`를 본 계획 HEAD에서 생성. 원 \`core.py\`, P3 frozen input/adapter, \`P2_SPEC.json\`/LUT·원 NPZ/H 영구 보존.

| 예정 파일 | 목적·산출물 |
|---|---|
| \`p4_pre_run_audit.py\` | P3 receipt 재사용 조건 + P4 exact-source, P2 solver, workflow ordering 및 truth isolation \`P4_PRE_AUDIT.json\` |
| \`p4_frozen_cases.py\` | 원 14 trace case/pose enumeration, same-prior \`mu3/P3\`→\`mu4/P4\`, immutable mask \`P4_INPUT_INDEX.json\` |
| \`p4_one_step_models.py\` | J3, J4, SF4-R/S, SR4, M4-P/R 단일 시점 결과·공분산 및 detailed numerical status |
| \`test_p4_math.py\` | correlated-R frozen sequential/joint/4state, zero-cross bias, negative controls/PD, no hidden fallback |
| \`p4_fixed_replay.py\` | P4-C/D/E canary and full, stage-separated immutable \`P4_C/FIXED/MAP\` snapshots |
| \`p4_offline_score.py\` | 완료된 결과를 read-only truth reader로 집계, \`P4_METRICS.csv\`, group denominators, failure listings |
| \`p4_archive_audit.py\` | SHA/sample IDs/manifest/counterfactual prior parity, output readback and \`P4_FINAL.json\` |
| \`.github/workflows/ekf4-r4-p4-one-step.yml\` | audit → immutable artifacts download verify → math regression → canary → full fixed → guarded MAP → offline scoring → independent post-audit → artifact upload even if FAIL |

원시 artifacts: \`P4_PRE_AUDIT.json\`, \`P4_INPUT_INDEX.json\`, \`P4_C_CANARY.csv\`, \`P4_FIXED_ALL.npz\`, \`P4_MAP_ALL.npz\`(실행된 범위), \`P4_FAILURE_SNAPSHOTS/*\`, \`P4_METRICS.csv\`, \`P4_NUMERICAL_VERDICT.json\`, \`P4_SCIENTIFIC_SCOPE.json\`, \`P4_FINAL.json\`, manifest of SHA256 for every file. 실패 시에도 outputs 보존, 완료/부분·`NOT_RUN`/`BLOCKED` 명확히 구분한다.

## 9. 완료 판정

- **\`P4_FIXED_LINEAR_PARITY_PASS\`**: P3 audited frozen data reuse, 3/4state/J4/frozen-sequential numerical identity, common gate/NIS·posterior covariance·no duplicate measurement, full 14,502 frame completion.
- **\`P4_NONLINEAR_ONE_STEP_EVALUATED\`**: SR4/MAP-P/MAP-R 동일 objective/원 80/1e−8로 실제 실행 범위·수렴/미수렴 분모, RF LoS/Full error/consistency를 공개. MAP 일부 실패하면 해당 arm **INVALID**, fixed-linear PASS는 유지; full nonlinear PASS는 별도.
- **\`P4_REAL_RF_IMPROVEMENT\`**는 사전 선언한 과학적 기대 결과가 아님. 성능이 실제로 악화해도 위의 기술 PASS를 임의 FAIL시키지 않고 한계/위험을 정확히 보고한다.
- 마지막 상태 기본 \`scientific_PASS=false\`, \`P5/P6=NOT_RUN_ON_THIS_BRANCH\`. 독립 외부 RF scene 검증이나 P5 multi-mode reference는 별도 단계에서만 승격한다.

**본 문서는 코드 감사에 근거한 향후 구현·실행 계약이며 현재 P4 실행 결과가 아니다.**