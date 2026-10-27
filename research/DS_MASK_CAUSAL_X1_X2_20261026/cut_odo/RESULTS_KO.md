# CUT_ODO 결과

주 분석 여섯 조건의 α0/1 oracle replay 완료. B0/L2는 쌍이며 독립 표본으로 세지 않는다.

## 핵심 결과

방위각 gap은 R2_m45에서 43% 감소(부분), R4_aA에서 27% 감소(0.3 미만), R4_aB에서 32–34% 감소(부분)했다. 어떤 조건도 0.7 기준을 넘지 않았다. 시작 Heading→위치 경로만으로 range 보정에 따른 방위각 gap을 설명하기에는 부족하다.

Heading gap은 R2_m45에서 59%, R4_aA에서 96–98%, R4_aB에서 16–17% 감소했다. R4_aA는 방위각 gap이 상당히 남아도 Heading gap이 작아져, 두 지표를 동일한 현상으로 취급할 수 없다. R4_aA B0는 Heading gap 부호가 음→양으로 반전했지만 잔여는 +0.0052°로 작다. 모든 조건의 방위각 gap 부호는 유지된다.

CUT_RT가 다음 후보이나 이 실행에서는 수행하지 않았다. H4 전체 기각이나 H1 확정으로 확대하지 않는다.

## 정확히 차단한 경로

원래 원호 전파는 a=gyro−b_g dt, d=ds sinc(a/2)[cos(ψ+a/2),sin(ψ+a/2)]이다. 위치식의 시작 ψ만 이전 packet의 GT ψ로 교체했다. 추정 Heading 자체의 전파와 측정은 그대로 유지했다. 위치식의 ∂/∂ψ=0으로 하고 F/G에 맞춰 공분산을 다시 계산했다. gyro 및 b_g가 a를 통해 위치로 전달되는 경로는 남는다. 따라서 이 결과는 시작 Heading→주행 위치 경로의 개입이며 모든 방향 오차를 제거한 전파가 아니다.

mask=A_B, 편파 평균과 R, 거리·gyro 관측 입력, 초기 상태는 원래 값이다. 기존 h_s는 추정 상태를 사용한다. 평가 표본은 t≥30 s 모든 packet이다.

## Posterior gap 결과

G=bias(α1)−bias(α0). 각도는 도, e_t는 cm. f_magnitude=1−|G_cut|/|G_E1|이며 각도 분모 최소 .01°. 0.7/0.3은 운영 기준이다. 음수는 gap 확대를 뜻한다.

| case | bias | beta_G_E1 | beta_G_CUT_ODO | beta_f_magnitude | beta_decision | heading_G_E1 | heading_G_CUT_ODO | heading_f_magnitude | heading_decision | et_G_E1 | et_G_CUT_ODO |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R2_aA_m45 | B0 | -1.0541 | -0.6010 | 0.4299 | partial | -0.4493 | -0.1825 | 0.5939 | partial | -8.9430 | -3.9480 |
| R2_aA_m45 | L2 | -1.0654 | -0.6012 | 0.4357 | partial | -0.4442 | -0.1840 | 0.5858 | partial | -9.0510 | -3.9686 |
| R4_aA_m0 | B0 | -0.9718 | -0.7073 | 0.2722 | insufficient | -0.1393 | 0.0052 | 0.9624 | support | -8.7232 | -5.9382 |
| R4_aA_m0 | L2 | -0.9637 | -0.7041 | 0.2693 | insufficient | -0.1368 | -0.0028 | 0.9798 | support | -8.6720 | -5.9264 |
| R4_aB_m0 | B0 | 0.9376 | 0.6220 | 0.3366 | partial | 0.1986 | 0.1670 | 0.1589 | insufficient | 3.7765 | 2.3477 |
| R4_aB_m0 | L2 | 0.9225 | 0.6276 | 0.3197 | partial | 0.2003 | 0.1665 | 0.1687 | insufficient | 3.7489 | 2.3836 |

## 해석 한계

각도 gap 감소 여부와 부호 반전은 GAP_REDUCTIONS.csv에 함께 기록했다. 공분산과 후속 측정 gain도 달라지는 oracle 개입이므로 유일한 원인이나 배포 가능한 해결책으로 해석하지 않는다. 감소하지 않아도 남아 있는 gyro-bias→위치 경로를 포함한 모든 주행 적분 가설을 기각할 수 없다.

## 검증

차단 OFF 여섯 조건 α0/1에서 x/P/prior/Pprior/h/H/K/mu/R/nu/acc를 E1과 1e-10 이내로 검산한 뒤에만 CUT을 실행했다. 수정 상태 Jacobian은 유한차분과 1e-8 이내로 일치했고 Heading 평균 전파 보존을 확인했다. 입력 해시는 실행 전후 동일했다. 모든 검산 364개 PASS.

- [고정 프로토콜](PROTOCOL.md)
- [gap·감소율·부호 반전](GAP_REDUCTIONS.csv)
- [Heading RMSE·bias·std·NEES·95%·range·XY 지표](SCORES.csv)
- [prior/posterior 기하 분해](DECOMPOSITION.csv)
- [검산](CHECKS.json)

CUT_RT 및 추가 replay는 실행하지 않았다.
