# PREREG v1.0 — CIR amplitude 특성과 편파 RF-heading reliability

작성일: 2026-10-10 (Asia/Seoul)  
상태: LOCKED BEFORE PRIMARY FEATURE–HEADING-ERROR ANALYSIS / 새 heading-CIR 상관, 예측모델, 프로브 개선의 결과는 아직 없음.  
소스 기준: post-A23 evidence HEAD 047cce2acb244ec2d7badc563345ccdd1f48613f, sensor-v2 감사 16d22fc3121963743cf7f1bf56233e00083c5518. 본 문서는 기존 RF·필터를 수정하거나 과거 scientific FAIL을 해제하지 않는다.

## 0. 먼저 분리할 질문

- H-F: LoS가 존재하고 시간적으로 unresolved된 경로들 때문에 생긴 RF-heading 오차를 단일 포트의 전통적 CIR delay 지표보다 **두 RX 포트의 amplitude-CIR 형태 차이**가 더 잘 예측하는가?
- H-R: 알려진 anchor 좌표와 FFD LoS LUT, 수신 amplitude, RF를 사용하기 전 IMU+wheel 추정만으로 P(|wrap(psi_RF - psi_true)| <= 5 deg)을 올바르게 보정(calibrate)할 수 있는가?
- H-P: 동일 위치의 2각 또는 3각 프로브가 단일각 passive model보다 reliability discrimination 및 selective-heading error를 개선하는가?
- H-G: 이 결과가 경로/앵커를 바꿔도 유지되는가? 현재 7개 케이스는 동일 복도 geometry라서 **새 환경 일반화 증거로 취급할 수 없다**.

확인 대상: first-path **s** 왜곡, 역 LUT의 추정 heading 오차, RF 업데이트의 유익성. 별개 endpoint로 반드시 보고한다. ranging error만으로 heading 성능을 대신하지 않는다.

## 1. 소스/입력 동결, 정체성

원본 branch codex/post-a23-evidence-20261010 @ 047cce2. 데이터: results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C 의 FULL_RF/H_*.npy, H_LoS_*.npy, <case>/SAMPLES.json, INPUTS/rf_poses_R*.json, freq_hz는 ../freqs_hz.npy. 7케이스: R2_aA_m0, R2_aB_m0, R2_aA_m45, R4_aA_m0, R4_aB_m0, R5_aA_m0, R5_aB_m0. RF shape (Nposes,257,2rx,2tx), TX column0(+45 LP), RX(+45,-45). 공개된 CASES.json/원 SHA256 필수 확인.

고정 LUT: 기존 2° FFD LoS hs_lut_2deg.npy 및 hs_lut_meta.json (원 hash: 711e12ee48a30cb666db4dada749b983de49bd565ea351b906269ec8da375a079). 공개 브랜치에는 대형 LUT payload가 없을 수 있으므로 로컬 원본이 반드시 존재하고 SHA가 일치해야 한다. 없으면 실험 BLOCKED; 대체 LUT 생성 금지.

원본 observation: Hann, zero-pad 4N, IFFT×N, 가장 강한 RX에서 peak의 30% leading-edge 최초 정수 tap, 양 포트의 **같은 tap**에서 P1/P2, s=(P1-P2)/(P1+P2). 반드시 기존 qclean_uwb.drivesim.observation과 결과 일치 시험. sampling dt=1/(1028 df); interpolation으로 물리 분해능을 과대평가하지 않는다.

기본 센서 출력 가능성은 별도 하드웨어 계약으로 확인: amplitudes P1/P2는 최소; CIR |c_i[n]|이 모듈에서 실제 접근 가능한지 아직 확정되지 않음. full complex H, path별 계수/지연, LoS truth, Jones 위상은 **offline oracle/label 전용**, inference input 금지. amplitude-CIR이 실제 하드웨어에서 제공되지 않으면 해당 특징은 DEPLOYMENT_UNAVAILABLE로 보고한다.

## 2. 단위, 표본, 분할

- 기본 관측단위: (case, pose_id, RF realization). 본 결과는 동일위치 yaw 그룹 기준으로 묶어야 한다. 동일 (route,x,y)의 anchor/mount 복제와 반복 noise seed를 독립 환경으로 세지 않는다.
- R2: 1303 RF pose, 21곳의 3점 이상 yaw; R4: 922 pose, 23곳; R5: 1883 pose, 30곳. 고유 yaw 측정 위치 74곳. 7케이스를 통틀어 위치-케이스 그룹 169개 (21×3+23×2+30×2). 확인된 것은 데이터 메타데이터이며 신뢰도 실험 결과가 아니다.
- Primary exploratory CV: leave-one-ROUTE-out (R2, R4, R5를 각각 1회 test), 동일한 route의 모든 anchor/mount와 반복 seed는 같은 fold. 훈련 내부에서만 feature 선택·scaling·calibration. 이 결과를 cross-geometry 일반화로 주장 금지.
- 공간적으로 인접한 pose와 yaw sweep은 고도로 correlated. CI는 station/route 단위 cluster/block bootstrap로 보조 보고; 7 케이스 또는 5 Hz 샘플 수를 독립 환경 반복으로 취급 금지.
- 입력 조건 primary: 기존 저장된 full H vs LoS H의 **noise-free paired** RF 차이; 30 dB SNR이 실제 구현과 해시로 재현되는 경우 별도 secondary noise run. 조건/난수와 threshold 변경 시 새 prereg.
- 5Hz, 0.2m/s 주행, sample dt=0.2s (v2 상세는 01 문서). 기준 오류각 primary 5°, sensitivity 2° 및 10°; wrap 각도 범위 [-180,180), |오차|는 deg.

## 3. Label 정의 및 leakage 금지

A. **직접 관측모델 잔차** (oracle pose를 사용한 진단값)
  e_s = s_full - h_LUT(p_true, psi_true), e_MP = s_full - s_LoS_direct_same_pose.
  두 값 모두 보고. 첫째는 F01/L1/L2 LUT 오차와 MP가 섞이고, 둘째는 matched-channel path 차이 진단. estimator feature에서 true pose/yaw를 읽을 수 없음.

B. **RF heading 역해**:
  - 후보: psi in [-180,180) 0.25° grid로 기존 LUT s_model을 탐색; 동일 s를 만족하는 모든 local/root 후보와 최솟값·root branch 수 저장.
  - Deployable primary: RF-disabled sensor-v2에서 같은 시점 업데이트 **전** 예측 (p_minus,psi_minus,P_minus)에 가장 일관적인 branch 선택. heading만 우선 1D scan, 위치는 p_minus를 고정하며 position prior uncertainty도 따로 기록. 다중 후보가 비슷하면 ambiguous=true; 아무 후보도 충분하지 않으면 no_match=true. 유리한 true yaw를 선택 기준으로 사용 불가.
  - RF-only best-oracle: true pose/yaw를 이용해 가장 가까운 branch 선택한 intrinsic lower-bound; 오직 진단용, 모델 학습·수용정책·primary 성능으로 사용 금지.
  - ground truth heading error: abs(wrap(psi_RF-prior_assisted - psi_true)). bad_5deg = error > 5°, equality는 correct. No-match/ambiguity은 primary에서 무조건 PASS 처리하지 않고 selective abstention/coverage 지표에 포함.
  - 별도 outcome: harmful_RF = abs(wrap(psi_after_RF - psi_true)) > abs(wrap(psi_minus - psi_true)); paired same prior+noise. 이는 필터를 통한 오차 영향으로, RF-only correctness와 반드시 구분.

RF-disabled prior trace가 없는 케이스에서는 B-deployable 및 H-R/H-P 유의성 실행을 BLOCKED로 표시. 파일 H와 true yaw만으로 만든 oracle heading을 온라인 성능인 양 대체하지 않는다.

## 4. CIR 특징군: 등록된 primary 후보

모든 특징은 두 수신 포트의 **amplitude 또는 power CIR**로만 계산; complex phase 및 full-path oracle 사용 금지.
k_fp는 기존 strongest-branch 30% leading-edge. p_i[n]=|c_i[n]|², t_n=(n-k_fp)dt. 임의 시간축 shift나 새로운 peak-selection을 primary observation에 적용하지 않는다. 잡음값이 있으면 양 포트에 동일한 명시적 noise-floor rule 적용. window는 범위를 벗어나는 경우 availability flag를 추가해 sample을 슬쩍 버리지 않는다.

Core D (전통적인 지연/CIR 지표):
  D1 RMS delay spread: energy-weighted std(t) on n in [k_fp, k_fp+80] per RX; 두 포트 평균/차를 별도로 보관.
  D2 early energy fraction: sum p_i[k_fp:k_fp+8] / sum p_i[k_fp:k_fp+80]. slice offset은 [0..7], [0..79] 포함.
  D3 peak-to-first energy: p_i[k_peak_i]/max(p_i[k_fp],eps); positive ratio (log1p optional; 학습 inner-fold에서만 선택).
  D4 rise time: each RX amplitude가 자신의 peak의 10%→90%를 최초 통과하는 tap difference; threshold 교차 없으면 missing flag. 주파수 제로패딩 time grid는 물리 분해능이 아니다.

Core P (이중 편파 특화):
  P1 JSD(port shape): 양 포트의 [k_fp..k_fp+15] 비음수 에너지를 합1로 정규화 후 Jensen–Shannon divergence; epsilon=1e-12, natural log.
  P2 peak-delay difference: (argmax_{window} p1 - argmax_{window} p2)×dt in ns.
  P3 early fraction asymmetry: |D2_rx1-D2_rx2|; D2의 두 포트 값도 저장.
  P4 normalized early shape mismatch: L1 distance between 16-tap per-port normalized powers (0..2).
  P5 power ratio s=(P1-P2)/(P1+P2) and log10(P1+P2) with receiver gain conditions recorded; single-port intensity non-invariant across TX power must be standardized from training only.

Auxiliary K: measured link distance, LUT slope |dh_s/dpsi| at p_minus,psi_minus, position covariance, 5Hz gyro–wheel yaw discrepancy, pre-update innovation standardized by correct predictive S. These are NOT pure-CIR features; report separate ablation. No true distance/true pose/oracle path labels at inference.

Offline upper bound U: true first-second path gap, reflection-to-LoS amplitudes, Jones complex terms. **Forbidden as inference features**. Used only to stratify unresolved region defined first/second gap <1/B, B≈500MHz (nominal ~2ns). For full path set where this is almost always true, distinguish **high-error versus low-error inside unresolved**, not unresolved vs resolved classifier.

## 5. 가설검정 및 예측모델

Primary target: correct_5deg (binary), secondary continuous abs heading error and harmful_RF. 기준선: (i) constant prevalence, (ii) distance-only, (iii) distance+|slope|, (iv) D-only, (v) P-only, (vi) D+P, (vii) D+P+K. 모든 표에서 availability/abstention/true anomaly prevalence 보고.

- Univariate: Pearson(r) for feature vs continuous |heading_error| and vs binary correct (point-biserial), Spearman(rho), station-group confidence intervals, scatter/hexbin and 10-quantile binned means; residual-vs-distance/slope partial association.
- Linear relation 판단: r/R², slope, held-out MAE/RMSE, binned nonlinearity; Spearman 및 spline/monotone 관계와 구분. 높은 Pearson이면 calibration이 자동 성립하는 것은 아님.
- Primary supervised 모델: StandardScaler(train only)+LogisticRegression(L2,C=1,max_iter=2000,class_weight=None) for good_5deg. Missingness indicator + train-only median imputation. Training-only calibration 가능하면 independent group-split sigmoid, 불가능하면 uncalibrated+reason. Secondary HistGradientBoosting(max_depth=2,learning_rate=0.05,max_iter=100) exploratory.
- 평가: Brier (primary probability score), AUROC, AUPRC with prevalence, ECE(10 equal-width bins), calibration slope/intercept, risk-coverage/selective RMSE at retained 25/50/75/100%, reject rate and high-confidence false accept. Held-out case와 각 route별 보고. 학습 데이터 기반 threshold 튜닝 후 test 반복 금지.
- "신뢰도 q와 실제 정답이 선형인가": 단일 이진 label과 q가 직선상의 점이라는 뜻이 아니다. calibrated probability인 경우 **bin별 P(correct|q) ≈ q**인 reliability diagram으로 판정. |heading error| vs q의 선형성은 별도의 경험적 검정.
- 원변수별 다중 테스트는 탐색으로 표기하며 FDR-BH 보정 p값 보조 표기 가능. 작은 3-fold 수에서 일반화 유의성 과장 금지.

## 6. 2/3점 프로브 (H-P)

Primary offline schedule (실제 저장된 16~19 점 yaw 데이터):
  각 동일 XY의 연속 yaw block에서 첫 pose를 기준(0점)으로 하며, 2-point는 index[0,2] (~0/10°), 3-point는 index[0,2,4] (~0/10/20°)를 사전 고정. 4.76° step이면 +/−9.52°/~19.04°. 실제 부호는 sweep rotation에 따라 기록; post-hoc 가장 좋은 3점 선택 금지.
  1-point는 index[0]. 같은 H·noise realization의 관측만 사용. 시간/회전 비용은 yaw offset/각속도 계약이 없으면 NA.
  Secondary (new RF required): symmetric nominal [-10°,0,+10°] 및 slope-steered angles는 신규 v2 RF poses를 추가 생성한 이후 평가; 저장된 full sweep의 최선3점은 ORACLE UPPER BOUND로만 표기.

각도 i별 r_i=z_i-h_LUT(p_minus,psi_minus+delta_i), H_i=dh/dpsi.
  common heading correction: min_delta (r-H delta)^T Sigma_probe^-1 (r-H delta) + delta²/P_heading_prior.
  shape-consistency: projected residual (r-H delta_hat), sigma 정규화 chi²는 Sigma_probe가 실측 정합됐을 때만 확률값으로 사용, 아닐 땐 진단 score.
  차분 D_ij=H_j r_i-H_i r_j는 1차적으로 공통 heading error를 제거하지만 개별 multipath bias 분리 정답이 아니다.
  동일 장소 다중각 observation errors는 correlated; 독립 R로 처리해 정보량 과대평가 금지.
  Leave-one-out point consistency/point influence, worst point residual, slope span 및 ambiguity count를 보고. "가장 작은 residual 한 점을 무조건 채택" 금지.
  1/2/3점 각각 RF-heading correction의 bad_5deg, Brier, selective risk, probe cost 비교. single-angle vs probe 분류기 입력을 공정하게 동일 split에서 paired 비교. LOOCV가 가능한 곳만 별도 subset으로 평가하고 그 subset의 단일각 기준선도 재계산.

핵심 식별성 한계: 완벽한 2ψ harmonic 형태의 일정한 effective polarization rotation은 3점이나 full sweep에서 true heading shift와 구분할 수 없음. probe shape-consistency가 좋다고 true heading correctness로 등치하면 안 된다.

## 7. 필수 결과와 STOP/FAIL

출력:
  00_input_audit.json (original SHA, dimensions, branch/commit, LUT, Sionna version)
  01_feature_rows.parquet/csv (case,pose,xyz,yaw, d, kfp, two ports features, available flags, oracle labels 별도)
  02_distance_bias_variance.csv: bins [0,5),[5,10),[10,∞) m, n, E(e_s), Var(e_s), RMS(e_s), E(e_MP), Var(e_MP), heading error stats, angle/slope stratification. Sample variance convention ddof=0; n below 20이면 descriptive only.
  03_feature_correlations.csv; 04_leave_route_out_predictions.csv; 05_calibration_risk.csv;
  06_probe_pairing.csv; 07_probe_uplift.csv; 08_failure_cases.csv; EXECUTION_STATUS.json.
  각 숫자는 noise-free/30dB/SNR-realized/mount/anchor/route/drift/seed split을 명확히 표기. 적어도 station 기반 paired bootstrap (1000 replicates, seed=20261010) and n groups.
  graph: feature-error scatter by case, probability-calibration, risk-coverage, grouped probe consistency, distance mean/variance + CI.

STOP: missing raw H or external LUT / hash mismatch, missing waveform amplitude for claimed hardware, unverified pose pairing, mixed source SHA, R2 LUT L1/L2 FAIL의 상태 미기록, RF prior 없이 operational heading label 주장, data leakage. Failures는 재튜닝 없이 JSON status BLOCKED/FAIL로 남긴다.

기존 L1/L2 FAIL·F01/F02 OPEN 및 scientific_PASS=false는 그대로 유지. 본 실험은 진단·신뢰도 특성 검증이며 아직 production 채택 연구가 아님.

## 8. 참고

- A19: results/DRIVE_SIM_20261007/DEV_RESULTS/RESIDUAL_STRUCTURE_A19.json (s residual vs slope nearly uncorrelated)
- A21: DISTANCE_SIGMA_CALIB.json 및 DISTANCE_SIGMA_HELDOUT.json (distance-binned sigma held-out 미승인)
- A23 Q1/Q2: POST_A23_RESULTS_20261010/{Q1,Q2_JOINT_L2}/FINAL_REPORT_KO.md
- A23 supplement: SUPPLEMENT_01a12449/FINAL_REPORT_KO.md (7 matched full/LoS H and R2 path-center-bin data)
- Wong et al./other NLoS work: CIR RMS-DS, rise-time, kurtosis, energy metrics are established for **ranging/NLoS**; direct extrapolation to polarization-heading is unverified.
