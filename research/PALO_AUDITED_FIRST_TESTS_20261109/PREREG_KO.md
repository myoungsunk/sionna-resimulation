# PALO 세 후보 선행 검증 및 감사 계약

상태: 구현 및 실행 전 계약. 새 시스템 채택/안전성/독립 환경 일반화 인증을 의미하지 않음.
원본 입력: Actions 42466288321 single-metric-inputs ZIP SHA256 46c6070a138f181d73f21796160fba1d52291faef1097f77d205963ddc12e140. 원본 S4/LUT 4c43020; RF loader 151d1af2f30070780f43d94327e50c50d60c4103. 원래 source·controls·LUT·Rs=.0081·Q 유지.

## 공통 범위
R2_aB_m0, R4_aA_m0, R5_aA_m0, R5_aB_m0. Full/LoS × B0/L0/L1/L2 (32조건), 동일 초기 X/P·같은 운동 입력. 각 모델은 자기 상태/P 전파. 비교군 DR, S4(6.6348966), NIS .5, NIS 2. 새 센서·RF 분류기·새 multipath 물리모델 추가 금지. Ground truth/LoS은 점수와 원인분석에만 사용. R2/R4/R5는 이미 관찰한 같은 복도 개발 자료이며 미사용 환경이 아님.

## ① 정보식별성 사전검사
B0/L2 × Full/LoS의 S4/DR prior에서 1/2/5초 비중첩 창. 초기 4상태 perturbation을 정확한 동결 전이 F로 전파하고, 운동 과정잡음을 시점간 관측 공분산으로 주변화. 공통 RF offset c 하나를 whitening 후 소거. (a) 위치·bias nuisance를 소거한 prior-free heading 정보 (b) full P를 사용한 posterior heading/bias 정밀도 증가를 분리. 백색 관측 잡음과 rho=.5,.9 가정 민감도는 별도 표기. rho는 추정 결과가 아닌 스트레스 조건. 전체 정보행렬·PSD·Schur equivalence를 별도 계산으로 검산. 정보잔존이 미약하면 전체 주변화 필터 구현으로 넘어가지 않는다. ①은 필터 궤적 성능 실험이 아니다.

## ② 두 가설 최소 구현
정상 ON: 기존 LUT Gaussian 관측. OFF: s∈[-1,1]의 정규화 균등분포, 상태 갱신 없음. 모드 초기확률 OFF=.1/ON=.9, 전이행렬 대각 .95/비대각 .05를 결과 조회 전에 고정한다. 연구용 값이며 물리적 정답으로 주장하지 않음.
2개의 현재 모드 각각에서 가장 가능성 높은 history 하나를 유지(K2); K4는 모드당 두 history의 계산예산 대조. pruning 질량을 기록하고 선택 가지를 재정규화. 대조군은 동일 모드 관측모델/전이에서 매 시점 moment-matching으로 즉시 축약하는 K1. 모든 모드 확률은 갱신 전 predictive likelihood의 분산 정규화 상수를 포함한다. 참값 기반 branch 선택 금지. 가설 내부/가설 사이 공분산 모두 유지. mixture HPD 포함률·NLPD와 moment-ellipse 진단은 구분하며 혼합분포의 단일 NEES를 신뢰도 인증으로 해석하지 않음. 같은 IMU의 두 가지를 독립센서로 융합하지 않음.

## ③ 철회 기능 최소 구현
체크포인트부터 RF group을 빼고 X/P를 비선형 재생하며 active window에 extended RTS pass를 수행한다. 이것은 checkpoint replay+fixed-lag smoother 최소 구현이며 완성된 nonlinear factor-graph optimizer가 아님.
R2 event starts k=201,483,525; R4-A k=300,450,600; R5-A/B k=500,900,1150. 모두 알려진 대표·반례/위험 구간의 사전 고정 fixtures. 그룹 첫 3개 RF 제외와 유지 대조. 활성 창 2/5/10초, 10/20초 뒤 점수. 충분한 미래가 없으면 제외 이유 기록. 현재 출력과 지연된 과거 출력의 점수는 분리.
기계적 검증: 지연 삭제 후 재생 X/P가 동일 그룹을 처음부터 제외한 순방향 재실행과 일치해야 함. 수용 마스크는 각 branch에서 다시 계산. 같은 관측을 posterior prior에 중복 반영 금지.
추가 온라인 가능성 진단: 삭제 후보 생성 후 등장한 validation 관측만으로 ON/OFF replay predictive score를 비교(log BF>log9로 삭제). scoring model .9 Gaussian+.1 uniform은 고정. 참값은 선택에 미사용. 이는 사건별 지연 의사결정이며 새로운 전체 궤적 온라인 정책의 성능으로 주장하지 않음.

## 감사 3층
A 신규 코드: 차원/단위/각도/정보중복/GT 누출, projection Schur identity, likelihood 정규화·가지 mass·mixture covariance, RTS의 선형 batch posterior 일치, 철회와 fresh run parity, 인위적 fault 주입을 실제로 탐지하는지 검사.
B 재사용 코드: ZIP 및 source/LUT hash, 원래 core transition/LUT Jacobian의 유한차분, scalar-vs-batch 갱신, R2 S4·DR X/P/NIS/mask parity. 원본 재현 허용오차 X<1e-7/P<1e-8/NIS<1e-7, mask 차이0; 실패 시 결과 해석 중단. 허용오차 완화로 통과시키지 않음.
C 결과: 저장 원시 arrays로 RMSE/10초블록/q95·q99/NEES/포함률 재집계, posterior PSD/finite, 미래 정보 누출 없음, 같은 event/시간 모집단 비교, 제외/실패 누락 금지. 테스트의 numerical PASS와 알고리즘 efficacy/HOLD를 분리.
동일 저자가 별도 코드 경로로 수행하는 감사이며 독립 외부 과학 감사라고 주장하지 않는다. 단계별 audit receipt와 실패 기록·원시 배열·실행 source hash를 GitHub에 게시한다.
