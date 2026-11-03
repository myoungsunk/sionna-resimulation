# Anchor-B 오류 발생–은폐–공분산 과신 인과 검증 계약 (제안, 미실행)

**상태**: PROPOSAL / NOT FROZEN / NOT EXECUTED.  
**목적**: R4-B 및 R5-B의 Full RF에서 필터의 수학적 구현과 통계적 모델 오지정을 구분하고, 물리적 다중경로 오차가 발생·수용·유지되는 단계를 최소한의 개입으로 규명한다. **모든 경우 성능을 개선하는 새 필터 개발이 1차 목적이 아니다.**

## 0. 고정 입력과 비교 대상

- 두 케이스만: R4_aB_m0, R5_aB_m0. Anchor B=(10,0,2.65)m, RX Mount=0°, TX +45°, RX ±45°.
- 원본 고정 비교: B0 및 L2 각각, Full과 원본 Native LoS, POWER_DIAG/POWER1/JOINT4. 필요 시 MB_VAR는 별도 개입용 *서로 다른* arm.
- 원래 RF Full/LoS 257 bins, 원래 5 Hz timestamp, pose_id, origin, 4상태 로봇 운동 입력, seed, h/H/Joseph update, first-path detector 모두 변경하지 않음.
- GT 입력은 시뮬레이션 label 생성/사후 평가/oracle 대조에만 사용. 새 online estimator feature에 GT나 실제 reflection labels를 입력하지 않음.
- 재귀는 t=0부터, 점수 t≥30 s. 수용 집합은 전체 타임라인에서 동결 정의. Full/LoS의 모델 평균·분산을 교체하는 경우 무엇을 교체했는지 명시.
- 기존 source code/trace SHA와 execution SHA를 변경 불가능하게 freeze. 이 문서는 SHA가 없어 실행을 승인하지 않는다.

## 1. 필수 입력·감사 선행 조건

1. 원본 [POWER·JOINT·SEP trace](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39376076166) 및 [D2/D3](../DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/README_KO.md) 로컬 확보, 양 케이스 B0/L2 항목별 SHA 일치.
2. [원본 Native R4-B ray decomposition](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41578225906) 참조. 이 실행은 R4-B 4개 pose만 확인했으며 R5-B ray data의 존재를 가정하지 않는다.
3. 동일 prior/gate replay로 기존 trace의 state, H, P, h, mean/R, accepted mask, NIS, 갱신량 재현; 고정 SI 값의 엄격한 비교 기준을 명시하고 단위 별 절대/상대 오차를 고정. 종전 E1–E4 protocol의 state/P 동등성 atol=rtol=1e-10은 참고하되 이번 스키마·수치 표현 변화와 맞춰 독립 승인 필요.
4. B0/L2가 동일 RF이므로 독립적인 물리환경 반복으로 취급하지 않는다.

## 2. 판별 가설 및 대응 개입

| ID | 질문 | 개입(대조) | 원인 판별 방식 |
|---|---|---|---|
| H1 | 초기 0–15초의 편파 오염이 최초 Heading 급증의 주원인인가? | t=0–15s에서 Full s만 matched Native-LoS s로 치환. 동일 original range·controls. 별도 fixed prior/gate one-step와 natural full recursion 모두 실행. | 최초 갱신 \(\Delta\psi\), 이후 prior/Heading/P·gate mask 차이 |
| H2 | 고민감도 오염 수용이 재귀 누적오차를 유발하는가? | R4-B pose168 중심 사전 동결 동일 길이 window의 s만 LoS 치환. 부호 대칭 placebo time window도 함께 실행. | Heading error 악화와 posterior coverage 변화; 다른 시점 개입 placebo와 비교 |
| H3 | 저민감도 + 큰 오염은 Heading 전파가 작을 수 있는가? | R5-B pose982 중심 identical window. same-prior/same-gate one-step 분해 및 full recursion. | 실제 \(K_{\psi s}\nu_s\) vs joint total, posterior change, gate flip |
| H4 | 근접 앵커에서는 관측이 깨끗한데 왜 리프레시가 안 되는가? | R4-B t≈60.2–87.2s vs R5-B 각 near-pass에서 동일 거리 기준 window; Full/LoS, 고정 prior, inflated prior P, original P 비교. | 관측공간 \(H P H^\top\), heading/position별 posterior observability, spatial/sigma calibration |
| H5 | joint gate가 오염된 s와 정상 r을 함께 버리면서 문제가 악화되는가? | 동등한 조건부 scalar linear-Gaussian range-first/pol-second 비교. 오염된 s만 거절 가능하도록 정확한 cross-cov accounting. | rejected packet의 range 진실 오차·효용 및 전체 natural RMSE/coverage. Range가 깨끗하다는 가정 금지 |
| H6 | 시간상관된 잔차 반복사용이 covariance 과신을 유발하는가? | Same mean/measurement physical stream에서 사전 선정 decimation m, R-scale와 temporally modeled error를 각각 단독 개입. | P 축소/Heading NEES/coverage·RMSE/수용률·상태변화 분리; m은 평가 결과를 보고 조정 금지 |
| H7 | 특정 물리 반사원이 편파오차를 만들고 EKF에 어떤 효과를 내는가? | R4-B pose525/168와 R5-B pose982 matched ray solver. LoS only / LoS+벽 / LoS+천장 / LoS+바닥 / Full. | 복소 port별 재합산, matched first-path detector, s/r 측정 변화와 fixed-prior gain; ray labels offline only |
| H8 | mount 45°가 반사원에 유리한가? | R4-B/R5-B 같은 pose/body yaw/time controls에서 RX 물리 Mount0/45의 paired Full/LoS 257 bins. | \(|e_{MP}|\), \(|g_\psi|\), \(g^2/R_s\), \(K_{\psi s}\nu_s\), recursive RMSE/95%를 동시에 측정 |

**모든 개입은 “다른 설정을 고정했을 때 무엇이 달라지는가?”라는 인과 질문에만 답한다.** 사후로 가장 좋아진 통계량을 선택하여 최종 방법으로 채택하지 않는다.

## 3. 저장해야 하는 per-packet trace

- route, anchor, mount, arm, channel, bias, seed, time_s, pose_id, GT XY/yaw (offline 평가), robot XY/yaw prior/posterior
- r, s, s_LoS, s_Full, e_MP, corrected RF ε_s, state projection δh_s, \(\nu_r,\nu_s\)
- h_r/h_s, H, R with offdiagonal, S, K, Pprior, Pposterior, gates (joint/marginal/whole packet/accepted)
- g_GT [per degree], H_ψ prior [per radian], post-Heading error, heading sigma, XY radial/tangential error and sigma, NEES, coverage
- raw first-path tap and +45/−45 powers, thermal/noise realization, reflection category, path delay and coherent complex H when physically available
- intervention flags for every substituted sample; whether gate was force-fixed or natural; whether h/H/P recalculated
- exact source SHA/input SHA/result SHA and independent aggregation checksums.

## 4. 게이트와 실패시 중단 조건

- **G0 SOURCE/PARITY**: 양 경로 B0/L2 원 trace, original Full/LoS, μ/R/controls, sample/mask 정확 재현. FAIL이면 다른 단계 진행 금지.
- **G1 SCIENCE**: zero-intervention control이 원 점수 및 시점별 state/P/NIS/accepted와 일치; 직접 포트전력→s 계산/변환 일치. FAIL이면 원인 해석 금지.
- **G2 INDEPENDENT CHECK**: \(\nu_s=\epsilon_s+\delta h_s\), \(\sum_j H_{\rm ray}=H_{\rm Full}\), 각 포트 간섭기여량 합이 전력차와 같음; s/degree vs s/radian 일관성. FAIL이면 reflection 원인순위 금지.
- **G3 CALIBRATION**: Heading/XY 전체 RMSE뿐 아니라 heading95/XY95, NIS/NEES, bias 상태, near/far 구간의 악화와 gate 비교. 평가 통계는 동일 population으로 짝지어 작성.
- **G4 INTERPRETATION**: intervention을 했다는 사실과 성공을 구별. 단일-route 감소는 메커니즘 지지일 뿐, 재사용 가능한 모델 승인 아님. Full에서의 개선과 LoS·L2에서의 악화, oracle/deployable distinction 모두 공개.

## 5. 채택·서술 규칙

- 개인적으로 유리한 hotspot 두 세 개만으로 **전역 모델이 개선됐다**는 주장 금지.
- 관측오차 발생의 물리적 분석과 EKF의 state estimate drift를 별도 도표로 표현.
- Rx mount 교체는 FFD 전체 복소 H가 변하는 물리 개입이지 포트전력 재라벨링이 아니다.
- s-only correction이 작은 혁신을 만들었다고 그 자체로 실제 상태 정확도를 보장하지 않음.
- 리프레시는 실제 근접 LoS RF가 보장되지 않으며 단일 anchor의 instantaneous \((r,s)\)로 4상태가 독립적으로 결정되지 않는 한계가 있다.
- 결과를 보고 고른 창·분산 배수·관측 주기는 개발용 진단임을 밝히고 홀드아웃 검증 없이 논문의 성공 알고리즘이라고 부르지 않는다.
