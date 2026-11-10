# Heading·gyro bias 부분 갱신 및 S 허용폭 분석 — 적대적 적용성 리뷰

**기준일:** 2026-11-10 (KST)  
**검토 커밋:** `a4a0b60af00757f1f02817ea59c0362fb6d4d961`  
**대상:** `research/B_S_HEADING_FEASIBILITY_20261110`의 선형/비선형 보고서·코드·집계 및 관련 부분 갱신 연구.  
**범위:** 읽기 전용 코드 검토 + 동일 SHA의 기존 prior에서 대수 재계산. GitHub 수정, 새 RF 시뮬레이션, 신규 재귀 필터 실행 없음.

## 0. 요약 판정

1. 상태별 Heading·gyro-bias 부분 갱신은 수학적으로 정당한 비교군이다. 단순 output clipping과 다르며 공분산·교차공분산을 함께 계산해야 한다.
2. 제공한 선형/비선형 결과는 **s 허용폭에 따른 사전상태와 관측의 양립 가능성 검사**다. 부분 갱신 계수 alpha 또는 gyro-bias 갱신을 시험한 결과가 아니다.
3. 현재 겹침 규칙을 그대로 alpha 결정기로 사용하는 근거는 부족하다. 비선형 width10은 해로운 s 392건을 거르지만 유익한 s 524건도 거르고, 완전 제외로 해석할 때 heading 제곱오차 합이 +60.9913 deg² 증가한다.
4. 보고서의 G는 독립 gyro-only 95% 범위가 아니다. 기존 RF 영향을 받은 EKF prior의 ±1.96σ이며, 저장 truth와 대조한 실제 포함률은 R2 54.0%, R4 55.5%, R5 87.8%다.
5. 관측가능성 기반 부분 갱신은 명목 모델의 정보량·약한 방향을 다루지만, 그 RF가 편향되어 있는지 자동으로 알아내지 않는다. 현재 다중경로 오염 문제와 동일하다고 간주하면 안 된다.
6. s의 추가 기여가 연구 대상이면 `range 먼저 → 조건부 s 갱신만 부분 적용`을 명시해야 한다. joint range+s gain 전체를 축소하면 연구 질문이 바뀐다.

## 1. 출처·재현 범위

읽은 GitHub 자료: LINEAR_REPORT_KO.md, s_width_sweep.py, s_variance_components.json, nonlinear_20261110/{REPORT_KO.md,compute.py,report.py,COMPARISON.csv,CASE_INTERVALS.json,PROVENANCE.json}.

기존 Actions 42600632209의 R2/R4/R5 ZIP은 새 자료 PROVENANCE.json에 기록된 입력 SHA와 모두 일치했다. 이 ZIP의 B_FROZEN/OFF prior/H/P/R/nu를 사용하고, 기존 PRIMARY_3136.csv의 참값을 pose_id·timestamp로 연결했다. 원본 evaluator NPZ를 새로 다운로드한 것은 아니다. 선형의 두 위치 조건×8개 폭×3루트 및 전체집계를 독립 재계산했고 보고된 helpful/harmful/교차 수와 일치했다. 비선형 SourceFFD 전수 스캔과 원본 36파일 전체 해시를 이번에 재실행·재검증했다고 주장하지 않는다.

별도 계산 파일은 `recompute_frozen_audit.py`, 결과는 `AUDIT_RESULT.json`, `LINEAR_RECALC_*.csv`, `AUDIT_3136.csv`다. 비선형 집계의 해석은 공개 COMPARISON.csv 숫자를 전사해 계산한 별도 표로 구별했다.

## 2. 이번 허용폭 검사가 실제로 바꾼 것

관측값을 s, innovation covariance를 Sigma_nu라고 구별한다.

G = [psi_prior − 1.96 sqrt(Ppsi,psi), psi_prior + 1.96 sqrt(Ppsi,psi)].

A_s(c) = {psi: |h_s(x_prior,y_prior,psi) − (s_B−mu_s)| ≤ c·1.96 sqrt(Rss)}.

G와 A_s(c)의 교집합이 비어 있으면 reject이다. 위치고정 선형 검사는

|nu_s| > |H_s,psi|·1.96 sqrt(Ppsi,psi) + c·1.96 sqrt(Rss)

와 같다. xy allowance를 더한 선형 버전은 별도 집계다. 비선형은 같은 위치·같은 prior·같은 mu/R에서 실제 모델의 psi 곡선을 평가했다.

- width10은 s 잡음 **표준편차 허용폭의 10%**다. 전체 허용집합의 10%도, Heading 갱신의 10%도 아니다.
- 이 실험은 K/R/P를 바꿔 새 갱신을 실행하지 않았다. width 축소와 R inflation을 혼동하지 않는다.
- 같은 폭 축소를 실제 covariance 수정으로 구현하면 R은 감소하므로, 명목 KF에서는 s를 *더* 강하게 믿는 방향이 될 수 있다. 현재 진단은 좁은 band를 **거절 판정에만** 사용했다.
- no_extra의 extra는 거리 의존 s 관측 추가분산이다. gyro bias b_g의 process variance가 아니다.
- G와 A_s는 두 별도 marginal 범위의 존재 교차다. 이 검사 자체가 95% 신뢰구간 또는 posterior probability라는 보장은 없다.

## 3. 주요 데이터 결과의 적대적 해석

### 3.1 비선형화는 이 판정 규칙의 병목을 해소하지 않았다

|비선형 정책|유익 s 배제/1735|해로운 s 검출/1390|배제 전체|배제 시 Heading 손실합 변화(deg²)|
|---|---:|---:|---:|---:|
|current|3|0|3|+2.26953|
|no_extra|5|5|10|+3.56232|
|no_base|4|10|14|+2.89594|
|width75|4|5|9|+3.55075|
|width50|30|19|49|+15.89215|
|width25|187|119|306|+36.61158|
|width10|524|392|916|+60.99127|
|width0|1200|963|2163|+63.08371|

`net_heading_se = -sum(dh[mask & reject])`, `dh = squared_heading_error(range+s) − squared_heading_error(range-only)`다. 그러므로 표의 양수는 **S를 제외한 정책의 오차 증가**다. 개선량으로 읽으면 부호가 뒤집힌다. 이 값은 같은 기존 prior에 대한 단일 갱신 SSE 합이며 새 재귀 RMSE가 아니다.

width10에서 배제한 916건 중 harmful 비중은 42.79%로, 전체 accepted 집단의 harmful 비중 44.48%보다 높지 않다. 해당 operating point는 건수 기준으로 해로운 갱신을 농축하지 못했다. 이것이 모든 다른 score의 무용성을 증명하는 것은 아니다.

현재 폭에서는 선형/비선형 판정 차이가 0이며, 더 좁은 폭에서 일부 차이가 존재한다. 이를 '시스템 비선형성이 중요하지 않다'고 일반화하지 않는다. 이번 검사는 위치고정·현재 prior 근방 1차원 Heading 곡선에 대한 것이다. 위치–Heading 결합, 과정 모델, 다중 시점 선형화는 별도다.

### 3.2 실제 G 포함률은 명목 95%에 훨씬 못 미친다

|루트|전체 표본|G의 실제 Heading 포함률|G 반폭 중앙값|s 허용 반폭 중앙값|
|---|---:|---:|---:|---:|
|R2|979|54.03%|2.371°|0.2853|
|R4|742|55.53%|0.672°|0.2538|
|R5|1415|87.77%|1.114°|0.2981|

전체 실제 포함률은 69.61%다. 독립 gyro 참조를 검증한 결과가 아니라 기존 RF-fused prior의 경험적 포함률이다. 잘못되었거나 과신된 G를 좁은 판단 기준으로 믿으면, 정확한 s 관측이 G 밖의 참 Heading을 지지할 때 오히려 거절될 수 있다.

R4 k492의 공개 구간은 OFF prior −31.818805°, 반폭 0.517342°다. 기존 참값 −32.479924°는 이 G 밖에 있다. 이는 해당 시점 모든 s 보정이 유익하다는 뜻이 아니라, G를 참 Heading의 보장된 범위로 사용하면 안 된다는 구체적 반례다.

### 3.3 RF 정상과 유익한 s는 다른 라벨이다

정상 1743건의 기준은 Full의 B tap n_F를 양쪽 파형에 공통 적용한 |s_F(n_F)−s_L(n_F)|≤0.03이다. clean 파형 자신의 B tap n_L에서 읽은 값과의 차이가 아니다. 이 기준은 같은 tap의 파형 차이를 평가하며 정확한 Heading 또는 유익한 상태 갱신을 보장하지 않는다.

유익 1735건/해로움 1390건은 모두 기존 게이트가 수용한 3125행에서 'range+s vs range-only' Heading SSE 비교다. gyro bias 미래효과, XY 손익, RF 자체의 진위를 동일하게 평가한 라벨이 아니다.

## 4. 부분 갱신에 대한 추가 frozen-prior 검산

range-only 결과를 psi_r, 그 위에 조건부 s가 더하는 Heading 양을 d_s라 하자. 같은 선형화에서 psi(alpha)=psi_r+alpha*d_s, 0≤alpha≤1이다. 사후 참오차 e_r=psi_r−psi_true에 대해

L(alpha)=Σ(e_r+alpha*d_s)^2,  alpha_oracle=clip[−Σ(e_r*d_s)/Σ(d_s²),0,1].

이 oracle은 참값을 사용하므로 운영 알고리즘이 아니다. 사전 정의한 선형 교차 규칙의 각 reject 집단에 **하나의 공통 alpha**를 적용할 수 있다고 가정한, 고정 prior에서의 최대 가능성을 검사했다.

**결과:** 위치고정/포함 × 8개 정책의 16개 pooled reject 집단 모두 최솟값은 alpha=1(감쇠하지 않음)이었다. 전체 accepted 3125행에 하나의 공통 alpha를 적용한 경우도 동일했다. 예를 들어 위치고정 width10의 940건에서 Σ(e_r d_s)=−34.495999, Σd_s²=5.317139이므로 alpha의 비제한 최솟값은 1보다 크고, [0,1] 안에서는 1이 최선이다.

이것은 **현재 집단 선택에 일률적 부분 감쇠를 붙이는 것**에 불리한 증거다. 각 시점에 다른 alpha를 선택하는 새 판별기, gyro bias의 장기효과, 비선형 교차 집단에 대한 부분갱신, own-state 재귀 효과는 검증하지 않았다. 이 한계를 넘겨 'partial-update 자체가 효과 없다'고 결론 내리지 않는다.

## 5. 연구와의 정확한 대응

### 5.1 Brink (2017), Partial-Update Schmidt–Kalman Filter

Journal of Guidance, Control, and Dynamics 40(9), 2214–2228. DOI: 10.2514/1.G002808.

고전 Schmidt/consider는 일부 nuisance 상태의 평균을 측정으로 갱신하지 않되, 그 상태의 불확실성과 교차공분산의 영향을 유지한다. 부분 갱신은 그 비율을 0–1로 일반화한다. Heading 자체도 수학적으로 적용 가능하지만, 목표 상태 Heading을 nuisance처럼 제한하는 것은 통계적 trade-off를 추가하는 선택이다. 상태를 삭제하거나 bias variance를 0으로 두는 것은 Schmidt와 다르다.

본 검토에서는 정식 출판 서지/초록과 공개 학위논문의 수식을 교차 확인했다. AIAA 원 논문 전체 본문은 접근 제한으로 직접 열람하지 못했다.

### 5.2 Ramos et al. (FUSION 2021), Observability Informed Partial-Update Schmidt Kalman Filter

DOI: 10.23919/FUSION49465.2021.9626946.

명목 관측가능성의 null/weak direction과 nominal update의 정렬을 이용해 nuisance-state 그룹의 갱신 비중을 조절한다. covariance-based stochastic 방법도 제시한다. 공개 저자 원문은 재진입체 ballistic coefficient와 camera–IMU extrinsic calibration을 검증하며, 핵심 core 상태는 그대로 갱신한다. 전반적 nuisance 그룹 weight와 각 상태별 자동 독립 weight를 구별해야 한다. 논문 결론은 state-by-state 선택을 후속 연구로 명시한다.

**적용성:** gyro bias의 약한 식별조건에서 과도한 보정을 억제하는 발상은 관련성이 높다. **제약:** 명목 h와 잡음 가정에서의 관측가능성은 실제 편파 오염 여부가 아니다. 본 데이터처럼 P가 실제 Heading을 충분히 포함하지 못하면 P eigenstructure 기반 weight도 잘못된 확신을 계승할 수 있다. H_s,psi가 크다는 이유로 alpha를 크게 하면 오염된 s에 더 크게 반응할 수도 있다.

### 5.3 Ramos & Brink (FUSION 2023), Nonlinearity-Aware Partial-Update Schmidt–Kalman Filter

DOI: 10.23919/FUSION52260.2023.10224165. 공개 저자 preprint 10890.

과정·관측 모델의 고차항과 covariance에 대한 비선형 영향을 평가해 weight를 선택한다. 기본 모델은 zero-mean white Gaussian process/measurement noise다. 현재의 시간상관·방향의존 다중경로 편향을 자동 추정·교정한 연구는 아니다.

사용자 실험은 'heading 관측함수를 정확하게 평가하면 교차 판정이 달라지는가'를 시험했고, 논문은 '고차항으로 생기는 update 위험을 줄이는가'를 다룬다. 둘은 같은 실험이 아니다. 다만 현재 폭에서 선형/비선형 차이가 없었다는 결과는 이 허용집합 검사에 대해 비선형 탐색만 정밀화하는 것이 병목 해결이 아님을 지지한다.

## 6. 수학적 정당성과 실제 성능 보장을 분리

nominal optimal gain K와 D=diag(1,1,alpha_psi,alpha_b)에 대해

x_D=x_prior+DK nu,

P_D=(I−DKH)P_prior(I−DKH)^T + DK R K^T D^T

= P_K+(I−D)K Sigma_nu K^T(I−D)^T.

고정된 선형화·같은 prior·고정 D에서 성립한다. 따라서 P_D−P_K는 PSD이고, 모델과 통계가 정확한 선형 문제에서는 full optimal update보다 MSE가 항상 좋아지는 마법은 아니다. 이상적 full update의 정보를 덜 쓰는 비용을 감수하고, 모델 불일치·비선형 오추정에 대한 손실을 줄이려는 절충이다.

alpha_b=0이면 측정 단계에서 bias 평균과 Pbb를 보존하되 core–bias 교차공분산은 일관되게 갱신해야 한다. covariance가 nominal PSD라고 해서 실제 NEES/coverage가 맞는 것은 아니다. colored error, nonzero mean, prior/measurement correlation, current innovation에 따른 adaptive D는 별도 검증이 필요하다.

## 7. Heading과 gyro bias를 한 정책으로 묶으면 안 되는 이유

현재 측정 Jacobian은 H_s=[h_x,h_y,h_psi,0]. 보존된 3136행에서 H_s,b_g=0임을 확인했다. gyro bias는 순간 s의 직접 관측량이 아니라 과거 전파·교차공분산을 통해 갱신된다.

psi_(k+1)=psi_k+Delta_gyro−b_g dt 이므로 F_psi,b=−dt이다. bias 갱신 delta b_g는 그 시점의 yaw를 직접 바꾸지 않아도 이후 예측에서 대략 −T delta b_g의 누적 Heading 차이를 만든다(추가 관측 갱신이 없고 bias가 일정한 국소 대조).

따라서 단일 시점 Heading SSE 표는 alpha_b의 장기 이득·손해를 평가하지 못한다. alpha_psi와 alpha_b를 같은 값으로 고정할 근거도 없다. 특히 B0/seed10만으로 bias freeze가 좋아 보일 경우, 실제 비영/변화 gyro bias를 못 추적하는 비용이 숨겨질 수 있다.

미지의 RF 편향 b_s까지 고려하면 국소적으로

nu_s,j ≈ H_s,p,j delta p_j + H_s,psi,j(delta psi_0−T_j delta b_g) + b_s,j + epsilon_j.

b_s,j의 허용 시간형태가 넓으면 초기 heading 오류나 gyro bias 효과를 흉내낼 수 있다. 누락한 RF bias 상태를 기존 gyro-bias row 감쇠만으로 '모델링했다'고 부르면 안 된다. 또한 실제 gyro bias가 이미 틀렸다면 freeze는 그 오류를 유지한다.

## 8. 현재 질문과 맞는 부분 갱신 대조 구조

현재 자료의 label은 **s를 추가했을 때의 기여**다. joint gain DK는 range의 heading 보정도 함께 줄여 이 질문과 맞지 않을 수 있다. 첫 구분은 다음과 같다.

A. joint RF Heading/bias partial update: D K_[r,s] nu_[r,s].
B. range는 그대로, **조건부 s**의 Heading/bias update만 partial.

B의 공정 대조는 원래 prior에서 h/H를 고정하고 range를 먼저 갱신한 뒤, 그 posterior에서 s의 조건부 innovation과 gain을 계산한다. R_rs가 있으면 먼저 whitening해야 한다. 이번 저장된 R_rs는 모든 행에서 0이었다. 비선형 모델을 range 갱신 뒤 다시 선형화하면 다른 알고리즘 변화가 추가되므로 최초 대조에서는 금지한다.

같은 선형화에서 range→conditional s는 full joint와 정확히 일치한다. 실제 3136개 기존 prior에서 최대차이 3.55e−15로 검산했다. 이 위에서 s-stage D_s=diag(1,1,alpha_psi,alpha_b)를 적용하고, 상태·P·교차공분산을 함께 계산할 수 있다. 4개 고정 D 대수검산의 covariance identity 최대차이는 1.39e−17이었다. 이것은 재귀 성능 검증이 아니다.

alpha_psi=0이면 해당 s의 Heading 직접 보정만 제외하고, alpha_b=0이면 해당 s가 gyro bias로 흡수되는 경로를 차단한다. 위치에 대한 s 갱신은 유지되므로 위치 변화→다음 s 예측→Heading이라는 우회 경로는 남는다. partial update를 완전한 오염 차단으로 설명하면 안 된다.

## 9. 적용성 판정 및 필요한 반증

|항목|판정|
|---|---|
|상태별 partial-update 수식·Joseph/Schmidt covariance|적용 가능한 수학적 구조|
|현재 s 교차 규칙으로 갱신 비중 결정|현재 결과로 지지 부족, 일률 감쇠에도 불리한 frozen-prior 증거|
|관측가능성 정보로 gyro-bias 과잉 갱신 제한|연구 후보, 오염판별기와 구별 필요|
|강한 H_s,psi를 신뢰도 증거로 사용|불충분|
|공분산 eigenvalue만으로 안전 weight 설정|현재 P의 실제 포함률 때문에 위험|
|고정 위치 1프레임으로 gyro-bias 관측가능성 판정|불가; H Phi의 시간누적·교차효과 필요|
|새 재귀·독립 조건의 성능 입증|미실시|

먼저 비교해야 하는 것은 s의 완전 제외, s 정보량 감쇠, s→Heading partial, s→gyro-bias partial, 두 state partial, joint-RF state partial의 역할 차이다. 최초 테스트는 frozen common prior에서 label과 action을 맞추고, gyro-bias 판단은 같은 시작 상태에서 미래 horizon·초기 bias 조건을 바꿔 검증해야 한다. 현 결과를 근거로 즉시 active 정책을 켜거나 사후 최적 alpha를 배포하지 않는다.

적대적 필수조건: 깨끗한 s+잘못된 initial heading, 오염 s+정확한 gyro bias, 깨끗한 s+잘못된 gyro bias, 양쪽 오염, 지속/완만 RF 편향, 동일 prior에서 위치만/Heading만/P만 변경. 참값은 평가에만 사용하고, 실제 상태·관측의 불확실성을 판별 score에 다시 중복 융합하지 않는다.

**최종 판단:** 직접 Heading·gyro-bias 부분 갱신은 포기할 이유가 없지만, 현재 overlap 검사와 결합해서 채택할 근거는 없다. 이번 실패는 계수 alpha를 적용하는 수식보다, 어떤 보정을 줄여야 하는지 정하는 정보와 기준의 실패를 더 강하게 보여준다.

## 참고문헌 / 원본

- 사용자 고정 자료: https://github.com/myoungsunk/sionna-resimulation/tree/a4a0b60af00757f1f02817ea59c0362fb6d4d961/research/B_S_HEADING_FEASIBILITY_20261110
- Brink (2017): https://doi.org/10.2514/1.G002808
- Ramos et al. (2021): https://doi.org/10.23919/FUSION49465.2021.9626946
- Ramos & Brink (2023): https://doi.org/10.23919/FUSION52260.2023.10224165
- 2021 저자 공개 원문: https://www.researchgate.net/publication/354522139_Observability_Informed_Partial-Update_Schmidt_Kalman_Filter
- 2023 저자 preprint: https://easychair.org/publications/preprint/NBGF
- Ramos dissertation (2020; arXiv 2022 공개): https://arxiv.org/abs/2208.12402

문헌의 표·그림 실험 수치 전체를 본 데이터의 성능 보장으로 사용하지 않았다. PDF 스크린샷은 도구에서 cache 오류로 얻지 못했으며, 공개 원문의 추출 가능한 수식·본문과 서지에 근거해 리뷰했다.