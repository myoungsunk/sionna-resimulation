# 실행 전 고정 정의

## 사용자 승인 수정
- M2: 창 끝 prior 추정 접선축을 세계좌표에 고정한다. 2D 위치 Fisher 행렬의 역행렬을 이 축에 투영해 반경 nuisance를 주변화한다. 순간 접선 감도를 더하지 않는다.
- M3: 회전 고정 2자유도만 Go 판정. 3자유도는 단일 앵커 주위 회전 gauge 특이성 진단으로만 남긴다. Heading prior를 추가하지 않는다.
- 대상은 R2_aA_m45/R4_aA_m0/R4_aB_m0/R5_aA_m0/R5_aB_m0 × B0/L2 = 10조건. BB/MB는 E1 names A0/A1에서 검색.

## 공통
- 원래 범위모델 h_r=sqrt(horizontal_distance²+height²)+B_OLD. B_OLD=-0.5315983906250129m이며 원본 코드에서 확인. 정렬에도 같은 모델을 사용한다.
- 기존 A_B 수용 packet만 정보/정렬 목적함수에 사용. 통과/사후 평가는 기존 GT P2 창. 통과 첫회가 주 판정, R5는 3회 모두 강건성 확인. B0/L2 둘 다 만족해야 case 성공.
- M1의 평가①: MB RMSE<=BB_OFF 또는 양의 원래 gap의50% 회복. 원래 MB<=BB이면 첫 조건으로 판정.
- ② 유지율=(BB_OFF range RMSE - MB_new range RMSE)/(BB_OFF range RMSE - MB_OFF range RMSE)>=0.8. 분모<=1e-12이면 NA(개선폭이 없으므로 유지율 정의 불가).
- ③ post에서 mean(abs(e_t)), mean(abs(beta_error)) 모두 MB_OFF보다 감소. abs(mean(error))와 구분한다.
- ④ MB XY RMSE와 Heading NEES가 각각 MB_OFF의1.1배 이하. ⑤ BB Heading RMSE가 BB_OFF의1.1배 이하.
- R4_aA 비악화 조건은 BB/MB Heading RMSE가 각각 OFF 이하로 정의한다. ①–⑤를 주3case 중2개 이상에서 만족하고 R4_aA 비악화를 충족해야 M1 Go. R5는 각 pass 결과와 전체점수 별도 보고.
- 첫 pass post는 사용자 확정 최소10초/다음통과/기록끝 절단 정의 그대로. 부동소수 경계는 시간 소수8자리로 정규화한다.

## M3-pre (replay 없음)
- 각 arm의 prior d_est<2m episode를 추출하고 GT pass 최소거리 시각을 포함하는 episode에 pass_id를 대응한다. 이 대응에 GT를 쓰는 것은 진단 구간 식별이며 최적화 입력에는 GT가 없다. episode 미포함은 NA, 임의 최근 episode로 대체하지 않는다.
- T_pre,T_post는 {5,10,20}의 직적9개. 기록 양끝으로 자르고 실제 길이, packet 수, 절단 여부를 기록한다. 다중 pass와 겹치는 창도 기록해 한계로 해석한다.
- q_j=posterior_xy_j-posterior_xy_windowstart. translation은 시작점의 세계좌표이며 초기값은 원래 시작점. 관측 target=nu_r+h_r (=z_r-mu_r).
- residual=(sqrt(||q_j+translation-a||²+height²)+B_OLD-target_j)/sqrt(R_rr,j). Huber f_scale=1.345, scipy least_squares, max_nfev=1000, ftol/xtol/gtol=1e-11.
- GT를 쓰지 않는 다중 초기값: 원 시작점 및 세계 x/y 방향 ±0.5m, ±2m (총9개). 최소 Huber cost 해를 선택한다. 성공 여부·cost·최적성·해의 퍼짐·near-tie 해를 기록한다. 전역 최적임을 주장하지 않는다.
- 2D 정보행렬=sum w_j H_j^T H_j/R_rr,j; w=min(1,1.345/|normalized residual|). residual variance로 재조정하지 않는다. 조건부 local Fisher이며 상관된 RF/고정 궤적의 오차는 반영하지 않는다.
- sigma_dt는 정렬 끝 추정 접선축에서 sqrt(u_t^T I^-1 u_t), 단위cm. 참축 sigma도 진단용으로 별도 저장. rank 조건: lambda_min>max(1e-12,1e-10*lambda_max). 미달시 sigma=inf, cond=inf, 판정NA. 미식별 방향을 pseudoinverse로 유한 sigma 처리하지 않는다.
- 3DOF Jacobian=[H_xy, H_xy dot R90(q)], 원3D 정보행렬의 rank와 null 검산을 기록한다. 동일 궤적을 앵커 주위0.1rad 회전했을 때 range 불변을 검산한다. sigma_dt=inf, result=UNIDENTIFIABLE.
- 주판정은 하나의 공통(T_pre,T_post)에서 MB 첫pass의 |e_t_end| 감소>=50%, sigma_dt<3cm가 주case2/3이상(B0/L2 모두)이고, R5두case 3pass전부(B0/L2 모두)에도 성립할 때 Go. 원래 |e_t|<0.1cm는 감소율NA. 가장 좋은 창 선택은 탐색적이며 독립 검증 성능이 아니다.
- No-Go는 이 고정 궤적·평행이동 검사 실패일 뿐, 모든 fixed-lag 방법 불가능 또는 앵커 추가가 필수라는 증거가 아니다. posterior 상대 궤적에는 이미 편파/Heading 정보가 섞여 있으므로 순수 range-only 전역 관측성 판정으로 확대하지 않는다.

## M2-pre (replay 없음)
- T={5,10,20}s. 창은 (t_k-T,t_k], 전체 T 확보된 시점만 평가, 통계는 t>=30. 갱신 벡터는 (K_r nu_r+K_s nu_s)*acc를 세계좌표에서 먼저 합산한다. S_t=u_t(prior_k)^T sum delta_xy.
- I=sum accepted H_r,xy^T H_r,xy/R_rr. 2D 상수 평행이동 surrogate이며 동역학/시간상관은 생략. sigma=sqrt(u_t^T I^-1 u_t). 같은 rank 규칙 적용, 특이창은 NA, 비율=|S_t|/sigma.
- 구간은 GT d: near<1.5, mid[1.5,4), far>=4. 모든 구간별 유효표본n>=30일 때 중앙값/p90. 특이/유효 개수 함께 보고.
- 각 T에서 MB near중앙값이 mid와 far 각각의2배 이상인 주case가2개 이상(B0/L2 모두)이면 Go. 선택T는 이 count최대, 그다음 주조건별 min(near/mid,near/far)의 중앙값최대, 동률이면 짧은T. R5는 다중통과 기술검증.
- 누적 갱신은 posterior 기반 상관된 양이므로 이 비율은 엄밀한 혁신 검정통계가 아니다. k={1,2,3}은 pre Go 때만 별도 고정 개입정의 후 실행한다.

## M1
- M1-0 OFF, a(lambda=.5,D=1.5), b(.25,1.5), c(0,1.5), d(.5,2.5), e(Rrr*4 when d_est<1.5).
- 현재 packet prior d_est로 switch, GT/미래데이터 사용 안 함. d_est==D는 OFF. 순간 prior 접선축으로 range gain의 XY만 변경. Joseph 공분산. 자연gate 보조는 이번 필수 sweep에 포함하지 않는다.
- OFF 10조건이 E1 전체 상태/공분산/모델/gain/혁신/mu/R/mask를1e-10 이내 재현한 후 개입. 고정A_B, 편파R/평균/Q 동일. M1-e만 rangeR을 변경한다.
- 방법1은 사전검사2/3와 독립적으로 진행한다. M2/M3 통합은 각 pre Go가 전제이며 통과하지 않으면 실행하지 않는다.
