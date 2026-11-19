# iPALO — Corridor 원거리 Kriging 대 POWER A/B 사전 계약 (2026-11-19)

**상태: CODE_PREPARATION / RUN_NOT_EXECUTED.** 기존 Corridor M8 Phase B의 결과를 본 이후의 후속 가설이며, 이전 B단계 seed 30–49는 탐색 평가로만 사용한다. G-T2/G-V 봉인 자산은 접근하지 않는다.

## 질문
원거리(`6.0 <= rho < 10.0` m)에서 편파오차 1차 모멘트 `mu_s`를 POWER 대신 station-sweep Kriging으로 계산하면 XY/heading 정확도와 무결성이 개선되는가?

## 변경 잠금
- **기준 모델**: `F2SKRWV` (Corridor station sweep, B 재가중 `mu_r`, Rrr; Kriging `mu_s` 0–6 m, POWER `mu_s` >=6 m; V형 c1/c0; normalized eta GM + KI, frozen NIS gate/gyro Q).
- **시험 모델**: `F2SKRWV_FAR_K`. 상기와 모든 항목이 동일하고 `mu_s`만 `6 <= rho < 10 m`에서 `krige_s(prior_x, prior_y, prior_psi, rho)`를 사용한다.
- `krige_online.py`의 **기존 코드/훈련 데이터/초모수** 사용. 6–10 m 미리 동결된 `e_s|2`: `(ell_x, ell_y, ell_psi, nugget)=(0.15 m, 1.5 m, 25°, 0.2)`, 이웃 최대 150.
- 학습표, 후처리, `R_ss`의 `c1,c0`, `eta`의 alpha/kernel, `mu_r`, `R_rr`, 양 조건의 입력, 자체 gate는 **변경하지 않는다**.
- 진리 자세는 **채점용으로만 사용**. Kriging 입력은 각 arm의 사전 예측 상태 `nav`; `rho`도 `nav`로 구한다.
- 원거리 Kriging으로 평균이 달라져도 V형 분산표를 사후 변경하지 않는다(변경된 평균에서 분산 재보정하는 문제는 후속 독립 시험).
- 동일 이전 상태에서 분산이 바뀌지 않음을 검사하되, 재귀 이후 서로 다른 posterior로 (a,R_{ss})가 달라지는 것은 정상적인 2차 영향이다.

## 1차 수행 범위
- R2/R4/R5, mount 0°, 앵커 B; `B0`, Q-일치 `L2_GYRO_ARW`; 기존 Phase B seed 30–49(각 20).
- 기존 `POINT_B.csv`의 `F2SKRWV` 지표와 **재생한 기준 모델을 먼저 정밀도 1e-8 이내로 대조**, 실패하면 즉시 중단.
- `F2SKRWV` 및 `F2SKRWV_FAR_K`를 같은 입력에서 재귀 EKF 실행하고, 수정 전후의 측정 채널 `mu_s`와 관측 갱신 결과를 별도 기록한다.
- 기존 `m8s3_score.py` 및 M7 평가 함수 사용: H2와 H2S 기준의 `N_I / N_A / N_J`, 거울해; 경로별·pooled XY/heading RMSE, Pose95, Heading95, NEES3; seed 짝 RMSE 비율·10,000회 seed bootstrap 95% 구간. **단순 지표 향상이 18/20 기준의 PASS는 아니다**.
- 기준 arm과 Kriging arm 둘 다 `CONDITION_PASS`는 `N_J >= 18/20` 및 60경로 거울해 0이어야 함. 원래 평가 기준 유지.
- 원거리 Kriging의 실제 online 사용 비율과 예측 `mu_s` 차이를 별도 출력. `6 m` 경계의 예측 전환·분산 불연속성도 진단.
- **새 확인 수행(후속)**: 새 센서/초기화 seed 50–69로 반복. 같은 RF 실현과 동일 경로라는 한계를 명시하며 독립 공간 일반화라고 부르지 않는다.

## 실행 환경과 정직한 상태
이 연구의 freeze/NPZ/LFS 및 `/home/claude/m8`, `/home/claude/m8cal`, `/home/claude/rel`의 원본 자산이 있는 Snowball 실행 환경이 필요하다. GitHub 웹 연동만으로는 원본 2-runner EKF를 직접 재생할 수 없다. 해당 자산 없이 점수를 추정하거나 재활용하지 않는다.

## 기존 기준 소스
- 분기 커밋: `1d36b227f7c6115dc26e9d3ee12ec98e3fe20fbd`.
- `dist_unc_m8/step3_fair/code/{run_m8s3.py,m8_replay.py,krige_online.py,m8s3_score.py}`.
- `dist_unc_m8/step3_fair/freeze/{SWEEP_TABLE_V.json,SWEEP_CAL_B_R*.csv,HEADING_HIST_B_R*.csv}`.
- `dist_unc_m8/step3_fair/tables/{POINT_B.csv,DECISION.csv}`.
- 경로별 빌드와 실행은 기존 `common.packet` 및 `gen_inputs_ext.py`의 law를 그대로 따른다.
