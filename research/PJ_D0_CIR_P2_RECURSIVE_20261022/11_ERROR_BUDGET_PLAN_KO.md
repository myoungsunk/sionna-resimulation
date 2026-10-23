# 재귀 필터 오차 예산 (실행 전 고정, 2026-10-23)

## 왜 반사실(10번)만으로 부족한가
- 설명 대상인 "재귀 손실"이 GT pose 정적 구간 편향비라는 근사 지표에 대한 차이로 정의되어 있다. 이 지표는 prior·gyro가 없고, 구간 길이에 따라 크게 변하며(R2_aA_m45: 30/65/130 패킷에서 0.65/0.97/2.59), 절대값이 실제 RMSE와 맞지 않는다.
- 기전을 하나씩 끄는 반사실은 서로 더해지지 않는다. 결합 효과를 놓칠 수 있다.
- 기전을 끄면 좋아지는지는 알려 주지만, 각 오차원이 heading 오차의 몇 %를 만드는지는 알려 주지 않는다.
10번 반사실 run(39944391557)은 교차 확인용 보조 자료로 둔다.

## 방법
실제 재귀 궤적에서 실현된 이득 K_k(gate 거부 시 0), prior에서의 H_k, 전이 F_k·G_k를 고정하면 상태 오차는 원천별 선형 합으로 정확히 분해된다.
$$\delta^-_k=F_k\delta^+_{k-1}+G_kw_k+r^{\text{pred}}_k,\qquad \delta^+_k=(I-K_kH_k)\delta^-_k+K_k\varepsilon_k+K_k r^{\text{meas}}_k$$
- w_k: odom·gyro 입력 오차(측정 − 참 증분, gyro는 참 bias 제외), r^pred: 전이 선형화 나머지, r^meas = h(x^GT) − h(x̂⁻) + H δ⁻: 관측 선형화 나머지.
- ε_k = z_k − ê_k − μ_k − h(x_k^GT): range, 편파 c1(FP 이동 0/±1/≥2 층별, 오프라인 라벨), 편파 c2(ê(d0 GT) − ê(d0 prior)).
- 원천: initial, odom, gyro, range, pol_c1_fp0/fp1/fp2, pol_c2, r_pred, r_meas. 합이 실제 오차와 1e-6° 이내로 같아야 한다(closure QA).
- 몫: share_s = mean(c_s · δψ)/mean(δψ²), t ≥ 30 s. 합이 1. 부호가 음이면 그 원천이 다른 원천을 상쇄한다.
- gyro bias 경로: 같은 K·H에서 F의 bias 열만 0으로 둔 선형 반사실과의 차이(필터 재실행 없음).
- 기억: 현재 오차 중 T(10, 30 s) 이전 상태 오차가 동차 전파로 남은 몫.
- arm: BASE, CIR(W_X1), WIDE_NOES(W_D0), PWIDE_NOES(P_D0), ORACLE. R = POWER V_s. 사다리 4와 heading RMSE parity 1e-6.
- 재귀 손실은 arm − BASE의 heading MSE 차이를 원천별로 나눠 직접 귀속한다.

## 판정
원천별 몫과 MSE 차이 귀속을 route × 조건 × case로 크기 그대로 보고. 임계값 없음. 진단 전용.
