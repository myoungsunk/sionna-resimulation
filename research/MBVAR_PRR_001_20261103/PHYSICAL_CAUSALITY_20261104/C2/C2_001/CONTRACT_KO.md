# C2-RECURSIVE-001 — 창 한정 RF 관측 개입의 재귀 전파

PROPOSER 초안. C1a/C1b 독립 수용을 전제로 하는 후속 상세 계약이며 이 문서는 실행 GO가 아니다. 기존 CAUSAL_VERIFICATION_PLAN_KO.md §5를 구체화한다. Mother의 PROPOSER→IMPLEMENTER 순차 역할과 별도 precision_audit의 읽기 전용 독립감사를 구분한다. RESEARCH-GOVERNANCE-v1의 적용 문서 SHA를 GOVERNANCE.json에 묶는다. 원본 RT·관측·학습 모델·S1–S3·N0B·기존 R2 결과를 변경하거나 재실행하지 않는다.

## 질문과 개입

이미 관측한 hotspot의 range/polarization Full−Native-LoS 차이를 짧은 창 안에서만 제거하면, 같은 controls·초기조건·잡음에서 미래 Heading/XY 오차와 P·NEES가 어떻게 변하는가? 다른 설명은 현재 관측의 직접 갱신, 미래 prior/H/K/R의 재귀 변화, BASE gate 이력 변화다. 같은 RF의 공개 seed10–29를 쓰므로 독립 환경·비노출 확인평가·온라인 복구 정책의 유효성을 주장하지 않는다.

원래 MB_VAR W0만 사용한다. Full packet의 muMB, muBASE, RBASE는 모든 arm에서 그대로 유지한다. SourceFFD/core/online.py, original controls/Q, bank, Windows runtime은 C1b와 같은 SHA로 잠근다. 새 학습·Native RT·가중치 정책·복구·guard는 없다. GT/LoS는 오프라인 evaluator/oracle 개입이고 온라인 알고리즘으로 채택하지 않는다.

FF는 모든 시점 Full, LF는 개입창의 range만 Native-LoS, FL은 polarization만 Native-LoS, LL은 두 성분을 바꾼다. 창 밖은 다시 Full 관측이며 한 번의 joint update만 수행한다. Full/LoS에 포함된 기존 센서 잡음과 B0/L2 조건을 그대로 유지한다. packet 전역 pose_id/t를 exact join하며 순서 변경·보간·누락 제외는 금지한다.

## 창과 표본

R4: [0,15], [33,35.2], [99,105.4], [59,61]초. R5: [79,81], [92,94], [195,198], [132,135]초. 양 끝을 포함한다(격자 매핑 atol1e-9). R2: pose525 대조 [104,106]초, no-shift 정상 대조 pose735 [146,148]초, tap-shift 대조 pose507 [100.4,102.4]초.

R2의 추가 두 대조는 C0A 원본 CSV SHA c134fcc16f78220abc00485cafd09e9596d3b091817112a88e19de7177d85966에서 GT 상태오차나 C2 효과를 보지 않고 선택했다. t>=30, pose525 제외, delta_tap=0의 |physical_e_mp| 최소(동률 최소pose)는735, |delta_tap| 최대인 shift(동률 최소pose)는507이다.735의 eMP_s=0.00009602797931129725,507의 delta_tap=6이다. 기존 hotspot과 이미 공개한 RF를 사후 진단용으로 택했다는 한계를 유지한다.

대조 명칭은 중심pose의 선택 조건이다.735의±1초11pose 전체가 no-shift라는 뜻은 아니다(실제 tap-shift1pose,최대|eMP_s|0.010047561265101757).507의±1초는11pose 중tap-shift7pose,최대|eMP_s|0.3713856100205286이다. 창/선택 규칙은 바꾸지 않고 모든 패킷을 포함한다. 이를 순수 yaw-only·tap-only 대조나 창 전체의무오염 보장으로 읽지 않는다.

총11창×2bias×20seed=440 창 조건. 창 조건마다 2gate모드×3개입arm=6 재귀 궤적, 합계2640개. FF는 기존 수용 Full trace를 공통 비교로 재사용하되 DEV에서 원본 source full recursion 일치를 검사한다. DEV seed10은22창 조건/132개입궤적, 잔여 seed11–29는418창 조건/2508궤적. DEV 성공을 본 뒤 수치/선택 기준을 바꾸지 않는다. seed10을 잔여 단계에서 반복하지 않는다.

## 재귀 수학과 계산 재사용

C2a: 기존 Full BASE mask를 시점별로 고정한다. MB_VAR의 x/P/h/H/K/Rvar는 각 arm의 재귀 궤적에서 다시 계산한다. 같은 mask가 같은 gain/P라는 뜻은 아니다.

C2b: 각 arm의 자체 BASE shadow x/P를 원래 online.replay와 같은 predict→SourceFFD→joint NIS<=9.210340371976184→전체 수용/거절→Joseph 순서로 진행한다. 이 shadow의 해당 arm 관측 이력이 다음 BASE prior를 결정한다. MB_VAR NIS를 BASE gate로 대체하거나 채널별 gate를 만들지 않는다. Full muBASE/RBASE는 유지한다. C2a의 BASE 이력은 기존 Full shadow 참조이며 새 hybrid shadow를 진행하지 않는다.

MB_VAR의 rho는 predict 전 이전 posterior의 anchor-XY 거리다. sigma_b=interp(rho,[0,1.5,3,6,10],[.011,.020,.050,.120,.240]); Rvar=RBASE_F에 (s,s) 항 sigma_b²만 더한다. W0이므로 Reff=Rvar. original online.joseph의 S 대칭화, gain, Joseph 대칭화와 accepted yaw wrap을 그대로 사용한다. source의 [x,y,yaw,bg] 단위는 m,m,rad,rad/s. Q_input=diag(2e-5|ds|,radians(.015)²dt,0), k0 identity predict를 그대로 쓴다.

첫 개입 시점 k0 직전까지는 FF와 모든 상태가 동일하므로, 동결 Full MB_VAR posterior와 C1b의 검증된 Full BASE posterior (k0−1)를 prefix checkpoint로 재사용한다. k0=0은 원래 control.x0+[0]/packet.P0. controls의 전역 index를 유지해 k0에서 해당 predict를 한 번 수행한다. 창 이후 경로 끝까지 계속 진행한다. prefix의 pose별 결과는 기존 Full trace를 참조하고 인과 차이는0이다. 이는 관측 개입 이전 계산 재사용이며 S3 checkpoint 복구 처치가 아니다. DEV에서 각 경로/bias의 FF from-t0 재현6건 및 모든22창의 seed10 prefix-vs-from-t0 개입 궤적 비교를 독립 검증한다. 이6건은 새 구현의 원본 일치 검사이며 기존 Full 성능 평가를 새로 수행한 것으로 세지 않는다. 실제 검증 계산 횟수는 숨기지 않는다. 비교는 mask exact, x/P/H/R/K atol/rtol1e-10, yaw circular다. 임의 새 checkpoint·사후 길이 단축은 금지한다. 같은 시점의 독립 branch들을 SourceFFD.batch에 함께 넣는 계산 배치는 허용하되 branch의 상태/공분산/관측/이력은 공유하지 않으며 scalar reference와 DEV에서 비교한다.

## 기록과 evaluator

각 재귀 시점에 control ds/gy/dt, Q_input/F/G/Q_state, prior/post x/P, h/H, Full mean, sigma_b/rho/Rvar, K, innovation/NIS/mask, C2b BASE prior/post x/P/h/H/NIS, pose/t/개입flag를 저장한다. 원래 Full 상태·mask와 C1b BASE prefix 입력 SHA/index를 기록한다. SourceFFD의 active cell/FP tap/margin은 감도 진단이며 H_psi는 s/rad이다. source h_GT는 원래 연속거리+B_OLD/FFD surrogate이며 물리 Native-LoS 관측과 동치라고 하지 않는다.

분리된 evaluator에서 원래 GT에 SourceFFD를 적용한 h_GT/H_GT를 계산하여 epsilon=z_arm−h_GT−muFull, delta_h=h_GT−h_prior, nu=epsilon+delta_h 항등식을 검사한다. physical eMP는 C0A의 noisefree Full−LoS r/s와 tap 차이를 사용한다. source의 가상검출 tap과 실제 RF tap을 구분한다. GT h/H나 오차·NEES를 필터/gate 함수에 전달하지 않는다.

XY Euclidean[m], Heading circular absolute[degree], bg[rad/s]를 평가한다. NEES3는 e[:3]^T P[:3,:3]^-1 e[:3], NEES4는 full P와 bg GT를 사용한다. yaw error를 rad로 wrap한다. Cholesky PD/finite 검사 후 solve, jitter/clipping/pinv 금지. GT에 bg 정답이 없으면 NEES4를 NA와 사유로 표시하고 추정/0 가정으로 채우지 않는다. Heading68=1sigma,95=1.959963984540054sigma; XY95는 mahalanobis2<=5.991464547107979; NEES upper95 df3=7.814727903251179/df4=9.487729036781154 참고값. 같은 RF·조건부 표본의 기술적 coverage이며 NEES 감소만으로 일관성 개선을 확정하지 않는다.

개입 시작 기준 [0,2],[2,5],[5,10],[10,20]초의 Heading/XY 절대오차 적분을 실제 t trapezoid로 계산한다. 단위 deg·s와 m·s. 각 구간의 양 끝 격자가 없으면 NA/가용분모와 사유를 저장하며 부분 적분을 완전 구간이라고 부르지 않는다. 전체 t>=30의 Heading/XY RMSE·mean absolute 및 NEES/coverage를 보고한다. 원본 prefix를 포함한 같은 전체 분모를 쓴다. FF 대비 paired차이와 C2b−C2a 차이를 각 arm/seed/창/bias별로 모두 유지한다. 20개 seed 요약은 중앙값·최소·최대와 개별값, 독립 RF 표본의 신뢰구간이나 eventwise 표준오차를 만들지 않는다.

창 내 첫 수용 진단은 (a) 실제 전달한 s가 Full일 때만 기존 S1의 |eMP_s|>.20 AND accepted, (b) 원본 Full/LoS RF의 tap-change pose AND accepted를 별도로 정의한다. FL/LL은 s를LoS로 바꾸므로(a)의 Full s오염 표시는0이다. (b)는 원본 RF pose 진단이며 hybrid나 LL이 실제 Full tap을 유지했다고 주장하지 않는다. range 큰오차의 임의 이진 임계값을 새로 만들지 않는다. 없으면 NA. 창 내 corrected epsilon 및 physical eMP_s/r autocorrelation lag1–10은 lag 양쪽 subvector를 각각 중심화한 Pearson 상관으로 계산하며 두 점 미만/분산0이면 NA. 개입창 내의 t=0 기준1초 bin과 GT XY 누적거리0.2m bin으로 RF/오차를 별도 기술한다. 경계는 floor((t+1e-9)/1),floor((누적거리+1e-12)/.2)다. 이는 evaluator 전용 층화다.

## 승인·중단·주장

SPEC_APPROVED→구현/합성검사→정확한 코드/입력/runtime SHA 독립 GO_DEV→seed10 DEV→독립 결과감사→새 GO_REMAINING→seed11–29→전체 누락/중복·결과·주장 독립감사→단계별 GitHub 게시. C1b의 GO는 C2 GO가 아니다. source FFT 관측 계산은 신규 Native RT와 구분해 횟수를 기록한다.

독립 검산은 모든 행의 motion/Joseph/이전posterior rho·Rvar/gate/평가/해시·키 연결을 확인한다. DEV의 source h/H는 모든 새 prior에서 검증하며, from-t0 참조의 공통 Full prefix는 경로/bias별1회 계산한 검증된 참조를 공유해 중복 계산할 필요가 없다. 개입 뒤 reference branch는 독립 코드의 재귀로 확인한다. 나머지114조건의 새 source h/H 검산 표본은 모든 trajectory의 전역index 25배수,첫/끝3점,개입창 양끝±1점,gate 변경·source tap/cell 변경 전후±1점의 합집합으로 미리 고정한다(BASE도동일). 변경검사는 이전 시점과 비교한다. 실제 표본수/전체수를 결과감사에 기록하며 source h/H 전수 재평가라고 표현하지 않는다. 이는 원래 SourceFFD를 고정 재사용하는 코드/수치감사로, 새로운 관측모델 미분 정확성이나 새로운 물리 ground truth를 검증하는 절차가 아니다.

baseline/prefix/항등식/해시/키/runtime/mask 불일치, nonfinite, covariance 비대칭/음의 고유값 tolerance1e-12*max(1,||P||2) 위반, solve/PD 실패, 누락/중복은 최초STOP. 부분 결과·실패조건·오차·로그를 보존하고 자동 재실행/잔여확장/사후 제외하지 않는다. 기준1e-10을 결과 후 완화하지 않는다. 효과 부호/크기는 수치 PASS 조건이 아니다. P 증가·NEES 감소·오차 감소를 별도 보고한다. 특정 창의 offline oracle 개입 기전만 허용하며 새로운 실제환경, 온라인 guard/복구 채택 또는 기존NO-GO/HOLD 변경은 허용하지 않는다.
