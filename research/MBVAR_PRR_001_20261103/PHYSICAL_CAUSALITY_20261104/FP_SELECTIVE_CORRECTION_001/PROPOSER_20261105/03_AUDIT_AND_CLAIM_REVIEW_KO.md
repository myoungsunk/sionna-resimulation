# FP-SC-001 — 구현·실행·결과 독립 감사 요청서

**대상:** `01_EXECUTION_PLAN_KO.md` v0.1와 향후 동결된 `04_RUN_CONTRACT_DRAFT.json`의 정식 버전.  
**현재 상태:** 감사 요청 설계만 작성. 독립 감사자 미배정, 감사 미실행, 승인 토큰 미발급.  
**감사 목적:** 코드가 계획대로 동작하는지와 결과가 H0–H7을 지지하는지를 서로 독립적으로 판정한다.

## 1. 감사 역할과 증거 범위

감사자는 구현자의 요약·PASS 문자열을 그대로 수용하지 않는다. 정확한 input/code/contract SHA, payload 바이트, 원시 packet trace, 별도 계산기로 검산한다. 별도 agent 이름만 지정하거나 같은 production scorer를 다시 실행한 것은 독립 검증으로 충분하지 않다. 입력·결과의 일부만 읽었으면 실제 읽은 행/byte/검사 수를 명시한다.

문서의 과학적 타당성을 검토하는 SPEC 감사, 구현 수학을 검토하는 CODE 감사, 데이터·결과를 검토하는 RESULT 감사, 저장소 게시 무결성을 검토하는 PUBLICATION 감사를 분리한다. 감사 통과가 다음 단계 전체 실행·채택을 자동 허가하지 않는다.

### 감사자에게 전달할 최소 묶음

`FROZEN_CONTRACT`, `POLICY_SPEC`, `INPUT_LOCK`, `ENV_LOCK`, `SPLIT_MANIFEST`, `RUN_MATRIX`, exact implementation SHA, 독립 checker SHA, 모든 원시 출력·실패·보류 ledger, 요약을 재생성할 명령, 논문/보고서의 claim matrix. 비밀번호·토큰·사용자 개인정보는 포함하지 않는다.

## 2. 구현 전 SPEC 감사

### A0-01 — 정의

1. raw detector tap, 연속 direct delay, geometric range, bias-corrected range, state radial error가 구별되는가?
2. nL0를 operational reference라고 명시하고 true earliest physical path 또는 polarization-optimal tap으로 오인하지 않는가?
3. noisy LoS에서 참조 불확실·신호 부재를 unknown 처리하는가? unknown을 제거해 유리한 결과만 만들지 않는가?
4. h_r와 실제 detector range의 offset/quantization mismatch를 확인하도록 했는가?

### A0-02 — 인과 설계

1. 기존 FP가 잘못됐다는 판단과 대체 후보가 타당하다는 판단이 분리되는가?
2. candidate pool을 고정한 상태에서 CIR-only/P/M/PM을 비교하는가?
3. 4cm는 연속 0.2초·0.2m/s의 기하학적 이동 한계이며, detector 또는 prior 오차의 확정 경계가 아님을 지키는가?
4. F00/F10/F01/F11에서 raw ranging 보존과 calibration 변경이 분리되는가?
5. current CIR를 선택에 사용하고 다시 filter에 입력하는 selection dependence를 인정하는가?
6. 오염정보를 할인하는 C arm과 FP를 바꾸는 E/F arm을 분리하는가?

### A0-03 — 학습·선정·확인

1. 기존 3,136 pose 및 G4·seed0–29의 공개 이력을 명시했는가?
2. 주 E4는 same-RF 조건부 검증인지, 전체 pipeline outer route holdout인지 명확한가?
3. confidence와 μ/R가 각각 어떤 라벨·route·seed·pose block을 보았는가?
4. threshold/가중치/최소 교정률/평가지표를 개발 결과 후 확정하고 SEALED 전 동결하는 절차가 있는가?
5. 아직 정하지 않은 parameter나 source hash가 남으면 GO를 차단하는가?

**SPEC 결과:** `PASS_FOR_STAGE_Ei`, `REVISION_REQUIRED`, `BLOCKED_INPUT`, `INCONCLUSIVE_DESIGN`. 같은 reviewer가 제안의 작성자이면 독립성 수준을 명시하고 별도 승인 조건을 둔다.

## 3. CODE 감사 — 필수 음성·합성·재현 테스트

| ID | 시험 | 요구 결과 |
|---|---|---|
| C01 | no correction 및 correction disabled | 원본 tap·포트·gate exact; 관측/state/P 사전 허용오차 내 동일 |
| C02 | 강한 RX amplitude 30% vs power 30% | amplitude 정의만 baseline과 일치해야 함 |
| C03 | TX/RX swap·부호·deg/rad 손상 | fail-closed 또는 명확한 parity FAIL |
| C04 | h_r offset 1tap·sub-tap 편차 | interval/보류에서 드러나야 하며 단순 rounding 성공으로 숨기지 않음 |
| C05 | 미래 suffix·GT·LoS evaluator label 교란 | ≤k 시점의 selector 및 online output 불변 |
| C06 | current posterior를 selector에 넣음 | API/schema/timestamp 검사가 거절 |
| C07 | 현재 packet noisy waveform 공통화 | 모든 arm의 같은 sample noise hash 동일; 후보 수에 따른 RNG advance 없음 |
| C08 | 1/2/5/10tick 간격과 잘못된 이전 tap | elapsed bound·history age가 반영되고 hard4cm lock-in을 피함 |
| C09 | 제자리 yaw 변경·물리 distance 불변 | detector 변화와 motion bound를 혼동해 무조건 reject하지 않음 |
| C10 | 두 RX 중 한 포트가 실제 편파 null | 정상 direct 후보를 양포트 최소전력 조건으로 제거하지 않음 |
| C11 | noise-only·direct 제거·denominator≈0 | 지지 없는 tap/편파비를 만들어 내지 않고 hold/invalid 기록 |
| C12 | 모든 후보 틀림·1위 점수차 큼 | margin만으로 high confidence 부여하지 않도록 null/abstain 보호 |
| C13 | original correct→candidate wrong | false correction 분모·횟수에 반드시 포함 |
| C14 | reference mismatch이나 s오차 감소/증가 혼재 | nmatch와 s improvement를 서로 다른 라벨로 계산 |
| C15 | 같은 prior/H/R/mask의 F00/F10/F01/F11 | KΔz 및 fixed posterior covariance 동등성 |
| C16 | FP 변화 이후 μr/μs/Rrs 변경 | 정책에 맞는 feature 재추출·학습/평가 분리·PSD·단위 검증 |
| C17 | range-first/pol-second 또는 반복 갱신 | joint 결과와 동등하거나 단일 likelihood를 유지. 동일 CIR 정보 중복 금지 |
| C18 | original gate reject/hybrid accept | pre-mask gain 정확, mask 변화 별도 로그 |
| C19 | closed-loop prior provenance | E/F가 자기 state/history 사용, baseline future prior 접근 차단 |
| C20 | source/code/parameter 해시 변경·old GO | 프로세스 시작 전에 중단 |
| C21 | raw payload 미다운로드·LFS pointer | BLOCKED_DATA. pointer를 array로 간주하거나 명목 PASS 금지 |
| C22 | 지연·dropout·중복·역순·불완전 종료 | 모든 사건 보존, 정상 종료와 저장 결과 수용 분리 |

위 시험은 최소 목록이다. 미구현 기능의 테스트를 PASS로 채우지 않는다. 예를 들어 순차 갱신을 구현하지 않으면 C17은 NOT_APPLICABLE with evidence로 표시한다.

## 4. 단계별 RESULT 감사

### R-E0 — 입력·정의·기준선

원시 H dtype/shape/ports/frequency grid·index mapping을 검증한다. read-only checksum, raw data 접근성, 기준 수신기와 관측값의 exact tap parity, μ/R의 거리 정의, 각 range 오차 지표를 별도 재계산한다. 기존 oracle24 결과는 재현 가능한 동기일 뿐 실제 prior 성능으로 사용하지 않는다.

**차단:** raw 미수신, mapping 불명확, 기준 수신기 불일치, CURRENT_STOP 삭제. 결과가 없다면 NOT_RUN 또는 BLOCKED_DATA이지 FAIL 과학결론이 아니다.

### R-E1 — 탐지·후보 가용성

모든 packet의 reference label, validity, candidate inclusion, flag를 독립 산출한다. 원래 정상/오류/큰오류/unknown 분모 일치, candidate pool pruning 전후 recall, false flag와 false correction 구분을 점검한다. 특정 phase·route·yaw·seed·오류 사건이 누락되지 않았는지 확인한다.

**주장 한계:** H1 지지는 후보 선택의 성공이나 Heading 개선을 의미하지 않는다. “wrong”이라는 문구가 operational reference deviation인지 물리 직접파 오류인지 명확해야 한다.

### R-E2 — 선택·신뢰도·편파 영향

정책마다 같은 candidate pool인지, 미래정보 없이 prior/history가 생성됐는지 확인한다. correct→wrong, wrong→correct, wrong→farther, none→fabricated의 네 위험을 각각 표로 만든다. prior error와 self-updated tap history 시험을 반드시 포함한다.

confidence의 reliability, margin-bin별 손해, s spread-bin별 실제 s MSE, risk–coverage curve를 원자료에서 다시 계산한다. CAL에서 고른 cutoff를 SEALED에서 다시 선택하지 않았는지 검증한다. signed Δs correction을 실제 error reduction으로 잘못 표시하면 FAIL.

**주장 한계:** high-confidence correction이 잘돼도 현재 dataset의 조건부 결과다. 모호한 경우 abstain한 수와 update coverage를 공개해야 한다. 비정정 정책이 아무것도 안 해서 false correction=0인 것을 전체 성공으로 승인하지 않는다.

### R-E3 — 관측모델·단일 갱신

F00/F10/F01/F11의 한 packet 추출을 독립 재계산한다. range convention, two-port same-index, denominator·noise subtraction, μ/R provenance를 검토한다. fixed old model의 기전 결과와 matched μ/R의 성능 결과를 다른 표로 둔다. reference time-series 상관과 candidate selection dependence가 R 검증에 드러나는지 확인한다.

고정 prior/K/mask에서는 원래 P와 candidate P가 같아야 한다. calibrated R을 바꿨으면 Joseph에서 같은 R을 사용하는지 별도 확인한다. 평균 상태만 clip하면서 P를 강하게 줄이거나 원래 gate를 새 gate처럼 표시하면 FAIL.

### R-E4 — 자연 재귀

원래 controls·initialstate·noise 배열이 paired인지 확인하고 baseline A/B 무처치 parity를 검사한다. 각 정책의 자기 prior/history/selection/mask를 t=0부터 독립 replay한다. 선택된 hotspot 몇 개의 개선을 전체 개선으로 바꾸지 않는다.

route별·B0/L2별·Full/LoS별 primary와 initial/near/late를 모두 재집계한다. seed별 paired ratio·absolute delta, false-correction lock-in, range/polarization/Heading/XY/calibration을 함께 본다. 평균·정상 범위·tail·최악 시드 중 어느 것이 악화됐는지 사전 규칙으로 판정한다.

**주장 한계:** 오래된 RF의 새 sensor/noise seed는 새 물리환경이 아니다. 계측·보정·상태정확도·불확실성을 각각 독립 판정한다. “정확한 ranging 보존”은 raw값인지 corrected detector output인지 구분한다.

### R-E5 — 실행·운용

동일 hw·소프트웨어·입력 arrival pattern에서 실제 출력 지연을 재측정한다. FFT/selector만의 kernel timing으로 5Hz PASS라고 하지 않는다. timeout, stale data, buffer miss, dropped output, cross-thread race를 기록한다. 정확도 PASS와 runtime HOLD를 공존시킬 수 있다.

## 5. 과학 주장 판정표

| Claim | 필요한 가설·증거 | 허용 서술 | 금지 서술 |
|---|---|---|---|
| Q0 | H0/E0 | 원래 정의와 baseline 재현 | 모든 물리 FP를 정확히 알았다 |
| Q1 | H1/E1 | 지정 참조에 대한 오선택 탐지 | 교정 완료 |
| Q2 | H2/E2 | CIR-only 대비 운동·후보 정보의 선택 이득 | 4cm 안의 후보가 무조건 정답 |
| Q3 | H3/E2–E3 | 정상 보호를 포함한 s/r 측정오차 개선 | Heading/XY 자동 개선 |
| Q4 | H4/E2–E3 | calibration 범위의 신뢰도·잔여 MSE 정합 | posterior 독립성·완전 Bayes 증명 |
| Q5 | H5/E3 | 동일-prior 정보계상·갱신 정합 | 장기 재귀 성공 |
| Q6 | H6/E4 | 지정 route/bias/channel에서 정확도·보호조건 충족 | 모든 공간·경로의 일반화 |
| Q7 | H7/E5 | 고정 hw 5Hz 기한 충족 | 실환경 성능·다른 hw 보장 |

모든 claim에 `SUPPORTED / PARTIAL / NOT_SUPPORTED / INCONCLUSIVE / NOT_TESTED`를 부여하고, 이를 `TECHNICAL_PASS / FAIL`과 별도 필드로 저장한다.

## 6. 발급 가능한 단계별 승인과 필수 결속

`GO_FP_SC_Ei_DEV`는 해당 단계의 SPEC·CODE·INPUT 감사와 **정확한 implementation/contract/policy/environment/input hashes**가 모두 일치할 때만 발급한다. `GO_FP_SC_E4_SEALED`는 주 정책1개, 6arms의 정의, SEALED source 목록과 측정계약이 동결된 후 별도 승인한다.

승인 토큰에는 stage, 허용 데이터·seed·arms·개수, baseline commit, implementation SHA, control hashes, 최대 실행범위, 승인자 및 독립 auditor ID, 필수 선행 verdict를 넣는다. `OWNER_APPROVAL`과 `AUDIT_ACCEPT`를 서로 대체하지 않는다. hash drift·허용범위 초과는 중단한다.

## 7. 감사 결과서의 필수 내용

- 실제 검산한 raw files/bytes/rows/packets와 검사 개수; 검산하지 않은 범위.
- 기존 source SHA와 실제 실행 code/contract/input의 일치 증거.
- PASS·실패·기각·보류·unknown 전체 count reconciliation.
- 각 H/Claim별 증거와 반례, 수치의 정확한 모집단·단위.
- 독립 reviewer/agent/session·runner·checker SHA와 사용 도구.
- 실행 결과가 계약의 주장을 지지하는지, 다음 단계가 허용되는지 **분리된 판정**.

**새로 발견한 수정이 필요하면:** 원본 실패·STOP과 수치를 보존하고 amendment를 만든다. 결과를 보고 gate·threshold·평가분모를 바꾼 경우 새로운 version/run으로 재등록한다. 미래의 auditor는 이 원칙에 따라 재현 가능한 판단을 내려야 한다.
