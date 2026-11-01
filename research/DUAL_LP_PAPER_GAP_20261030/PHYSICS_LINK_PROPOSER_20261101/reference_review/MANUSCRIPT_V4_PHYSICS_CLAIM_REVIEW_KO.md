# 원고 v4 평가: Dual-LP 물리응답–관측오차 처리–Heading 개선의 연결

평가 대상: `1aac4d38`의 `PAPER_MANUSCRIPT_WORKING_DRAFT_KO.md` (Git blob `155fd6ae66f4863680d2b6c9f642923e0ea88767`). 근거 snapshot: `6c7200091028fd3f0e55aa83b777d0f10b7cf063`.

**대상은 R2-B·R4-B·R5-B, Mount 0°, B0/L0/L1/L2의 12조건이다.** 모델은 원고의 MB_VAR/self, 비교선은 BB_ORIG/self다. R4-A 중심 논문, 5상태 공간 GM 또는 SUB3 논문으로 바꾸지 않는다. 모든 환경의 성공이나 모든 XY 개선을 승인 조건으로 추가하지 않는다.

이번 작업은 원고·코드 열람, 저장된 점수 재집계와 대수 검산이다. 새 RT·필터 재실행·학습·저장소 수정은 하지 않았다.

## 1. 요약 판정

v4의 데이터 범위·baseline 구분·12/12 Heading과 8/12 XY의 구분은 적절하다. 원고의 주요 감소율은 D2 원 CSV의 선택 12조건 및 RA4 원본 고정밀 점수와 일치한다. 다만 현재 문장은 관측오차 처리의 일반론에 가깝다. 물리 기반 강점은 **실제 복소 FFD와 동일한 first-path 관측 연산으로 만든 s(x)와 그 기하 Jacobian**에 있다. 이 부분을 전면에 두고, 거리 평균 교체와 편파 추가분산이 그 물리적 관측경로를 어떻게 바꾸는지 보여주면 주장이 선명해진다.

현재 입증 범위를 세 단계로 구분한다.

| 연결 | 이미 지지하는 것 | 보강할 것 |
|---|---|---|
| 관측 현상 → 모델 가정 | SourceFFD 방향·거리·tap 응답과 Jacobian, 세 case의 잔차·ACF | 물리 민감도와 선택한 3경로의 잔차 연결, 거리 lookup의 정량적 설계 근거 |
| 모델 가정 → 개선 원인 | 동일 입력의 평균/분산 factorial와 fixed/self 시스템 효과 | 같은 prior·실제 packet에서의 gain/오차 투영, 누적 기여 |
| 선택 결과 → 재현 가능한 주장 | seed0·12조건의 수치 재현 및 범위 명시 | 학습 fold–예측파일–전체 재생 연결, 더 강한 통계 주장을 위한 선택적 반복 |

**권장 중심 주장:** 물리적 Dual-LP 응답으로부터 Heading에 민감한 관측과 Jacobian을 구성하고, 그 관측에 남는 구조적 오차를 거리 평균 처리와 편파 신뢰도 조절로 구분함으로써, 선택한 단일 앵커 12조건에서 Heading 점추정 오차를 줄인다. 이는 정확한 시공간 covariance 필터나 완전히 물리법칙에서 유도한 R이라고 주장하는 것이 아니다.

## 2. 재집계에서 확인한 중요한 사실

### 2.1 최종 성능 문장은 정확하다

원고의 12조건에서 Heading 감소는 12/12, XY 감소는 8/12다. R4-B의 Heading 감소는 0.735–2.543%이고 XY는 10.499–11.796% 증가한다. 실수치/전체 조건은 `tables/SELECTED_12_CONDITIONS_RECHECK.csv`에 있다.

동일한 D2의 6유효숫자 표시를 RA4 고정밀 원본과 대조한 선택 48값은 48/48 일치했다. 이 대조는 출력물 사이 재현성 확인이지 독립적인 전파/통계 검증이 아니다.

### 2.2 분산만 추가해도 Heading은 12/12 개선한다

| 구성 | Heading 개선 /12 | XY 개선 /12 |
|---|---:|---:|
| 평균만 MB_ORIG/self | 4 | 6 |
| 분산만 BB_VAR/self | 12 | 8 |
| 결합 MB_VAR/self | 12 | 8 |

그러므로 12/12라는 숫자만으로 두 요소의 결합 필요성이나 물리적 인과를 증명할 수 없다. 핵심은 **R2-B·R5-B의 8조건에서 결합 모델이 두 단독 모델보다 두 지표 모두 낮다는 것**이다. R4-B의 4조건에서는 분산만이 결합보다 두 지표 모두 낫다. 결합 모델을 바꾸지 말고 이 차이를 설명 대상으로 남긴다.

### 2.3 RMS 감소와 signed mean 제거는 구분해야 한다

B0, t≥30초, fixed BASE의 동일 수용집합:

| Case | Range RMS BB→MB (cm) | Range 잔차 평균 BB→MB (cm) | E[eps_s²]/E[Rss_BB] |
|---|---:|---:|---:|
| R2-B | 8.19→5.16 | −2.508→−0.697 | 0.517 |
| R5-B | 8.41→4.63 | −2.669→−0.0366 | 0.163 |
| R4-B | 7.97→5.58 | −0.188→−0.497 | 0.897 |

R4-B도 전체 RMS는 줄지만 집합 평균의 절댓값은 커진다. 따라서 “선택한 모든 경로에서 평균 편향을 제거했다”보다 “조건부 평균 예측을 교체하여 Range 잔차의 제곱오차를 낮췄다”가 맞다. 평균의 절댓값 변화만으로 최종 XY 악화의 원인을 확정할 수도 없다.

### 2.4 추가분산은 누락된 marginal 잡음분산과 같지 않다

원고의 세 선택 case에서 위 비율은 모두 1보다 작다. 이 사실은 accepted/scoring 집합의 진단으로 제한한다. 별도의 t≥30초·gate 선택 없는 거리-bin 표에서도 R2-B와 R5-B는 각 거리 구간의 편파 RMS가 기존 sqrt(mean Rss)보다 낮다. R4-B는 일부 구간에서 초과한다.

편파 RMS의 거리-bin 경향:

| Case | 0–1.5m | 1.5–3m | 3–6m | 6–10m |
|---|---:|---:|---:|---:|
| R2-B | .00801 | .01692 | .07091 | .17440 |
| R5-B | .00836 | .02007 | .05004 | .14984 |
| R4-B | .01155 | .05636 | .12135 | .21203 |

거리에 따른 오차 규모 변화는 이미 보인다. 그러나 이것만으로 hand-table sigma를 유도할 수 없으며, 거리와 입사각·방위·반사기하가 혼재한다. **추가분산은 현재로서는 유효 갱신 가중치의 보수적 조절이며, 참 센서 분산의 복원이 아니다.**

## 3. 물리 기반 논지를 전면에 둘 방법

### 3.1 편파비는 전력 특징이 아니라 상태에 의존하는 물리 관측이다

개념식으로 포트 p의 LoS 응답을

H_p(f;x)=G_p^FFD(f,Omega_T,Omega_R(x),psi) a(f,d) exp(−j2pi f d/c)

로 쓴다. 실제 코드의 좌표 회전·복소 vector contraction·주파수 처리·Hann/4N IFFT·공통 first-path detector를 보존한다. 단순 cos(2psi)를 실제 안테나의 정답으로 대신하지 않는다.

공통 선택 tap에서 P_+,P_-를 계산하여

s=(P_+−P_-)/(P_++P_-)

로 관측한다. 같은 복소 스칼라가 두 포트에 곱해지면 ratio는 변하지 않는다. 다만 임의의 주파수 선택적 common filter까지 불변이라는 뜻은 아니다. 반사경로의 편파·위상 중첩과 포트별 차등 응답, receiver noise, detector selection은 ratio를 바꿀 수 있다.

따라서 sigma(rho)의 근거를 “거리가 멀수록 공통 자유공간 감쇠가 커져 s가 달라진다”로 단순화해서는 안 된다. 거리 조건은 실제 입사/반사 기하, 약한 port의 noise, 복소 주파수 응답, tap 선택에 대한 대리변수일 수 있다.

### 3.2 같은 물리 민감도가 원하는 Heading 정보와 원하지 않는 왜곡을 함께 전달한다

안정된 detector branch에서 u∈{x,y,psi}에 대하여

ds/du = 2(P_- dP_+/du − P_+ dP_-/du)/(P_++P_-)².

따라서 h의 Jacobian은

H = [[h_rx,h_ry,0,0],[h_sx,h_sy,h_spsi,0]]

형태다. h_spsi가 yaw 민감도를 제공하지만 h_sx,h_sy도 함께 존재한다. b_g는 단일 packet의 직접 관측량이 아니라 운동모델 및 교차공분산을 통해 갱신된다. h_spsi≠0만으로 전 상태의 전역 관측가능성을 입증하지 않는다.

국소 작은 power 섭동에서

e_s≈g_P^T deltaP,  g_P=2/(P_++P_-)² [P_-,−P_+]^T,

C_s(k,l)≈g_P,k^T C_deltaP(k,l) g_P,l.

이 식은 **두 편파 채널의 물리적 오차 구조를 ratio의 시공간 상관으로 연결하는 분석 틀**이다. tap 전환이나 큰 왜곡에는 직접 적용하지 않고 별도 층으로 분리한다. 현재 구현이 C_s(k,l) 전체를 사용한다는 뜻도 아니다.

### 3.3 추가분산은 정보를 생성하지 않고 그 관측의 갱신 강도를 바꾼다

같은 H, P^-, mean, lookup state에서 S0=HP^-H^T+R_B, e_s=[0,1]^T, lambda=sigma_b²이면

K_lambda e_s = (K_0 e_s)/(1+lambda e_s^T S0^(-1)e_s).

즉 편파 관측 column의 gain은 이 조건에서 정확히 축소된다. 검산용 무작위 양의정부호 행렬 100개에서 이 항등식의 오차는 4.72e−16 이하였으며 실제 RF 시험은 아니다. 실제 재귀 arm끼리는 prior가 달라져 이 국소 단조성만으로 전체 성능을 예측할 수 없다. joint innovation의 교차항이 있으면 range-column gain도 변한다.

따라서 “sigma를 추가해 Heading 정보를 늘렸다”가 아니라 **“물리적으로 yaw에 민감한 편파 관측에 남은 구조적 오차가 과도한 각도 갱신으로 투영되지 않도록 신뢰도를 조절했다”**를 검증할 가설로 삼는다.

## 4. 사용할 수 있는 기존 분석과 용도

| 근거 | 현재 쓸 수 있는 주장 | 대상/한계 |
|---|---|---|
| SourceFFD code 및 P0 검증 | 복소 FFD 기반 h_s와 active-branch Jacobian이 구현되어 있고 native LoS와 대조됨 | 기존 광범위 검증을 12조건별 재계산으로 오인하지 않음 |
| D3_DECOMPOSITION | RF 잔차·prior 투영오차·교차항 분리, Range RMS 및 평균 차이 | fixed BASE, t≥30, 동일 accepted 집합 |
| D3_EPS_BY_DISTANCE | 선택 세 case의 거리별 mean/RMS/std 및 R 비교 | t≥30, 유한 packet, gate 선택 없음; GT 거리로 offline 진단 |
| D3_EPS_TEMPORAL | 같은 RF 잔차의 순차 지속성 | 전체 시간축, 시간독립 drift나 공간 kernel 식별 아님 |
| D2_GATE_SCORES, RA4 | 12조건 2×2 평균/분산, fixed/self, 실제 update 수, coverage | self는 수용집합·prior도 바뀌는 시스템 개입 |
| X1 BB/MB/BM/MM | 평균변경과 수용이력 효과를 분리한 기존 개입 | 선택 3case의 B0/L2에 적용 가능; L0/L1 동일 진단은 미실행 |
| 동일 prior/첫 gate, R4/R5B 순열 및 R 배수 | 특정 선택 case의 순서·가중치·기하 결합에 대한 반사실 근거 | 모든 12조건의 공통 원인으로 확대 금지 |
| E2/E5 정정·초기상태 교차 | 잘못된 정규화 결론 배제, seed0의 주장 범위 | 정정되지 않은 FIM 요약 재사용 금지 |

RA0–RA3의 출처·H→packet parity는 짧은 방법/부록 근거로 유지한다. 현재 논문의 주 내용을 새 tap·5상태·신규 환경 연구로 바꾸는 자료는 아니다.

## 5. 필요한 추가 분석 — 모든 단계에서 같은 12조건 유지

### P0-A. 물리 민감도–잔차–Heading 갱신 연결 (최우선, RT 0)

보존 Full/Native LoS H, 동일 pose와 SourceFFD로 선택 3경로의 h_s, J_sx,J_sy,J_spsi, 공통/차등 port power, selected tap/port, margin을 함께 기록한다. truth 사용은 offline 진단에만 한정한다.

산출물: (1) 동일 geometry의 LoS/Full polarization response, (2) 거리×상대방위/회전별 signed residual와 민감도, (3) stable branch와 switching 구분, (4) local inverse-angle 또는 정보지표. e_s/J_spsi는 J가 0에 가까운 곳에서 쓰지 않고 위치가 알려진 국소 진단으로만 사용한다. 전 상태 정보는 prior를 포함한 정보행렬의 Schur complement로 nuisance를 제거해 평가한다.

이 분석으로 “편파 물리를 사용했다”를 source 구현 설명에서 선택한 3경로의 정량적 증거로 연결한다. 새로운 R나 필터 구조는 바꾸지 않는다.

### P0-B. 동일 prior의 2×2 shadow update와 재귀 영향 분해 (최우선, RT 0)

각 원본/선택 arm의 prior를 공통 기준으로 동결하고 같은 packet에서 (mu_B,R_B),(mu_M,R_B),(mu_B,R_B+lambda eeT),(mu_M,R_B+lambda eeT)를 계산한다. 실제 코드와 같이 이전 posterior lookup 상태도 맞춘다.

기록: H,K,nu,range/polarization의 signed yaw·XY 갱신, NIS 수용 여부, 즉시 오차제곱 변화. 이어 fixed-mask 전체 재귀와 self-gate 전체 재귀를 구분하여 기하·잔차·gain의 누적 방향을 보여준다. range correction이 J_s의 작동점을 개선했는지 여부는 기록으로 검사하며 미리 결과로 단정하지 않는다.

R4-B는 “mean sign이 다르다”를 원인으로 확정하지 않고 **평균 교체를 넣었을 때 분산-only보다 왜 불리해지는가**를 같은 prior 및 누적 trace로 분석한다. R2/R5-B는 결합이 두 단독 모델을 앞서는 연결을 설명한다.

### P1-C. 거리 조건의 추가 가치 대조군 (거리 조건이 기여라고 주장할 때 필수, RT 0)

현재 lookup vs 추가분산 0 vs train-fold에서 맞춘 상수 추가분산을 비교한다. 상수는 평가 결과에 맞춰 고르지 않고 train fold의 평균 추가분산 또는 미리 정한 정보량 기준을 사용한다. 모델/기준을 고정한 뒤 같은 12조건 평가; current self 결과와 fixed 진단을 별도 보고한다.

거리 lookup이 상수와 같거나 열등해도 기존 Heading 개선의 사실은 유지된다. 그때 주장은 “거리 함수의 특별한 물리적 우월성”이 아니라 “경험적 편파 신뢰도 조절”로 제한한다. gamma=0/.5/1/2 같은 사전 민감도 표는 최적값을 사후 선택하지 않는 한 선택 robustness를 설명할 수 있다.

### P1-D. 시간/공간 상관을 주장하는 수준에 맞춘 분석 (RT 0)

조건부 mean을 제거한 뒤 matched geometry/안정 tap 내 covariance를 시간·이동·회전 lag로 따로 산출한다. 현재 시간 lag에 이동거리를 붙인 표를 별도 공간 kernel로 재명명하지 않는다. 같은 pose·같은 yaw/anchor/mount의 재방문이 있으면 두 차원을 구분하는 보조 자료로 사용하고, 없으면 정적 field를 주행하며 관측한 상관으로 범위를 제한한다.

즉시 projected correction a_k=K_psi,r eps_r+K_psi,s eps_s의 평균·covariance와, 고정 선형화에서 후속 closed-loop state transition까지 포함한 G_{K,k} eps_k의 누적항을 구분한다. 최종 heading MSE에는 mean의 제곱과 i≠j covariance 항이 들어간다. unweighted lag1 또는 AR1 표본평균 n_eff를 그대로 EKF 정보량 손실계수로 쓰지 않는다.

현재 논문을 exact colored likelihood 논문으로 바꾸지 않는다면 새로운 AR1 state나 혼합필터 구현은 필요 없다. 필요한 것은 상관이 “신뢰도 조절을 고려한 이유”임을 뒷받침하는 분석이다.

### P1-E. 학습–예측–재생의 재현성 (RT 0)

각 held route의 train case/XY exclusion/scaler/coefficients/source hashes, 실제 CIR 및 Delta-s feature 정의, 예측파일 hash, correction reconstruction 식, 관측 및 source-model SHA를 한 표로 잠근다. 복원된 archived prediction과 실제 회귀 inference가 일치하는지는 별도 단계로 검사한다. 동일 하이퍼파라미터와 동일 학습 가중치를 구분한다.

12조건 main table은 유지한다. “seed0의 재현 가능한 관찰”이면 현 주장에 새 seed가 필수는 아니다. “초기화에 강건/통계적으로 유의”까지 주장할 때만 같은 3 RF route를 유지하고 paired sensor/initial seed 반복을 추가한다. 패킷 또는 네 gyro 조건을 독립 RF 표본으로 계산하지 않는다.

### 조건부 추가: Dual-LP/Delta-s 고유의 기여를 별도 headline으로 만들 때

기존 source 검증의 s 제거 결과는 다른 subset일 수 있다. 이 12조건 자체에 “Dual-LP가 Heading 향상의 원인”이라는 추가 비교를 주장하려면 동일 운동·noise/mean 기준의 Range-only ablation과 실제 source h_s를 비교한다. 단순 고정각도 toy model을 허수 baseline으로 쓰지 않는다. “Delta-s feature 자체가 range 평균 개선 원인”까지 주장하려면 동일 학습 fold의 CIR-only vs CIR+Delta-s feature ablation이 별도로 필요하다. 지금 mean replacement 비교만으로 feature 한 개의 기여를 분리했다고 쓰지 않는다.

## 6. 수정용 중심 문단

본 연구는 Dual-LP 수신 안테나의 두 직교 편파 포트가 로봇 자세와 입사 방향에 따라 보이는 차등 응답을 이용하여 단일 UWB 앵커 환경의 Heading 관측을 구성한다. 포트별 복소 FFD를 실제 송수신 기하에 따라 변환하고, 관측 생성과 동일한 CIR 및 공통 첫 경로 탭 연산으로 정규화 편파비와 상태 Jacobian을 계산한다. 이를 통해 거리 관측의 직접 yaw 민감도를 보완하면서, 편파 관측이 평면 위치와 Heading에 동시에 의존하는 구조를 4상태 Joint EKF에 반영한다.

다중경로는 이 차등 응답과 첫 경로 선택을 변화시키므로, 방향 민감도가 존재한다는 사실만으로 편파 관측을 독립적이고 정확한 각도 제약으로 취급할 수는 없다. 본 연구는 보존된 관측에서 거리 평균 보정 전후의 잔차, 편파 잔차의 기하 의존성 및 주행에 따른 지속성을 구분하여 분석하고, CIR·인접 tap 편파 특징으로 예측한 거리 오차 평균의 교체와 거리 조건별 편파 신뢰도 조절을 결합한다. 여기서 복소 FFD 관측함수는 물리 기반 구성이고, 추가분산은 잔여 모델오차의 효과를 보수적으로 다루는 경험적 설정이다. 선택한 R2-B·R4-B·R5-B의 네 gyro-bias 조건에서 같은 구조를 적용한 결과 Heading RMSE는 12조건 모두 감소했으며, R2-B·R5-B에서는 결합 모델이 각 단독 개입보다도 우수했다. R4-B에서는 작은 Heading 이득과 XY 악화가 공존하여, 관측 잔차의 감소와 재귀 상태오차의 감소가 동치가 아님을 보였다.

위 문단은 현재 증거 범위에 맞춘 제안이다. 물리 민감도가 실제 개선을 일으킨 세부 경로는 P0-A/B 분석으로 정량화해야 하며, 아직 수행하지 않은 결과를 이미 입증한 것처럼 적지 않는다.

## 7. 원고의 구체적 수정 위치

- §1.1: SourceFFD→CIR→common tap→s의 chain과 H의 구조를 명시. 물리적 정보 경로와 잠재적 distortion 경로를 함께 소개.
- §1.2: RMS와 mean/std를 분리. EXDS는 전체 range mean 교체이며 Delta-s 단독 보정이 아님.
- §1.3: 시공간 상관은 동기/관측 특성. 단일 ACF→분산표의 유도는 하지 않음.
- §2.1: 추가분산을 calibrated true variance로 쓰지 않음. 물리 기반 h/J와 empirical reliability를 분리.
- §2.2: matched-prior gain 축소의 정확한 식과 actual lookup timing 유지.
- §3.2: 분산-only도 Heading12/12라는 전체 ablation 요약 및 결합모델의 8조건 추가 이득 제시.
- §4.1: R4-B의 잔여 mean/prior mismatch는 후보 설명. 원인 확정은 P0-B로 연결.
- 재현성: 3 RF sequences×4 gyro, seed0, t≥30, self/fixed 구분, archived prediction의 범위를 유지.

## 8. 출처

- 원고: https://github.com/myoungsunk/sionna-resimulation/blob/1aac4d38/research/DUAL_LP_PAPER_GAP_20261030/PAPER_MANUSCRIPT_WORKING_DRAFT_KO.md
- SourceFFD 구현/검증: https://github.com/myoungsunk/sionna-resimulation/tree/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/FFD_P0P3_20261016
- D1/D2/D3 결과 및 코드: https://github.com/myoungsunk/sionna-resimulation/tree/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029
- X1 평균/mask 개입: https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/x1/RESULTS_KO.md
- RA4 저장 점수: https://github.com/myoungsunk/sionna-resimulation/actions/runs/40859507594/artifacts/12890904334

재현 패키지의 D2 선택값과 D3 선택값은 connector로 확인한 값을 명시적으로 전사한 부분집합이다. 원 CSV 전체 또는 그 Git blob과 동일한 바이트라고 주장하지 않는다. RA4 원 점수 CSV는 기존 다운로드 artifact의 원바이트를 보존했다. `recompute_review.py`와 `RECHECK_QA.json`에 계산과 검사 범위를 남겼다.
