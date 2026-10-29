# RA0–RA1 출처·검증 범위 재감사 보고서

**저장소:** [`myoungsunk/sionna-resimulation`](https://github.com/myoungsunk/sionna-resimulation)  
**고정된 조사 기준:** `research/mbvar-info-001-20261029`의 `f100a983cc389fcdef073592a254add61e7115da`; 소스 비교 기준 `af8e0a1b5299ae5e279f9b602afd2f1bb710c4e3`; 공통 역할 지침 `250d617ad89a4105fa1af546cc83ceed9de98f42`.  
**대상:** 기존 Corridor 데이터 생성 → native RT H → 관측(r,s) → FFD LoS 모형 → 원 packet 평균·R → BB/MB/MB_VAR → 점수·주장. 최신 `MBVAR-INFO-001` P0는 별도 후속 스코프로 구분한다.  
**작업 유형:** 사후 출처 감사 + 정적 코드 검사 + 원본 CSV/JSON 재집계. **원래 RT 재실행·raw binary H 재계산 아님.**  
**역할:** 하나의 세션에서 PROPOSER → IMPLEMENTER → AUDITOR로 분리해 작업했다. **독립적인 감사자 행위는 없으므로 `SELF_REVIEW_ONLY`**; 구현과 검산은 다른 코드 경로로 수행했으나 연구적 독립 감수로 표시하지 않는다.  
**결론:** `REVISION_REQUIRED` (자체 감사·근거 제한), 과학적 원인 판정 `INCONCLUSIVE`; RA2는 **관측 계보 QA에 한해 조건부 GO**, 새 과학 성능 주장·물리 타당성 승인에는 NO-GO.

## A. 핵심 결과 — 확인된 사실과 미확인 범위

1. **원 점수표의 정확한 개선 수:** `PB_SCORES.csv` 392행 = 7 case × B0/L0/L1/L2 × 14 arm. `MB_VAR` 대 `BB_ORIG`의 Heading RMSE가 작은 것은 **23/28**, XY RMSE가 작은 것은 **20/28**, 양쪽 모두 작은 것은 **19/28**이다. 원 `PB_DECISIONS.json`의 MB_VAR 사전 판정 `P1/P2/P3`는 모두 `false`다. 이 28조건은 28개의 독립 RF 환경이 아니다.
2. **RT 경로 검증:** 2026-10-08의 G3 정정본은 6개 anchor-route 블록 × 실제 검증 위치 총 **5,630개**를 기록한다. 본 감사에서는 원 timeline CSV를 별도로 읽어 R2:925, R4:547, R5:1,343개의 서로 다른 drive 위치를 다시 계산했고, 두 앵커 합계가 일치함을 확인했다. 엄격 `5e-14 s` 기준에서는 **26개 경로 미매칭·6블록 FAIL**, 승인된 `2e-13 s` 기준에서는 **0개·6블록 PASS**다. 이 재검사는 과거 S6 실행 **이후** 실시됐고 H/S6는 재생성하지 않았다. 원 0-station PASS는 무효다.
3. **H 출처의 교차 검산:** 저장된 H 12개 무결성 목록 중 `EKF3_P0_INPUT_MANIFEST`에 있는 7개 FULL H SHA256이 **7/7** 일치한다. 최신 P0에 투입된 `H_R4_aB_m0.npy`와 `H_R5_aA_m0.npy` SHA256도 **2/2** 일치한다. FFD bank 두 파일도 P0 기록상 SHA256 기대값과 일치한다. **해시 동일성은 물리 정확성의 증거가 아니다.**
4. **관측 재현은 좁은 범위에서 확보:** 저장된 P0 `P0_PREMISE.json`에서 R4-B B0 **742/742**, R5-A B0 **1415/1415**가 raw H의 noise-free first-path `r,s`와 일치한다(`s` 최대 절대차 `2.22e-16`, `r` 최대 `3.55e-15 m`). 해당 두 case에는 중복된 truth pose가 없어 '동일 pose 재방문 시 H/z/μ/ε 동일성' 검사가 실제로 실행되지 않았다.
5. **BB/MB_VAR canary 재현:** P0 `P0_PARITY.json`의 BB_ORIG, MB_ORIG, MB_VAR state/P 및 BASE mask 검사는 R4-B, R5-A B0에서 PASS였다. 그러나 이것은 두 case의 archival 재현이며 원 predictor의 독립 학습 재생성이나 모든 28조건 검증이 아니다.
6. **기하 P0의 최신 결과:** `40840192251`은 `BLOCKED_GEOMETRY_MATCH`; `40840770105`는 PASS였지만 60/60 pose가 FFD 90° 격자 보간 kink에 놓여 `AMENDMENT-002`에 의해 **대체**됐다. 이후 `40842954635`는 새 5% smoothness 기준에서 PASS, 기하 쌍 `A|T2_TANGENT_A_Y7|0` (LOW) vs `A|T4_S_CURVE|60` (HIGH), `ΔG=0.7821977853504691`, 유효 창 3/13·허용 쌍 1개다. 최신 source는 `FROZEN_LOCK`을 포함하지만 reviewer_status=`SELF_REVIEW_ONLY`, 즉 science release 아님. RA0/RA1은 이 P0 결과를 새 메커니즘 검증 결과로 인용하지 않는다.

### 검증 수치 요약

| 범위 | 수치 | 판정 |
|---|---:|---|
| 원 데이터 성능표 | 392 score 행 / 28 조건 / 14 arm | 재집계 PASS (archived numeric table) |
| BB 대비 MB_VAR Heading / XY / 양쪽 개선 | 23 / 20 / 19 (분모 28) | *관측된 수치 감소*만 |
| R2 / R4 / R5 drive 위치 | 925 / 547 / 1,343 | 원 timeline에서 별도 계수 |
| G3 전체 위치(앵커 A+B) | 5,630 | coverages 일치 |
| G3 strict / relaxed 미매칭 | 26 / 0 | strict FAIL, authorized relaxed PASS |
| Original 7 H / recent P0 2 H 해시 | 7/7, 2/2 | 교차 출처 일치 |
| R4-B / R5-A 관측 packet 일치 | 742/742, 1,415/1,415 | 두 case 범위의 parity |
| R4-B / R5-A 필터 state/P | 두 case B0 PASS | 전역/과학적 감사 아님 |
| P0 기하 3차 (run 40842954635) | 유효 창 3/13, 허용 쌍 1 | amended P0 기술 PASS |

## B. 1/5 — 현재 주장→원자료 의존성 지도

```mermaid
flowchart TD
  A[장면·경로·안테나 좌표] --> B[Sionna RT 경로/Jones 물리]
  P[FFD Etheta/Ephi bank + 주파수] --> B
  B --> H[raw H_FULL/H_LOS : N x 257 x 2 x 2]
  R[원 timeline, SAMPLES, pose_id] --> H
  H --> O[Hann 4N IFFT, 강한 RX 30% leading edge]
  O --> Z[측정 z_r = delay*c / z_s = signed P1-P2 ratio]
  P --> F[SourceFFD LOS h(x), H Jacobian]
  R --> F
  Z --> CAL[경로 제외 보정의 μ_B/μ_M, POWER R0]
  Z --> M[오리지널 BB NIS gate A_B]
  F --> M
  CAL --> M
  M --> EKF[4-state EKF f/F/Q, Joseph 갱신]
  Z --> EKF
  F --> EKF
  CAL --> EKF
  EKF --> S[BB_ORIG / MB_ORIG / BB_VAR / MB_VAR]
  S --> V[Heading/XY/NEES/coverage, t>=30 s]
  T[truth: 생성·평가에만] --> V
  V --> C[조건별 score, CLAIM_REGISTER]
```

**코드상 실제 연결:** raw `.npy`와 SAMPLES는 `reflect_model/common.py::load_rf`로 읽는다. 원 관측은 `qclean_uwb/drivesim/observation.py`의 Hann, 4N IFFT, strongest RX, 첫 30% leading-edge 및 동일 tap의 두 포트 power를 사용한다. `s=(P1-P2)/(P1+P2)`, `r=delay*c`. SourceFFD는 TX/RX FFD로 LoS 관측 `h_s`, 해석 Jacobian을 만든다. SourceFFD의 filter range prediction은 **연속 bridge `distance+B_OLD`**, 원 packet의 range는 **정수 tap의 `delay*c`**이다. 기존 실험은 이 차이를 보정·비선형 모델링 한계로 관리했다.

**비교 시 의존성:** `z`는 stored BB trace에서 `nu_B + h_B + mu_B`로 복원되며, `mu_B`, `mu_M`, `R0`은 archive에서 packet-keyed 값을 가져온다. 새로운 RF pose에 이 저장된 `mu`를 단순 복사하면 원 predictor의 합법적인 적용이 아니다. `gyro`·`odom`은 원 sensor generator로 재생성하되 GT는 생성기와 평가에만 허용한다. `BASE`로 계산한 joint NIS accept mask를 동결해 네 개 arm의 업데이트에 동일 적용한다. 따라서 기존 28조건의 MB_VAR 수치는 **fixed-gate replay** 범위이지 self-gate 온라인 구현의 성능이 아니다.

전체 표는 `01_implementer/CLAIM_DEPENDENCY_MAP.csv`의 11개 주장에 `question → input/code → archived proof → permitted statement → unresolved test`를 연결했다.

## C. 2/5 — BB·MB_VAR 실제 실행 정의

| Arm | 측정 평균 보정 | 측정 공분산 | Gate | 원칙상 평가 대상 |
|---|---|---|---|---|
| `BB_ORIG` | 저장된 BASE `μ_B(k)` | `R_0(k)` | 각 조건의 BASE NIS mask 고정 | 기준선 |
| `MB_ORIG` | 저장된 Δs 계열 `μ_M(k)` | `R_0(k)` | 동일 mask | 평균 보정 효과 |
| `BB_VAR` | `μ_B(k)` | `R_0(k)+diag(0,σ_b²)` | 동일 mask | 분산 보정 효과 |
| `MB_VAR` | `μ_M(k)` | `R_0(k)+diag(0,σ_b²)` | 동일 mask | 평균과 분산 결합 |

위에서 원 PB/ctl_core의 표는 `σ_b(ρ)`를 **시간 k 예측 전, k−1 posterior**에서 계산한다. 반면 `ds_state_info_forensics/run_four_priorities.py::trial`은 **현재 k의 predicted prior**에서 계산한다. 같은 `MB_VAR`라는 이름이어도 **실제 알고리즘 버전이 다르다**. 두 구현 모두 동작은 확인했지만, 성능 차이의 크기는 본 감사에서 재실행하지 않았다. 조회 시점을 조용히 하나로 통일하지 말고 `sigma_lookup_state`를 계약 변수로 지정해야 한다.

원 PB `σ_b` table은 `ρ=[0,1.5,3,6,10] m`, `σ=[0.011,0.02,0.05,0.12,0.24]`, 수평거리의 선형보간이며 `R_ss += σ²`로 적용한다. `R_rs`는 원 R0를 그대로 유지한다. 4상태 `[p_x,p_y,ψ,b_g]`, `Q_input=diag(2e-5·|Δd|,(0.015°)^2·Δt,0)`, Joseph P 갱신이다. `R0`는 POWER/기준선 보정 계보에 따른 저장값이지 본 `σ_b`와 동일하지 않다. `t≥30s`만 채점하되 필터는 시작부터 재귀 수행한다.

원 코드 `exp_pb.py`의 설명은 `σ_b`가 predicted state라고 말하지만 실제 계산 위치는 예측 전이다. **코드와 문구의 모순이 확인**되므로 문구를 정정하되 기존 계산·원 score는 변경하지 않는다.

독립 코드·실행 계보를 포함하는 정확한 variant 표: `01_implementer/ESTIMATOR_DEFINITIONS.csv`.

## D. 3/5 — 유효·정정·폐기된 검증 근거

| 증거 묶음 | 현재 상태 | 반드시 붙일 경계 |
|---|---|---|
| 과거 'G3 6/6 PASS' | **무효** | `stations=0`을 검사 못한 예전 검사기 |
| 2026-10-08 G3 재검사 | **유효(제한적)** | 5,630위치/완화기준 PASS; 엄밀기준 6/6 FAIL; S6 종료 후 수행 |
| H 12 파일·S6 37개 hash | **유효(무결성)** | 다시 실행하거나 물리 정확성을 확인한 것 아님 |
| 입력 manifest 7 H vs G3, P0 2 H vs G3 | **유효(출처)** | 7/7, 2/2 SHA256 일치; raw `.npy` 바이트를 이 세션에서 열어 검산하진 않음 |
| P0 40840192251 | **BLOCKED** | 원거리 매칭 실패; 다른 canary 검사 결과는 보존 |
| P0 40840770105 | **대체됨** | 60/60 kink; 임의로 S0 geometry에 재사용 금지 |
| P0 40842954635 | **유효(기술)** | `AMENDMENT-002` 조건에서 PASS, 근거는 좁은 P0/기하 |
| P0 r/s + BB/MB_VAR canary | **유효(기술)** | 2 case B0, 상태+P 및 mask parity; 반복 pose 없음 |
| E5 과거 비정상 정규화와 큰 배수 결론 | **철회됨** | 새 E5는 `DᵀID`, Q-aware nominal 정보로 수정; 실제 상관 RF 정보는 아님 |
| R5-B 'seed3/8/9가 BB까지 모두 실패' | **정정됨** | 후속 control/initial seed 교차 실험상 초기조건 영향이 큼; 사후 선택 |
| CL-004의 `NEEDS_CORRECTION` | **ledger 갱신 필요** | 새 재검증 보고서와 register 표가 함께 유지됨. 과거 주장 재사용 금지 |
| MBVAR-INFO frozen status | **FROZEN/SELF_REVIEW_ONLY** | 상단 문구의 DRAFT와 FROZEN_LOCK 충돌; 독립 signoff 아님 |
| MBVAR-INFO CI | **실제 workflow 존재** | 컨트롤 정보 폴더만 해당; 전체 생성기·BB 코드에 강제 적용된다는 증거 없음 |

세부 상태(17개): `01_implementer/EVIDENCE_STATUS.csv`. 출처 URL과 커밋(30개): `SOURCE_REFERENCES.json`.

## E. RA1에서 새로 수행한 출처·coverage 대조

### E1. 원 timeline과 RF SAMPLES를 직접 계수

GitHub의 원 `results/DRIVE_SIM_20261007/S1/routes/timeline_{R2,R4,R5}_Tnone.csv` 3개와 `.../BLOCK_C/{case}/SAMPLES.json`을 **원본 행 단위로 읽고** 독립 계산했다.

| Route | timeline 전체 | drive | turn | 고유 drive x,y (소수 6자리) | H/SAMPLES 전체 | timeline ID 대응 | 부가 pose ID |
|---|---:|---:|---:|---:|---:|---:|---:|
| R2 | 979 | 925 | 54 | 925 | 1,303 | 979 | 324 |
| R4 | 742 | 547 | 195 | 547 | 922 | 742 | 180 |
| R5 | 1,415 | 1,343 | 72 | 1,343 | 1,883 | 1,415 | 468 |

G3는 **drive 위치만** 검사하므로 `(925+547+1343)×2=5630`이다. H/SAMPLES의 부가 pose ID는 생성된 추가 조사 위치이며, timeline과 1:1 매칭되지 않는다는 사실만으로 결측/오류로 세면 안 된다. `RA2`는 관측 목적(regular/turn/auxiliary/probe)을 직접 판별해 각각 기대 개수를 검증해야 한다.

### E2. G3 정보와 검증 강도 구분

원 G3의 6개 재검사 JSON에서 strict mismatch는 R2-A/B=1/1, R4-A/B=3/3, R5-A/B=9/9, 합 **26**이다. relaxed 미매칭 합 **0**이다. 최대 정합 잔차는 약 `1.00642e-13 s`다. 이 시간차는 5e−14 기준 이상이지만 2e−13 이내다. 독립 trajectory 대응과 원 모델 path path-set의 유일성을 증명한 것은 아니다.

원 `TRACE_AUDIT`에서 Anchor B의 dropped-path flag는 R2 925, R4 547, R5 1,343, 합 **2,815 위치**, screen-exceeded flag는 **507+299+704=1,510 위치**다. A에서는 그 flags가 0이다. 최대 dropped relative amplitude는 약 **4.8%**다. 이는 **보고된 approximation/flag**이지 자동 과학적 FAIL은 아니다. first-path tap과 정규화된 signed-s에 민감한 위치를 우선 표본으로 뽑을 이유다.

### E3. source·관측·원본 동등성과 미실시 사항

원본 `FFD_P0P3`의 native LoS 9,519-point 관측 대조 및 `s`-RMSE `6.59e−7`, raw complex 상대 차이는 과거 보고서의 결과다. 현 RA1에서는 source/manifest/code가 서로 연결되는지만 재확인했으며 그 계산을 다시 하지 않았다. 별도 Sionna 실행·LFS bank 재검증·복소 H 배열 전체 해시의 현재 로컬 바이트 검증은 **NOT_RUN**이다. 따라서 RA1은 `PROVENANCE_VERIFIED_WITH_BOUNDARIES`이며 `PHYSICS_VALIDATED`로 승인하지 않는다.

## F. 4/5 — 위험순위별 결함·한계·미검증

**P0 — 주장 체계를 뒤집을 수 있는 우선 위험**

- `RA1-01` 실제 RT 생성 장면·경로·편파·Jones·재질의 독립 재실행 없음 — **미검증**. 해시일치와 G3만으로 물리 정확성을 전부 보장할 수 없다.
- `RA0-01` MB_VAR 관련 코드 간 분산 조회 시점 불일치 — **확인된 구현 정의 차이**. 이 차이의 수치적 영향은 아직 측정하지 않음.
- `RA0-02` frozen 새 계약의 reviewer_status=`SELF_REVIEW_ONLY` — **확인된 감사 독립성 미충족**. 기술 run을 연구 RELEASE로 표시하면 안 된다.
- `RA1-02` P0 검사기는 매칭된 `rows[ok]`의 s 동등성만 전체 premise PASS의 필요조건으로 보고, 현재의 `matched==packets`, r parity, RF expected SHA 일치 검사가 fail-closed로 묶이지 않음 — **확인된 검사기 설계 공백**. 현재 두 canary 자체의 matching 오류가 있다는 뜻은 아니다.

**P1 — 중요한 모델/증거 범위 위험**

- `RA1-03` 예전 G3 0-station PASS — **과거 결함, 이미 정정**. 정정 이전 G3 통과를 새 주장 근거로 재사용 금지.
- `RA1-04` Anchor B 원 path-drop/screen flags — **관찰된 데이터 품질 경고, 효과 미측정**.
- `RA1-05` native tap range vs SourceFFD 연속 range bridge — **의도된 모델 근사 한계**, 관측 오차를 반사 편파 오차로 전부 귀속할 수 없음.
- `RA0-03/04` in-sample σ table, fixed BASE gate vs self gate — **확인된 일반화/운영 해석 한계**.
- `RA0-05/06` frozen contract 문구/CLAIM_REGISTER 상태 불일치 — **확인된 문서/claim 갱신 공백**.

**P2 — 결론 범위/차기 방법 위험**

- `RA0-07` 28 조건의 독립성·사전 판정 `P1/2/3`와 단순 RMSE 개수 혼동 — **확인된 주장 경계**.
- `RA2-01` 같은 corridor 내 LORO가 새 장면 holdout은 아님 — **확인된 일반화 한계**.
- `RA2-02` 동일 raw H에서 나온 `s,Δs`의 결합 오차/새 상태 식별성 — **검증 전 새 방법 위험**.

전체 위험/상태/증거/수정 액션은 `01_implementer/RISK_REGISTER.csv`를 참고한다.

## G. 5/5 — 최소 수정과 재실행 범위

| 우선 | 수정 | 영향을 받는 최소 재실행 | 중단 조건 |
|---|---|---|---|
| 1 | RA1 P0 checker: key 전수·중복·RF hash expected vs observed·r/s parity를 필수 검사로 강화 | 두 canary P0 + 0/누락/중복/교체 H 음성 fixture | 관측 불일치면 이후 BB/MB 결과 채택 중단 |
| 2 | estimator 정의표에 `sigma_lookup_state`, `rho_geometry`, `gate/donor`, `mu_model/version` 고정, 코드/문서 mismatch를 erratum으로 정정 | 기존 R4-B/R5-A parity + 분산 조회 시점 교차 one-step; 차이가 있으면 영향받는 28조건 | 하나라도 intended estimator와 다르면 해당 점수 재평가 |
| 3 | 기존 G3 정정 provenance를 release/claim register에 연결 (old PASS 금지) | 경로 집계/검사 6블록만; **전체 H 재생성 불필요** | 원 checker PASS를 재인용하면 BLOCK |
| 4 | Anchor B의 screen/drop 영향이 큰 frozen pose 선정·직접 H/first-path tap/port ratio 대조 | 대표 canary만; 효과 클 때 해당 장면 H 재생성 | 독립 RF 예산/물리 기준 없으면 bulk RT 금지 |
| 5 | native tap range vs continuous bridge, direct-only negative control | 소규모 LoS 상태/한두 경로; fit/자료 재사용 금지 | nominal observer mismatch가 크면 모델 재설계 |
| 6 | E5/seed 정정의 claim 변경 이벤트·frozen contract status 안내 | 문서만; 과거 결과 보존 | claim register 미동기화 시 논문 주장 release 차단 |
| 7 | 독립적 감사자 세션에서 계약·수학·원자료 검산 | raw trace 소량과 선택된 반례, source keys | 독립 signoff 전 SCIENTIFIC_PASS 금지 |

상세 수용 기준·대상 파일·재실행 범위는 `01_implementer/NEXT_PATCH_QUEUE.csv`에 9개의 패치 티켓으로 분리했다. 이번 RA0/RA1은 *수정 제안까지*이며 원 데이터·기존 브랜치·frozen 계약을 변경하지 않았다.

## H. 역할별 인계 및 이번 감사의 실제 독립성

- **PROPOSER (`00_proposer/RA0_RA1_PROPOSER_CONTRACT.md`)**: 5개 산출물, competing explanations, 단위·분모, 6개 검사 gate, immutable source cutoff를 정하고 RA2 진행 기준을 제안했다. 원 과학 계약 `MBVAR-INFO-001`을 소급 수정하지 않는다.
- **IMPLEMENTER (`01_implementer/IMPLEMENTER_RECEIPT.json`)**: GitHub `fetch_file`·source/manifest 교차 확인, 원 CSV와 JSON에서 source-row 추출, 28개 score·3개 timeline·6개 G3 rows를 다시 집계했다. `verify/verify_ra0_ra1.py`를 Python 표준 라이브러리로 실제 실행했고 통과했다. 기존 연구코드를 패치·실행한 것은 아니다.
- **AUDITOR (`02_auditor/AUDIT_REPORT.md`)**: 구현 결과가 아닌 원 GitHub 자료·별도 산식·두 출처 사이의 SHA 교차표를 이용해 반증을 시도했다. 그러나 동일 모델/대화 세션이므로 **SELF_REVIEW_ONLY**이며 `ACCEPT_WITH_BOUNDARIES`라는 독립 verdict를 발급하지 않는다.

**RA0 scope 판정:** claim/definition/source map 완료, `REVISION_REQUIRED` (일부 문구와 독립 감사/모델 실행 정의 불일치).  
**RA1 scope 판정:** coverage/입력 계보 감사 완료, `PASS_WITH_BOUNDARIES` (역사적 출처 범위), 물리 원출력 재계산은 `NOT_RUN`이고 최종 과학 판정 `INCONCLUSIVE`.  
**개선 여부의 통계:** B0/L0/L1/L2는 같은 RF realization에 여러 센서 바이어스 조건을 적용한 것이므로 28개를 independent RF scene으로 bootstrap하지 않는다.

## I. RA2 진행 판정과 실행 계약

**결정: RA2의 raw-channel→observation→packet 계보 및 검사기 수정은 지금 조건부 GO.** 기존 원 코드 수정이나 새 성능 실험을 위한 승인으로 해석하지 않는다. 첫 RA2는 **데이터 전수 정렬·단위·tap/Detector·누락/중복·부분조인·hash**에 국한한다.

**선행 조건:** `RA0-ESTIMATOR-DEFINITIONS`와 source/ref hashes 고정; 실제 raw H+SAMPLES+timeline+stored trace + FFD bank 접근 가능해야 함. 고정 source `f100a...`의 frozen MBVAR-INFO P0와 역사적 BB/MB_VAR 실행 계보는 섞지 않는다.

**RA2-1:** full source ledger — 7 기존 case와 모든 원 데이터 arm의 join key `(case, channel, anchor, mount, pose_id, timestamp, raw H version, bank, solver)`를 등록하고 one-to-many sample/packet 관계 정의. 각 key에서 결측·중복·extra probe를 분리, raw packet count와 일치 여부 확인.

**RA2-2:** independent observation — `H[f,rx,tx]`, FFD 편파/좌표 convention, TX=0, Hann/4N IFFT, peak branch/tap, r/s 부호, s∈[-1,1], finite/undetected policy를 별도 코드로 계산. `r`과 `s`가 모두 원 packet과 사전 허용오차 일치할 것. Canary는 `|Δs|<=1e-12`, `|Δr|<=1e-9 m`, key/시간 exact. 새 RT와 archive H는 *별도의* 사전 tolerance가 필요하다.

**RA2-3:** mean/reference partition — `h_LOS`, `μ_B`, `μ_M`, `R_0`, `ε=z-h(GT)-μ`, `ν=z-h(x^-)-μ`를 각각 로그. `truth_scoring_only`가 온라인 estimator를 통과하지 않는지 자동 검사. stored packet-keyed μ의 재생과 new-pose trained predictor를 혼동하지 않음.

**RA2-4:** negative control — raw H 한 파일 치환, 1 packet 삭제·중복, pose ID 재배치, TX/RX port swap, angle 단위 오류, time shift, 0-row gate, s bounds 위반을 삽입하면 validation **반드시 FAIL**. 원자료 복제와 테스트 fixture는 새 경로만 사용.

**RA2-5:** 구현자 및 감사자 인계 — 위 결과에 `MANIFEST`, 실제 해시, failure evidence, 7-case coverage 표 첨부. 독립 감사가 없으면 `SELF_REVIEW_ONLY`; 동적 재귀/성능 실험은 RA2 통과 후 다른 계약에서만 시행.

**RA2 종료 기준:** 7-case 입력 중 하나라도 source 불명·부분 key join·미승인 변환이면 `BLOCKED_INPUT`으로 표시하고, 그 영향을 받는 모델/점수만 중단. 다른 독립 case를 조용히 제외해 overall PASS를 내지 않는다. 우선 계약 본문은 `03_next/RA2_EXPERIMENT_CONTRACT_DRAFT.md`를 따른다. **원 H 재생성과 S0/S1 science release를 RA2 범위에 섞지 않는다.**

## J. 자료 인용·재실행 한계

이 보고서의 검증 근거는 `SOURCE_REFERENCES.json`의 정확한 GitHub 링크로 따라갈 수 있다. 감사 증거는 upstream LFS 전체를 다운로드·검증하지 않았고 GitHub 연결로 파싱 가능한 자료만 읽었다. 정적 코드 확인·CSV/JSON 집계·SHA 문서 비교는 수행했으나, 실제 원 native Sionna RT와 raw binary H 전체를 계산해 물리 성질을 확인하는 작업은 수행하지 않았다.

`verify/verify_ra0_ra1.py`는 동봉한 *GitHub에서 추출한 정확한 수치 행*을 다시 계산한다. 원 데이터와 연결되는 검증은 source Git blob SHA, fixed run identifiers 및 상기 origin links로 고정했다. 이 local verifier의 PASS는 **복사된 수치표에 한정되며 독립 연구자 감사가 아니다**.