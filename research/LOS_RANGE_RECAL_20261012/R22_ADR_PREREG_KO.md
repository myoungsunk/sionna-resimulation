# R2-2 사전등록 — A_DR(RF off) 일관성 실패 원인 분해 (실행 전 동결)

## 질문
P5에서 RF를 쓰지 않는 A_DR(IMU+wheel EKF)조차 pose NEES 평균 62.9(중앙값 8.3), pose95 coverage 64 %로 불일치였다. 원인이 (i) 필터가 모델하지 않는 생성기 오차항, (ii) 칼리브레이션 prior 불일치, (iii) 식별 불가능성(wheelbase 오차 ↔ gyro scale), (iv) 평가 통계 자체(런 내 시간평균 NEES의 상관), 중 무엇인가?

## 설정 (고정)
- 필터/생성기: 동결된 sensor-v2 코드(`RUN_01a124ff/source/src/qclean_uwb/drivesim`), EKF 6상태, A_DR = `use_range=False,use_s=False`, odom heading 사용. P5와 같은 초기 pose prior(xy 3 cm, yaw 2°), 칼리브레이션 prior는 코드 기본값.
- 경로: R2, R4, R5 (`inputs_R2/MOTION_*_legacy-euler.npz`, SHA256SUMS 참조). 드리프트 레벨 0,1,2. 센서 seed 6000..6299 (N=300, P5/G7 seed 범위와 분리). 평가 구간 t ≥ 30 s (P5와 동일). 셀 = 경로 × 드리프트 = 9.
- 통계: pose 3자유도 NEES(`e = truth − est`, heading wrap, `cov6[:3,:3]`). **앙상블 방식**: 셀·시간 k마다 300 seed 평균 ANEES_k. (P5의 런별 시간평균 NEES는 시간 상관 때문에 χ² 구간 판정에 부적합 — 이를 같이 보고하되 판정에는 앙상블을 쓴다.)

## 판정 기준 (사전 동결, 엔지니어링 허용오차)
셀이 **일관(CONSISTENT)** = (a) t ≥ 30 s 시간평균 ANEES ∈ [2.4, 3.6], (b) 같은 구간 앙상블 pose95 coverage ∈ [0.92, 0.98], (c) 경로 마지막 25 % 구간 ANEES ∈ [2.4, 3.6]. 구성이 일관 = 9셀 중 **9셀 모두** 일관. 보수적/과신 방향 분리: ANEES < 2.4 는 CONSERVATIVE, > 3.6 는 OVERCONFIDENT (둘 다 불일치).

## 구성 (한 번에 하나만 변경, 모두 N=300)
| id | 변경 | 해석 |
|---|---|---|
| B0 | P5의 A_DR 그대로 (생성 all, wheelbase unknown) | 기준 |
| G_none, G_gyro_bias, G_gyro_sf, G_wheel_asym, G_wheelbase, G_wheel_noise, G_gyro_noise, G_slip | 생성기 조건을 해당 항 하나(또는 none)만 활성, 필터 불변 | 어떤 생성 오차항이 불일치를 만드는가 (하나만 켜면 다른 항의 Q 때문에 CONSERVATIVE가 정상일 수 있음 → 해당 항이 OVERCONFIDENT를 만드는지만 읽는다) |
| F1_known_eb | 필터에 실제 wheelbase 오차를 알려줌 (`known_wheelbase_error` = 생성값; oracle) | 식별 불가능성 가설 |
| F2_prior_matched | 칼리브레이션 prior 1σ를 레벨 크기에 맞춤 (gyro bias = level dps, gyro sf = level sf, eps = level wheel_ratio) | prior 불일치 가설 |
| F1F2 | F1 + F2 | |
| D_Q×2, D_Q×4 | 공정잡음 k_s,k_theta,k_stheta,gyro_N 을 ×2, ×4 | **진단 전용**: Q 튜닝으로 일관성을 맞추는 것은 해결로 인정하지 않음 |

## 판정어 (사전 고정)
- 합법 구성 집합 = {B0, F2, F1, F1F2}(Q 튜닝·진단 구성 제외). 이 중 하나라도 일관이면 → 해당 구성을 **"DR 일관 기준선"**으로 채택 (R2-3 이후 RF 일관성 비교의 A 기준). 어느 구성이 처음 통과하는가(B0 < F2 < F1 < F1F2 순)로 원인을 기록.
- 합법 집합 모두 불일치 → **`DR_MODEL_MISMATCH_UNRESOLVED`**: 이후 RF 일관성 주장을 보류하고 R2-3 일관성 비교는 "상대 비교(A_DR 대비)"로 제한, R2-6은 정확도 비교만.
- F1(oracle)만 통과 → "wheelbase 식별 불가능 한계; 절대 pose 일관성은 RF/실측 없이는 불가"로 기록 (DR 단독으로는 해결 아님).
- 결과를 본 후 기준·허용오차·구성 변경 금지. 추가 구성은 "탐색(사후)"로 구분해 별도 표기.

## 부록 (실행 후 기록): 입력 저장 형식 변경
사전등록 커밋 시점의 `inputs_R2/MOTION_*_legacy-euler.npz`는 이 저장소의 `*.npz` LFS 규칙 때문에 업로드가 거부(`lfs.github.com … Forbidden`)되어 푸시 전 로컬 커밋에서 제거했다. 동일 배열을 `inputs_R2/MOTION_R{2,4,5}.csv`로 저장했고 원본 npz와 **비트 단위로 같음**을 확인했다(`float_precision='round_trip'`). 원본 npz의 SHA256은 `inputs_R2/SHA256SUMS.txt`, CSV의 SHA256은 `inputs_R2/SHA256SUMS_CSV.txt`. 스크립트(`r22_*`, `r23_*`)의 로더만 npz→CSV로 바뀌었고, R2-2 실행은 npz로, R2-3 실행은 npz로 수행했다(결과 파일 생성 시점). 변경 후 동일 task의 NEES 시계열 재현을 확인했다(B0, R2, drift 2, seed 6000). 판정 기준·구성은 불변.
