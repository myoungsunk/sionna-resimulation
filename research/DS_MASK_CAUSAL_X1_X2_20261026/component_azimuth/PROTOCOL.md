# B 재개 및 방위각 이식: 실행 전 고정

사용자 변경을 반영한 별도 실행. 기존 X1/X2/E1–E4/A0″/A/C 및 B 중단 산출물 보존.
순서 B 재개 → 방위각 이식 → 적용 범위를 명시한 종합 보고. 새 학습 없음.

## 공통

source commit 0686b23ceeefb696bc158b32b39f8077c564ef5d. E1의 packet ID/시각/GT/동일 packet prior를 사용한다.
평가는 t>=30 전체 packet(거절 포함), 균등 가중. B0/L2는 같은 RF의 쌍이며 독립 표본으로 세지 않는다.
mask=A_B, 편파 평균/R 고정, h/H/P/K 정상 재계산. 공분산 대칭/PSD 및 거절 packet posterior=prior 검산 유지.
기준 0.7/0.3은 운영 기준이며 통계적 검정 아님. 상태/관측/공분산 재현 절대 1e-10.

## (a) B 재개

14조건(case × bias) 각각 자기 A_B 전체 시간축에서 c=mean(delta_mu|A_B), v=delta_mu-c.
mean(v|A_B)=0 절대 1e-12m. B0/L2 c 동일성 검산은 삭제한다. c_B0/c_L2/차이/mask 차이 개수는 기술값이다.
CONST/VAR alpha=0,.25,.5,.75,1. FULL 기존 E1 재사용, alpha1 대조 재실행.
CONST/VAR alpha0=E1 BB, FULL alpha1=E1 MB 검산 유지.
Heading RMSE/bias/std/95/NEES, range/XY RMSE 및 beta/phi/e_t/e_r의 bias/std/RMSE를 Arm×alpha별 보고한다.
GT 반경/접선 기준축, 위치 출력 cm. beta=atan2(a_y-y,a_x-x), 각도 wrap=(-180,180]deg.
상수 성분의 접선 이동은 mean(e_t_CONST)-mean(e_t_BB)로 정의한다. 같은 값은 mean(u_t_GT dot (p_CONST-p_BB))로 검산한다. 변동/전체도 같은 방식으로 보고한다.
4–9cm라는 예상 범위에 맞춰 결과를 선택하지 않고, 실제 signed 변화량과 FULL 대비 비율을 보고한다. FULL 접선 변화의 절대값<1e-6cm이면 비율 미정의.
s_c=Delta bias_CONST/Delta bias_FULL, s_v=Delta bias_VAR/Delta bias_FULL. 분모<0.05deg 미정의.
I_bias=Delta_FULL-Delta_CONST-Delta_VAR, |I_bias|/|Delta_FULL|>0.3이면 성분별 몫 해석하지 않음.
동일한 FULL-CONST-VAR+BB에 대해 Heading MSE 및 wrap한 Heading 오차 시계열의 RMS도 보고한다.
문구는 'Heading bias 변화에서 각 성분이 차지하는 몫(기술)'로 제한한다.

## (b) 충분성: frozen prior 방위각 이식

주 분석 case R2_aA_m45/R4_aA_m0/R4_aB_m0 × B0/L2=6조건.
신규 replay: 각 조건 4셀, (range alpha0/1) × (방위각 출처 E1 BB prior / E1 MB prior).
기존 C의 CUT_AZ alpha0/1은 GT donor 2셀로 재사용한다. 이식 구현의 CUT_AZ 경로는 기존 geometry_model.py를 byte-identical 재사용하고 provider만 바꾼다.
donor는 같은 packet의 E1 prior 위치. posterior/보간/다음 시점/현재 수신 Arm의 자기 prior로 대체하지 않는다. 시각/pose_id/배열 길이를 검산한다.
u의 방위각만 donor에서 가져오고, 수신 Arm의 추정 앙각/거리/psi는 유지한다. 태그/앵커에 동일 u 적용. donor 방위각의 x/y 미분은 0. psi의 두 회전 경로 미분 유지.
보조 TAGSIDE/ANCHORSIDE 실행하지 않음.

### 대조 및 분모

6셀의 방위각 미분 조건은 같다. 단, BB donor+alpha0/MB donor+alpha1은 E1의 자연 갱신과 Jacobian이 다르므로 E1 BB/MB 재현을 요구하거나 가정하지 않는다. 대조군의 E1 대비 bias 차이를 명시한다.
주 비율은 앞 단계에서 사용한 G_E1=bias(E1 MB)-bias(E1 BB)를 분모로 사용한다. 사용자가 준 G 표기와 기존 결과의 연속성을 유지한다.
추가로 G_control=bias(alpha1, MB donor)-bias(alpha0, BB donor)를 분모로 한 비율을 함께 보고한다. 두 분모/부호를 숨기거나 사후 유리한 분모로 교체하지 않는다.
forward=bias(alpha0, MB donor)-bias(alpha0, BB donor).
backward=bias(alpha1, MB donor)-bias(alpha1, BB donor).
각 forward/G, backward/G; |G|<0.01deg이면 미정의. 양 방향 모두>=0.7이면 해당 분모 기준 충분성 지지. 넘침(>1)과 부호 반전도 수치로 보고한다.
두 분모의 판정이 다르면 무조건적인 충분성 결론을 내리지 않고, 'E1 기준/동일 Jacobian 대조군 기준의 결론 불일치'를 보고한다.
동일 prior에서 GT donor를 provider에 넣었을 때 기존 CUT_AZ h/H와 1e-12로 일치하는 전 시점 함수 검산을 수행한다. 추가 GT replay는 하지 않는다.

## (c) 범위 및 종료

B와 이식 계산/검산이 끝나면 주 분석 6조건의 검증을 완료로 닫는다. 가설 지지/부분/비지지는 실제 수치로 남기며, 완료를 가설 PASS와 혼동하지 않는다.
R2_aA_m0/R2_aB_m0/R5_aB_m0는 '현재 위치→편파 차단만으로 설명되지 않음' 별도 트랙으로 기록하고, 같은 R2에서 mount에 따라 기전이 달라지는 이유를 첫 질문으로 둔다. 추가 replay는 이번 범위 밖이다.
R5_aA는 기존 gate 진단 트랙이며 주 분석 6조건에 포함하지 않는다.

## (d) 패키지 정리

다음 커밋에서 추적된 __pycache__/*.pyc만 제거하고 .gitignore에 __pycache__/ 및 *.pyc를 추가한다. 원본 로컬 frozen evidence는 수정하지 않는다. 기존 manifest가 cache를 포함하면 패키지 제외 목록을 별도로 기록하여 provenance를 보존한다.
