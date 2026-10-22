# P2 — CIR+D0 WIDE 실제 주행 prior 기반 4-state EKF 재귀 검증 (실행 전 고정)

기준: 2026-10-22. 출발 P1R [run 39752301964](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39752301964), source commit 2f96c33, results commit da6bab8, frozen report adc62f5. 이 P2 계획은 별도 branch에서 수행하며 기존 P1/P1R 결과를 덮어쓰지 않는다.

## I. 질문과 성공 기준

- H1: GT 중심 합성 prior 대신 gyro+wheel+RF 경로의 진짜 EKF 예측 상태(x,y,psi,b_g)에서 d0를 계산해도 Full CIR+D0 WIDE 편파 보정이 BASE와 CIR_ONLY보다 heading RMSE를 줄인다.
- H2: 위 정확도 이득이 heading q99·미수렴·XY·NEES(1D 기준 1)·nominal 95% coverage를 훼손하지 않는다.
- H3: Δs range HGB를 추가하더라도 재수용된 편파 오염으로 heading이 악화하지 않는다(P2-C).
- 각 H의 결론은 **세 held route 각각** 보고한다. B0/L2 반복 및 case 7개를 독립된 route 14개라 주장하지 않는다.
- 사전 평가 기준: heading RMSE route 중앙값 R2/R4/R5에서 WIDE < BASE, WIDE < CIR_ONLY. q99 절대각오차 및 XY는 baseline 대비 현저한 악화가 없어야 하며, heading NEES가 1에 접근하고 95% coverage가 0.95에 접근하는 방향이어야 한다. 실패 항목과 실제 수치·범위를 모두 보고. 10초 시간블록 paired bootstrap CI는 exploratory로 표기한다.

## II. 원본 자산·학습 격리

- 평가 route H ∈ {R2,R4,R5}; train T=나머지 두 route. 7 cases, Full B0/L2 및 LoS B0 음성 대조. 0–2s, 2–10s, 10–30s, >=30s 분리. 초기 heading 0(기존 random), ±10°, ±20°. P0 heading σ=5°(과신) 대조와 오차 크기와 일치하도록 *초기에만* 지정한 보조 대조를 분리한다. **주행 중 실제 GT heading 오차에 맞춰 P를 조정하지 않는다.**
- SourceFFD와 원본 RF, 포트/first path observer, 원본 IMU·wheel noise seed, initial generator 모두 이전 frozen 조건 유지. 기존 artifact run IDs: source snapshot 39256621315, verified FFD banks 38875080492, final trace 39376076166. stage에서 SHA 원본 검증 필수.
- 평가 H의 GT, LoS CIR, 실제 e_s를 모델 입력, gate, 하이퍼파라미터, R 보정에 사용 금지. H용 POWER range μ_r/V_r는 strict held-route OOF; train T에서의 inner teacher는 T 내부 나머지 route만 사용.
- HGB 구성, ±1° NARROW와 U(-20,20)×3 WIDE(랜덤 시드 포함)는 P1R source 그대로. train T에서만 e_true=s_F−s_L 지도 라벨 사용. route H 완전 제외.
- WIDE ehat는 FULL−LoS **전체 편파 오차** 추정이다. 따라서 corrected s=sF−ehat 후 POWER μ_s를 다시 빼면 안 된다.

## III. P2-A: 재귀 정확도 (한 변수씩 변경)

- 동일 initial x0,P0 / IMU·wheel / RF packet으로 filter arms 독립 재귀. 이전 갱신이 다음 prior에 영향; 각 arm d0는 **자신의 실제 예측 상태**에서 계산.
- Arm: DR_ONLY(no RF), RANGE_ONLY, BASE_POWER(original μ_r,μ_s,R,gate), RAW(shared R control), CIR_ONLY, CIR_PLUS_D0_WIDE, CIR_PLUS_D0_NARROW(과신 음성 대조), ORACLE_LOS(오프라인 상한). Range predictor와 gyro model은 전 arm 동일.
- 공통 통제: CIR_ONLY와 WIDE는 **같은 사전 보정 R_s**와 같은 gate 옵션으로 평가한 arm-neutral comparison을 반드시 두어, heading 차이가 R 설정 차이에서 온 것을 보정기 효과라 주장하지 않는다. train T 안에서 inner LORO 추정한 arm-specific R_s는 **별도 보조** 결과.
- P2-A 우선 일반 EKF (한 packet 1 update, 기존 SourceFFD 물리 Jacobian, 2D χ²₂(0.99) gate, Joseph covariance). P1R에서 IEKF는 핵심 개선 요인이 아니었으므로 첫 재귀 기준선에는 넣지 않는다.
- z_s*=s_F−f(CIR,d0(prior)); μ_s*=0. z_r와 μ_r=POWER는 동일. range-pol 교차cov은 strict baseline의 diag 계약 유지. 올바른 R 품질은 B에서 검증.
- 모든 arm에 NIS, accept mask, raw/corrected innovation, delta heading, ehat, d0, Ppsi, gyro bias, XY state, observer Jacobian을 로그에 남겨 full causality 비교.
- BASE parity: 기존 4-state strict BASE replay와 동일한 first 100 step state/cov/gate를 1e−8 이내 재현. 관측 조건·시드·입력 미일치 시 성능 분석을 중단.
- 모든 임계값(η, α, tau, R, gate) 변경은 held H를 보지 않고 train T에서만 확정.

## IV. P2-B: 신뢰도와 오염 원인 (P2-A 이후)

- P2-A는 state-dependent pseudo-observation을 기존 H_s 물리 Jacobian으로 사용한 **진단적 baseline**이다. P2-A 정확도 개선만으로 posterior NEES calibration 성공이라 주장하지 않는다.
- train T의 inner recursive priors로 d0 입력 분포와 bias residual e_s−ehat의 분산, signed bias, FP-mode, lowfreq autocorrelation을 재검증한다. P1R GT±U20 teacher와 온라인 prior(위치·heading 오차 포함)의 OOD를 측정.
- 같은 matched gate·same R에서 H만 변경하는 arm과 R만 변경하는 arm을 분리. HGB는 계단 함수라 point derivative=0/불연속; 글로벌 G≈.92를 곧장 per-packet H_eff로 사용 금지. held H를 쓰지 않는 finite-perturb prior residual 테스트와 smoothed/surrogate H_eff 후보만 비교.
- decorrelation, temporal-bias OU/Schmidt, calibrated η를 비교할 때 heading RMSE와 NEES/coverage 둘 다 보고. 기존 GM consider가 accuracy를 악화시킨 과거 결과를 무시하지 않는다.
- Gate raw/corrected/range-only는 각각 독립 조건으로 조작하고 모델 효과와 gate acceptance 효과 분리.

## V. P2-C: Δs range 보정 결합

- P2-A/B에서 사전 선택한 WIDE 조건을 freeze 한 다음 Δs HGB range mean (training T only)을 결합한다.
- 동시에 BASE, Δs range-only, WIDE-only, Δs+WIDE, Δs+WIDE+GRAW, Δs+WIDE+RJ_D0/RJ_STATE vs no-rejection을 재귀 비교. 초기 ±20°에서 d0는 상태 오차를 오염으로 오인 가능함을 반영.
- anchor-distance / radial / tangential / XY RMSE, heading RMSE/q95/q99, NEES, coverage, gate accept switching, temporal persistence 전부 보고.

## VI. 실패 시 사전 약속

- P2-A heading RMSE 실패: 01_FAILURE_TO_P1R_RETEST_KO.md의 순서대로 (1) GT고정 위치 반사실 (2) 실제 위치 prior 오차만 적용 (3) 실제 heading prior 오차만 적용 (4) full prior joint 적용, 그리고 내부 R/gate 영향을 분리한다.
- P2-A heading RMSE는 좋지만 NEES/coverage 악화: P1R의 동일패킷 pseudo-observation prior 상관과 R residual stratification/temporal-correlation 수정. posterior P 수치만 맞추는 임의 floor는 쓰지 않는다.
- q99/초기 수렴 실패: 큰-|d0| gate, FP shift, H_s sensitivity, 1- vs multi-root, δ 분포 OOD를 train T에서 재검증한다. GT known δ on held H를 기준으로 online 선택하는 규칙은 금지.
- Δs range 결합 실패: range bias correction, combined gate acceptance, signed pol/range coupling을 같은 상태 prior/동일 sensor stream에서 분리; 학습 라벨을 held route로 다시 맞추지 않는다.
- 위 검증은 탐색적 실패 진단이며, P1R을 고쳐 얻은 새 모델은 같은 H에서 확증된 것으로 간주하지 않는다. 가능하면 새 held route/scene을 외부 테스트로 마련.

## VII. 실행 게이트
G0: 원전 SHA, sensor/SourceFFD, input/QAs, BASE parity.
G1: smoke 1 case full B0/LoS B0, 포함률·전파 PSD·GT 사용 계약.
G2: R2/R4/R5 × B0/L2 × 정상·±10°·±20° 전체 실행; 실패 cases 누락/제외 금지.
G3: arm-neutral R 및 arm-specific R, raw/corrected gate, t-split 분석. 좋은 값만 선택해 보고하지 않음.
G4: P2-B 통과 후 P2-C 결합 또는 실패별 P1R revision 수행.

## 제외
현재 연구는 두 수신 포트의 power CIR 편파 응답 기반이며, 장비 두 포트 복소 위상 동기화/원시 복소 직접파 분리 성공을 주장하지 않는다. 세 route는 이미 분석에 반복 사용된 개발 경로이고 새 환경 일반화 근거가 아니다.
