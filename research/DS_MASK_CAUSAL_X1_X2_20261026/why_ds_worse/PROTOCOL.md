# Δs 보정은 왜 BASE보다 나빠지는가 — 수정 승인안 실행 계약

기준: research/ds-x1-x2-results-20261026 / 2ee731336fc2b37ffcd67f96a07bdaf3dccc2898
출력: research/DS_MASK_CAUSAL_X1_X2_20261026/why_ds_worse/
이 문서는 사용자의 마지막 수정안을 실행 정의로 기록한다. 이전 첨부는 ORIGINAL_REQUEST_ATTACHMENT.txt에 보존하며, 충돌하면 이 수정 계약이 우선한다.

## 범위와 고정
- E1 A0=BB, A1=MB, names에서 검색. 7case×B0/L2=14조건. 주3case는 R2_aA_m45/R4_aA_m0/R4_aB_m0. 나머지는 기술값. B0/L2 모두 만족해야 case 지지; 주case2/3 이상이면 전체 지지.
- 기존 결과, 학습, Q, 편파 mu/R, mask A_B 보존. GT는 진단·채점만, 이번 oracle 거리 switch는 명시적으로 GT 사용. T1-est만 자기 prior 거리 사용.
- h_r(p)=sqrt(horizontal²+height²)-0.5315983906250129m. e_r=(z_r-mu_r)-h_r(GT). c=mu_M-mu_B. r_GT는 e_lat에서 상수를 뺀 기하학적 3D 거리.
- c는 A_B 수용 packet에서만 정의/집계/교란. 거절 packet은 출력 c=NA; 필터 실행은 해당 배경 mu를 유지하되 갱신되지 않는다. D2/score는 거절을 포함한 전체 posterior.
- D1/D4 주 기술통계는 전체 시간의 수용 packet. D1은 t>=30 요약도 별도 제공. 통과별 D1/D2/D3는 초기 통과를 놓치지 않도록 t=0부터. 전역 필터 점수는 t>=30.
- 통과는 기존 P2_PASSES_GT.csv의 GT d<1.5 연속 episode, 첫pass 주판정. 확장창 [start-10,end+10] 기록끝으로 제한. 확장창이 겹치면 중단하고 보고한다.
- pre/post는 기존 P2 창 재사용: pre30초 최소5초, post30초 최소10초, 다음통과/기록끝에서 절단. pre 부족 시 초기 BB/MB gap<0.1cm 조건을 검사하고 각 arm 자기 초기 e_t를 기준으로 삼는다(개별 arm 오차를 0으로 만들지 않음). 실제 시간/packet수/유효성 기록.

## 단계0: D0–D4
D0: mu_B/mu_M/Rrr_B/Rrr_M와 c/e_r를 packet별 저장. e_M=e_B-c 오차<=1e-10m; 동일 원측정 재구성 및 mask/R 검산. 실패시 중단. Rrr 차이0이면 W5의 R변경 가설 기각, T4 미실행. R동일이어도 상태/P를 통한 gain차이는 남는다.
D1: GT d bins [0,.5,1,1.5,2,3,4,6,8,inf). n/mean,RMS e_r/mean,RMS c/mean,RMS e_lat=e_r*r_GT/d. d<=1e-8이면 e_lat NA. 모든 통과도 동일 통계. 부호 일관성=max(n_pos,n_neg)/n_nonzero, 1pass는 반복 근거가 아니며 single_pass 표시.
D2: GT 접선축 u_t=R90((p_GT-a)/d), 각 arm의 e_t=u_t·(p_hat-p_GT). pre/post signed mean과 delta=post-pre, 부호/통과간 일관성. 절댓값 평균과 구별.
D3: 수용 packet에서 range열 K_r*nu_r XY. 정확한 분해:
  M-B = -K_M*c + (K_M-K_B)*nu_B - K_M*(h_M-h_B).
packet별 XY 및 창별투영합 오차<=1e-10m. 주축GT, 비교축은 BB prior 공통축. 각 arm 자기 prior축 F도 별도 출력하고 축변화 효과는 3항 합에 섞지 않는다.
각 항을 접선/반경, 확장창 전체/전(start-10<=t<start)/중(start<=t<=end)/후(end<t<=end+10)/창밖으로 요약. outside는 해당pass 확장창의 여집합이며 pass끼리 중복되므로 더하지 않는다.
보정항과 예측차이항의 동부호/반대부호 표시. 크기비[0.5,2]를 similar로 고정. opposite+similar는 '복원 방향의 투영 성분'이라는 기술적 후보이며 원인 확정 아님.
자기상관 시간: 확장창의 e_r를 accepted 평균으로 중심화, 실제 규칙시간축 lag별 유효 accepted pair 평균곱/lag0 평균제곱. 최소10pair, 창절반까지 탐색, 첫 <=0.5 lag. 도달하지 않으면 right_censored/NA, 분산0이면NA. packet 압축으로 시간을 줄이지 않는다.
D4: accepted near d<1.5/far>=1.5에서 c~intercept+sinψ+cosψ+sin(ψ-β)+cos(ψ-β)+world y+d+zigzag sign. zigzag sign=sign(GT world-y 시간미분), |dy/dt|<1e-8은0. 이는 실제 경로 위상 대용변수임을 명시. 특성 표준화 OLS, 상수열 제거, rank/condition/n/R²/원단위계수와 pass block수 기록. CI/p값 없음. W4는 여기서 판정하지 않는다.
W1 기술후보: 전체 accepted near의 |mean e_M|>|mean e_B|. W2 기술후보: 첫 확장창 GT |F_M|>2|F_B| 및 tau_M>2tau_B; censored는NA. D1–D4 결과와 무관하게 T1–T3 실행.

## 단계1: replay
먼저 OFF_BB/OFF_MB 모든14조건을 E1 상태/P/prior/Pprior/h/H/K/mu/R/nu/acc <=1e-10 재현. 실패하면 다음단계 중단.
T2 복원 대조 ORACLE_BB/ORACLE_MB도 같은14조건 OFF 재현 후 본실험 진행. 창밖 각배경, 창안 hGT+e_B 또는hGT+e_M. 원측정 z를 유지하고 유효mu=z-target로 구현. 수용값이 동일한지 검산.
T1: D=1.0,1.5,2.5; NEAR_ONLY는 dGT<D에서만 c, FAR_ONLY는 dGT>=D에서만c. 나머지mu_B. NEAR가 heading signed-bias gap>=70% 동부호 재현, FAR gap크기<=30%, 앵커거리 RMSE 개선폭 유지>=70%일 때 해당D W1지지. RMSE gap도 별도 보고. 분모 |biasgap|<=.01deg 또는 range개선<=1e-12는NA. D별 B0/L2 모두, 주2/3case 충족시 그 D FAR_ONLY_EST를 모든14조건 재실행. 실패시 새 D 탐색 안 함.
T2: ORACLE0_BB/ORACLE0_MB는 확장창 합집합 안에서 모델GT로 보정range를 대체, 밖은각배경. W3운영지지=ORACLE0_BB HeadingRMSE>1.1*BB. 이는 상쇄가설과 부합하는 근거이며 단독원인확정 아님. ORACLE0_MB signed-bias gap제거>=70%와 ORACLE0_BB RMSE<=BB이면 W1/W2방향 별도표시.
T3: 창밖mu_M, 창안accepted c에 C_MEAN0=c-passmean, C_MEANONLY=passmean, C_FLIP=-c, C_PERM=순서교란. 평균은 각 case×bias×pass 자기 A_B의 확장창. 20 seed=2026102700..2026102719, 각pass seed에 pass_id를 더한 SeedSequence; 동일조건결정적, 다른mask 강제동일화 안함.
W2: C_PERM 각seed f=1-|bias_arm-bias_BB|/|bias_MB-bias_BB|, 20seed 중앙값>=.5. mean/p10/p90/min/max와 성공seed수 보고. R2/R5 다중pass는각창내별도perm. C_MEAN0/ONLY는 기존 전역성분 분리와정의차이설명.
W4: C_FLIP에서 첫pass delta_e_t와 전역heading bias의 'BB대비 이동'이 각각 MB대비 반대부호. 각원gap 최소 .1cm/.01deg. 절대bias부호가 아니라 BB대비효과부호. 추가로 absolute delta_e_t 부호도 기술. 이것만으로 특정기하상관이 유일원인임을 주장하지 않음.
T4: D0 Rrr차이 있을때만 MB_RB/BB_RM. 현재 사전확인0이나본D0검산으로 결정.

## 지표/판정/산출
전역 t>=30 HeadingRMSE/signedbias/std/heading95/XYRMSE/앵커거리RMSE/HeadingNEES, 첫pass및모든R5pass pre/post delta_e_t.
f_magnitude=1-|G_arm|/|G_MB|, G=arm-BB. signed f=1-G_arm/G_MB도추가. 각원값및부호같이보고, 분모<=.01deg/.1cm NA. 판정결측은NA이며실행실패와구분.
D0_STRUCTURE.csv,D1_RANGE_ERR_BY_BIN.csv,D1_RANGE_ERR_BY_PASS.csv,D2_ABS_TANGENT_BY_PASS.csv,D3_FORCING.csv,D4_C_REGRESSION.csv,T1/T2/T3_SCORES.csv,C_PERM seed및요약,HYPOTHESIS_DECISIONS.csv.
F1 거리bin mean e_r/e_lat, F2 각통과 absolute arm delta_e_t, F3 고정 R2_aA_m45 B0 c/e_B/e_M/누적F, F4 개입Heading/XY와BB/MB기준. R2_aB D1–D3 별도표.
INPUT_LOCK.json/CHECKS.json/OUTPUT_SHA256.json/RESULTS_KO.md. 재학습/기존산출물변경없음. __pycache__/.pyc 생성안함. 이번 요청에커밋/푸시명령없으므로로컬완료후보고.

## 학습기준 확인
PJ_SEPARATE_RS_20261020/experiment.py build_dataset는 GT sample x/y/yaw에서 SourceFFD를평가한 잔차를라벨로쓴다. fit_models는 held route R2/R4/R5를제외하고 test위치와1e-4m이내train위치를제외; full RF로학습, POWER_DIAG는 POWER평균과대각화R. BASE posterior 궤적라벨아님.
r2_bias_replay.py predict_one의 제어잡음 q=diag(2e-5*abs(ds), radians(.015)^2*dt, 0), Q는이를운동모델로전파한고정설정이며여기서학습하지않음.
