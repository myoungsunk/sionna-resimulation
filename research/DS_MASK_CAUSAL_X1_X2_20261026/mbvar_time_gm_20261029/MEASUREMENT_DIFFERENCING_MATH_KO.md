# Measurement differencing 수학 계약 (아직 EKF 구현·실험하지 않음)

## 1. 시작 모델

기존 측정:
\[
z_k=h(x_k)+\mu_k+B b_k+e_k,\quad
b_k=\phi_k b_{k-1}+\eta_k.
\]
\(B=[0,1]^\top\), 유색 편파 성분만 상태/시간 모델에 포함한다. 
\(e_k\)는 독립 측정오차로 가정하고 \(\operatorname{Cov}(e_k)=R_{w,k}\).
\(b\)와 \(e\)가 실제로 분리 가능한지는 별도 검증이 필요하다.
포트 전력 비선형 관측, 모델 불일치 및 cross-channel covariance가 있으면 단일 AR(1) 충분성은 불확실하다.

## 2. 유색 성분의 차분

시간 간격이 불규칙하면 
\[
\phi_{k,j}=\exp[-(t_k-t_j)/\tau].
\]
모든 시각의 전역 차분이 아니라 이전 **사용된** 시각 \(j\)의 z를 이용한다면
\[
y_{k,j}=z_k-\phi_{k,j}z_j
=h(x_k)-\phi_{k,j}h(x_j)+\mu_k-\phi_{k,j}\mu_j+
B\widetilde\eta_{k,j}+e_k-\phi_{k,j}e_j.
\]
\(\widetilde\eta_{k,j}\)는 \(j+1,\ldots,k\) 구간 FOGM innovations의 누적이다.
정상 분산 \(\sigma_b^2\)일 때
\(\operatorname{Var}(\widetilde\eta_{k,j})=
\sigma_b^2(1-\phi_{k,j}^2)\).
단, 과정잡음이 연속시간 FOGM에 맞게 정의돼야 한다.

비유색 \(e_k\)가 존재하면 잡음은
\[
n^*_{k,j}=B\widetilde\eta_{k,j}+e_k-\phi_{k,j}e_j.
\]
단일 차분의 공분산:
\[
R^*_{k,j}=B\sigma_b^2(1-\phi_{k,j}^2)B^\top+
R_{w,k}+\phi_{k,j}^2R_{w,j}
\]
(innovation 및 white e 독립 가정).
인접한 두 차분 간에는 **직전 측정의 \(e_j\)** 가 공유되어 
\(\operatorname{Cov}(n^*_{k,k-1},n^*_{k+1,k})=-\phi_{k+1} R_{w,k}\).
따라서 잔여 잡음은 MA(1)형 유색 잡음일 수 있으며, 통상적인 white-noise EKF에 그대로 넣으면 틀린다.

## 3. 이전 상태 미지수와 상태-측정 교차공분산

\[
h^*(x_k,x_j)=h(x_k)-\phi_{k,j}h(x_j)
\]
는 현재 상태만의 함수가 아니다. 이전 참값 상태 \(x_j\)는 모른다.
단순히 \(h(x_j)\)를 \(h(\hat x_j^+)\)로 대체하면 이전 상태오차가 유효 측정오차에 들어간다.

일차 근사:
\[
r^*_{k,j}\simeq
H_ke_k^--\phi H_je_j^+ + B\widetilde\eta+e_k-\phi e_j^{meas}.
\]
여기서 \(e_k^- = x_k-\hat x_k^-\), \(e_j^+=x_j-\hat x_j^+\),
\(e_j^{meas}\)는 이전의 **측정 백색오차**를 뜻한다. 
아래의 일반화된 갱신에 사용할 \(n^\star=-\phi H_je_j^+ + B\widetilde\eta +e_k-\phi e_j^{meas}\)는
상태 예측오차 \(e_k^-\)와 일반적으로 상관된다.

\[
C_k=\operatorname{Cov}(e_k^-,n_k^\star),\qquad
S_k=H_kP_k^-H_k^\top+R_k^\star+H_kC_k+C_k^\top H_k^\top
\]
\[
K_k=(P_k^-H_k^\top+C_k)S_k^{-1},
\quad
P_k^+=P_k^--(P_k^-H_k^\top+C_k)S_k^{-1}(H_kP_k^-+C_k^\top).
\]

\(R^\star_k\)는 이전 상태오차 등을 포함한 실제 유효 오차 공분산이며, 2절의
\(\operatorname{Cov}(n^*_{k,j})\)만으로 충분하지 않다.
여기에 \(C_k\)를 0으로 가정하는 표준 EKF는 검증 없이 사용할 수 없다.

## 4. 같은 결과를 처리하는 실현 가능 경로

- **안전한 기준 구현:** 기존 상태 + FOGM bias 증강. 5상태이며 2×2 측정 innovation 역행렬 유지.
- **정확한 differencing 구현 후보:** state lag 또는 cross-covariance를 저장하는 Gaussian-memory filter,
  또는 원시 관측과 full block covariance를 이용한 windowed GLS/KF.
- **단순 차분 EKF:** only analytic/negative control. 4상태에 naive white R*를 붙여 얻은 점수를 유효 해법이라고 주장하지 않는다.

## 5. 필수 단위 시험 및 release gates

1. 스칼라 선형-Gaussian 예제에서 정확 augmented KF와 full-covariance GLS 결과 parity.
2. \(e_k\ne0\)일 때 차분 후 lag-1 covariance가 \(-\phi R_w\)로 남는지 검산.
3. 불규칙 \(\Delta t\), 누락 packet 및 gate reject 이후 이전 사용 시각 \(j\) 갱신.
4. \(C_k\)를 계산/추적하지 않는 shortcut이 기대 오차 및 reported P에 만드는 차이를 계량.
5. RF 편파 모델에는 독립 연산 가능한 residual mean과 white+colored variance의 식별성 확인.
6. 시간 파라미터 및 보정 학습은 outer LORO 평가 경로 제외; 자체 gate는 별도 단계.

**주의:** D3의 lag-1 ACF는 \(\phi\)와 동일하지 않을 수 있다. 
관측된 \(\epsilon_k=b_k+e_k\)는 통상 \(\rho_1=(\sigma_b^2/(\sigma_b^2+R_w))\phi\).
따라서 lag1 상관만으로 \(\phi\), \(\sigma_b^2\), \(R_w\) 세 개를 식별할 수 없다.
