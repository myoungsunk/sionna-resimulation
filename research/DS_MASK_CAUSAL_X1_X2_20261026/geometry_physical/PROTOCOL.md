# 물리량 단위 기하 진단: 실행 전 고정

순서 A0″ → A → C → 결과 검토 → B. 기존 X1/X2/E1–E4 수정 금지.
14조건 전체, 주 분석 R2_aA_m45/R4_aA_m0/R4_aB_m0의 B0/L2 6조건.
B0/L2는 같은 RF의 쌍이며 독립 표본으로 세지 않는다. 운영 기준 0.7/0.3은 유의성 검정이 아니다.

## A0″: 코드 명세

source_model.py의 SourceFFD.spectrum/batch, checkout 0686b23ceeefb696bc158b32b39f8077c564ef5d.
원본 경로: D:/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849/p2/research/FFD_P0P3_20261016/source_model.py.
u=(a-p3)/r, r=||a-p3||, p3=(x,y,robot_z_m).
q_T=Rz(psi+m)^T u, q_A=RA^T(-u), RA=diag(1,-1,-1).
m=0° 또는 +45°의 yaw offset. 고정 높이/앵커 위치는 P0_INPUT_MANIFEST.json의 조건별 값이다.
태그 전기장을 Rz(psi+m)로 세계 좌표에 회전시킨 후 앵커 전기장과 내적한다.
거리 r는 공통 전파 진폭과 주파수별 위상에 들어간다. Hann/IFFT/첫 경로 검출을 거쳐 편파비를 산출한다.
두 안테나가 같은 위치 차이 벡터의 반대 방향을 사용하며 별도 위상중심 offset 없음. 위치 키 lookup 없음. FFD 방향 lookup은 u 경로에 포함된다.
위치 의존성은 u와 r뿐이다. psi는 q_T와 세계 좌표 전기장 회전에 함께 유지한다.
E1 14조건 × 5alpha의 모든 posterior 및 prior 시점에서 원본 h_s와 별도 G를 비교한다. 절대허용차 1e-12. 불일치 시 중단.
UNCUT의 해석 Jacobian도 원본과 절대허용차 1e-12로 비교한다.

## A: 기술 분해

점수 표본: t_s>=30 전체 packet, 거절 포함, 균등 packet 가중. 기존 heading/XY/3D 앵커 거리 RMSE와 절대 1e-10.
위치 출력 cm. XY 제곱합 항등식은 원 계산 단위 m²에서 절대 1e-12로 검산하고 cm² 잔차도 별도 기록한다.
beta=atan2(a_y-y,a_x-x); e_r/e_t는 GT 위치 기준 바깥쪽 반경 및 +90° 접선 투영.
psi/beta/phi 오차는 (-180,180]deg. phi는 기술적 상대각 오차이며 '편파가 보는 각'으로 해석하지 않는다.
wrap 없이 psi_error=beta_error+phi_error가 성립하지 않는 표본 수를 센다. 0이 아니면 해당 조건 분해 해석 제외. bias 항등식 절대 1e-12 deg.
작은 오차 beta_error≈e_t/d는 근사이며 비선형 잔차를 보고한다. 정확한 부호는 atan2(e_t,d+e_r)와 비교한다.

psi_eq: G(u(p_hat),r(p_hat),psi_true+psi_eq)=G(u(p_true),r(p_true),psi_true).
검색 [-20,20]deg, 0에 가장 가까운 근. 도함수는 원본 해석 Jacobian의 psi 열.
최소 |dh_s/dpsi|=1e-3 /rad (=1.7453292519943296e-5 /deg). 선택된 근에서 평가.
근 허용 잔차 1e-9(편파비), 각도 bracket 폭 1e-8deg. 불연속에서 부호만 바뀐 후보는 잔차 기준 미달 시 근으로 인정하지 않는다.
0에서 양방향 0.5deg 간격으로 탐색하고 발견 구간은 0.125deg로 세분한 뒤 이분법으로 푼다. 동률은 음의 근 우선. 낮은 기울기/미발견은 undefined.
유한 격자 탐색이므로 격자 사이의 매우 가까운 복수 근을 완전히 배제하는 수학적 인증은 아니다. 근 잔차/기울기/검색 실패를 저장한다.
undefined 비율>10%인 alpha는 해석 제외. A5는 alpha0/1 공통 유효 packet에서 psi_eq와 psi bias 변화를 함께 산출하고, 전체 E1 psi 변화도 별도 보고한다. 공통 결측>10%도 판정 제외. 분모 0.05deg 미만 판정 불가. 비율/분자/분모/부호 모두 보고하며 인과 문구 금지.
입력별 delta_s는 true psi에서 beta/epsilon/r 한 물리량씩 교체하고 태그와 앵커 양쪽에 동일 u를 사용한다. 상호작용=전체 위치 변화-세 변화의 합. |bias(delta_s_pos)|<1e-9이면 정규화 불가; 그 외 상호작용 비율>0.3이면 성분별 몫 해석 제외. 거리 음성대조 잔차/첫 tap 변화도 보고.

## C: oracle replay

UNCUT/CUT_ALL/CUT_AZ/CUT_EL/CUT_R × alpha0,1. 두 안테나는 동일한 u에서 파생한다. 보조 TAGSIDE/ANCHORSIDE는 실행하지 않는다.
차단 물리량만 GT 값으로 고정. 해석 chain rule에서 해당 x/y 미분 제거. psi 미분은 두 회전 경로 모두 보존.
range 관측 h_r/H_r는 원본 추정 위치를 유지. 편파만 차단한다. mask=A_B, 편파 평균/R 고정, P/K 재계산.
UNCUT 두 alpha의 전체 trace x/P/prior/H/h/mu/R/mask 및 모든 score가 E1과 절대 1e-10 일치해야 한다. 실패하면 차단 실험 무효/중단.
공분산 대칭/PSD와 거절 packet의 posterior=prior 검산은 기존 X1 기준을 유지한다.
G=bias(alpha1)-bias(alpha0), |G_UNCUT|<0.01deg이면 판정 불가.
f_signed=1-G_cut/G_uncut, f_magnitude=1-|G_cut|/|G_uncut|; 부호반전 별도 보고.
CUT_ALL f_magnitude>=0.7이면 위치→편파 예측 경로 필요성 지지(oracle); 0.3~0.7 부분; <0.3 다른 경로도 후보.
개별 주 경로 문구는 CUT_ALL>=0.7이고 해당 개별 차단>=0.7일 때만 사용한다. CUT_R의 효과가 작은 것은 이 데이터/개입에서의 음성대조 관찰이지 일반적인 거리 의존성 부재 증명이 아니다.
차단별 G 변화의 합과 CUT_ALL G 변화 차이를 상호작용으로 보고한다. 공분산/이후 gain 변화가 포함된다.

## B: C 결과 확인 후

delta_mu=muM_r-muB_r; c=BASE accepted 전체 시간 packet 평균; v=delta_mu-c.
B0/L2 c 동일성 절대 1e-12m, mean(v|A_B) 절대 1e-12m. 불일치 시 평균을 교체하지 않고 중단.
CONST/VAR alpha0,.25,.5,.75,1; FULL alpha1 대조 재실행, 나머지 FULL은 E1 재사용.
alpha0/E1 BB 및 FULL1/E1 MB 전체 trace 절대 1e-10. mask/편파/R 고정, 정상 재귀.
signed bias/MSE/시계열 상호작용 FULL-CONST-VAR+BB, 시계열 wrap 후 RMS.
|Delta bias_FULL|<0.05deg이면 비율 판정 불가. 정규화 bias 상호작용>0.3이면 몫 해석 제외.
0.7/0.3 성분 비중은 기술적 구성 비중이며 원인/배포 채택 근거가 아니다.

각 단계의 입력/코드 hash, 실행 로그, 반환 코드와 STOP/PASS를 기록한다. PASS는 수치 검증이며 가설 지지와 구분한다.
