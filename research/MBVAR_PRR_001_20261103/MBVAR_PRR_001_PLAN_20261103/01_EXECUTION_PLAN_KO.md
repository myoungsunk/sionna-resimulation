# MBVAR-PRR-001 — 예방·공분산 복구·체크포인트 재처리 실행 계획

**버전:** v0.1 / 2026-11-03  
**상태:** PROPOSER DRAFT · NOT FROZEN · NOT IMPLEMENTED · NOT RUN  
**대상:** 단일 앵커 B, R4-B / R5-B, Mount 0°, 기존 MB_VAR 4상태 EKF  
**현재 산출물:** 실행 설계·실험 행렬·독립 감사 요청서. 코드 변경·GitHub 푸시·실험 실행·독립 감사 완료를 뜻하지 않는다.

---

## 0. 실행 목적과 결론의 범위

검증할 최종 가설은 다음과 같다.

> **d₀·Δs로 오염 관측을 식별하고 그 영향력을 제한하면 새로운 오차와 과신을 줄일 수 있다. 이미 오염된 상태에 대해서는 선택적 사전 공분산 복구 또는 체크포인트 재처리를 추가하여, 실제 추정오차와 공분산 일관성을 함께 개선할 수 있다.**

이는 검증 대상이지 확정 결론이 아니다. 국소 검출 성공, 동일-prior 단일 갱신 개선, 전체 재귀 성능 개선은 각각 다른 주장으로 평가한다.

### 실행 순서

| 단계 | 조치 | 주 검증 질문 | 다음 단계로 넘어가기 전 확인 |
|---|---|---|---|
| **1. 예방** | d₀·Δs 기반 편파 관측 가중치 조정 | 오염된 관측의 잘못된 영향과 공분산 축소를 줄이며 전체 재귀에서도 이득인가? | 실제 정확도·불확실성·보호조건 결과, 잔존 실패 시점 |
| **2. 공분산 복구** | 관련 상태 방향의 P 확대, 평균은 그대로 | 이미 틀어진 동일 상태에서 실제 오차를 회복시키는가? | P만 커진 효과와 평균상태 회복을 분리 |
| **3. 체크포인트 재처리** | 의심 구간 이전 상태를 복원하고 관측을 재가중·재처리 | 과거 잘못된 평균/P 이력을 바로잡으며 현재 시점 성능을 추가 개선하는가? | 정보 중복·미래정보·과거곡선 재작성·실시간 비용 감사 |

새 경로 학습, 새 RF 생성, 새 앵커, Mount45°, 팩터 그래프 전환, 전체 관측 평균 재학습은 이번 실행 범위 밖이다. 기존 데이터의 제한된 운용계수 보정은 별도로 기록하고, 이를 새 경로 학습이나 독립 환경 검증으로 표현하지 않는다.

**복잡성 최소화:** 1단계만으로 목표가 충족되고 복구의 추가 이득이 없다면 1단계 모델을 유지한다. 2·3단계까지 구현했다는 사실 자체가 더 우수한 방법의 근거가 아니다.

## 1. 현재 근거와 출발점

### 1.1 확인된 것과 미확인인 것

| 현재 근거 | 허용되는 해석 | 아직 허용되지 않는 해석 |
|---|---|---|
| R4-B 수용 표본의 사후 검사에서 d₀ 임계값 0.339→0.20은 지정한 고민감도·큰 오차 13개에 대한 검출 8→13 | 해당 저장 prior에서 놓친 오염을 더 검출함 | 0.20을 쓰면 전체 Heading이 개선됨 |
| 33.6초 동일-prior에서 Rss×4는 공동 Heading 갱신 −0.314°→−0.069°, 사후 σ 0.828°→0.839° | 그 시점에서 잘못된 갱신과 확신 증가를 줄임 | 전체 재귀 필터의 정확도·coverage가 개선됨 |
| 이전 d₀ 기반 게이트/분산 실험은 측정 정합성 개선과 재귀 Heading 개선이 일치하지 않았음 | 관측 검사와 재귀 평가를 분리해야 함 | 모든 게이트/가중치 방식이 실패함 |
| 현재 MB_VAR는 거리 기반 편파 추가분산과 BASE 수용 마스크를 사용함 | 가중치 변경과 게이트 변경을 분리할 수 있음 | 자체 NIS로 모든 수용 여부를 결정하고 있음 |

기존 33–35초, 100초, 105초 등의 hotspot은 **이미 확인한 개발 사례**다. 이를 보고 설계했으므로 해당 결과를 미사용 holdout 성과로 명명하지 않는다. [S2–S5]

### 1.2 기준 모델의 정확한 정의

상태는 \(x=[p_x,p_y,\psi,b_g]^T\), 관측은 \(z=[r,s]^T\)이다. 위치는 m, 각도는 rad, 자이로 바이어스는 rad/s를 내부 단위로 쓴다.

\[
\nu_r=z_r-h_r(\hat x^-)-\mu_{r,\Delta s},\qquad
\nu_s=z_s-h_s(\hat x^-)-\mu_{s,\mathrm{base}},
\]
\[
R_{ss}^{\mathrm{VAR}}=R_{ss}^{\mathrm{base}}+\sigma_b^2(\hat\rho).
\]

**MB는 거리 평균 보정 변경, VAR는 편파 추가분산**이다. 편파 평균까지 새 Δs 모델로 바꾸는 실험으로 해석하지 않는다. 입력 배열의 μr/μs/Rrr/Rss/Rrs를 직접 확인하여 이 조건을 승인한다. 이름이나 과거 설명문만으로 arm을 선택하지 않는다.

원래 σb 표는 ρ=[0,1.5,3,6,10] m에 σ=[0.011,0.020,0.050,0.120,0.240]이다. 기준 구현은 **예측 직전 posterior 위치에서 σb를 계산**한다. 이것을 새 prior 위치로 바꾸는 것은 별도 개입이므로 이번 parity 단계에서 조용히 수정하지 않는다. [S1,S6]

기준 reference는 PR #19의 조회 시점 HEAD `7e2855314de867e0481f8eb5ed1a07c48710f364`이다. 이는 참조 SHA이며, 미래 구현의 실행 SHA나 감사 승인 SHA가 아니다.

## 2. 공통 고정 계약

### 2.1 데이터·모델·범위

| 항목 | 고정 내용 |
|---|---|
| 본 평가 | R4_aB_m0 / R5_aB_m0, Anchor B=(10,0,2.65)m, RX 높이 0.45m, Mount0 |
| 채널 | 기존 Full 및 Native LoS. 새 RT를 돌리지 않음 |
| 바이어스 | B0, L2 각각. B0라고 bg 평균을 0으로 재설정하지 않음 |
| 시드 | 개발·회귀 seed 0–9, 별도 안정성 확인 seed 10–29 제안. 후자는 소스 감사 후 생성·실행하며 RF는 동일 |
| 운동·센서 | 원본 5 Hz timestamp, 제어·초기조건 생성 규칙, 동일 seed의 모든 arm에 동일 잡음 실현 |
| RF 체인 | 원래 복소 H / first-path·편파 추출 / SourceFFD / 포트 순서 / 지연 convention 유지 |
| 학습된 값 | μr, μs, 기본 R, σb 표 동결. LoS도 선택한 기준의 μ/R 적용 convention을 동결 |
| 재귀/평가 | t=0부터 재귀. 주 점수 t≥30s. 초기 0–30s는 별도 표로 보고하며 숨기지 않음 |
| 새 입력 | runtime에는 truth, s_LoS, e_MP, reflection label, route별 정답상태, 오류 크기 라벨 금지 |
| 금지 | 평가 결과를 보고 임계값·시간창·시드·실패 기준·대표사례를 추가하거나 삭제하는 행위 |

GT는 입력 데이터와 분리된 evaluator에서만 읽는다. oracle 실험은 `DIAGNOSTIC_ORACLE`로 별도 저장하며 온라인 방법의 성능으로 합산하지 않는다.

**Seed 10–29의 의미:** 같은 RF 채널 위의 추가 센서 실현에 대한 안정성 평가다. 새로운 경로·반사환경·독립 RF 샘플에 대한 일반화 검증이 아니다. 해당 seed가 이미 다른 실행에서 사용됐는지 사전 등록부로 점검하며, 사용 이력이 있으면 그 사실을 표시한다.

### 2.2 학습·보정 자료의 경계

새 궤적은 생성하지 않는다. Δs의 scale에 필요한 단순 분위수는 기존 **R2-B, Mount0, Tnone**의 측정 특징만으로 계산하는 안을 제안한다. μ/R 모델은 재학습하지 않는다. 원본 timeline의 유일 pose_id를 사용하고 drive/turn을 모두 포함하며 추출·표본 가중치·분위수 알고리즘을 동결한다.

R2-B 자료를 확보하지 못하면 R4-B 평가 표본으로 조용히 대체하지 않는다. 해당 결합형 후보를 BLOCKED로 두고 d₀-only 개발 대조만 수행할지 별도 승인한다. 기존 μ/R의 과거 학습에 다른 앵커 자료가 들어갔다면 그 lineage를 그대로 공개하며, 이번 runtime 분석을 앵커 B로 제한한다.

### 2.3 두 종류의 게이트 운용

- **F: 메커니즘 분리 시험.** 시드·바이어스·채널별 기준 BASE 마스크 A_B를 재생성해 모든 arm에 동일하게 적용한다. 새 R이나 P 때문에 기각 관측이 다시 수용되면 실패다.
- **O: 인과적 운용 시험.** 동일 센서 prefix만 보는 shadow BASE를 함께 실행하여 A_B를 현재 시점마다 제공한다. 이는 oracle-free이지만 **단일 필터가 아니라 shadow를 포함한 구현**이다. 연산·메모리를 함께 보고한다.

F와 O가 동일 입력에서 같은 A_B를 생성하는지 감사한다. 미래 데이터로 생성한 마스크를 그냥 읽는 F의 성적만으로 O 구현 완료를 주장하지 않는다. 새로운 단독 self-gate, gate의 R 변경, 편파-only reject 후 range 구제는 이번 주 실험에 섞지 않는다.

### 2.4 시작 전 반드시 동결할 항목

`templates/EXECUTION_CONTRACT_DRAFT.json`의 승인 상태를 채우고 다음을 잠근다.

- 기준 소스/관측모델/센서코드 SHA, 원본 RF·bank·controls·μ/R·timeline·기준 trace의 SHA256.
- runtime 환경과 dependency lock, precision, 각도 convention, gate 비교 연산자.
- 후보 목록과 주 후보, 계수 선정에 사용한 데이터, 평가 제외·선택 규칙.
- trigger, cooldown, 최대 복구 횟수, checkpoint 범위, replay budget, missing-data 정책.
- 모든 점수·실패 기준·확증 seed 목록·실험 수 상한.
- 감사자 식별자, 별도 runner, 독립 검산 저장소/commit, 승인권자 기록.

미확정 값은 임의 default로 채워 실행하지 않는다. DRAFT→FROZEN은 문서 작성이 아니라 별도 승인 사건이다.

## 3. 공통 운영 절차: 제안자 → 구현자 → 독립 감사자

각 단계 i=1,2,3은 같은 순서를 따른다.

1. **PROPOSER:** 해당 단계의 estimand·처치·음성대조·주장 경계를 확정한다.
2. **독립 사전 설계 감사:** 구현 전에 과학적 식별성·누출·입력·수치 허용오차를 검토한다.
3. **IMPLEMENTER:** 승인된 격리 브랜치에서 단계 i 코드와 단위시험을 작성한다. 이때 전체 과학 실험은 실행하지 않는다.
4. **코드 SHA 동결 → 독립 코드 감사:** 별도 에이전트·별도 runner가 자신의 검산 코드로 parity·수학·인과성을 검사한다.
5. **`GO_Si_DEV`** 후 개발 실험. 설정이 바뀌면 새 버전으로 코드·계약·감사를 다시 동결한다.
6. **`GO_Si_LOCKED_EVAL`** 후 잠긴 평가 세트 실행. 결과를 본 뒤 같은 평가를 다시 최적화하지 않는다.
7. **독립 결과 감사:** 원시 trace부터 지표를 다시 계산하고, 사전 주장이 지지되는지 판정한다.
8. **승인권자 결정:** 다음 단계 진행, 재설계, 또는 최소 모델 유지. 감사 PASS와 사용자/책임자 승인 기록은 분리한다.

동일 세션이 역할 이름만 바꾸거나 구현자의 점수 함수를 그대로 호출한 것은 독립 감사가 아니다. 독립 에이전트를 확보하지 못하면 `SELF_REVIEW_ONLY`, runner가 분리되지 않으면 `INDEPENDENCE_NOT_ESTABLISHED`로 표시하고 독립 PASS를 발급하지 않는다.

**상태를 분리한다:** `TECHNICAL_PASS`, `SCIENCE_SUPPORTED`, `SCIENCE_PARTIAL`, `SCIENCE_NOT_SUPPORTED`, `HOLD`, `NOT_RUN`.

수학·누출·재현성 실패는 즉시 중단한다. 과학적 무효 결과는 실패를 보존하며, 사전에 정의된 별도 원인 질문을 위해 다음 단계를 수행할 필요가 있을 때만 재승인한다. 무효 결과를 성공으로 바꾸어 단계 통과시키지 않는다.

## 4. 1단계 — 오염 관측의 가중치 조정: 새로운 과신 예방

### 4.1 가설과 변경 범위

**S1-H:** 동일한 MB_VAR 평균·운동모델·관측 선택을 유지할 때, 중간 수준의 오염까지 포착하는 위험도 기반 편파 가중치가 잘못된 갱신과 후속 과신을 줄인다.

변경: 편파 관측의 가중치 및 그 가중치와 일관된 K/P 갱신만. P 복구·checkpoint replay·mean 재학습은 OFF.

\[
d_{0,k}=z_{s,k}-h_s(\hat x_k^-),\qquad
D_k=|s(fp+1)-s(fp)|.
\]

주 운용에는 실제 e_MP·GT Jacobian을 사용하지 않는다. Hψ는 실제 arm의 prior에서 계산하며 내부 radian 단위를 유지한다.

### 4.2 사전 제안 후보 — 최적값이 아님

| 후보 | 정의 | 역할 |
|---|---|---|
| W0 | w=1 | 원본 MB_VAR parity |
| H-d0 | |d₀|>τ이면 s행 제거, 아니면 w=1 | 임계값 효과를 확인하는 hard-gate 대조 |
| W-d0 | \(w_d=\max(w_{min},\min(1,\tau_d/(|d_0|+\epsilon))^2)\) | 연속적인 할인 |
| W-d0-DS | \(w_s=\max(w_{min},w_d w_D)\), wD는 D에 같은 함수를 적용 | Δs 추가 정보의 독립 기여 |

**v0.1 주 제안값:** τd=0.20, wmin=0.25, 지수=2, τD=위에서 동결한 R2-B 측정 D의 90분위. τd∈{0.20,0.25,0.30}는 개발 민감도 표로만 보고한다. 0.3387926은 과거 R4 비교값일 뿐 새 범용 최적값이 아니다. 이 값들은 기존 실패를 본 뒤 제안했으므로 독립 holdout 설계라고 주장하지 않는다.

주 후보는 W-d0-DS, 필수 ablation은 W-d0이다. 이 결합은 검증 후보이지 ‘Δs가 작으면 안전’ 또는 ‘두 지표가 독립’이라는 가정이 아니다. 평가 결과를 보고 주 후보를 바꾸면 새 계약 버전으로 분리한다. 조건부 잔여 MSE 회귀모델은 이 단계의 주 실험에 추가하지 않고, 필요하면 별도 확장 계약으로 다룬다.

### 4.3 갱신 정의

\[
R_{ss}^{eff}=R_{ss}^{VAR}/w_s,\quad R_{rr}^{eff}=R_{rr}^{VAR}.
\]

**σb²까지 포함한 전체 Rss_VAR를 할인**한다. 기본 Rss만 확대하고 σb²를 그대로 두는 방식과 혼동하지 않는다. 기준의 Rrs=0을 검산하고, 0이 아니면 임의로 지우지 말고 조건부 관측 정의를 재승인한다.

같은 Reff를 S, K, 상태 갱신 및 Joseph P 갱신에 사용한다. w=0인 hard 대조는 큰 숫자 10^6을 넣는 대신 실제 s행 제거로 정의한다. 기준 공동 마스크가 false면 range도 새로 구제하지 않는다.

### 4.4 실험 순서

- **S1-a 입력·무처치 재현:** W0가 원본 MB_VAR와 전 시점 state/P/mask/μ/R에서 일치하는지 검산.
- **S1-b 검출·동일-prior 시험:** 저장된 동일 prior에서 H-d0/W-d0/W-d0-DS를 비교. 큰 RF 잔차 검출, 잘못된 단일 갱신, P 감소량을 보고하되 전체 성능 결론은 내리지 않음.
- **S1-c 자연 재귀:** t=0부터 각 arm 자신의 prior로 d₀,H,K,P를 재계산. 기존 prior의 d₀를 재사용하지 않음.
- **S1-d 잠긴 평가·보호:** R4/R5×B0/L2×Full/LoS의 seed별 쌍대 비교. 초기·근접·후반 및 전체 구간을 모두 공개.

### 4.5 코드 구현 독립 감사

필수 시험:

- w=1 무처치 parity; w=0과 exact range-only 동일성.
- 동일 prior/H/mask에서 Rss 증가에 따른 Ppost 차이의 양의 준정부호성. **전체 상태 갱신량 절댓값의 단조 감소는 일반 법칙이 아니므로 시험 invariant로 두지 않는다.**
- 평균·range R·기준 마스크 불변; σb 계산 시점 보존; wmin 경계·단위 확인.
- d₀=νs+μs, Δs tap 정렬, pose_id와 timeline 매칭 검산.
- GT를 섞거나 suffix를 교체해도 같은 prefix의 추정 출력이 변하지 않는지 검사.
- 위험도에 사용한 현재 측정이 외생적 독립 변수라는 허위 가정 금지. robust 가중 갱신의 공분산은 경험적 calibration 대상임을 표기.

감사 요청서: `audit_requests/S1_CODE_AUDIT_REQUEST_KO.md`.

### 4.6 결과 감사·주장 지원 판단

| 주장 | 지지에 필요한 증거 | 부족한 증거 |
|---|---|---|
| S1-C1 오염 검출이 좋아짐 | 정의한 오염 수준별 recall/precision/오검출, 깨끗한 관측 손실 | 임계값을 낮춰 기각 수만 증가 |
| S1-C2 잘못된 단일 갱신이 줄어듦 | 같은 prior에서 실제 오류 증가량 감소, covariance 할인 일치 | K만 작아짐 |
| S1-C3 전체 예방 효과 | 자연 재귀에서 실제 RMSE·tail·calibration 동시 개선, 보호조건 준수 | 한 시점 또는 수용표본만 개선 |

S1-C1/C2만 통과하면 `LOCAL_SUPPORT_ONLY`. 전체 연구 주장의 예방 부분을 지지하려면 S1-C3 결과가 필요하다. 결과 감사 요청서: `audit_requests/S1_RESULT_AUDIT_REQUEST_KO.md`.

## 5. 2단계 — 선택적 P 복구: 이미 과신된 상태의 교정 가능성 회복

### 5.1 가설과 처치

**S2-H:** 새 관측의 신뢰도를 관리한 상태에서, 이미 과신된 prior의 관련 방향을 넓히면 실제 상태가 더 잘 교정된다. P만 확대하여 coverage가 좋아진 것은 복구 성공이 아니다.

주 처치는 평균을 유지한 PSD 추가다.

\[
\widetilde P^- =P^-+q_tu_tu_t^T+q_\psi u_\psi u_\psi^T,
\]

ut는 앵커 수평 방향에 수직인 위치 접선 단위벡터, uψ는 Heading 축이다. v0.1 제안은 접선 표준편차 목표 0.10m, Heading 목표 1°를 **하한**으로 두어
\(q_j=\max(0,\sigma_{j,target}^2-u_j^TP^-u_j)\)로 계산한다. 기존 분산을 줄이지 않는다. 각도 제곱을 rad²로 변환한다.

주 실험에서 bg 평균과 Qbg는 그대로, bg 분산도 그대로다. bg 불확실성 확대(예: 목표 0.05°/s)는 별도 명시된 ablation이며 주 처치에 섞지 않는다. B0 정답에 맞춰 bg를 0으로 리셋하는 것은 금지한다.

ρhat<0.25m에서는 접선 방향이 불안정하므로 사전 등록한 isotropic XY 추가분산으로 전환한다. 예: \(q_{xy}=\max(0,0.10^2-\lambda_{min}(P_{xy}))\), ΔPxy=qxy I. 이 fallback 자체의 발동과 비용도 기록한다.

### 5.2 복구 발동: 오류 정답을 보지 않는 상태기계

다음은 **초기 구현 제안값**이며 승인 전 최적값이 아니다.

1. 모든 arm은 가중치 적용 여부와 무관하게 동일 정의의 위험도를 계산한다.
2. 최근 5초 내 BASE 수용 관측 중 1−w≥0.5가 3회 이상이면 `SUSPECT_LATCH`를 켠다. 최초 관련 관측과 그 이전 checkpoint를 기록한다.
3. latch는 현재 d₀가 작아졌다는 이유만으로 지우지 않는다. 60초를 초과하면 `HISTORY_EXPIRED_REMAIN_SUSPECT`로 전환하여 오래된 근거로 무조건 재처리하지 않는다. 복구를 적용했다는 사건(`RECOVERY_APPLIED`)과 실제 정답오차가 회복됐다는 사후 평가를 구분한다.
4. 자동 복구 후보는 위험도 1−w≤0.25가 연속 1초 유지되고 ρhat≤1.5m인 시점으로 제한한다. **이 조건이 LoS 정답을 보장한다는 주장은 금지**한다.
5. 최근 2초의 예측 Jacobian·운동 정보가 충분한지 검사한다. 시간 전이 Φ를 포함한 4상태 데이터 정보행렬을 fixed scale D₄=diag(0.10m,0.10m,1°,0.05°/s)로 정규화한다. bg를 알려진 상수로 고정해 pose 정보를 과대평가하지 않고, nuisance bg를 Schur complement로 제거한 pose 유효정보(특이한 경우 사전 등록한 pseudo-inverse/rank 규칙)의 λmin≥10^-6를 제안한다. 미달이면 `INSUFFICIENT_GEOMETRY`, 복구 보류. 이 수치는 실제 가관측성 보증이 아니라 사전 운용 guard이며 conditional 정보와 marginal 유효정보를 모두 기록한다.
6. 1개 episode당 P 확대 1회, cooldown 20초, 경로당 최대 3회. 적용 후 2초의 관측 품질 유지와 geometry guard 통과 시 `MONITORING`으로 복귀하지만, 이것을 상태 정확성의 증명으로 쓰지 않는다. 조건 실패 시 평균을 임의로 이동하지 않는다.

과신된 P 자체로 geometry scale을 정규화하지 않는다. 상태가 틀려도 작은 d₀가 나올 수 있으므로, 현재 위험도뿐 아니라 의심 이력·운동 다양성·실패 시 보류를 함께 사용한다. 관측이 여전히 심하게 오염됐으면 P를 키워 그 관측에 더 끌려가지 않도록 보호조건을 둔다.

### 5.3 두 가지 시험을 분리

**M — 동일 시작점 복구 시험:** 기존 MB_VAR의 같은 (x,P)와 같은 이후 입력을 A/B/C/D에 제공한다. 등록된 30/60/90초 checkpoint 및 baseline에서 인과적으로 생성한 episode 시작점을 사용한다. 이 시간점은 알려진 데이터의 진단점이고 일반화 증거가 아니다.

**P — 전체 운용 시험:** t=0부터 각 arm이 자신의 prior와 상태기계로 발동한다. trigger 수·시점 변화도 방법 효과에 포함하여 보고한다.

M에서는 공통 shadow가 결정한 발동 스케줄을 사용해 ‘처치의 효과’와 ‘서로 다른 발동’ 효과를 분리한다. P에서는 각 arm의 현재 상태로 발동한다. 두 결과를 합쳐 동일 시험으로 표현하지 않는다.

### 5.4 필수 대조

- P 주입 OFF / 접선+Heading ON.
- Heading-only / 접선+Heading / 접선+Heading+bg는 개발 ablation. 주 비교가 바뀌면 새 동결.
- 순수한 P 확대 후 **측정 갱신을 하지 않는 대조**: 평균은 변하지 않아야 한다.
- ν=0 합성 음성시험: P 확대만으로 평균이 ‘복구’되었다는 구현을 차단.
- 깨끗한 LoS·이미 정확한 상태에서의 불필요한 복구; 초기 큰 prior 오차와 일시적 RF 오염을 구분하는 합성 시험.
- P 확대가 NIS를 낮춰 더 많은 오염을 통과시키는 효과는 F 게이트로 우선 차단하고 O에서 별도 검사.

### 5.5 코드 및 결과 감사

코드 감사는 ΔP≽0, cross-covariance 유지, 평균 불변, 주입 1회성, cooldown, 축·단위·near-axis fallback, gate separation을 검산한다. 전체 P를 임의 diagonal로 바꾸거나 eigenvalue clipping으로 오류를 숨기지 않는다.

결과 감사는 **같은 잘못된 시작상태에서** 실제 Heading·XY가 줄고, 회복시간·tail·calibration이 좋아지는지 본다. P만 커져 z-score/coverage가 좋아진 경우는 `UNCERTAINTY_RELAXED_ONLY`, 아직 상태 복구를 지지하지 않는다.

요청서: `audit_requests/S2_CODE_AUDIT_REQUEST_KO.md`, `audit_requests/S2_RESULT_AUDIT_REQUEST_KO.md`.

## 6. 3단계 — 체크포인트 재처리: 잘못된 평균/P 이력을 다시 계산

### 6.1 가설과 핵심 구분

**S3-H:** 과거 오염 구간에 대한 신뢰도를 사후 현재 시점에서 재평가하고, 그 이전 체크포인트부터 EKF를 재실행하면 현재 상태와 P를 추가로 개선한다.

**같은 체크포인트·같은 관측·같은 가중치·같은 상태기계로 다시 계산하기만 해서는 이득이 없어야 한다.** 이 `IDENTITY_REPLAY`는 필수 음성대조다. replay 이득은 과거 가중치/수용 해석이 명시적으로 바뀌었기 때문에 발생해야 한다.

주 실험에서는 **P 주입 OFF**로 두어 순수 replay 복구를 평가한다. 2단계 P 복구와 replay를 함께 쓰는 D_P+CP는 주 시험 후 별도 승인한 보조 대조로만 실행한다.

### 6.2 checkpoint·재처리 정의

- 주 버퍼 60초, checkpoint 간격 1초. 10/30초는 길이 민감도 대조로만 보고하며 결과를 보고 주 버퍼를 바꾸지 않는다.
- 최초 의심 episode 직전 checkpoint를 선택한다. checkpoint 저장내용: x/P, 마지막 처리 sample id, 위험도·episode·cooldown 상태, shadow BASE 상태, frozen 설정 hash, RNG 상태가 필요한 보조 모듈의 상태.
- 저장된 원본 z, controls, timestamp, RF 특징, μ/base R를 시간순으로 다시 처리한다. 센서잡음을 새로 추출하지 않는다.
- retrospective 추가 할인: 현재 시점까지 판정된 의심 episode 안에서만 \(w_j^{hist}=\min(w_j^{recomputed},0.25)\). episode 경계 규칙은 2단계와 공유하고, 현재 이후 데이터는 보지 않는다.
- d₀, H, K, σb, P는 **재처리 중 새 상태**에서 다시 계산한다. 상태 비의존 CIR 특징만 재사용 가능하다.
- 해당 episode는 복구 당시까지의 관측으로 정해지므로 과거 시점에 대한 delayed reweighting이다. 과거 시점에서 이용할 수 있었던 온라인 정보라고 주장하지 않는다.
- 후보 채택은 GT·작은 NIS·평가 RMSE로 정하지 않는다. 주 제안은 finite/PSD/인과성·packet 완전성 통과와 현재 상태 대비 변화량 안전한계(위치 0.5m, Heading 10°, bg 0.10°/s 이하 제안)를 만족하는 모든 후보를 채택하는 결정론적 규칙이다. 한계 초과 시 구성요소를 clip하여 강제 채택하지 않고 `CANDIDATE_OUT_OF_BOUNDS`로 보류한다. 이 값도 실행 전 승인한다.
- 최종 후보의 x/P·내부 상태·history를 원자적으로 교체한다. 평균만 새것, P는 옛것인 혼합 상태를 만들지 않는다. 현재 main filter의 마지막 sample id와 후보가 처리한 마지막 id가 다르면 그대로 교체하지 않는다. 들어온 관측까지 catch-up하거나 budget 초과로 후보를 폐기하고 이전 출력계열을 유지한다.
- episode 중복 replay 방지, 중첩 replay 금지, 처리 횟수·최대 버퍼·예산을 제한한다.

### 6.3 정보 중복과 미래정보 차단

1. **현재 posterior에서 과거 관측을 다시 추가하지 않는다.** 적용할 첫 관측 이전 checkpoint로 되돌아간다.
2. 새 추론 체인에서는 동일 관측을 한 번만 사용한다. 계산 과정에서 다시 처리했다는 횟수와 최종 정보 계상 횟수를 구분한다.
3. 재처리 결과를 현재 추정과 독립 측정처럼 Kalman fusion하지 않는다. 교체하거나 미채택 상태로 폐기한다.
4. replay 완료 전 이미 외부로 보낸 출력은 지우지 않는다. `online_emitted`와 `retrospective_smoothed`를 따로 저장한다.
5. 주 성능은 **각 시점에 실제 이용 가능했던 online_emitted 상태**로 계산한다. 수정된 과거곡선은 부수 결과다.
6. t 시점의 replay 후보는 t 이후 데이터를 사용할 수 없다. suffix 변경 테스트에서 t까지의 출력이 동일해야 한다.
7. 관측-derived risk로 가중치를 변경하는 robust 근사이므로, raw packet을 한 번 썼다는 사실만으로 통계적 독립성·정확한 Bayesian posterior를 보증하지 않는다.

### 6.4 checkpoint가 이미 잘못됐거나 부족한 경우

의심 구간이 버퍼 이전에 시작했거나 checkpoint가 없으면 `HISTORY_INSUFFICIENT`. 조용히 잘못된 최근 checkpoint를 ‘정상 초기점’으로 취급하지 않는다. baseline 유지/보호 모드 지속을 주 정책으로 하고, P fallback을 자동 추가하지 않는다. fallback을 추가하면 별도 처치로 평가한다.

무처치 재처리 성공과 오염 이전 checkpoint에서의 재가중 복구를 각각 확인한다. 의심 구간 이후 checkpoint, 짧은 버퍼, 순서 뒤바뀜·중복 packet·missing packet을 의도적으로 넣어 보류가 작동하는지 감사한다.

### 6.5 결과 감사·주장 경계

- `IDENTITY_REPLAY`와 원래 causal pass가 같은지, `REWEIGHTED_REPLAY`와 동일 checkpoint에서의 독립 cold replay가 같은지 검증한다.
- D_CP 대 B 및 D_CP 대 D_P의 현재 시점 오차 차이, recovery rate, latency, peak memory를 비교한다.
- 과거 smoothed 곡선만 좋아지면 **온라인 복구 지지 아님**.
- 동일·보다 적은 정보의 재계산으로 P만 계속 작아지면 정보 중복 또는 convention 오류를 먼저 의심한다.
- 같은 관측률 5 Hz에서 per-packet/replay stall·queue lag를 측정한다. p99 200ms 안의 전경 출력 예산을 주 제안으로 두되 하드웨어·측정범위는 사전 동결한다. 미달이면 정확도 결과는 보고하되 실시간 적용 가능 주장에는 HOLD를 건다.

ROS robot_localization의 지연관측 복원/재처리 기능은 구조 참고 자료일 뿐, 이번 오염 복구의 검증 결과는 아니다. [S8]

요청서: `audit_requests/S3_CODE_AUDIT_REQUEST_KO.md`, `audit_requests/S3_RESULT_AUDIT_REQUEST_KO.md`.

## 7. 전체 성능을 위한 네 실험 — 예방×복구 2×2

### 7.1 주 factorial

| Arm | 현재 관측 예방 가중치 | 복구 | 설명 |
|---|---|---|---|
| **A** | OFF | OFF | 원본 MB_VAR |
| **B** | ON | OFF | 예방만 |
| **C_R** | OFF | ON | 복구만 |
| **D_R** | ON | ON | 예방+복구 |

복구 R은 하나씩 바꾼다.

- **2단계 R=P:** A/B/C_P/D_P.
- **3단계 R=CP:** A/B/C_CP/D_CP. P 주입은 OFF.

C_CP의 ‘예방 OFF’는 **앞으로 들어오는 관측에 상시 가중치를 적용하지 않는다**는 뜻이다. 복구 시 과거 의심 episode만 재가중하는 것은 checkpoint 복구의 정의에 포함된다. 원래 가중치 그대로 다시 계산하는 C_CP는 identity 대조일 뿐 효과가 기대되는 복구 방법이 아니다.

### 7.2 비교해야 하는 효과

오차 손실 L(작을수록 좋음)에 대해 각 route·bias·channel·seed별로 계산한다.

\[
\Delta_{prevent}=L_B-L_A,\quad
\Delta_{recover}=L_{C_R}-L_A,\quad
\Delta_{recover|prevent}=L_{D_R}-L_B,
\]
\[
I=L_{D_R}-L_B-L_{C_R}+L_A.
\]

D가 A보다 좋다는 사실만으로 복구가 유효하다고 하지 않는다. 복구의 추가 가치는 D−B, 예방의 추가 가치는 D−C로 본다. I<0은 선택한 **손실 척도에서**의 상호작용이고, D가 가장 좋다는 사실과 같지 않다. RMSE·MSE·coverage는 각각 따로 보고하며 사후 가중 합으로 유리한 종합 점수를 만들지 않는다.

### 7.3 실행 규모 제안

동결된 대표 정책 1개에 대한 R=P 또는 CP 한 묶음:

- 개발: 2 routes × 2 bias × 2 channels × 10 seeds × 4 arms = **320개 경로 replay**.
- 추가 시드 안정성: 동일 조건 × 20 seeds × 4 arms = **640개 replay**.
- 2·3단계 모두 수행하면 최대 1,920개 arm 실행에 해당하며, 동일 A/B 결과는 입력·설정 해시가 같을 때 재사용 가능하다.

단일-prior·snapshot 복구·합성 음성시험·정책 ablation은 이 수에 포함되지 않으므로 별도 상한을 등록한다. 후보 전체를 모두 확증 seed에 돌려 가장 좋은 것을 고르지 않는다. 추가 대조는 계약 amendment가 필요하다.

## 8. 평가지표와 결과 판정 기준

### 8.1 반드시 함께 보고할 지표

| 영역 | 지표 | 해석 주의 |
|---|---|---|
| 정확도 | Heading·XY RMSE, radial/tangential RMSE, signed bias, p95/max 오차 | route 길이가 다른데 packet pooling으로 R5가 결과를 지배하지 않게 함 |
| 불확실성 | Heading 68/95/99% coverage, XY95, NEES3/4/XY, σ·ellipse 면적 | P를 크게 해 coverage만 높이는 것은 충분하지 않음 |
| 관측 | pregate NIS, 수용·할인 수, 잔여 ε²/R, 평균비와 비평균 | 수용 집합의 NIS를 무조건 χ² 평균과 비교하지 않음 |
| 복구 | 동일 snapshot 이후 10/20초 오류 적분, 정확도 회복시간, false recovery, 실패/보류 | 미복구·short remainder는 삭제하지 않고 censoring/실패로 보고 |
| 운용 | p50/p95/p99 latency, replay stall, peak memory, buffer miss, shadow 비용 | offline 계산 성공을 실시간 성공으로 바꾸지 않음 |

**복구시간의 v0.1 운용 정의 제안:** trigger 이후 Heading 절대오차≤1°, XY오차≤0.10m가 2초 연속 유지된 최초 시각. offline evaluator만 GT로 평가한다. 이미 만족한 시작점은 recovery-time 모집단에서 분리하고, 불필요한 복구 손해를 평가한다. 이 물리 목표는 사용자가 확정한 요구치가 아니라 승인 대상 제안값이다.

### 8.2 사전 성과 기준 제안

다음 수치는 확립된 물리 법칙이나 이미 통과한 결과가 아니라 **v0.1 채택 기준 제안**이다. 실행 전에 감사·승인하고 이후 바꾸지 않는다.

- **R4-B Full 정확도:** B 또는 D가 A 대비 Heading RMSE 쌍대 비율 중앙값≤0.90, XY 중앙값 비율≤1.05. B0와 L2를 각각 보고한다.
- **불확실성 개선:** R4-B Heading95의 |coverage−0.95|가 감소하고 평균·최악 시드 NEES가 악화하지 않아야 한다. 10%p 이상 coverage 증가를 의미 있는 개선 목표로 제안한다. 이것만 통과하면 `CALIBRATION_IMPROVED`, 95% 복원이 증명됐다는 뜻은 아님.
- **복구의 추가 가치:** D 대 B의 recovery-only 동일-snapshot 오류 적분과 온라인 전체 성능을 함께 보고한다. P 확대만으로 coverage가 오르면 복구 주장은 미지지.
- **보호조건:** R5-B 및 LoS의 Heading·XY RMSE 중앙값 비율≤1.05, 시드별 p90 비율≤1.20, 새 발산·비정상 재초기화 증가 없음. 기준 오류가 0에 가까우면 사전 등록한 절대 허용량을 사용한다(Heading 0.05°, XY 0.01m 제안).
- **효과 일관성:** 추가 20개 시드의 쌍대 차이와 seed-cluster bootstrap 구간을 보고한다. 최소 80% 시드에서 개선 방향이라는 보조 목표를 제안하되, RF 환경 일반화 검정으로 해석하지 않는다.
- **간결성:** D가 B보다 의미 있게 좋지 않으면 예방-only를 우선한다. replay가 P 복구보다 좋지 않으면 복잡한 replay를 채택하지 않는다.

정확도와 calibration을 모두 개선한 경우에만 ‘전체 성능 개선’을 해당 조건 범위에서 주장한다. 일부 route/bias만 좋아지면 범위를 축소한다. 모든 결과를 한 평균으로 합쳐 실패 조건을 숨기지 않는다.

### 8.3 통계적 독립성

독립 단위는 동일 RF에 대한 센서/초기조건 실현이며 packet이 아니다. seed별 쌍대 차이를 기본으로 하고 각 route를 따로 보고한다. block 분석을 추가해도 서로 같은 RF·바이어스 수준을 독립 환경 반복처럼 세지 않는다. 이미 본 R4/R5 전체는 개발된 실내 복도의 검증 자료이며 미사용 route/scene 일반화라는 표현은 금지한다.

## 9. 감사 체계와 단계별 산출물

| 감사 | 언제 | 독립 감사자가 직접 확인할 것 | 승인 토큰 |
|---|---|---|---|
| A0 설계·입력 | 구현 전 | 소스/원본 hash, 모델 정의, 데이터·설정 누출, 후보/지표/stop 동결 | SPEC_APPROVED |
| C1/C2/C3 코드 | 각 단계 구현 후·본 실행 전 | 별도 reference 연산, parity, PSD/Joseph, GT 차단, causality, 단계별 음성시험 | GO_Si_DEV / GO_Si_LOCKED_EVAL |
| R1/R2/R3 결과 | 각 단계 실행 후 | 원시 결과 집합 완전성, 독립 점수 계산, 사전 주장별 반례·지원 범위 | Si_RESULT_ACCEPTED_WITH_SCOPE |
| 책임자 승인 | 각 단계 이후 | 다음 단계 필요성·변경 범위 승인 | APPROVE_NEXT_STAGE 또는 STOP |

에이전트 기록에는 proposer/implementer/auditor id, 세션 id, runner id, 시작·종료, 입력·코드·계약 SHA, 독립 검산 SHA와 계산 로그를 저장한다. 같은 모델 계열을 써도 다른 컨텍스트·독립 코드·별도 실행으로 운용할 수 있지만, 그 사실만으로 인간 감독이나 완전한 독립성을 대체한다고 주장하지 않는다.

**현재 패키지에는 감사 요청 문안만 있다. 독립 에이전트 지정·호출·승인·실행은 아직 이루어지지 않았다.**

## 10. 수치 QA·중단 조건

### 10.1 제안 허용오차

- 새 F64 무처치 reference와 구현 간 state/P/h/H/μ/R: SI 좌표에서 atol=1e-10, rtol=1e-10 제안. 마스크와 sample id는 완전 일치.
- gate 경계 부근에서 부동소수점 차이가 나면 조용히 마스크를 고치지 않고 경계 샘플을 분리·검산한다.
- 기존 A_LOG처럼 F32로 저장한 자료는 양자화 한계가 있으므로 1e-10 parity 인증용으로 쓰지 않는다. F64 원본 재실행 또는 저장 정밀도에 따른 별도 허용오차를 **실행 전** 확정한다. F32 대조는 provenance·진단 용도다.
- P 대칭/PSD는 사전 동결한 상태 스케일로 정규화하여 검사한다. 실질적인 음의 고유값을 eigenvalue clipping으로 숨기지 않는다.
- 독립 감사자가 같은 production update/score helper를 import해 얻은 일치만으로 독립 재현을 인정하지 않는다.

### 10.2 즉시 STOP

원본 hash 불일치, 라벨/GT 누출, 같은 관측의 중복 계상, 알려진 과거 output의 미표시 교체, 동결 설정 변경, 무처치 불일치, 실제 실행 SHA와 보고 SHA 불일치, 독립 감사 누락, 원본 파일 덮어쓰기, 신규 RF/경로 생성, 미등록 후보·시드 선택, 수치 발산 은폐.

과학적 성능 악화는 반드시 남긴다. 오류 수정으로 재실행할 때는 원 실패 결과를 보존하고 새 code SHA/계약버전/실행번호를 사용한다. `exit 0`이나 CI 성공만으로 과학 PASS를 발급하지 않는다.

## 11. 저장할 원시 기록

각 logical timestep에 다음을 저장한다.

- source/contract/code/artifact SHA, route/channel/bias/seed/arm, timestamp, pose_id.
- z, μr/μs, Rbase/RVAR/Reff, σb 계산 시점·ρ, H/h, d₀, Δs, risk, weight.
- x/P before predict, after predict, before recovery, after recovery, posterior; K/ν/S/NIS.
- BASE gate, method gate(있으면), r/s 사용 flag, 위험도와 실제 적용 처치를 분리.
- episode/trigger/quality/observability/cooldown 상태, ΔP 구성·PSD 검사, skip 원인.
- checkpoint id·저장시각·contains_until, replay start/end/decision/commit 시각, 역사 가중치 변경 사유, packet 적용 ledger, prefix causality hash.
- online_emitted, retrospective_smoothed를 분리한 상태/공분산, replay 지연 중 출력 정책.
- evaluator 전용 GT/error/NEES/coverage. algorithm_input 파일과 evaluator_truth 파일을 분리.

핵심 산출물: `CONTRACT_LOCK.json`, `INPUT_LOCK.json`, `ENV_LOCK`, `CODE_AUDIT_Si.json`, `RUN_MANIFEST.json`, `TRACE_F64.*`, `SCORES_PER_SEED.csv`, `FAILURES.jsonl`, `CLAIM_SUPPORT_Si.csv`, `RESULT_AUDIT_Si.json`.

## 12. 최종 주장 매트릭스

| Claim ID | 주장 | 필요한 최저 증거 | 실패 시 축소 표현 |
|---|---|---|---|
| C1 | 낮춘 기준이 놓친 오염을 검출 | 동결된 오염 정의·오검출 대조 | 개발 표본에서 검출 증가 |
| C2 | 가중치가 잘못된 갱신·P 축소를 완화 | 동일-prior 독립 재계산 | 국소 사례의 영향 제한 |
| C3 | 예방이 전체 MB_VAR를 개선 | 전체 causal replay + 보호조건 + 추가 seed | 일부 조건 개선/재귀 미확인 |
| C4 | P 복구가 이미 틀린 상태를 회복 | 동일-snapshot 평균오차 감소 + coverage/sharpness | 불확실성 완화만 확인 |
| C5 | checkpoint가 추가 온라인 이득 | identity/cold replay 감사 + emitted 성능 | retrospective 개선 또는 추가 이득 없음 |
| C6 | 예방+복구가 단독보다 낫다 | D−B, D−C, interaction·계산비용 | 결합 필요성 미확인, 단순 모델 유지 |
| C7 | 일반적으로 더 우수한 필터 | 별도 미사용 RF/환경·다른 모델 검증 | **이번 계획으로는 주장 불가** |

## 13. 근거·참조

- **S1:** `pol_bias_model/exp_pb.py`, source blob `1430a8bb66cf919ef0932b271935b420098b5ba3`, [고정 reference](https://github.com/myoungsunk/sionna-resimulation/blob/7e2855314de867e0481f8eb5ed1a07c48710f364/research/DS_MASK_CAUSAL_X1_X2_20261026/pol_bias_model/exp_pb.py).
- **S2:** `evidence/threshold_sweep_same_prior.csv` — 기존 저장 prior의 사후 임계값 진단. 전체 재귀 결과 아님.
- **S3:** `evidence/one_step_Rss_counterfactual.csv` — F32 원본 로그에서 독립 재계산한 단일-prior 결과. F64 실행 parity 인증 아님.
- **S4:** [이전 d₀ 재귀 실험](https://github.com/myoungsunk/sionna-resimulation/blob/7e2855314de867e0481f8eb5ed1a07c48710f364/research/PJ_DS_GATED_20261021/14_D0_VARIANCE_GATE_RECURSIVE_KO.md).
- **S5:** [PR #19](https://github.com/myoungsunk/sionna-resimulation/pull/19), read-time HEAD `7e2855314de867e0481f8eb5ed1a07c48710f364`. 이 계획은 해당 분석을 MB_VAR 중심 예방·복구 설계로 좁힌 후속 초안이며 자동 대체·병합하지 않음.
- **S6:** [ctl_core.py](https://github.com/myoungsunk/sionna-resimulation/blob/7e2855314de867e0481f8eb5ed1a07c48710f364/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_control_correction_20261029/ctl_core.py), blob `6a86870bbc97aadca4ff139c5a716befa18ff4cb` — baseline, σb timing, per-channel update 및 checkpoint continuation의 기준.
- **S7:** Duran-Martin et al., ICML 2024, [Outlier-robust Kalman Filtering through Generalised Bayes](https://proceedings.mlr.press/v235/duran-martin24a.html). 가중 관측 필터의 일반적 참고이며 이번 제안에 해당 논문의 정리·보장을 자동 이식하지 않음.
- **S8:** [robot_localization 원본 문서](https://github.com/cra-ros-pkg/robot_localization/blob/rolling-devel/doc/state_estimation_nodes.rst), smooth_lagged_data/history_length. 상태 복원·재처리 구조 참고. 사용자 시스템의 오염복구 성능 근거가 아님.

---

**다음 승인 대상은 코드 실행이 아니라, 이 초안의 입력 lock·계수·주장 기준과 독립 감사자 배치이다.** 모든 승인이 없는 현재 상태에서는 구현·과학 실행·성능 개선 선언을 시작하지 않는다.
