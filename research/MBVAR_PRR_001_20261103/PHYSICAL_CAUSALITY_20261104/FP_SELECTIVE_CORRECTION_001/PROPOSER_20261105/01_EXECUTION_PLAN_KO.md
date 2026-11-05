# FP-SC-001 — 운동·CIR 증거를 이용한 선택적 first-path 정정 검증계획

**문서 버전:** v0.1 / 2026-11-05  
**작성 역할:** PROPOSER  
**상태:** PROPOSER_DRAFT · NOT_FROZEN · NOT_IMPLEMENTED · NOT_RUN  
**승인 상태:** 모든 실행 GO = false. 이 문서는 구현·실행·채택 승인이 아니다.  
**대상 저장소:** `myoungsunk/sionna-resimulation`  
**주 기준:** PR #37 `c68dcdcdd01180617b827e1f6ebb58e6740a8e29`; RF·기존 필터 기준 PR #35 `e38de517a21a43bb210c7e04c9fbd6517d8a95cf`.

---

## 0. 제안의 핵심과 이번 문서의 경계

### 핵심 가설

> 현재 패킷을 사용하기 전의 EKF/DR 예측, 이전 신뢰 가능한 관측의 시간적 일관성, 현재 두 RX의 CIR 증거를 결합하면 기존 first-path(FP)의 정상 선택은 보존하면서 오선택만 선별적으로 교정할 수 있다. 그 교정이 거리의 정확도를 훼손하지 않으면서 Dual-LP 편파비 오차를 줄이고, 최종적으로 MB_VAR의 Heading·XY 정확도와 불확실성 일관성에 도움이 되는지 검증한다.

이 문장은 하나의 가설이 아니다. **오선택 식별 → 후보 내 정답 존재 → 올바른 후보 선택 → 편파비 개선 → 신뢰도 정합 → 재귀 개선**의 각 연결이 모두 검증돼야 한다. 어느 하나의 성공을 전체 성공으로 대체하지 않는다.

이번 제안은 기존 S1–S3 복구 정책의 재튜닝이 아니다. **EKF에 관측을 넣기 전, 관측 생성 단계의 FP 선택**을 바꾼다. 주 실험에서는 S1 예방 가중치·S2 공분산 주입·S3 체크포인트 재처리를 끄고 기존 MB_VAR(W0)를 비교 기준으로 사용한다. 기존 완료 결과·STOP·NO-GO·실시간 HOLD는 수정하지 않는다.

**산출물은 계획·계약·감사 요청서뿐이다.** 기존 PR #37의 탐색 코드와 oracle 수치를 검토했지만, 이 문서를 작성하면서 RF·CIR 실험이나 EKF 재귀를 새로 실행하지 않았다. 문서 자체 검수와 향후 독립 과학감사는 구분한다.

### 출발 근거와 아직 검증되지 않은 사항

| 확인된 저장소 근거 | 이번 계획에서의 취급 |
|---|---|
| 기존 관측기는 257-bin Hann / 1,028-tap IFFT, 강한 RX의 **진폭** peak 30% 첫 crossing을 사용한다. [S03] | 이 수신기 정의를 무처치 기준으로 정확 재현한다. 전력 30%와 혼용 금지. |
| 현재 tap 거리 간격은 약 0.1495522588m이다. [S04] | 간격이지 물리적 다중경로 분해능이나 실제 ranging 오차가 아니다. |
| G4 24조건에서 같은 위치의 yaw 변경만으로 tap 및 편파비가 바뀌었다. [S05] | 시간적 이동시험으로 재해석하지 않고 정지 자세·검출 경계 대조로 사용한다. |
| 정답 pose를 사용한 거리모델의 최근접 tap은 24조건 중 22개에서 LoS 참조와 일치했지만, 기존 정상 tap을 잘못 바꾼 1건도 있었다. [S04] | **oracle 가능성 진단**일 뿐 온라인 교정 성능이 아니다. |
| 같은 oracle 거리예측에 −4/0/+4cm를 더하면 일치 수가 20/22/8개였다. [S06] | 물리적 이동을 새로 시뮬레이션한 결과가 아니라 고정 CIR 위의 예측 섭동이다. hard rounding의 음성 대조로 보존한다. |
| PR #37은 3,136개 pose의 clean CIR와 저장된 B0 seed10 prior를 이용하는 open-loop 파일럿이다. [S01]·[S02] | 이 결과만으로 noisy packet·실제 폐루프·교정된 R의 성능을 주장할 수 없다. |
| 확인한 PR #37 HEAD에는 `RESULTS_ORACLE_001`이 있고 `RESULTS_001` 실데이터 결과 폴더는 없다. [S09] | 그 스냅샷에서 실데이터 파일럿 완료·독립 ACCEPT를 전제하지 않는다. 후속 커밋은 별도 registry로 추가한다. |

## 1. 검증이 필요한 가설군

| ID | 반증 가능한 하위 가설 | 실패 또는 반례 | 주 실험 |
|---|---|---|---|
| **H0 정의·재현** | 참거리, 검출거리, 보정거리, state radial error를 분리하고 기존 FP/MB_VAR를 재현할 수 있다. | prior가 다른 거리 정의를 사용함; no-op에서 상태나 tap이 달라짐 | E0 |
| **H1 오선택 식별** | 현재 CIR와 인과적 이력만으로 정상 FP를 거의 건드리지 않고 참조 이탈 FP를 검출할 수 있다. | 정상 LoS·회전·양자화 경계를 오검출로 표시; 검출률을 높이려 정상 측정을 희생 | E1 |
| **H2 후보 선택·운동정보** | 후보 간 거리·편파 차이와 DR 이동 제약이 CIR-only보다 선택에 추가 정보를 주며, 잘못된 prior에서도 강제 선택을 억제할 수 있다. | 참조 후보 자체가 없음; 과신 prior가 신호를 이김; 4cm hard gate가 정상 tap 배제 | E1,E2 |
| **H3 편파 개선·ranging 보호** | 선택적 FP 교정이 같은 tap에 남는 간섭과 구별되는 편파비 오차 감소를 만들고 ranging을 보호한다. | 참조 tap을 맞춰도 편파오차 증가; 정상 range 훼손; changed-only 이득이 전체 손해 은폐 | E2,E3 |
| **H4 신뢰도·불확실성** | 후보 점수차·CIR 지원·후보별 s 차이가 실제 교정 성공/손해와 연결되고, 교정 후 관측오차분포를 보수적으로 표현할 수 있다. | 높은 점수차인데 후보 모두 잘못됨; s 변화량을 개선량으로 오인; 좁은 R과 낮은 NIS만 생성 | E2,E3 |
| **H5 단일 갱신 정합** | 같은 prior에서 교정된 r/s의 영향이 분리되며, 한 패킷의 정보가 중복 계상되지 않는다. | current posterior로 재선택 후 재갱신; raw r와 corrected s의 상관 무시; 상태만 제한하고 P는 원대로 축소 | E3 |
| **H6 폐루프 순이득** | 새 selector가 자기 prior를 사용하며 t=0부터 실행돼도 R4 개선과 R2/R5·LoS 보호를 동시에 만족한다. | 저장 baseline prior의 이득만 존재; 오선택 lock-in; calibration이나 range가 악화 | E4 |
| **H7 운용 가능성** | 동일 정책을 5Hz에서 기한 내 실행하고 누락·지연·초기화 실패에서 안전하게 보류한다. | p99 출력 지연>200ms, stale range 사용, 누락 패킷 후 잘못된 4cm 적용 | E5 |

**의존 관계:** H0 → H1/H2 → H3/H4 → H5 → H6 → H7. H1/H2가 실패해도 원인 분석과 음성 결과 기록은 가능하지만 H6를 성공 후보의 확증으로 자동 확대하지 않는다.

## 2. 공통 계약: 무엇을 ‘FP 오류’로 부를 것인가?

### 2.1 네 거리 정의

- `r_geo`: 안테나 기준점에서 앵커까지의 3D 기하 거리. GT는 사후 평가 전용이다.
- `r_det(n)=c·n/(N_FFT·Δf)`: 특정 tap의 수신기 출력 거리.
- `r_corrected`: 원래 관측함수의 지연편향과 학습 평균 등, 실제 filter convention에 따라 보정된 거리. `z_r−μ_r`만으로 참거리라고 부르지 않는다.
- `r_state`: EKF 위치에서 계산한 앵커 거리. 그 오차는 ranging 관측오차와 다르다.

E0는 이 네 값의 signed bias·MAE·RMSE·p95/p99·maximum을 **원본과 동일 모집단**에서 각각 산출한다. “기존 ranging은 충분히 정확했다”를 미리 가정하지 않고 검증한다. 대부분의 구간이 정확하고 소수 tap jump만 나쁘다면 정상 구간 보호를 우선한다.

### 2.2 참조 tap과 실제 전파 도달시간은 같은 정의가 아니다

`n0(k)`는 현재 Full 패킷에서 원래 검출기가 고른 tap이다. `nL0(k)`는 같은 pose·yaw의 **clean direct-only LoS를 같은 검출기로 처리한 참조 tap**이다. 둘의 일치 여부는 검출기 참조 정합도이지 직접파의 정확한 연속 도달시간을 알아냈다는 의미가 아니다. RT direct delay 및 기하 거리는 별도의 물리 진단으로 둔다.

주 라벨은 clean 데이터에서 `wrong_ref=1[n0 != nL0]`, `correct_ref=1[n0 == nL0]`이다. 1tap 차이와 ≥2tap 차이를 별도 계층으로 보고한다. noisy 시험에서는 `nL0` 기준을 주로 유지하되, 동일 noise recipe를 사용한 noisy LoS detector 분포도 평가하여 경계의 애매함을 표시한다. 저전력·직접파 부재·분모 미달에는 `UNKNOWN_REFERENCE` 또는 `NO_DIRECT_SUPPORT`를 부여한다. 이 표본은 정상/오류 분모에서 분리하지만 dropout과 출력 손실에서 삭제하지 않는다.

`nL0`가 선택됐다고 s 오차가 반드시 최소인 것은 아니다. 실제 표적은 **참조 일치와 s/r 오차 개선을 각각** 검증하는 것이다. LoS tap oracle은 기전 대조이며 모든 손실의 수학적 최적 상한이라고 부르지 않는다.

### 2.3 편파 정의와 목표 오차

두 RX에서 반드시 같은 n을 사용한다.

\[
s(n)=\frac{|C_+(n)|^2-|C_-(n)|^2}{|C_+(n)|^2+|C_-(n)|^2}.
\]

`e_s(n)=sFull(n)−sLoS(nL0)`와, 기존/교정 후 `z_s−h_s(xGT)−μ_s`를 분리한다. 전자는 수신기·물리 진단, 후자는 필터 관측모델 정합 진단이다. 둘을 섞어 개선율을 계산하지 않는다.

원래와 새 tap의 `Δs_corr=s(n*)−s(n0)`는 **처치 크기**다. 부호·크기가 크다는 사실 자체는 정답에 가까워졌다는 증거가 아니다.

## 3. 시간·운동·선택 신뢰도 계약

### 3.1 온라인 입력 경계

선택기 입력은 `Full CIR_k`, `F_(k−1)`, 현재 패킷 이전에 도달한 odom/gyro, `x_k^−,P_k^−`, 이전 trusted observation의 값·시각·신뢰도이다. 현재 raw FP와 현재 CIR 특징은 입력할 수 있지만 **현재 패킷을 넣은 posterior**, GT, LoS 참조, 미래 frame, route/seed ID는 금지한다. route/seed는 평가·파일 조인 키로만 사용한다.

한 tick의 순서: 입력 정렬 → 이전 상태 전파 → 후보·위험도·선택/보류 → r/s 추출 → 관측모델·gate 계산 → **최종 관측정보 1회 반영** → 이력 업데이트.

### 3.2 4cm는 prior 오차의 표준편차가 아니다

\[
|r_{geo,k}-r_{geo,j}|\le\|p_k-p_j\|\le\int_{t_j}^{t_k}v_{max}(t)dt.
\]

0.2m/s, 연속 유효 tick 0.2s일 때 4cm이다. 2/5/10 tick 누락 뒤에는 elapsed time에 맞게 8/20/40cm로 달라진다. 실제속도, 동기오차, 슬립·레버암이 있으면 별도 불확실성을 더한다. heading 변화만으로 `nL0`가 움직일 수도 있으므로 검출기 정의의 시간 변화는 기하 거리 변화와 분리한다.

후보 j의 support는 점 하나가 아니라, **검출기 offset/quantization을 포함한 거리 구간**으로 표현한다. `r(n)±Δr/2`가 leading-edge detector의 실제 구간이라고 미리 가정하지 않고 E0의 직접파·sub-tap sweep으로 확인한다. `round(r_pred/Δr)` 단독 정책은 음성 대조로만 유지한다.

이전 FP가 틀렸을 가능성, 그 관측의 나이, yaw에 따른 detector offset 변화, DR 변위오차, 상태의 누적 오차를 기록한다. 같은 거리 오차가 공유되므로 이전 FP와 EKF prior를 독립 거리 센서처럼 두 번 결합하지 않는다. detector offset을 현재 s에 맞춰 추정하여 혁신을 인위적으로 줄이는 것도 금지한다.

### 3.3 후보 생성과 신뢰도는 분리

현재 CIR의 두 포트에서 신호 지원 후보를 만든 뒤 prior로 순위를 매긴다. 두 포트 중 하나가 편파 null일 수 있으므로 **양쪽 모두 큰 전력**을 필수조건으로 두지 않는다. 단일 포트 support, 총전력, noise floor, leading-edge 구조를 각각 남긴다.

CIR-only / absolute-prior / DR-continuity / 결합 비교에는 **동일한 후보 집합**을 제공한다. 후보 생성기를 바꿀 때는 별도 ablation으로 분리한다. 원래 n0는 항상 후보와 fallback에 포함한다. 광선 정답·LoS tap을 이용해 후보를 삽입하거나 참조 주변만 탐색하지 않는다.

후보가 많은 경우 인접 tap은 독립 경로가 아닐 수 있다. 후보의 `Δn`, `Δr`, `Δs`, `Δphase`와 같은 lobe/basin 여부를 기록하고, 점수차는 인접 보간 tap 차이와 서로 다른 경로군 후보 차이를 구분한다. 전체 후보열을 합성 확률로 가정해 표본 수처럼 늘리지 않는다.

신뢰도는 적어도 세 항목을 구분한다.

1. `wrong_score`: 기존 n0가 의심스러운 정도.
2. `candidate_score/margin`: 대체 후보의 RF·시간적 지원과 차선 후보 대비 분리.
3. `pol_ambiguity`: 유효 후보들 사이 s 분산/범위. 이는 s 불확실성이지 교정 이득 확률이 아니다.

점수는 calibration 전에는 확률이라고 표시하지 않는다. `P(기존이 틀림)`과 `P(후보가 맞음)`을 독립이라고 가정해 곱하지 않는다. 모든 후보가 잘못된 경우에도 1위–2위 차이가 클 수 있으므로 null/no-valid-path 가설과 abstain이 필요하다.

### 3.4 기본 fallback과 별도 처치

주 정책은 `KEEP_ORIGINAL` 또는 `REPLACE_WITH_SUPPORTED_CANDIDATE` 두 선택이다. 증거 부족은 원래 detector 출력과 원래 update를 유지한다. 기존 패킷 자체가 미검출이면 새로운 정보를 만들어 내지 않고 원래 invalid handling을 유지한다.

불명확할 때 `R 확대`나 `pol update skip`을 추가하면 별도 정책이다. 이를 primary 선택기 안에 숨기지 않고 E3/E4의 위험도-only 대조와 비교한다.

## 4. 데이터·학습·고정 기준

### 4.1 데이터 층

- **D1 원래 동적 RF:** R2-B 979, R4-B 742, R5-B 1,415 = 3,136 pose. 고정 Full/LoS complex H, 원래 pose_id와 timeline 정렬.
- **D2 G4 정지 대조:** 6개 XY×4yaw=24조건. 시간순 이동 궤적으로 연결하지 않는다. oracle/양자화/회전 반례용이다.
- **D3 실제 prior와 controls:** B0/L2의 동결 MB_VAR W0, C1a prior 및 원래 gyro/odom/초기상태·mean/R. 저장 prior는 open-loop 단계에만 쓴다.
- **D4 noisy waveform:** 기존 `observe`의 **IFFT 이전 복소 H noise**를 정확 재현한다. 모든 arm에 같은 frame별 noise 배열을 제공한다. RNG stream은 candidate 개수나 arm의 처리 순서에 따라 달라지면 안 된다.
- **D5 실패·스트레스:** 잘못된 이전 tap, biased/overconfident prior, dropout, 약한 직접파, 직접파 제거 등. 저장 complex-field에서 직접파 제거는 합성 반례이며 실제 새 NLOS 환경 검증으로 부르지 않는다.

기존 noisy packet이 보존되지 않았으면 원래 RNG·variance·dtype·순서로 재생성하여 원래 관측 parity를 먼저 확인한다. 이것이 안 되면 새 noise realization이라는 사실을 표시하고 원래 noisy trace와 완전히 같은 입력이라고 주장하지 않는다. 추가 RF 시뮬레이션은 우선 시행하지 않으며, 필요한 원시 채널 또는 새로운 물리환경이 없을 때 별도 요청한다.

### 4.2 공개 데이터와 확인 평가를 구분

기존 clean RF, G4, 공개 seed0–29는 이미 관찰된 개발·재현 자료다. 세 번에 나눠 읽었다고 새 holdout이 되지 않는다. 랜덤 packet 분할은 동일 RF 인접 pose 누출 때문에 금지한다.

제안된 새 센서/초기오차 realization은 CAL seed30–39, SEALED seed40–59로 둔다. **사용 여부를 E0에서 확인**하고 이미 사용됐다면 최초 실행 전에 미사용 ID를 대체 동결한다. 새로운 noise/IMU seed는 같은 RF의 조건부 반복이지 새로운 propagation 환경이 아니다.

주 E4는 **이미 알려진 세 경로에 하나의 공통 selector를 적용하는 same-RF 조건부 검증**이다. selector의 TRAIN(seed0–9)/CAL(seed30–39)에는 공개된 세 경로를 사용할 수 있으나, route별 별도 rule·λ·신뢰도 cutoff를 두지 않고 모든 보호조건을 만족하는 공통 1개를 선정한다. SEALED seed40–59를 선택에 사용하지 않는다. 따라서 이 결과를 미사용 경로 검증이라고 부르지 않는다.

관측오차모델 재보정은 기존 baseline과 비교 가능한 route-heldout recipe를 명시한다. 예를 들어 R4 평가용 μ/R의 fit에는 R2/R5만 사용한다. selector가 이미 해당 경로를 본 사실은 여전히 남으므로 이것만으로 전체 pipeline이 route-heldout이라고 주장하지 않는다. **전체 pipeline의 경로 전이 검증**이 필요하면 selector/신뢰도/μ/R 전부를 나머지 두 경로에서 학습·선정하는 3개 outer-fold를 별도 등록한다. 이 경우 fold별 학습 모델은 달라도 정책 family·특징 정의·성과 기준은 같아야 하고, 각 fold는 미사용 경로 하나에 적용하는 독립 배포 가정이다. 이 추가 cross-route 실험은 E4의 720/1,440 예산에 포함되지 않으며 별도 GO가 필요하다.

fit/CAL/SEALED의 source IDs·pose blocks·controls IDs·noise seeds 전체 목록을 `SPLIT_MANIFEST`에 동결한다. raw RF가 공유된 반복의 제한과, 어떤 모듈이 어떤 경로를 보았는지를 module별 exposure table로 공개한다.

### 4.3 새 학습의 최소화

E0/E1에서는 새 estimator를 학습하지 않는다. E2에서는 고정된 점수 규칙을 비교하고, 필요할 때만 CAL에서 **신뢰도 보정**을 수행한다. 새 neural network, route별 classifier를 기본 경로로 넣지 않는다. E3의 μ/R 보정과 E2의 선택 정책 학습은 별도 작업·데이터·SHA로 기록한다.

현재 PR #37의 0.20m sigma floor·10% amplitude·±5tap·score margin0.8은 탐색 설정이다. 새 정책의 최적값으로 승계하지 않는다. E2의 후보군·계수·최대 탐색 횟수·선택 목적함수를 먼저 동결한다. 최대 27개 조합의 개발 탐색을 제안하며, **선정된 1개 주 정책**만 후속 확증 대상으로 지정한다. 선정에 실패하면 가장 좋아 보이는 잠금 결과를 나중에 고르지 않는다.

## 5. 단계 E0 — 정의·입력·기준선 감사

**대상 가설:** H0. 새 selector 구현에 앞서 실행할 첫 단계.

| ID | 실험·대조 | 가정/계약 | 필수 결과 |
|---|---|---|---|
| E0-01 | 원본 무처치 수신기·MB_VAR 재현 | 원래 dtype/phase/FFT·RX/TX 순서·threshold tie 규칙 유지 | tap/포트 exact, r/s·h/H·K/P parity |
| E0-02 | 참거리–검출거리–보정거리–state range 분해 | model h_r의 정의와 offset provenance 확정 | route/bias/channel별 bias·RMSE·tail, ±4cm/1tap 비율 |
| E0-03 | G4 정답 pose 및 ±4cm rounding 반례 재현 | oracle는 evaluator only, 무신규 RF | 12/24→22/24 및 20/22/8의 범위와 반례 보존 |
| E0-04 | 관측모델 mapping·noise·timing readiness | LFS 실 payload/hash/arrays 검증, current k input 봉인 | DATA_LOCK, RAW_PRESENCE, SPLIT_MANIFEST |

**설계상 중요:** `h_r`가 native quantized detector output과 다를 수 있다. 이 편차를 교정모델·interval uncertainty에 반영하지 못하면 **HOLD_MAPPING_UNRESOLVED**. 현재 h_r를 0.14955m로 나누어 가장 가까운 tap을 강제 선택하는 것을 주 실험으로 승인하지 않는다.

**감사:** SPEC 검토와 데이터감사를 분리한다. 파일 목록/LFS pointer만 확인한 것으로 raw 사용 가능 PASS를 내리지 않는다. 필요한 파일이 없으면 정확한 path·hash·shape·dtype·noise seed를 명시해 `MISSING_DATA_REQUEST`를 생성하고 해당 분기만 BLOCKED 처리한다.

## 6. 단계 E1 — 오선택 식별과 후보 가용성

**대상 가설:** H1, H2의 후보 생성 부분. 아직 FP 교정 결과를 EKF에 되먹임하지 않는다.

### 실험 세트

- **E1-01 후보 가용성:** clean D1·D2에서 baseline tap, strongest-only 후보, two-port 후보를 비교한다. 원래 n0가 참조 이탈인 사건에서 nL0가 생성 집합에 있는지 측정한다. prior로 pruning하기 전/후 recall을 모두 기록한다.
- **E1-02 오선택 탐지:** CIR-only, 절대 detector-prior 일관성, 이전 FP+DR 일관성, 결합 위험지표의 동일 모집단 성능 비교. 임계값 곡선은 개발자료에서만 생성하고 봉인 cutoff를 등록한다.
- **E1-03 음성 대조:** LoS 정상, 정지 yaw 변경, 양자화 경계, 이미 틀린 이전 FP, prior만 ±4/15/30/60cm 오류, 2/5/10tick 누락, 유효 후보 없는 낮은 SNR.

**가정:** D1의 실제 controls/timestamps로 elapsed motion을 계산한다. “1tick당4cm”를 이전 정상 sample과의 간격을 무시한 상수 gate로 쓰지 않는다. G4 yaw 배열을 순차 frame으로 연결하지 않는다.

**핵심 분모:** 전체 valid packet, 원래 참조정상, 원래 참조이탈, ≥2tap 이탈, UNKNOWN 각각. TP/FP 검출률과 candidate recall을 따로 보고한다. 후보가 없는 것과 선택점수 실패를 구분한다.

**제안 진입 기준:** reference-valid 큰 오류(≥2tap)의 후보 recall≥95%, 정상 집단 flag FPR와 coverage 전체 공개. 이 조건을 만족하지 못하면 H2 선택기 최적화보다 후보 생성 또는 신호 부재 문제를 먼저 기록한다. 통계적 희소성은 성공으로 보지 않고 `INCONCLUSIVE_SUPPORT`.

## 7. 단계 E2 — 선택적 정정, 4cm·후보 차이의 추가 가치

**대상 가설:** H2–H4. 테스트 가능한 정책을 다음과 같이 분리한다.

| ID | 정책 | 확인할 추가 정보 |
|---|---|---|
| B0 | 원래 30% detector, no correction | 정상 ranging·FP 보호 기준 |
| B37 | PR #37 공개 pilot 그대로 | 기존 exploratory absolute-prior 대조 |
| C | 같은 후보 집합의 CIR 증거만 | RF만으로 가능한 부분 |
| P | CIR + 현재 측정 전 absolute detector-range prior | 기존 state가 주는 정보 |
| M | CIR + 이전 관측/DR의 interval continuity | 짧은 radial 변화 제약 |
| PM | CIR + P + M, 두 단계 detect/replace | 결합의 추가 가치; 주 후보 |
| PM-FORCE | PM과 같은 점수이나 최상위 후보 강제 교체 | 보류·선택적 적용의 가치; 음성 대조 |
| NN-HARD | 단일 가장 가까운 예측 tap | 양자화·overconfidence 음성 대조 |
| O-REF | nL0 강제 선택 | oracle 기전 대조, online arm 아님 |

점수 함수는 `distance(candidate_support, predicted_support)`를 uncertainty로 정규화한 값과 CIR support를 사용한다. point rounding 대신 support interval을 사용한다. P와 M은 상관될 수 있으므로 점수 합을 독립 Gaussian likelihood라고 주장하지 않는다.

**정정 결정:** 기존 n0의 이탈 증거, 후보의 실제 CIR 지원, 차선 유효 후보와의 분리, prior 신뢰도가 모두 만족될 때만 replace. 각 항의 threshold·함수·가중치·tie·null 후보·cooldown은 CODE_AUDIT 이전 `POLICY_SPEC.json`에 고정한다. 이 문서의 식은 구현의 자동 승인 또는 임의 최적화 허용이 아니다.

### E2-01 동일 prior open-loop

첫 canary는 **기존 공개 B0 seed10의 R2/R4/R5 3,136개**다. 일부 유리한 hotspot만 선택하지 않는다. current CIR은 clean/noisy를 섞지 않고 별도 run으로 둔다. archived prior의 생성 관측과 현재 clean CIR이 다르다는 점을 기록한다. 이 시험은 selector 기전만 검증한다.

### E2-02 시간적 정정 tracker

EKF state는 fixed-prior로 두되, 선택기의 이전 trusted tap·보류 상태는 자신의 이전 결정으로 갱신한다. baseline tap history를 계속 제공하면 실제 lock-in을 시험한 것이 아니므로 별도 teacher-forced 상한 대조로 분리한다. initial history unknown 시 force correction 금지. trust 승격·유지·최대 age·오류 반복 시 reset을 동결한다.

### E2-03 후보 차이와 편파 이득 관계

각 packet의 모든 후보에서 `Δn_j`, `Δr_j`, `s_j`, `s_j−s0`, signal support, normalized motion residual, J0−Jbest, Jsecond−Jbest, same-lobe flag를 보존한다.

이후 evaluator에서만 `|e_s0|−|e_s*|`와 raw/calibrated range 손익을 연결한다. **큰 Δs는 큰 개선이 아니라 큰 위험일 수도 있다.** high/medium/low confidence 구간별 correction precision, harmful correction, s 및 range MAE/tail을 보고하고 reliability diagram·risk–coverage를 작성한다. 점수→확률 보정은 CAL에서만 수행한다. 후보별 측정치를 확률 가중 평균하는 정책은 본 주 실험에서 제외하며 별도 계약이 필요하다.

### E2-04 현실 noise·prior robustness

원 noise SNR 조건 및 그 조건에서 6dB 저하/6dB 개선을 스트레스 대조로 제안한다. 원 noise variance 정의와 실현 SNR을 함께 기록한다. prior의 radial bias {±0.04,±0.15,±0.30,±0.60m}, tangential bias {±0.10,±0.30m}, heading bias {±1°,±5°,±10°}, radial/heading P scale {0.25,1,4}는 **먼저 one-factor-at-a-time**으로 시험한다. 실제 위치를 이동하지 않고 prior를 오염시키는 시험임을 표시한다. 모든 조합의 무승인 대량 검색을 하지 않는다.

**채택 전제 제안:** nonzero coverage와 wrong→correct rescue를 확보하면서 reference정상→오류 교체율≤1%, high-confidence 교정 정밀도≥95%, 원래 잘못된 FP의 rescue≥30%. 마지막 수치는 do-nothing 정책의 가짜 안전 PASS를 막는 목표다. 희소·상관 자료로 유효한 상한을 확인할 수 없으면 기술 PASS와 별개로 안전성 판단을 HOLD한다.

## 8. 단계 E3 — ranging 보호, 편파 개선, 관측모델 및 단일 갱신

**대상 가설:** H3–H5. 사용자의 “ranging은 이미 정확할 수 있다”를 직접 비교하는 단계다.

### E3-01 관측 추출의 2×2 요인 실험

같은 packet·같은 선택 결과 n*에 대해 다음 네 관측을 만든다.

| arm | range tap | polarization tap | 해석 |
|---|---|---|---|
| F00 | n0 | n0 | 원본 |
| F10 | n* | n0 | range 변경의 효과만 |
| F01 | n0 | n* | **ranging 보존, 편파 tap만 정정** |
| F11 | n* | n* | 두 관측 공동 정정; 기본 end-to-end 후보 |

F01의 “ranging 보존”은 우선 **추출된 원래 range 값·tap을 유지한다는 뜻**이다. 기전 진단에서는 기존 range mean/Rrr도 고정한다. 후속 calibration에서 range 보정모델까지 바뀌면 별도 처치로 표기하고 corrected ranging 불변이라고 부르지 않는다. F10/F01은 한 tap에서 생성한 원래 관측과 다른 센서 정의이므로 hybrid임을 표시한다. 구현은 가능하지만 mean/Rrs와 기대관측을 다시 검증해야 한다. F01이 좋고 F11이 range를 악화시키면 공동 정정을 무조건 채택하지 않는다. 두 RX 편파 전력은 F01에서도 같은 n*에서 읽는다.

### E3-02 물리적 잔여오차·보정 분해

`eMP = same_LoS_tap + detector_choice`를 다시 확인한다. 실제 선택이 nL0와 다르면 그 위치의 Full 신호를 그대로 평가한다. oracle nL0의 signed s를 복사하거나 기존 eMP를 교정량만큼 인위적으로 빼지 않는다. R2 pose525 같은 **same-tap 큰 편파오차**는 FP정정의 한계 대조다. 물리적 잔여 간섭을 FP선택으로 해결했다고 주장하지 않는다.

전체 valid/원래 정상/원래 오류/changed/unchanged/abstained 각각의 r·s 손익을 계산한다. corrected subset 이득만 보고하지 않는다. 보정 range 기준과 raw detector 기준을 함께 제시한다.

### E3-03 μ/R 보정과 역할 분리

1. **기전 진단:** 원래 h/H/μ/R/gate를 고정하고 F00/F10/F01/F11을 비교한다. 이는 원 관측모델하의 치환 효과이며 deployable 성능 아님.
2. **보정만 대조:** detector는 F00로 유지하되 동일한 새 calibration recipe만 적용한다.
3. **정합 관측모델 대조:** F01/F11 각각의 selector-conditional residual에 대해, 훈련 자료만으로 mean·Rrr·Rss·Rrs를 재평가한다.

기존 μ_r,Δs 관련 feature는 FP와 함께 달라질 수 있다. 원래 tap feature와 교정 tap feature를 섞어 기존 EXDS μ_r을 자동 재사용하지 않는다. Rrs=0도 자동으로 유지하지 않는다. selector confidence에 따른 잔여 mean/MSE와 시간상관을 검증한다. 분산과 남은 편향의 제곱을 구별하고 같은 오차항을 중복 더하지 않는다.

state-dependent 보정 mean을 관측함수에 넣는다면 그 Jacobian도 포함하거나, 어떤 항을 fixed context로 취급했는지 명시한다. branch 경계에서 미분이 불연속이면 무조건 0 또는 smooth로 치환하지 않는다. 현재 prior로 선택한 관측이므로 **한 번 갱신했다는 사실만으로 오차의 prior 독립성이나 정확한 Gaussian posterior가 보장되지 않는다.** 경험적 정합성을 별도 보고한다.

### E3-04 동일-prior 단일 갱신

첫 대조는 같은 prior/H/K/μ/R 및 같은 accepted mask를 사용한다. 이때 선택값만 바꾸므로 Δx=KΔz를 독립 검산하고 posterior P는 동일해야 한다. 이 결과만으로 공분산 개선을 주장하지 않는다.

다음 대조에서 정합된 관측모델과 R을 사용해 K/Joseph를 다시 계산한다. 그 뒤 own-gate를 별도 시험한다. original FF가 거절됐어도 새 후보가 수용되는 경우 pre-mask K로 처리한다. 그 영향은 mask 고정 결과와 분리한다.

**정보계상:** current posterior→reselect→같은 CIR 다시 update 금지. 반복 추정이 필요하면 원 prior·단일 likelihood를 유지하는 별도 계약으로 분리한다. mean만 새값/P는 옛값인 혼합도 금지한다.

## 9. 단계 E4 — 실제 t=0 폐루프 MB_VAR

**대상 가설:** H6. E1/E2의 detector 성능만으로 전체 필터를 승인하지 않는다.

실험 ID는 **E4-01 개발**, **E4-02 봉인 센서/noise 평가**, **E4-03 전체 pipeline route-heldout(선택·별도 승인)**으로 구분한다.

### 주 대조군 6개

| ID | detector/처리 | 관측모델 | 목적 |
|---|---|---|---|
| A | 원래 FP | 원래 MB_VAR | 기준선 |
| B | 원래 FP | 새 calibration recipe | 학습·보정 효과만 |
| C | 오선택 위험 신호만으로 pol 할인/보류, FP 불변 | 사전 정의한 정합 모델 | 재선택 없이 위험 억제한 효과 |
| D | 선택적 공동 FP정정 F11 | **원래 모델 고정** | 관측모델 불일치의 기전 대조; 채택 후보 아님 |
| E | 선택적 공동 FP정정 F11 | selector-matched 모델 | 주 온라인 후보 |
| F | 선택적 편파-only FP정정 F01 | hybrid-matched 모델 | 기존 ranging 보호 후보 |

각 arm은 자신의 posterior·P·trusted-tap history·gate로 다음 tick을 시작한다. A의 저장 prior를 E/F에 계속 제공하면 폐루프 시험으로 인정하지 않는다. noisy waveform/control realization·초기조건은 짝지어 같게 유지하되 후보 선택의 추가 상태는 각자 관리한다.

**평가 격자:** R2/R4/R5 × B0/L2 × Full/Native-LoS × seed. 개발 10개 sensor seed에서 6arm=720 trajectory; 봉인 20개 seed에서 6arm=1,440 trajectory. B의 calibration fit 실행은 trajectory 수에 포함하지 않으며 별도 registry에 기록한다. 다른 source/hash가 같을 때만 A를 재사용한다. S1/S2/S3를 결합하는 추가 실험은 이번 주 예산·계약 밖이다.

평가 기간은 원 계획의 `t≥30s primary`와 initial·near·late·all을 함께 기록한다. 특정 hotspot을 발견했다는 이유로 primary 모집단에서 제외하지 않는다. Heading RMSE, XY/radial/tangential RMSE, signed bias, p95/p99/max, 68/95/99% 포함률·NEES, 상태불연속, false correction lock-in 길이, 미검출률, fallback 비율, 전체 update 개수를 함께 보고한다.

**제안 전역 기준:** R4 Full B0/L2 각각 Heading ratio≤0.90, XY ratio≤1.05; R2/R5 Full 및 모든 Native-LoS에서 Heading/XY ratio median≤1.05와 seed-ratio p90≤1.20. 거의 0인 baseline에서는 미리 정한 절대 한계(Heading0.05°, XY0.01m)를 사용한다. 평균 range나 s가 좋아져도 state 보호에 실패하면 전체 채택 NO-GO.

불확실성은 정확도와 별도 판정한다. coverage가 0.95에 가까워지고 NEES·영역 폭을 함께 개선했으면 `CALIBRATION_IMPROVED`; 명목 95% 회복은 적절한 CI·시간상관 처리·sharpness를 별도로 충족한 경우에만 표현한다. P를 키워 coverage만 올린 정책은 성공으로 승인하지 않는다.

## 10. 단계 E5 — 5Hz·출력 기한·실패 복구

실험 ID는 **E5-01 5Hz 지연**, **E5-02 운용 실패·재획득**, **E5-03 새로운 RF/실측 일반화(선택·별도 승인)**로 구분한다.

**대상 가설:** H7. kernel wall time만이 아니라 scheduled packet arrival부터 실제 출력까지 p50/p95/p99/max와 queue backlog를 측정한다. 목표는 기존 계획과 같은 p99≤200ms이며 평균 budget이 아니다. candidate generation, score·confidence, μ/R, EKF, logging 및 shadow/DR 비용을 모두 포함한다.

누락·timestamp 역전·같은 pose_id 중복·오래된 trusted FP·noise-only 입력·후보 overflow·초기화 실패·DR slip·급회전에서 명시적 HOLD/KEEP를 시험한다. 외부로 이미 낸 출력을 사후 corrected curve로 대체하여 온라인 성능으로 계산하지 않는다. 전체 과학 결과가 좋아도 지연 실패면 `REALTIME_HOLD`다.

새 실제 환경·기기·RF generalization은 본 3개 경로의 같은 복도에서 입증하지 못한다. 이것은 E5의 별도 optional branch이며, 기존 입력에 충분한 NLOS/실측이 없으면 정확한 데이터 요청과 새 계약을 작성한다.

## 11. 통계·성공 기준·선택편향 계약

### 11.1 각 지표의 분모

- detection precision/recall: valid reference와 wrong_ref 정의를 고정한다.
- false correction: 원래 `n0==nL0`였는데 `n*!=nL0`로 바뀐 수 / 원래 정상 수.
- rescue: 원래 wrong_ref인데 corrected reference match로 바뀐 수 / 원래 wrong_ref 수.
- harmful correction: 정확 일치 여부와 별개로 거리/편파/상태 손실이 늘어난 수. wrong→different-wrong도 포함한다.
- confidence risk: **실제로 replace한 관측**의 손해율과 전체 eligible 중 replace 비율(coverage)을 함께 표시한다.
- `UNKNOWN_REFERENCE`, `NOT_DETECTED`, `NO_CANDIDATE`, `HOLD_PRIOR`, `ABSTAIN_AMBIGUOUS`를 0오차 또는 성공으로 넣지 않는다.

### 11.2 paired 분석

동일 scene·pose·yaw·noise realization·controls·초기조건·seed를 묶고, route/bias/channel을 섞지 않는다. 서로 다른 길이의 경로를 packet pooling하여 R5가 결과를 지배하게 하지 않는다.

주 불확실성은 seed별 paired 지표의 bootstrap으로 보고하되 **같은 RF 위 센서/noise 실현에 조건부**임을 명시한다. RF 위치·event 상관은 route내 연속 block 보조분석으로 다루며, 24 G4를 24개 독립 환경으로 세지 않는다. block 길이와 episode 정의는 개발자료에서 고정하고 평가결과를 보고 바꾸지 않는다. IID packet bootstrap로 1% false correction 안전확률을 주장하지 않는다.

E2 confidence cutoff는 CAL에서 선택 후 SEALED에 고정한다. multiple candidates/27개 조합의 최선값을 확인평가에 다시 선택하면 해당 평가를 개발용으로 강등한다. 성능이 나쁜 seed·route·misdetection을 삭제하지 않는다.

### 11.3 제안 기준표 — 승인 전 값, 이미 달성한 결과가 아님

| 주장 | 제안 조건 | 통과해도 말할 수 없는 것 |
|---|---|---|
| 후보 가용 | reference-valid ≥2tap 오류 후보 recall≥95% | 후보 중 정답 선택 성공 |
| 선택적 정정 | 정상→오류 교체율≤1%, 높은 신뢰도 correction precision≥95%, wrong rescue≥30%; 유효 CI와 표본 충분성 확인 | 새로운 RF 환경에서 같은 확률 |
| 편파 관측 개선 | 원래 wrong_ref 집단 s MAE≥20% 감소, 전체 각 route s/r 보호≤5%; 꼬리와 false correction 동시 공개 | Heading 개선 |
| ranging 보호 | 같은 보정 정의의 각 route range RMSE 비율≤1.05; tiny baseline이면 절대0.01m 한계; p95/p99 악화 별도 실패표 | 원시 detector 오차가 물리 참거리 오차와 같음 |
| 재귀 개선 | §9의 R4 개선 및 R2/R5/LoS 보호 전부 | 모든 경로·환경의 보편 개선 |
| 일관성 개선 | accuracy와 coverage/NEES·영역 폭을 함께 보고, 원 모델보다 개선 | Gaussian 가정의 참/완전 95% 보장 |
| 실시간 | 같은 hw·5Hz p99 output latency≤200ms, 실패처리 보존 | 다른 hw의 동일 지연 |

수치 기준을 만족하지 못하면 `NOT_SUPPORTED`; 신뢰구간/지지집합 부족이면 `INCONCLUSIVE`; 실행·원시자료 미확인이면 `NOT_TESTED/BLOCKED`. 기술검사 PASS를 과학적 PASS로 승격하지 않는다.

## 12. 구현 계약과 데이터 스키마

### 12.1 실행 전 동결할 항목

`CONTRACT.json`, `POLICY_SPEC.json`, `METRIC_SPEC.json`, `SPLIT_MANIFEST.json`, `INPUT_LOCK.json`, `ENV_LOCK.json`, `RUN_MATRIX.csv`의 SHA를 승인 토큰에 묶는다. 입력은 G4/동적RF/controls/noisy arrays/mean/R/FFD의 실제 payload SHA256와 dtype·shape를 포함한다. LFS OID와 원격 pointer는 접근 확인의 일부이지 payload 검증의 대체가 아니다.

후보 구현·독립 checker 각각 code SHA, 환경 Python/NumPy/FFT/BLAS thread, random generator type·seed mapping, 단위·shape·threshold tie rule, 활성 SourceFFD branch를 고정한다. 구 SM0/S1/C1 GO를 재사용하지 않는다.

### 12.2 packet별 필수 로그

`source_run`, `route`, `bias`, `channel`, `sensor_seed`, `noise_seed`, `pose_id`, `timestamp`, `dt`, `prior_source`, `prior_timestamp`, `x_minus`, `P_minus`, `DR_delta`, `radial_prediction`, `detector_offset`, `trusted_tap/time/age/confidence`, `raw_tap`, `raw_rx`, `candidate_ids`, `candidate_support`, `candidate_r/s/powers`, `noise_floor`, `margin`, `wrong_score`, `choice_confidence`, `pol_ambiguity`, `action`, `reason`, `selected_tap`, `z_raw`, `z_selected`, `mu`, `Rrs_matrix`, `h`, `H`, `K`, `NIS_pregate`, `accepted`, `x_plus`, `P_plus`, `latency_components`.

GT·LoS reference·true physical path·oracle benefit는 **evaluator_truth 별도 파일/프로세스**에 둔다. 핵심 정책함수는 이 구조를 인자로 받지 않는다. 결과 병합 키와 row count assertions를 별도 auditor가 검증한다.

### 12.3 기술 QA 초안

pose_id·mask·tap·TX/RX order는 exact equality. 동일 frozen environment의 r/s·state·K/P는 단위로 정규화하여 no-op 최대오차1e−10, symmetry residual≤1e−12·max(1,||P||), eigenvalue≥−1e−12를 초기 제안으로 둔다. 기존 승인 계약이 더 엄격하면 기존값을 우선한다. dtype/환경 차이로 못 맞추면 사전 amendment 후 재감사하며, 결과를 본 뒤 허용오차를 조용히 늘리지 않는다.

## 13. 독립 감사와 단계별 승인

각 단계는 `SPEC_i → CODE_i → GO_DEV_i → RESULT_DEV_i → GO_EVAL_i → RESULT_EVAL_i → PUBLICATION_i`를 구분한다. exploratory E0–E2와 sealed E4의 승인범위도 분리한다.

- **PROPOSER:** 과학 질문·대조·지표·가설별 해석을 고정한다. 이번 문서 작성자가 이 설계를 자기 승인한 것으로 보지 않는다.
- **IMPLEMENTER:** 독립 reference와 분리된 구현, raw artifacts, 실행기·입력 해시, 실패 이력을 제출한다.
- **INDEPENDENT CODE AUDITOR:** 별도 session/agent 또는 reviewer, 별도 checker/runner로 단위·수학·causality·누출·기준선 parity를 검사한다. 이름만 바꾼 같은 계산 함수 재실행은 독립 검산이 아니다.
- **INDEPENDENT RESULT AUDITOR:** raw에서 점수를 재집계하고 가설별 `SUPPORTED/PARTIAL/NOT_SUPPORTED/INCONCLUSIVE/NOT_TESTED`를 판정한다. LFS 전체 bytes 재검산 여부와 요약만 본 범위를 구분한다.
- **OWNER:** 다음 단계와 계산 예산을 별도 승인한다. 감사 ACCEPT만으로 다음 단계 전체 실행이 자동 승인되지 않는다.

`03_AUDIT_AND_CLAIM_REVIEW_KO.md`와 `06_AUDIT_RESULT_TEMPLATE.json`을 감사자에게 전달한다. 후속 감사자는 반드시 이 계획의 동결 버전과 실제 implementation SHA를 비교해야 한다.

## 14. 실행 순서·예산·중단

1. **E0**로 ranging 전제·원본 재현·데이터 사용가능성부터 확인한다.
2. **E1/E2 clean canary**는 R2/R4/R5의 공개 B0 seed10 3,136시점 및 G4 24조건이다. 새 RT 없음.
3. **E2 noisy/스트레스**는 사전 RUN_MATRIX에 등록한 조건만. 같은 측정에 대한 여러 후보 score 계산을 별도 trajectory처럼 세지 않는다.
4. **E3**에서 혼합 tap·관측모델·정보계상을 통과한 뒤에만 **E4** 개발720/확인1,440 trajectory를 고려한다.
5. **E5** realtime 측정은 같은 주 정책으로 수행한다. 과학실패를 runtime 최적화로 덮지 않는다.

모든 단계에서 실패·기각·조기 종료·short history·no signal을 보존한다. 정상 종료와 강제 종료 후 저장 데이터 수용을 구분한다. 완성된 원래 C0–C3는 재실행하지 않고 필요한 입력/산술을 재사용한다. 데이터 부족 시 부족한 범위만 요청하고 전체 RF를 새로 생성하지 않는다.

## 15. 근거 문서

정확 ref·blob·링크·읽기 범위는 [05_SOURCE_REGISTRY.json](05_SOURCE_REGISTRY.json)에 있다.

- **S01** PR #37 `FP_PRIOR_PILOT_001/CONTRACT_KO.md`: 기존 open-loop 파일럿 범위와 4cm 직접검증 미포함.
- **S02** `FP_PRIOR_PILOT_001/pilot.py`: 실제 selector, strongest RX 후보, clean RF/저장 prior, GT 분리 구조.
- **S03** `src/qclean_uwb/drivesim/observation.py`: 원 관측 체인·복소 noise·leading edge·미검출 처리·range bias 정의.
- **S04** `RESULTS_ORACLE_001/SUMMARY.json`: GT-state 가능성 진단과 반례.
- **S05** `C3/G4_001/G4_PHYSICAL_FINDINGS_KO.md`: 같은 좌표 yaw에 따른 포트/CIR/tap/편파 변화와 분해의 한계.
- **S06** `RESULTS_ORACLE_001/SENSITIVITY_4CM.json`: 4cm 예측 섭동의 rounding 민감도.
- **S07** `S1/online.py`: MB_VAR mean·VAR·BASE shadow·Joseph·현재 posterior 사용 순서.
- **S08** `MBVAR_PRR_001_PLAN_20261103/01_EXECUTION_PLAN_KO.md` §7–9: paired 평가·보호·독립감사·5Hz 예산의 선행 계약.
- **S09** PR #37 head metadata 및 해당 디렉터리 listing: 작성 시 확인한 게시 범위. 파일 listing은 원시 바이트 검증이 아님.

---

**제안자 최종 결론:** 우선 E0에서 기존 ranging의 실제 정확도와 detector-domain 예측을 확인하고, E1/E2에서 정상 FP 보호와 오선택 정정의 선택성을 검증한다. 그다음에만 편파비 개선을 관측모델·재귀 성능으로 연결한다. 향후 감사는 이 연결의 각 단계에 대한 증거를 독립적으로 판정한다.

## 고정 원전 링크

[S01]: https://github.com/myoungsunk/sionna-resimulation/blob/c68dcdcdd01180617b827e1f6ebb58e6740a8e29/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_PRIOR_PILOT_001/CONTRACT_KO.md
[S02]: https://github.com/myoungsunk/sionna-resimulation/blob/c68dcdcdd01180617b827e1f6ebb58e6740a8e29/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_PRIOR_PILOT_001/pilot.py
[S03]: https://github.com/myoungsunk/sionna-resimulation/blob/e38de517a21a43bb210c7e04c9fbd6517d8a95cf/src/qclean_uwb/drivesim/observation.py
[S04]: https://github.com/myoungsunk/sionna-resimulation/blob/c68dcdcdd01180617b827e1f6ebb58e6740a8e29/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_PRIOR_PILOT_001/RESULTS_ORACLE_001/SUMMARY.json
[S05]: https://github.com/myoungsunk/sionna-resimulation/blob/e38de517a21a43bb210c7e04c9fbd6517d8a95cf/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/C3/G4_001/G4_PHYSICAL_FINDINGS_KO.md
[S06]: https://github.com/myoungsunk/sionna-resimulation/blob/c68dcdcdd01180617b827e1f6ebb58e6740a8e29/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_PRIOR_PILOT_001/RESULTS_ORACLE_001/SENSITIVITY_4CM.json
[S07]: https://github.com/myoungsunk/sionna-resimulation/blob/e38de517a21a43bb210c7e04c9fbd6517d8a95cf/research/MBVAR_PRR_001_20261103/S1/online.py
[S08]: https://github.com/myoungsunk/sionna-resimulation/blob/e38de517a21a43bb210c7e04c9fbd6517d8a95cf/research/MBVAR_PRR_001_20261103/MBVAR_PRR_001_PLAN_20261103/01_EXECUTION_PLAN_KO.md
[S09]: https://github.com/myoungsunk/sionna-resimulation/tree/c68dcdcdd01180617b827e1f6ebb58e6740a8e29/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_PRIOR_PILOT_001
