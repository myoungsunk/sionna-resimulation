# d0 + Full-CIR 편파 특징의 LoS 복원·Heading 정보 보존 검증 (2026-10-22)

## 고정 범위
- 원전: `research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz` (동일 pose의 Full/LoS 시뮬레이션 쌍).
- 실행 전 비교 정의를 동결한다. 해당 데이터는 이미 여러 연구에서 분석되었으므로 **탐색적 재검증**이며 독립적인 신규 환경 일반화가 아니다.
- Full CIR의 **전력 유래 요약 특징**(두 포트 s(fp), s(fp+o)-s(fp), fp index, 첫 탭 전력)을 사용한다. **원시 복소 Full CIR로부터의 직접파 분리 실험은 아니다.**
- `sL_+0`와 `e_true=sF_+0-sL_+0`는 학습 route의 지도 라벨/평가 정답으로만 사용; 평가 route LoS는 모델 입력·학습·하이퍼파라미터 선택에 사용하지 않는다.
- R2/R4/R5 route-heldout; 기존 POWER teacher, BASE trace의 d0, 사전 학습 teacher 사용 금지.
- d0는 Full s(fp)에서 **GT ±1°에 인위적으로 생성한 별도 pose prior의 LoS LUT 응답**을 뺀 값으로 구성; ±1° LUT 값은 기존 저장소 데이터로 계산된 값. GT를 이용한 합성 prior이므로 **실제 주행 중 IMU+odom prior 성능이라고 주장하지 않는다**.
- 실제 Full CIR 관측 특징 이외에 e_true·sL·sMGT(GT)의 직접 사용은 오라클 정답/오프라인 prior perturb 생성용만 허용.
- 모델: HGB max_iter=160, learning_rate=0.055, max_leaf_nodes=17, max_depth=5, min_samples_leaf=20, l2_regularization=1.0, random_state=20261022; 학습과 평가 모두 모델 변경/튜닝 금지. 결측은 train-route 중앙값으로 보정.
- `CIR_ONLY`: Full 유래 특징으로 e_true를 예측.
- `CIR_PLUS_D0`: 같은 특징과 d0로 e_true를 예측. train route에 ±1° 선형화가 아닌 저장된 정확 LUT prior response 두 개를 각각 추가하여 학습.
- `D0_DIRECT`: e_hat=d0. 순환성 음성대조군.
- `MIX_25`, `MIX_50`, `MIX_75`: e_hat=alpha*e_hat_CIR+(1-alpha)*d0 (alpha 고정).
- `RAW`: e_hat=0; `ORACLE_LOS`: e_hat=e_true (상한), `PRIOR_ONLY`는 heading 진단 참조.
- 측정 수준의 primary: `RMSE(s_hat-sL)` 및 RAW 대비 비율, 7-case·3-route별.
- heading 정보 보존 primary: 동일 Full CIR에서 prior yaw를 GT ±1°로 흔든 후 `nu_clean=s_hat-h_s(prior)`, oracle `nu_los=sL-h_s(prior)`; 양쪽 perturb 차분 `gain=<Δnu_clean, Δnu_oracle>/<Δnu_oracle,Δnu_oracle>`. 1이면 이상적인 민감도, 0이면 heading innovation 제거. **gradient만 보존해서 정확도가 개선되었다고 주장하지 않는다**.
- heading 단일갱신 secondary: `g=(sMGTp1-sMGTm1)/2` [s/degree], 가정값 `sigma_psi=3°`, `sigma_s=0.1`, 스칼라 gain `K=9g/(9g^2+0.01)`; `e_psi_post=δ+K*(s_hat-sMprior(δ))`의 RMSE; 실제 EKF가 아니라 **진단용 고정 게인**, 오염 잔차 covariance·cross-covariance 미반영.
- d0 검출 secondary: 학습 route의 |e_true| 95% 분위 극심 오차 라벨로 평가 route의 |d0| AUC 계산; 평가 route로 threshold 조정 금지.
- 결과: route, case, arm별 CSV, AUC, metadata QA, 사전 계획 원문과 GitHub commit/Actions run ID 기록.
- **제외 범위**: 초기화 시점 prior 오류 10° 이상, 실제 주행 동역학, 재귀 NEES·포함률, 실측 RF 위상 제약. 이 항목은 별도 후속 검증이 필요하다.

## 사전 판정
- Q1 LoS 복원: CIR_PLUS_D0가 CIR_ONLY보다 세 route 모두에서 LoS RMSE가 작아야 직접적인 d0 추가 이득으로 판정.
- Q2 Heading 정보 유지: CIR_PLUS_D0의 `gain`이 route별 0.8 이상이고, 세 route 모두 같은 모델의 고정 게인 heading RMSE가 `PRIOR_ONLY` 이하일 때 본 단계의 조건부 성공.
- Q3 d0 DIRECT: gain=0 (코드 항등식 확인), heading prior를 스스로 보정하지 못함을 negative control로 확인.
- 3개 route는 독립 반복 3개로 보고, 14 case-bias를 독립 실험이라 부르지 않는다.
