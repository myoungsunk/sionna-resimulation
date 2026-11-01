# 물리 관측구조→갱신→결과 검증 명세

계약: `DLP-PHYS-BRIDGE-012-001` v0.1 · PROPOSER · **전 실험 NOT_RUN**

이 문서는 기존 MB_VAR를 설명하기 위한 설계이다. 실제 효과의 방향이나 새로운 수치를 결과처럼 서술하지 않는다. 모든 주 결과는 R2-B/R4-B/R5-B의 B0/L0/L1/L2를 유지한다.

## 1. 수학적 대상과 단위

`x=[px,py,psi,bg]`, 단위 m,m,rad,rad/s. z=[r,s], 단위 m,1. H는 2×4, R는 2×2; Rrs의 단위는 m이다. 원본 motion f/F/Q와 실제 gyro/wheel 입력을 변경하지 않는다. θ gyro increment, position prior, t, accepted mask는 각각 별도 필드로 둔다.

공통 first-path tap에서 P±=|g±(n0)|², s=(P+−P−)/(P++P−). source FFD의 vector contraction, 좌표 회전, 주파수축, Hann/4N IFFT, strongest-port 30% detector를 그대로 사용한다. 이상적 cos(2ψ)를 실제 안테나 모델 대신 넣지 않는다. SourceFFD의 기존 continuous range bridge와 native integer first-edge r의 차이는 보존된 모형오차로 기록하며 이번 설계에서 sub-tap으로 교체하지 않는다.

안정된 detector branch에서 u∈{px,py,psi}:

    ∂s/∂u = 2[P−(∂P+/∂u) − P+(∂P−/∂u)]/(P++P−)^2.
    H = [[Hrx,Hry,0,0],[Hsx,Hsy,Hsψ,0]].

s는 위치와 Heading 양쪽에 의존한다. bg는 H의 직접 관측 열이 아니라 motion과 state cross-covariance를 통해 추정된다. Hsψ≠0을 4상태 전체의 전역 observability 증명으로 사용하지 않는다.

두 포트에 동일한 주파수-독립 복소 스칼라가 곱해지고 수신 잡음이 없는 경우 s와 상대 threshold tap은 불변이다. 이를 arbitrary common frequency-selective filtering, 열잡음 아래 SNR 불변, 포트별 phase distortion까지 확대하지 않는다. 거리 조건은 입사각·반사기하·약한 포트 SNR·detector 선택의 대리변수일 수 있다.

## 2. 서로 혼합하지 않을 잔차

동일 physical pose에 대해:

    e_prop = z_Full − z_Direct
    e_model = z_Direct − h_SourceFFD(xGT)
    e_total = z_Full − h_SourceFFD(xGT) = e_prop + e_model
    ε_B = e_total − μ_B
    ε_M = e_total − μ_M
    ν = ε + [h(xGT) − h(xprior)].

Direct는 같은 pose/frequency/port/observer 계열의 Native LoS만 허용한다. 다른 생성 경로의 LoS를 대입하지 않는다. GT는 이 오프라인 분해와 채점에서만 읽고, 필터 입력·lookup·회귀 추론의 feature로 사용하지 않는다. Full/Direct의 native tap이 다른 경우 그 차이 자체를 `TAP_MISMATCH` 층으로 남긴다. 원래 각 관측을 native tap에서 계산한 차이와, 공통으로 강제한 tap의 차이를 서로 다른 진단으로 기록한다.

E[ε²], centered Var(ε), mean(ε), raw RF error, prior innovation, posterior state error는 별개이다. 현재 추가 σ²를 정확한 true sensor variance 또는 시간 whitened covariance로 부르지 않는다.

## PB0. 입력·분모·기준선 잠금 — 후속 구현의 선행 gate

- manuscript base 1aac4d38…와 evidence 6c720009…의 exact file/blob 및 historical runtime 9bcd5da2… 간 연결을 기록한다.
- 선택 route timeline n: R2-B 979, R4-B 742, R5-B 1415. 물리 timeline 합 3136; 네 gyro로 반복한 조건-row 12544는 독립 RF 표본 수가 아니다. RF H에 supplemental pose가 있으면 timeline/보조 sweep을 별도 분모로 둔다.
- 기존 4 arm×2 gate×12조건=96 궤적의 score/packet/x/P/mask와 μ/R provenance를 복구한다. 처음부터 96개를 새로 돌릴 필요는 없으나 저장 trace가 없으면 후속 허가 범위에서 재생한다.
- 하위 표본: ALL_FINITE_FULL_TIMELINE, ALL_FINITE_TGE30, BASE_FIXED_ACCEPTED_TGE30, ARM_SELF_ACCEPTED_TGE30를 분리한다. accepted 통계를 gate 독립 통계처럼 인용하지 않는다.
- baseline PB0 parity는 각 선택 RF case B0에서 시작하여 전12조건으로 확대한다. 원래 archived prediction 재생과 EXDS model inference 재현을 다른 체크로 둔다.
- 실제 입력의 SHA256을 다 채우기 전 모델링 결과를 만들지 않는다. 저장된 점수만 있으면 `SCORE_ONLY_NO_TRACE`이고 posterior 기전은 미검증이다.

## PB1. 물리 민감도–잔차 정렬 (필수, RT 0)

### 질문/가설
Q: 선택 세 주행에서 물리 관측의 위치·yaw 민감도와 signed residual은 어떤 작동점을 가지는가?
H0: branch/기하별로 분리해도 물리 Jacobian과 잔차/갱신의 설명 가능한 정렬이 발견되지 않는다.
H1: 일부 구간에서 기하·포트 차등 응답이 잔차의 크기·부호와 함께 설명된다. H1은 모든 경로에서 동일 방향이나 높은 상관계수를 요구하지 않는다.

### 고정 연산
1. 세 RF timeline의 모든 유효 pose에서 Native LoS/Full의 P±, s, first tap/port, peak, threshold margin을 추출한다.
2. SourceFFD h/H는 GT pose(OFFLINE)와 두 reference arm의 actual prior에서 각각 평가한다. GT-J와 prior-J를 합치지 않는다.
3. 거리 rho 구간 [0,1.5,3,6,10,+∞), 상대 수평방위 8개 동일 폭 구간 [-π,π), detector stability 층을 함께 기록한다. bin당 20개 미만은 `SPARSE`로 표시하고 삭제/합치기 튜닝 금지.
4. J 검산 pose는 각 route timeline의 균등 인덱스 64개와 시간순 최초 detector-event 64개 이내의 합집합. 선택은 성능·잔차 크기 확인 전에 확정하고 중복 제거한다. 최대 384 pose. FD step x/y=1e-4m, psi=1e-5rad, step/2 재검산. perturbation에서 tap/port/peak/FFD cell이 바뀌면 smooth-J 통계에서 분리하고 전체 건수 보존.
5. stable branch의 componentwise FD 허용오차는 |Ja−Jfd|≤1e-5+2e-3 max(|Ja|,|Jfd|). 허용오차 초과 시 해당 source 경로를 조사하고 dependent 물리 민감도 claim을 중단한다. 데이터 보고 후 tolerance 수정은 amendment다.

### 보고
각 route의 signed e_prop/e_model/ε, Jx/Jy/Jψ, 포트 불균형과 detector event를 같은 time axis에 그린다. 두 포트 common scalar invariance·port swap 시 s 부호 반전·yaw wrap·duplicate pose·zero/weak denominator를 음성 시험에 포함한다. εs/Jψ는 |Jψ|가 사전 정규화 기준 아래이거나 위치가 알려진 국소 진단이 아니면 계산하지 않는다. 주 지표로 강제 역각도화를 사용하지 않는다.

전상태 정보가 필요하면 `Ipost=Pinv+HᵀRinvH`에서 nuisance를 Schur 제거한다. prior 포함 여부와 단위 정규화를 명시하고 rank-deficient single-packet J를 전역 정보로 확대하지 않는다.

## PB2. 동일 prior의 평균×분산 갱신 분해 (필수, RT 0)

### 비교 기준
Reference Rb=`BB_ORIG/self`, Rm=`MB_VAR/self` 각각의 t=0부터의 prior x−/P−, **직전 posterior lookup 상태**, source z/RB/μB/μM를 snapshot으로 잠근다. 각 snapshot에서 네 shadow arm을 계산한다:

    BB_ORIG: μB, RB
    MB_ORIG: μM, RB
    BB_VAR:  μB, RB+λ eeᵀ
    MB_VAR:  μM, RB+λ eeᵀ; e=[0,1]ᵀ.

λ=σ²(rho_lookup)는 같은 reference lookup 위치에서 네 shadow arm에 공통으로 정한다. 재귀 arm별 lookup값을 섞어 같은-prior라고 부르지 않는다. 이 shadow는 재귀 state를 덮어쓰지 않는다.

### 사전 대수 검사
S0=HP−Hᵀ+RB일 때:

    Kλ e = (K0 e)/(1+λ eᵀS0⁻¹e).

같은 λ에서 mean-only 차이는:

    Δx_mean = −Kλ[:,r](μM,r−μB,r).

편파 gain column의 국소 축소는 예상되는 부호이지만 전체 Heading 오차 감소는 예상 단조성이 아니다. Rrs 및 HPH 교차항 때문에 다른 gain column도 바뀔 수 있다. 비교는 `solve`를 사용하며 tiny diagonal을 임의 추가하지 않는다.

### packet별 결과
ν,H,R,S,K,x−,P−와 각 column의 K[:,r]νr/K[:,s]νs, NIS, 원래 gate의 수용 여부, 강제 1-step 갱신의 x+/P+, 실제 policy 적용의 x+/P+를 별도 저장한다. 오프라인 GT로 update 전후 squared heading/XY error 변화와 부호를 채점한다. 강제 갱신은 진단용이며 실제 수용 결과로 계산하지 않는다.

### 재귀와 인과 한계
같은 초기값·센서 입력에서 96개 기존 factorial 궤적을 재현하고 fixed/self 각각 보고한다. 실제 mask가 같은지 반드시 배열 비교한다. gate 표기가 같아도 내부 eligibility가 다르면 matched-mask가 아니다. scalar RMSE factorial difference를 정의할 수 있지만, 비선형 최종 RMSE의 유일한 인과 기여율이라고 부르지 않는다.

- R2-B: mean-only Heading 악화가 variance와 결합할 때 어떻게 바뀌는가?
- R5-B: mean 효과 위의 추가 신뢰도 조절이 어떤 packet/기하 구간에서 기여하는가?
- R4-B: variance-only보다 mean 추가가 왜 불리한가? residual mean 부호만으로 원인을 단정하지 않고 실제 signed update와 subsequent prior를 추적한다.

## PB3. 거리 lookup의 고유 가치 (필수 대조, RT 0)

현재 lookup을 새로 fitting하지 않는다. variance policy는 ZERO, CONST_TRAIN, LOOKUP_CURRENT 세 개다. μB/μM 각각, fixed/self 각각,12조건 전부 평가한다.

상수 산식은 사전에 고정한다. 평가 route r를 제외한 **선택된 다른 두 B-route**의 B0 BB_ORIG reference lookup 위치를 사용한다. t≥30s 유효 packet 전체, gate 수용 여부와 무관하게:

    λconst,−r = (1/2) Σ_{q≠r} [ (1/Nq) Σ_k σ²_current(rho_lookup,qk) ].

두 source route를 동일 가중한다. 평균 sigma의 제곱이 아니라 **추가분산의 평균**이다. 한 fold의 상수는 모든 gyro 수준과 μB/μM·gate에서 동일하게 사용한다. 평가 route 값·오차·RMSE로 상수를 정하지 않는다. source trace가 없으면 `BLOCKED_CONST_CALIBRATION`, 임의 sigma 대입 금지.

기존 ZERO/LOOKUP 96궤적은 재사용 가능; 새 CONST 48궤적이 최소 추가분이다. 총 프로토콜은 144궤적이며 필요 없는 중복 실행은 하지 않는다. train/test 모두 기존 Corridor에 속하므로 retrospective control이지 unseen generalization은 아니다.

주 비교: LOOKUP−CONST의 Heading RMSE difference(12개 모두), XY·coverage·accepted count 보조. 시드0 deterministic 차이를 유의성 검정으로 부풀리지 않는다. numerical tie는 deg/cm score 절대차 1e-8 이하로 표시하고, 실용적 의미는 baseline 대비 상대변화와 원 단위 모두 보고한다. 상수가 같거나 더 좋으면 기존 MB_VAR 개선 사실은 유지하되 거리 함수의 특별한 우월성 문구를 철회한다.

## PB4. 상관과 재귀 전달 (보조 설명, RT 0)

원래 ACF를 재현한 뒤 mean/기하/branch 층별 통계를 별도 계산한다. 기본 lag는 time {0.2,0.4,1,2,5}s, 누적이동 {0.04,0.08,0.2,0.4,1}m, 회전차 {0,5,10,20,45}deg의 사전 구간이다. 실제 샘플 간격과 matching 폭은 CONFIG_PROPOSED의 정의를 따르며 부족한 쌍은 부족하다고 보고한다. temporal order를 없애고 lag를 잇지 않는다.

기하 평균 제거를 새로 수행할 경우 두 source route B0만 사용하여 [1,rho,sinα,cosα,sin2α,cos2α] ridge(alpha=1, train 표준화)를 fitting하고 held route에 적용한다. 이 회귀는 오프라인 진단만이며 EKF μ를 변경하지 않는다. raw 잔차 ACF와 cross-fit 잔차 ACF를 같이 제시한다.

instantaneous signed Heading error projection a_k=Kψr εr+Kψs εs와 실제 이후 closed-loop transition을 통한 누적 G_K,k εk를 구분한다. 최종 MSE에는 평균의 제곱·cross-time covariance·process/prior 성분이 존재한다. unweighted lag1 또는 AR1 평균 n_eff를 곧바로 EKF 정보손실 계수로 쓰지 않는다. 한 정적 궤적만으로 독립 시간 drift를 식별하지 못하면 `NOT_IDENTIFIED`로 마친다. 대규모 dense stacked covariance inversion이나 새 GP/OU 시뮬레이션은 이 범위에 없다.

## PB5. 재현성·추가 주장 gate

기존 12조건 point result를 재현하려면 archived prediction provenance와 full recursion이 충분한지 검증한다. 새 seed는 현재 명제의 필수가 아니다. robust/significant라는 표현에는 별도 사전 반복설계가 필요하다.

Dual-LP 자체의 인과적 이득을 새 headline으로 주장할 때만 동일12조건 Range-only ablation을 별도 승인한다. Δs feature의 고유 기여를 주장할 때만 같은 fold CIR-only vs CIR+Δs 학습 ablation을 별도 승인한다. 이번 PB1–3은 그런 추가 주장을 자동 승인하지 않는다.
