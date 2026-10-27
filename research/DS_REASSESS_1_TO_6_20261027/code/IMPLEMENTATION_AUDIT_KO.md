# 기존 코드·보고서 중대 이슈 감사 및 새 코드의 수정 사항

**범위:** GitHub `myoungsunk/sionna-resimulation`, branch `research/ds-x1-x2-results-20261026`, 증거 commit `2ee7313`. 아래는 *확인된 기술 오류*, *분석 해석 오류*, *검증되지 않은 모델 가정*을 분리한 것이다. 원본 파일은 변경하지 않는다.

## P0 / 가장 먼저 수정해야 할 분석 설계

### P0-A: EXDS 효과와 Δs 추가 효과가 혼동되었다

- 확인: 원래 `mu_recursive.py`의 `MU_R_EX`는 CIR 기존 특징, `MU_R_EXDS`는 기존 특징 + Δs를 각각 학습한 **서로 다른 전체 range mean 예측기**다. 둘 다 POWER mean의 replacement이다. EXDS−BASE를 Δs-only correction이라 부르면 안 된다.
- 증거: [mu_recursive.py](https://github.com/myoungsunk/sionna-resimulation/blob/2ee7313/research/PJ_DS_GATED_20261021/mu_recursive.py), [기존 MR 결과](https://github.com/myoungsunk/sionna-resimulation/blob/2ee7313/research/PJ_DS_GATED_20261021/results_murec/MR_SCORES.csv).
- 수정: Stage 1은 frozen E1 `A_B` 위에서 동일 초기조건, 동일 SourceFFD/원래 R/Q로 BASE·EX·EXDS·range oracle을 독립 replay한다. EX predictions는 저장된 EXDS 잔차와 EX 잔차의 차이에서 정확하게 복원하며 원래 `MR_SERIES.csv.gz` SHA를 E1 INPUT_LOCK에 대조한다.
- 경계: EX→EXDS는 피처 세트 비교지만 학습 자체도 두 모델이 달라지므로 do(Δs)의 완전한 단독 인과 효과는 아니다.

### P0-B: 서로 다른 CUT_RT 개입의 결론을 같은 실험처럼 비교했다

- 확인: [이전 CUT_RT](https://github.com/myoungsunk/sionna-resimulation/blob/2ee7313/research/DS_MASK_CAUSAL_X1_X2_20261026/pass_rs_azimuth/run_rt.py)는 **Arm 별 prior 추정 접선축**을 사용하고 PASS/ALL 스케줄을 구분한다. [후속 CUT_RT](https://github.com/myoungsunk/sionna-resimulation/blob/2ee7313/research/DS_MASK_CAUSAL_X1_X2_20261026/DS_CUT_RT_20261027/run.py)는 **GT 접선축**을 사용하며 적용 범위도 다르다. 보고서의 핵심 감소율은 평가창도 다르다.
- 결과: R2_m45/B0에서 후속 CUT_RT는 접선 gap 절댓값이 축소되는데도 방위각 gap은 약 4.8% 확대된다. H2 누설이 **방위각 gap의 필요 원인**이라고 확정할 수 없다. Heading gap 감소를 곧 인과율로 읽어서도 안 된다.
- 수정: Stage 4는 **PRIOR/GT × PASS/ALL**을 완전 요인설계로 같은 첫-pass 스케줄과 `t>=30`, 동일 첫-pass post 평가창에 저장한다. GT는 oracle로 별도 구분.

### P0-C: Arm 간 gap 감소를 절대 Heading 개선으로 읽으면 안 된다

- 확인: 새 GT CUT_RT의 R4_aA B0는 Heading signed gap이 작아져도 BB RMSE가 0.7116°→0.8987°, MB RMSE가 0.8006°→0.9536°로 악화된다.
- 수정: 모든 replay에 BB/MB 개별 절대 RMSE·bias·std·Heading NEES·XY·anchor range RMSE·first-pass post 지표를 저장. Gap-only 채택 금지.

## P1 / 중요한 미검증 가정 및 코드 제약

### P1-D: 보정 후 R_rs=0 가정은 아직 통계적으로 검증되지 않았다

- 확인: `x1/run_stage.py`는 original `Crs==0`을 assert한다. [SourceFFD 관측](https://github.com/myoungsunk/sionna-resimulation/blob/2ee7313/research/FFD_P0P3_20261016/source_model.py)은 동일 CIR에서 첫 FP를 뽑고, range HGB 특징도 CIR에서 추출된다.
- **코드 버그 판정 아님:** 동일 CIR이라는 이유만으로 조건부 잔차 공분산이 0이 아니라고 주장할 수는 없다. 측정 전통/계측 기반 근거가 없다면 가설로 남겨야 한다.
- 수정: Stage 2는 원본 Sionna Full CIR을 메모리맵으로 읽어 Hann·4x IFFT·30% 첫 경로 검출을 **새로 작성**하고, `z_s`와 1e-9 이내 일치 확인. LoS 예상 FP tap과 실제 Full RF FP tap을 구분한다. BASE/EX/EXDS의 range·편파 error/공분산·cross moment/lag, 블록-bootstrap을 계산한다. Stage 3은 **테스트 route 제외** R 추정만 허용하고, 기존 R과 shrink하여 평가한다.

### P1-E: SourceFFD LUT의 편미분은 모든 상태에서 유효한 선형 모델이 아니다

- 확인: Original `source_model.batch`에서 first-path tap은 threshold/argmax로 선택하고, Jacobian은 선택된 tap에서의 complex field를 미분한다. tap 전환은 비연속이다. original source docstring도 이는 normalized Bayesian measurement likelihood가 아니라고 명시한다.
- **코드 버그 판정 아님:** branch 안의 국소 Jacobian이 정확하더라도 recursive H linearization에는 regime 전환 위험이 있다.
- 수정: Stage 3은 ±1 mm, ±0.0001 rad full-observer central FD를 계산하고, predicted tap·interpolation cell이 바뀐 packet은 안정 구간과 별도로 표시한다. FD 차이를 계산한다고 자동으로 H를 바꾸지는 않는다. 예측 FP detector margin이 작은 온라인 구간 R_s inflation은 탐색적 아암으로 평가.

### P1-F: 원래 관측성 판단 범위가 전체 상태보다 좁다

- 확인: M3-pre의 2D 고정 궤적 평행이동 조건부 Fisher는 동적 `[x,y,ψ,b_g]`, 시간상관, polarization의 Fisher가 아니다. 회전 gauge는 앵커+모션 geometry의 대표적인 null 방향이고, 기존 M3도 모든 fixed-lag 기법이 실패했다고 주장하지 않았다.
- 수정: Stage 5는 frozen 원래 수용 mask, 창 시작 시의 GT/BASE prior 하나로 초기화한 **측정 없는 동역학 일관 nominal 궤적**에서 motion F 누적, 네/다섯 상태, range-only 및 원래 SourceFFD s를 사용한 data-only/prior-aided Fisher를 구분한다. rank/null 방향과 terminal 접선 불확실성을 계산하되, 식별 불가능하면 무한대로 보고한다.

### P1-G: 새 앵커 위치에는 기존 RF 잔차를 그대로 붙일 수 없다

- 확인: 물리 앵커를 이동하면 다중경로 환경, 입사각, FP tap, SourceFFD `s` 관측, learned μ/R 모두 달라질 수 있다.
- 수정: Stage 6의 relocate/additional anchor는 **이상적 range 기하 Fisher 계산만 한다.** 기존 앵커가 남을 때만 기존 SourceFFD s Fisher를 포함할 수 있고, 가상 range 오차의 독립성·동일 R을 가정이라고 명시한다. 같은 Stage 6의 bias-state/Q 실험은 반드시 **원래 앵커와 실제 frozen RF**에서만 실행한다.

### P1-H: 앵커 아래 '평평한 거리곡선'과 큰 Kalman gain을 동일시하면 안 된다

- 사실: `dr/dd=d/sqrt(d²+h²)`는 d→0에서 작아진다. 그러나 1차원 gain `K=P_d H/(H² P_d+R_r)`는 유한 P,R>0일 때 d→0에서 0으로 간다. 이는 선형 갱신이 무조건 크게 움직인다는 근거가 아니다.
- 수정: 변동을 설명할 때 실제 K_r·innovation·상태 공분산과 이후 propagation을 구분한다. Stage 4는 발생 시점 축과 세계/GT 축을 요인으로 분리한다.

### P1-I: 시점별 GT/posterior를 붙인 Fisher는 가짜 관측성을 만들 수 있다

- 분석 코드 자체를 새로 작성할 때 발견한 위험이다. 각 packet의 GT나 posterior를 명목 선형화점으로 쓰면서 그 사이를 motion `F`만으로 연결하면, 그 명목 점들이 실제로는 같은 odometry의 전파 결과가 아니므로 `F*g_{k-1}=g_k` 같은 회전 gauge 정체성이 깨진다. 이 경우 단일 앵커 range-only가 식별 가능한 것처럼 보이는 **가짜 rank 증가**가 발생할 수 있다.
- 수정: Stage 5/6 Fisher는 *윈도우 첫 GT 또는 BB prior를 초기값으로 삼아* 저장된 odometry만 적분한 동역학적으로 일관된 명목 궤적에서 `H_k,F_k,Φ`를 계산한다. 별도 unit test에서 단일 앵커 range-only 회전 null rank 부족을 재현하고, 원래 SourceFFD 편파를 더하면 그 gauge가 완화됨을 확인했다. 이 선택도 odometry noise와 전자파 비가우시안성 등 모델 제약이 있으므로 실측 확률적 observability 자체는 아니다.

## P2 / 보고서 편집상 정정

- `pass_rs_azimuth/RS1`의 R2_m45 `0.9847°→1.6010°`은 **RS1_BB** 비교다. 본문에서 이를 MB의 개선/악화라고 표기했다면 BB로 정정해야 한다. [RS source](https://github.com/myoungsunk/sionna-resimulation/blob/2ee7313/research/DS_MASK_CAUSAL_X1_X2_20261026/pass_rs_azimuth/RESULTS_KO.md).
- `share_ψ`는 signed 국소 선형 응답 몫으로, 통계적 posterior의 전체 정보 배분 비율이 아니다. `κ`는 H_s의 국소 크기 비율이며 실제 K와 같지 않다.
- H1(rng_rad 후속 접선 투영)은 세계좌표 장부상 기술 귀속이지 개입으로 증명된 단독 원인이 아니다. [세계좌표 장부](https://github.com/myoungsunk/sionna-resimulation/blob/2ee7313/research/DS_MASK_CAUSAL_X1_X2_20261026/DS_WORLD_LEDGER_20261027/RESULTS_KO.md).
- B0/L2는 하나의 동일 RF 시퀀스에 다른 gyro-bias 조건을 씌운 쌍으로, 표본수를 2배로 셀 수 없다. R4의 두 anchor case도 독립 route 두 개로 취급하지 않는다.

## 실제 원본 파일에 적용한 수정 여부

**원본 repository 수정: 없음.** 이 ZIP에는 새로운 independent execution package와 검증용 synthetic unit test만 넣었다. 원래 source/E1/P0/snapshot/git history를 덮어쓰는 코드는 없다. 원본 SourceFFD, 학습기 HGB를 임의 변경하는 '수정'은 오히려 parity를 깨므로 하지 않았다.
