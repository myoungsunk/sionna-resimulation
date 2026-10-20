# S2 fitter 설계 (사용자 승인)

기준 n4b_rf_errors.fit_model@034e57a는 다변량 Ridge 평균을 지원하지만 POWER의 binfield는 log_fp_power로 고정한다. 기존 ScalarPower는 평균 입력과 bin 입력을 동일한 1차원 scalar로 치환한다. GEOM 거리 bin 규칙은 기존 구현에 없다. 사용자가 GEOM·GEOM_Q 모두 학습 거리 d의 삼분위를 사용하도록 직접 승인했다. 이는 명시적인 다변량 평균 확장이다.

Q_POWER1: q 평균 입력/q bin. DIST_ONLY: 원 3D d 평균 입력/d bin. GEOM: 고정 순서 10개 평균 특징/d bin. GEOM_Q: 11개 평균 특징/d bin. GEOM과 GEOM_Q의 학습 거리 배열이 같으므로 cutpoints가 같다. GEOM에 q가 들어가지 않는다.

StandardScaler는 학습 X에 비가중 적합, Ridge(alpha=30, fit_intercept=True)는 기존 site weights로 적합한다. 잔차 Y−Ridge(X)에서 정규화 가중 W=w/sum(w), 평균 sum(W*e), 중심 공분산 sum(W*(e−mean)(e−mean)^T)를 사용한다(ddof 보정 없음). global_cov를 원 fix_cov로 regularize한다. 각 bin effective_n=(sum w)^2/sum(w^2), a=effective_n/(effective_n+100). offset=a*bin_mean+(1−a)*global_mean, C=fix_cov(a*raw_bin_cov+(1−a)*regularized_global_cov). 원 floors(0.1*R0_r,0.1*R0_s)와 상관 ±0.90 cap을 그대로 둔다. 이는 기존 fitter의 regularization이며 새 jitter/PSD projection이 아니다.

삼분위는 학습 bin scalar의 비가중 numpy linear quantile [1/3,2/3], unique로 동률 cut를 합친다. searchsorted(side=right)로 경계 동률을 위쪽 bin에 넣는다. 범위 밖 값은 최외곽 bin, clipping 없음. unique cut 후에도 빈 bin 또는 15행 미만 bin이면 오류로 보존하고 중단한다. bin별 독립 격자, PCA, flatten, 위험 점수, GEOM에 숨은 q bin을 쓰지 않는다.

학습 기하는 GT로 계산하고 추론은 각 arm 자신의 RF 갱신 직전 prior로 계산한다. DIST_ONLY는 log d가 아닌 원 3D d다. provider에는 GT·미래·타 arm prior를 전달하지 않으며 nonradio에는 RF 특징을 계산하지 않는다. 모델은 fold별/all-old별 한번 저장하고 모든 seed·bias에서 재사용한다.
