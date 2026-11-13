# G1-FLOOR-001 사전등록 변경 기록

2026-11-13 KST. 기준 사양은 myoungsunk/sionna-resimulation의 `1ce68f358aee003116be5e077ac5bbb4a5f2b7d9`에 있는 SPEC_KO.md다. 사용자 지시에 따라 S1 parity, sweep 역산, 공간 상관 및 S2 결과를 확인하기 전에 아래를 고정했다. 이때 확인한 자료는 입력 해시, 배열 형상과 좌표, TB3 원자료의 필드, 기존에 공개된 1 case smoke에 한정된다. 기존 사양과 충돌하는 항목에는 이 기록을 적용한다.

## S1

- J 곡선은 모든 case, 물리 station, RF seed, 잡음, span, k, XY 및 full/LoS 조합에 대해 절대 yaw [-180°, 180°)의 0.25° 격자에 저장한다. 탐색창과 prior σ는 같은 J를 재사용한다. 동률이면 격자 인덱스가 가장 작은 후보를 선택한다. 유효 관측이 3개 미만이면 곡선을 결측 처리한다.
- N30/N10 RF seed는 0…19, N0는 RF 잡음 없이 0…19의 prior/XY 표본을 생성한다. XY-P의 x, y 교란은 서로 독립인 N(0, 0.1²) m이며 동일 station·seed에서 channel, k, span과 공유한다. Prior와 XY에 독립 난수 흐름을 사용한다.
- 1차 90°는 19점·90°를 모두 충족한다. R4의 71.4° station은 40° 분석에 사용한다. 40°는 상대 yaw 범위의 중점 ±20°, 세 점은 0°, 10°, 20°에 가장 가까운 서로 다른 관측을 사용한다.
- 독립 prior σ={2°,5°}는 S1 기술 통계 전용이다. margin 진단은 route(R2/R4/R5) 단위 홀드아웃으로, 훈련에서 bad5 ≤5%를 만족하는 최대 coverage를 선택한다. 조건을 만족하는 threshold가 없으면 전부 기권한다. 이 규칙은 인과적 탐색창에 검증되지 않아 S2 gate에 적용하지 않는다.
- 같은 물리 station의 잡음 seed와 anchor를 새 공간 표본으로 세지 않는다. 집계 CI는 route×XY station 클러스터 1000회(seed 20261113)다.
- 주행 pose의 δs는 직진 구간 내에서 계산한다. 0.45 m lag 허용 구간은 [0.43,0.47) m다. Markov에 쓰는 case별 ρ는 직접 추정한 δs 상관을 [0,1]로 제한한 값이다. heading 등가 잔차의 절대 Jacobian 하한은 0.1 rad⁻¹이며, 1/e 길이와 함께 보조 지표로 보고한다.

## S2

- 1차는 N30, mount 0의 6 case, full H, XY-P, 19점·90°, k=0.0085, E₀=0, χ²₁(0.99) gate다. G1과 DR-cal은 동일한 E₀, run당 고정 β_res~N(0,0.45²), 매 station의 w를 공유한다. 사양에 인용된 β_uncal과 σ_w는 원자료로 재현 여부를 보고하고, 1차 비교는 사전 명시 값 σ_w=0.34°를 사용한다. 원자료의 정지 시간 직접 측정이 없으면 추가 정지 drift를 0으로 두고 0.0005°/s와 로그 체류 proxy의 곱을 별도 보고한다.
- KF는 DR 오차 E, run bias β, 평균 0인 측정 AR 상태를 추적한다. 관측은 wrap(z−ψ_DR)=−E+n이다. 세 상관 모델 모두 동일한 필터를 쓴다. 측정 스케일은 평가 route를 제외한 다른 route의 J 곡선에서 ±10° 정렬 조건으로 계산한 각도 오차의 2차 모멘트다. 이 오프라인 보정은 E₀=0의 정렬 상태에 해당하며 독립 5° prior와 평가 route의 오차를 사용하지 않는다. 보정 시 제외·결측 수와 10° 경계 선택 비율을 보고한다. AR 계수에는 case의 δs 상관을 사용한다.
- 탐색창 중심은 업데이트 직전 예측 ψ_DR−Ê⁻, 반폭은 min(180°, max(3√P⁻_EE,10°))다. DR 중심 민감도는 동일 반폭을 ψ_DR에 적용한다. 참 heading은 창 miss 판정과 오차 평가, 그리고 모의 참 경로 생성에 사용한다. 예측이 틀려도 miss를 강제로 제외하지 않는다. 후보가 없거나 관측이 결측이면 업데이트를 건너뛴다.
- 한 run은 한 case를 사용한다. case별 배정은 200 run을 33 또는 34개씩 나누고 34개를 받는 case는 반복마다 순환한다. 곡선의 잡음 seed는 매 신규 곡선마다 균등 추출한다. 셀과 Markov의 재사용에는 같은 seed의 동일한 J를 쓴다.
- (a) 같은 lane(y 부호)의 실제 x에서 0.45 m씩 전진하며 가장 가까운 RT station J를 쓴다. 유한한 RT 구간 끝에서는 같은 lane의 첫 구간으로 넘어간다. 이 반복은 주기 경계의 근사다. (b) 매 station 같은 case의 RT station과 seed를 독립적으로 뽑는다. (c) 확률 ρ로 직전 J를 재사용하고, 아니면 같은 lane의 x 순서에서 다음 사용 가능한 물리 station으로 넘어간다. lane 끝에서는 같은 lane의 시작으로 돌아간다. 71.4° station을 90° 곡선으로 취급하지 않는다.
- 바깥 bootstrap은 case 안에서 물리 station을 교체 추출한다. Anchor A/B가 같은 route·XY를 공유하므로 같은 cluster 인덱스를 두 anchor에 적용하되, 각 run의 J는 배정된 case에 한정한다. Markov에서는 중복 횟수를 시작 station 추출 확률에 반영하고, 다음 station으로 이동할 때는 원래 순서의 서로 다른 station을 쓴다. 각 반복의 안쪽 200 run과 1000회 바깥 추출에 재현 가능한 난수 흐름을 사용한다. 세 모델 간에도 동일 DR 난수와 동일 bootstrap station 추출을 사용한다.
- 판정 통계량은 station 1–17에 걸친 run당 평균 제곱오차를 합산한 뒤 구한 G1/DR-cal RMSE 비율이다. 95% CI는 바깥 station bootstrap의 2.5/97.5 백분위다. NEES는 posterior heading 오차의 제곱을 P_EE로 나눈 1자유도 값이다. 포함률은 |heading 오차|≤1.96√P_EE인 비율이다. 두 지표 모두 1–17에 걸쳐 집계하고 N=17 끝점도 보고한다.
- 모델 (b),(c) 각각에서 RMSE 비율 ≤0.8, CI 상한 <1, 평균 NEES 0.5–2.0, 95% 포함률 ≥0.88을 충족하면 DR-cal 기준을 통과한다. 둘 중 하나라도 미달하면 STOP이다. 통과한 경우 (a)의 RMSE 비율이 <1이면 ROBUST, 그 외 CORRELATION_SENSITIVE로 표기한다. (b),(c) 모두 κ_m=0.1°/m인 DR-nosweep보다 낮은 1–17 RMSE를 얻으면 PROCEED이고, 그 외 RESTRICT다. §7의 과학 판정은 Step 3 실행 권한과 별개다.
- E₀~N(0,5²)는 초기 정렬의 별도 분석이다. DR 중심, gate 없음, Gaussian AR(1), 40° 및 N0/N10는 민감도다. N=1…50의 끝점 곡선과 P95를 보고한다. N*는 1…N 누적 RMSE 비율 CI 상한이 최초로 1보다 작은 N이다. N=41…50은 유한 구간 후기 지표로 보고한다.
- STOP의 필요 floor는 같은 DR·gate·필터 구조에서 Gaussian n의 σ와 ρ를 그리드로 스캔한 모델 조건부 요구치다. 이 스캔은 경험 J를 사용하는 1차 판정과 별개다.

