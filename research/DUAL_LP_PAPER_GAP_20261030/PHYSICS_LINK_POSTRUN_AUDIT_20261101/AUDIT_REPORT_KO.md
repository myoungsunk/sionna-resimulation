# DLP-PHYS-LINK-001 제안자·사후 기술 감사

기준일: 2026-11-01. 역할: 원 제안 목적 검토 + 별도 수식·원자료 재계산. 기존 구현자 validation helper는 호출하지 않았다. 물리 모델은 동일한 고정 SourceFFD 원소스를 공유했다. 외부 독립기관·사전 동결 감사 인증은 아니다.

## 1. 최종 판정

**제출·검사 계약의 최종 판정: REVISION_REQUIRED. 핵심 수치 결과의 판정: ACCEPT_WITH_BOUNDARIES. 과학적 해석: MIXED.**

현재 첨부된 재구현본의 4상태 모델, 관측 정의, 기존 평균, prediction 이전 lookup, fixed/self 분리, 상수 대조군, 평가 분모는 제안 목적에 부합한다. 기존 수치 결과를 폐기하거나 모델을 재설계할 근거는 발견하지 못했다. R4의 XY 악화와 상수 우세는 검증 실패가 아니라 사전에 허용한 유효한 반대 결과다. 모든 case에서 성공하도록 모델을 바꾸라는 요구는 하지 않는다.

수정 요청은 원본/재구현본 계보, 미확인 사전·사후 승인, 테스트의 실제 실행과 PASS 표시 사이의 간극, 첫 분기 원장, 물리적 설명용 집계에 관한 것이다. 수정 전에는 “원본 15503350 실행을 독립 감사까지 완료했다” 또는 “전 계약 항목이 모두 완료됐다”라고 표시하면 안 된다.

## 2. 감사 대상의 정체와 GitHub 확인

- 첨부: `DualLP_Physics_Link_Validation_20261101.zip`, 219,499,008 bytes, SHA-256 `fda9f1c34e8f14471ea00238b3c24a269ed17acc59d5f9a0c7f6041df314aca3`.
- ZIP 내부 `MANIFEST.json`은 `NEW_RETROSPECTIVE_RECONSTRUCTION`, `historical_original_archive_available=false`, `historical_original_commit_recovered=false`, `audit=SELF_REVIEW_ONLY`라고 명시한다.
- 원본으로 언급된 `1550335002367c656939bab4876675c612f0915c`는 원격 GitHub에서 422 “No commit found”였다. 첨부물에 해당 Git objects·FROZEN_EXECUTION_V1.md·INDEPENDENT_POST_RUN_VERDICT.json도 없다.
- 원격 `research/dual-lp-physics-link-validation-20261101` HEAD는 `20f4545ca5b462c1f8be4464607108f5fdc681fe`. 제안서 이후 추가된 것은 두 Markdown이며, 상태는 `PARTIAL_SOURCE_ONLY / VALIDATION_OUTPUTS_NOT_PUBLISHED`다.
- `research/dual-lp-physics-rebuild-20261101` HEAD `632568ae79de36ad4d75d4e40e3e5628c1181e7d`에는 입력 회수용 workflow 세 개가 추가됐다. 이 SHA는 첨부 패키지의 검증 코드·결과 전체를 담은 실행 커밋이 아니다.

따라서 **원본 실행의 게시·감사 인증은 BLOCKED_EVIDENCE**, 첨부 재구현본은 별도 객체로 감사한다. 이름과 일부 수치가 같아도 두 실행을 합쳐 인증하지 않는다. 현 사용자 지시는 게시 권한으로 충분하며, 다시 승인 요청할 필요는 없다. 다만 존재하지 않는 원본 Git commit을 새로운 파일로 재현했다고 할 수는 없다.

원격 근거:
- https://github.com/myoungsunk/sionna-resimulation/blob/20f4545ca5b462c1f8be4464607108f5fdc681fe/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_LINK_VALIDATION_20261101/AVAILABLE_SOURCE_STATUS.md
- 제안서: https://github.com/myoungsunk/sionna-resimulation/tree/43818124f39ad5ae20eb372d682dd2a63d8786bc/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_LINK_PROPOSER_20261101

## 3. 실제 재계산 범위

이번 감사는 제출 QA의 PASS 문자열을 읽는 데서 끝나지 않았다. 감사 스크립트 `independent_audit.py`, `source_ffd_audit.py`, `lineage_control_audit.py`를 별도로 작성·실행했다. 결과는 감사 다운로드 묶음의 `audit_results/`에 있다. 제출 구현·원자료는 수정하지 않았다.

|검사|이번 감사의 실제 범위|결과|
|---|---|---|
|아카이브 무결성|inventory가 지정한 368개 파일, 크기·SHA-256|368/368 일치|
|복구 원소스|현지 106개 파일의 SHA-256와 Git blob|106/106 일치|
|FFD bank|GitHub Actions에서 ±45° bank 두 개 별도 회수|원 NPZ SHA와 일치|
|원시 RF 관측|3,136 Full/LoS 시간표본에서 Hann/IFFT/공통 tap 독립 추출|CONTROL/ledger와 일치|
|대수 불변성|Full·LoS의 scalar·port 시험 18,816건|통과|
|SourceFFD 미분|3,136 pose × x/y/yaw = 9,408 차분; half-step 포함|stable 9,356 통과, transition 52 별도|
|실제 prior의 물리 모델|132개 trace마다 균등 32점, 총 4,224점 h/J 재계산|최대 차이 0|
|운동·필터 대수|144 논리 trace의 150,528 packet-visits: F/Q 예측, R, innovation, NIS, gate, 갱신, P|통과|
|전체 지표|144 × 9 = 1,296개 지표를 trace에서 재산출|통과|
|과거 CSV|96 × 9 = 864개, 원 CSV 표시 6유효숫자|864/864 일치|
|원 CONTROL|B0/L2 × 3경로 × BB/MB = 12개 full state/P/mask|12/12 통과|
|동일-prior|50,176 후보, 48개 조건·arm 손실행|통과|
|상수분산|다른 두 B-route B0의 모든 유한 t≥30 lookup², route 동일 가중|3개 상수 정확히 재현|
|평균 prediction 계보|HG/MR → CONTROL 6,272행|통과|

모든 SourceFFD h/J를 다시 사용해 132개의 필터를 처음부터 다시 실행한 것은 아니다. 대신 전체 저장 trace의 운동·업데이트는 전수 검산했고, 물리 h/J는 전체 true pose의 FD와 모든 trace의 체계적 prior 표본에서 재평가했다. 이 구분을 숨기지 않는다.

핵심 최대 오차:
- H→거리: 3.553e-15 m; H→signed s: 7.217e-16.
- motion state: 8.882e-16; motion P: 8.674e-19.
- 갱신 state: 1.777e-15; 갱신 P: 2.776e-17.
- 1,296개 지표 중 최대 Heading RMSE 차이: 2.221e-16°; 최대 XY RMSE 차이: 1.777e-15 cm.
- 원 CONTROL state: 3.936e-14, covariance: 2.810e-16; acceptance 불일치 0.
- source 포트 교환 시 J_s 부호검사 최대 오차: 5.052e-15.

사용한 새 FFD 회수 증거는 run 41314489537의 artifact 13085624480/13086865783이다. 원 NPZ SHA:
- plus: `b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b`
- minus: `39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9`

## 4. 구현이 제안 의도를 유지했는가?

### V0 — 기존 비교와 표본

`replay_validation.py`는 원 `diag_mbvar.run`을 사용하고, wrapper는 반환되는 J만 기록한다. original BB self의 mask를 fixed 대조에 사용했다. BB fixed 12개를 동일 self trace로 alias한 것은 동일 초기조건·규칙에서 유효한 중복 제거다. 이를 숨기지 않아 실제 132회와 논리 144개는 모순이 아니다.

같은 RF·관측·mu·R를 네 gyro 조건에서 재사용하며 sensor generator는 원 코드와 seed를 유지한다. truth로 sensor simulation과 평가를 하는 것은 기존 실험 정의이고, 필터의 h는 실제 prior에서 평가된다. 감사에서 평가한 4,224 prior의 h/J가 기록과 정확히 같았다. 같은 장면의 12조건을 독립 환경 12개로 세지 않았다.

### V1 — 물리 관측과 미분

Full→CONTROL, Full/LoS own-tap와 common-full-tap의 분리, FFD signed 관측과 미분 검증은 유효하다. 52개는 실패를 지운 것이 아니라 branch 전환 구간이다. 실제 필터 mask는 안정 미분 subset으로 바뀌지 않았다. SourceFFD–Native LoS의 차이는 zero parity로 숨기지 않고 따로 보고했다.

이것은 물리 관측함수와 코드의 연결 검증이다. 하드웨어 정확도·Full multipath의 정확한 확률우도·전체 상태의 전역 관측가능성 인증은 아니다. 서로 다른 source/native 비교에 같은 1e-12 threshold를 기계적으로 적용하여 허위 FAIL을 만들지 않는다.

### V2 — 평균×분산과 signed 갱신

BB_ORIG 기준 prior/P/J와 같은 직전 posterior lookup을 네 shadow cell에 제공한다. mu 변경은 innovation만 바꾸며 같은 R의 K는 동일하다. 추가분산의 gain identity와 Kepsilon+Kdelta_h 분해는 맞다. shadow 결과는 원 재귀에 feedback하지 않는다. 평균 손실의 주요 분모는 fixed accepted AND t≥30이고, 최종 RMSE는 모든 t≥30 시간점이다.

R2/R5의 8조건에서 평균-only의 즉시 Heading MSE가 더 작지만 최종 재귀 성능은 결합 설정이 더 좋다는 결과는 재현됐다. 이는 “모든 packet에서 분산 추가가 항상 나쁘다”를 의미하지 않는다. BB prior 위의 조건별 평균 비교이며, 다른 arm의 prior까지 보편화할 수 없다. 전체 누적 원인은 아직 분해되지 않았다.

### V3 — 상수 대 lookup

상수는 학습 두 route의 B0 BB lookup²를 route별 평균한 뒤 1/2로 합친다. held route의 결과·거리분포를 사용하지 않았고, bias/mean/gate마다 다시 조정하지 않았다. 상수는 각각 R2 0.010599432267663023, R4 0.012554155196859866, R5 0.01018782980886269이다.

R2/R5 8조건 lookup 우세, R4 4조건 constant 우세는 fixed/self 모두 재현된다. fixed에서는 실제 accepted keys까지 arm 간 동일하므로 packet 선택 차이만으로 설명할 수 없다. 그러나 prior와 P의 재귀 변화는 남는다. lookup의 역사적 설계가 in-sample이므로 새 환경 holdout 성공이라고 할 수 없다.

### V4/V5

V4는 선택 항목으로 미실행이며 이번 승인에 필수로 추가하지 않는다. V5 archived prediction의 계보는 검증됐지만 fresh inference와 학습 누출 여부의 완전 검증은 model/scaler/fold가 없으므로 BLOCKED다. 원래 입력을 다시 학습하거나 GT로 보정값을 채워 넣어 이를 해결하면 비교모델이 달라진다.

## 5. 구현자에게 반환할 수정사항

### R1 — 원본 실행·재구현·원격 게시를 하나로 말하면 안 됨 [필수, provenance]

현 원격에는 원본 15503350이 없고, 첨부는 이를 회수하지 못한 재구현본이다. 사용자가 전달한 원본 요약의 FROZEN_EXECUTION_V1/INDEPENDENT_POST_RUN_VERDICT/355 added 주장에는 이번 첨부로 확인할 증거가 없다. 재구현 패키지 자체는 이 한계를 솔직히 명시하지만, 인계 메시지를 그대로 쓰면 잘못된 인증이 된다.

**수정:** 새 실행 식별자·source revision·code hash·ZIP hash를 부여하고, original_commit와 reconstruction_commit을 별도 필드로 저장한다. 원본은 MISSING, reconstruction은 VERIFIED_WITH_BOUNDARIES로 기록한다. 현재 사용자가 게시를 명시했으므로 새 승인 질문 대신 실제 게시 결과·HEAD·원격 파일 해시를 남긴다. 존재하지 않는 원본 SHA를 붙여 새 커밋을 원본처럼 만들거나 force-push하지 않는다.

### R2 — 실행 권한·동결 상태의 machine-readable 모순 [필수, governance]

`CONFIG_LOCK.json`의 execution_authorized=true와 allowed_now=문서작업, statuses=NOT_RUN, input_lock_sha256=null이 함께 남아 있다. 해명 문서는 회고적 snapshot임을 설명하지만 자동 실행 입장에서는 승인/범위 판정이 불가능하다. 원래 제안은 V0→별도 pre-run 검토→FROZEN을 요구했고, 그 승인 원본은 회수되지 않았다.

**수정:** 기존 snapshot은 보존하고 `RUN_ADMISSION_RECORD_V2.json`을 append한다. RETROSPECTIVE_RECONSTRUCTION임을 명시하고 실제 사용자 요청 식별, 허용 stage, 실제 input/config/code hash, 실행/검토 역할을 기록한다. 제안자 사후 수용은 retrospective acceptance이지 과거 pre-run 서명으로 소급하지 않는다. 문서·구현·논문 발표 승인 상태를 분리한다.

### R3 — 평균 동일화 음성시험이 실계산 없이 PASS로 기록됨 [필수, test implementation]

`code/shadow_validation.py:51`의 BB/MB K 동일성은 R가 같을 때 mu와 무관하게 참이다. 이 비교는 mu_M=mu_B 개입을 시험한 것이 아니다. 같은 파일 54–58행은 sigma=0 경로만 실제 검사하고, 65행에서 copied_mean_identity_pass=True를 직접 기록한다. `quality_and_comparison.py:42–43`은 그 플래그를 다시 읽을 뿐이다.

**수정:** mu_M 배열 복사본을 mu_B 값으로 강제 설정한 별도 호출을 하고, 원본 배열이 변하지 않았음을 확인한 뒤 x_post/P_post/NIS/gate 및 signed correction을 BB와 비교한다. 실제 max error와 비교 수로 PASS를 계산한다. 소량의 고의 mu 오염을 넣으면 검사 실패가 나도록 mutation test를 추가한다. 이 항목은 테스트 커버리지 결함이며 현 수치가 틀렸다는 판정은 아니다. 재귀 132회 전체를 다시 돌릴 필요 없이 저장된 동일-prior 표본으로 먼저 보완 가능하다.

### R4 — 수치값을 계산하지만 최종 acceptance에 포함하지 않은 검사 [필수, fail-closed QA]

`replay_validation.py:40–41`은 prior/Pprior/nu/J/ds/gyro 차이를 기록하지만 pass에는 mask/x/P 일부만 포함한다. `shadow_validation.py:33–36,65–67`은 Schur 오차를 기록하지만 최종 assert에 그 tolerance를 포함하지 않는다. 현재 자료의 해당 값들은 이번 감사에서 작음을 확인했으므로 기존 결과를 폐기할 사유는 아니다. 그러나 미래 회귀 오류가 기록만 된 채 PASS할 수 있다.

**수정:** 필수 지표별 threshold와 check_id를 정의하고 `all(required_checks)`로 상태를 집계한다. mean equality·Schur·각 prior/control/observer parity에 실패 주입을 한 회씩 수행한다. 불가능/미실행이면 PASS가 아니라 BLOCKED/NOT_RUN을 반환한다. Python 최적화로 assert가 꺼져도 QA가 작동하도록 명시적 예외·검사기를 권고한다.

### R5 — 첫 분기 원장이 제안된 설명 스키마보다 축약됨 [필수 산출물 보완, 재집계]

`quality_and_comparison.py:76–80`의 FIRST_DIVERGENCE.csv는 첫 상태차 시점·첫 gate차·개수만 기록한다. 제안자 인계서가 요구한 첫 rho/sigma/R/nu/K/x/P/mask 값과 차이 순서가 없다. 전체 trace는 존재하여 정보 자체가 소실된 것은 아니다.

**수정:** 기존 NPZ에서 최초 분기 packet의 k-1 posterior, lookup rho/sigma, motion input, predicted x/P, h/J, mu/R, innovation/K/NIS, selected mask, post x/P를 두 arm에 대해 저장한다. `must_be_equal` 필드와 `allowed_to_change` 필드를 분리하고 최초 불일치 이유를 기록한다. 같은 prior 비교와 서로 다른 재귀 prior 비교는 다른 표로 만든다. 새 RT/학습/전체 재실행 불필요.

### R6 — 물리 검증과 개선 원인 설명의 완료 범위를 구분 [논문 활용 조건]

V1은 물리 미분을, V2는 갱신의 대수를 검증한다. F1 산점도와 같은 prior의 평균 손실만으로 특정 반사체 또는 전체 재귀 누적 원인이 식별된 것은 아니다. 현재 보고서는 이 한계를 인정하므로 결과가 무효인 것은 아니다. 다만 “원인 설명까지 완료”한 원고로 승격하려면 연결 집계가 더 필요하다.

**보완:** 기존 PHYSICS_PACKET_LEDGER와 MATCHED_PRIOR_2X2를 case/pose/time으로 조인하여, 사전 명세의 거리·상대방위·tap 조건별 n_all/n_used/n_stable, signed 잔차·mean/variance, Kpsi,r*epsilon_r, Kpsi,s*epsilon_s, Kdelta_h 및 즉시 손실 대비를 만든다. R2/R5/R4를 따로 보고 sparse bin을 숨기지 않는다. 이것은 새 필터가 아니라 기존 evidence의 추가 집계다. 누적 인과 설명을 핵심 주장으로 올릴 경우에만 선택 V4 또는 별도 설계가 필요하다. 현재 V4 미실행만으로 V0–V3의 유효성을 부정하지 않는다.

## 6. 결과를 사용할 수 있는 범위

유지 가능: 기존 12조건 성능, fixed/self와 mean/variance ablation, 설정을 유지한 상수 대 lookup의 경로별 결과, 실제 FFD 기반 signed 관측과 active-branch Jacobian의 수치적 정합성, 같은 BB prior에서 국소 효과와 최종 재귀 효과가 다르다는 진단.

보류: 원본 15503350 게시·복원·독립감사 인증, 사후 생성된 FROZEN 승격, 모든 packet의 즉시 개선, 거리 lookup의 일반적 최적성, 통계적 유의성/신규 장면 일반화, 실제 ML fresh inference, 완성된 물리 stochastic likelihood, 특정 반사체를 최종 오차의 단일 원인으로 지목.

R1–R5 수정은 이미 유효한 원 결과와 실패/한계 기록을 그대로 보존한 채 append-only로 수행한다. 검증 결함을 고친다는 이유로 lookup, gate, mean, seed, case를 바꾸거나 R4를 제외하지 않는다.
