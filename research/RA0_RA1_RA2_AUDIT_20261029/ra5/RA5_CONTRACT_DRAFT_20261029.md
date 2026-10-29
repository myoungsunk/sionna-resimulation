# RA5 — 원인 설명·Δs 정보량·일반화 검증 계약 (DRAFT, 2026-10-29)

역할 PROPOSER. 원본 RF, packet, G3, RA4 점수 모두 READ-ONLY. 현재 문서는 과학 실행 승인 계약이 아니라 실행 전 검토 문서다. 별도 독립 AUDITOR 승인과 SHA freeze 전에는 탐색/수치 QA만 허용한다.

## A. 확인된 근거
- G3 original 25-ray image-unmerged criterion 모두 strict 통과; class representative가 25/25 역사적 FAIL을 생성. R2_aA 1건은 별도, raw strict 5.1090357e-14 s. H 복원은 해당 23개 m0 row에서 relative max 7.28e-16 (source parity, 물리 진실 입증 아님). Run 40867280947.
- RA4 full 336 arms: MB_VAR_LEGACY vs BB_ORIG, BASE_FIXED Heading/XY/BOTH 개선 23/20/19 of 28, SELF_NIS 12/12/8. Run 40859507594.
- A4 selected-case first-flip: R5_aA B0 43.4s 최초 새 수용, self 47 packet 추가, Heading 3.833->8.886°, XY 39.60->87.75cm; R4_aB 첫 2.8s +9; R2_aA_m45 첫 7.4s +27이며 이 경우 SELF가 MB_VAR 자체 성능 개선. Run 40869832463. Sigma=0, muM=muB fixture 42 PASS/60-packet prefix; sensor bias-only 12 PASS. 초기 XY/Heading/noise 요인 전체 실험은 아직 NOT_RUN.
- Temporal GM historical B0 6 case에서는 MB_VAR 평균 Heading 1.530°, XY 13.33cm; FOGM_TIME_KEEP/SPLIT은 전반 악화. R5-A/B와 R4-B 효과 이질적, fitted colored covariance와 white covariance 분리가 입증되지 않음 (run 40828341230).
- Residual pair time shuffle은 local geometry pairing도 깸. 시간 correlation 단독 효과를 식별하지 못함 (run 40825807998).
- Synthetic MBVAR-INFO S0V2 PASS이나 S1V2 pilot QA pass=false, q_rel_diff_max=0.072496...; claim INCONCLUSIVE. POL-XCORR-001 v0.2도 preflight/auditor PENDING. 이 결과들을 RA5 증명으로 소급 사용 금지.
- Seven RF cases × 4 gyro labels는 한 corridor의 반복 trajectory/gyro interventions, independent scenes 28개가 아니다.

## B. 핵심 질문과 추정량
R5-Q1 공간 편파 오류 field e_s(x,y,yaw,mount,anchor)와 시간 동역학 b_s(t)를 분리 가능한가? 같은 pose 재방문, 다른 시간의 독립관측 없이는 일반적으로 불식별.
R5-Q2 관측기하 J=∂h/∂x와 잡음/모델 잔차 공분산 Sigma가 불확실성 및 정확도에 각각 얼마 기여하는가? matched-prior same mask 선형 정보량과 full-recursion 성능을 구별.
R5-Q3 온라인에서 추가 가능한 Δs가 무엇인가? Δs_oracle=s_Full-s_LoS는 truth-only. d0=s_full-h_s(x_prior)는 기존 s의 innovation 재표현으로 중복 측정 금지. ds1=s(tap_fp+1)-s(tap_fp)는 추가 raw tap이 하드웨어에 있으면 온라인이나 s_fp와 공통 잡음.
R5-Q4 ds1을 추가했을 때 조건부 정보가 증가하는가? 단일 raw s0를 넘어 s1의 신규 신호가 있는 경우에만 가능. 동일 raw 관측의 단순 재표현은 information zero.
R5-Q5 편파 nuisance state b_s를 추가하면 observability와 out-of-sample calibration이 개선되는가? 같은 raw 정보의 재매개변수화와 independent measurement를 구분.
R5-Q6 새 환경에서 accuracy/uncertainty calibration을 유지하는가? 기존 Corridor/Office 회고 결과는 DEV로만 처리. 실제 TEST는 아직 관찰하지 않은 새 scene/measurement에서 별도 freeze.

## C. Δs 수학·공분산 핵심 규칙
동일 packet first tap s0, 다음 tap s1, d=s1-s0일 때:
 Var(d)=Var(s1)+Var(s0)-2Cov(s0,s1),
 Cov(s0,d)=Cov(s0,s1)-Var(s0).
따라서 raw [r,s0,s1]를 [r,s0,d]로 바꿔도, 관측 Jacobian과 full covariance를 동일한 가역변환으로 바꾸면 추정 정보가 같아야 한다. Off-diagonal R_rs,R_rd,R_sd를 모두 포함. 같은 first-path tap detector 및 tap switching의 공통오차 필수 검사.
Linear Gaussian conditional incremental information:
 R_d|z = R_dd-R_dz R_zz^-1 R_zd,
 J_d|z = J_d-R_dz R_zz^-1 J_z,
 Delta I_x = J_d|z^T (R_d|z)^-1 J_d|z, z=[r,s0].
Singular constraint는 pseudo-inverse 또는 원 raw basis에서 처리. Regularization으로 가짜 Delta I를 생성하지 않음.
Pose x와 nuisance b를 동시에 추정할 경우 effective information:
 I_eff(x)=I_xx-I_xb (I_bb+P_b^-1)^-1 I_bx.
원래 s 관측 하나의 Jacobian에 yaw와 b_s 열이 함께 있을 때 단일 packet에서 두 상태의 분리가 일반적으로 불가능하며, time variation/추가 측정 geometry가 필요. Observability Gramian 최소 고유값, condition number, posterior psi-b correlation을 확인.
시간 차분 white noise e_k-e_{k-1}은 동일분산일 때 분산 2V, lag1 covariance -V의 MA(1) 성분을 만든다. 실제 data에서는 state estimation error와 prior cross covariance도 포함한다.

## D. 사전 정의한 비교 arm
R0: [r,s0], original 2x2 joint R, BB_ORIG / MB_ORIG / MB_VAR_LEGACY references.
R1: [r,s0,d0], d0 deterministic duplicate; negative fixture only. Independent diagonal R를 허용하지 않음; conditional extra information=0이어야 함.
R2: [r,s0,s1], raw two-tap 3x3 joint covariance, truly newly observed adjacent tap can add info relative to R0.
R3: [r,s0,ds1], covariance T R2 T^T, Jacobian T J; exact R2/R3 information and state/P equivalence fixture.
R4: [r,s0], nuisance b_s as 5th state. Independent extra observation 없음; Q_b,phi,Rwhite 모두 train-only, identifiable region에서만 pilot.
R5: [r,s0,s1]+b_s, R2 and R4 passed before evaluation, full cross-cov; no double counting.
RO: [r,s0,Delta s_oracle], diagnostic upper bound only, no online policy.
All primary comparisons BASE_FIXED; SELF_NIS as separate gate policy with first-flip ledger, not mixed estimates. MB_VAR_LEGACY and MB_VAR_PRIOR results separately named.

## E. 수행 순서 및 Gate
RA5-0 INPUT/PREFLIGHT: frozen H/LoS, CIR tap/port, packet, controls, time/pose/anchor, source SHA, original FFD and version lineage; verify Office source/labels and independent environment status. Audit geometry-J derivative against finite differences, full H→CIR replay. Output source_lock and online availability. STOP on wrong/missing sha, reused test labels, 0 valid rows.
RA5-1 MATH FIXTURES: two-tap transform exact X/P/NIS, PSD covariance, noise Monte Carlo, duplicated d0 zero information, timestamp/differencing MA1, singular rank negative, covariance fit on disjoint training data. Fail-closed before estimator.
RA5-2 SOURCE RESIDUAL DECOMPOSITION: join per-packet e_r/e_s, raw s0/s1, LoS, yaw/range/bearing, mount, anchor, motion phase; estimate m(g), spatial residual and temporal ACF conditional on geometry. Use same pose revisits and reverse/forward, stationary segments as differentiating controls. No revisits -> NOT_IDENTIFIABLE (do not fit temporal model and call it proven).
RA5-3 JxSigma 2x2 controlled synthetic experiment: geometry J_low/J_high × noise Sigma_low/Sigma_high at matched priors/truth/controls/seed; compute Fisher eigenvalues/logdet and nuisance-marginalized I_eff, matched-prior one-step K/innovation. Independent follow-up full recursion at same BASE mask. Physically realizable scene conclusions require new RT, not inferred from synthetic intervention.
RA5-4 ONLINE INFORMATION: R0/R2/R3/R1 negative control, train-only full covariance incl r/s0/ds1 off-diagonals, PSD and shrinkage sensitivity, conditional incremental information, held-route log predictive density, RMSE, NIS/NEES and coverage. Online availability of adjacent tap and synchrony is a separate hardware gate.
RA5-5 IDENTIFIABILITY: 4-state vs 5-state R4/R5 only after covariance QA, compare Gramian eigen spectrum, correlated psi/b_s, b_s prior/Q sensitivity, calibration and negative controls. Test mean-only, variance-only, nuisance-only, combined under matched mask. Report adverse results equally.
RA5-6 NEW ENVIRONMENT: predeclare frozen model and score metrics, no retuning on blind TEST. Corridor three routes + seen Office = retrospective DEV; require newly held-out scene, independent trajectories, seeds and possibly measurements for generalization claim. If unavailable stop at SUPPORTED_RETROSPECTIVE and GENERALIZATION_NOT_TESTED.

## F. 사전 수용·중단 규칙
Engineering PASS does not mean RMSE improvement. Any nonfinite trace, missing hash, R not PSD, broken equivalent-transform fixture, σ=0 or μM=μB parity failure, oracle leakage, independent-feature assumption on correlated taps, or unapproved gate/mask change: BLOCKED/FAIL. Ambiguous observable rank: NOT_IDENTIFIABLE; do not silently regularize into PASS. No post-result changes of thresholds, priors, folds or source hashes. Holdout bootstrap unit is scene/route-run block, never individual packet/gyro label as independent scene.
Before P3 formal science, independent auditor separately recomputes at least R5-A/R5-B/R2aA edge cases and deliberate negative fixtures. Even successful same-session audit is SELF_REVIEW_ONLY.

## G. Mandatory outputs
RA5_SOURCE_LOCK.json; RA5_DATA_PROVENANCE.csv; RA5_ONLINE_FEATURE_AVAILABILITY.csv; RA5_TWO_TAP_COV.csv; RA5_CROSSTIME_COV.csv; RA5_NEGATIVE_FIXTURES.json; RA5_J_SIGMA_FACTORIAL.csv; RA5_CONDITIONAL_INFORMATION.csv; RA5_OBSERVABILITY.csv; RA5_R0_R5_SCORES.csv; RA5_GATE_POLICY.csv; RA5_HELD_SCENE_RESULTS.csv; RA5_QA.json; RA5_FINAL_REPORT.md. Every run has config hash, input/output hashes and exact command. No original artifacts overwritten.
