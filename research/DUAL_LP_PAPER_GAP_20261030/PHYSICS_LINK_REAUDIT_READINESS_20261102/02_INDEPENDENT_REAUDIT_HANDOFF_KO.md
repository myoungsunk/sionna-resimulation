# 독립 감사자 인계서 — DLP-PHYS-LINK-001 REPAIR-V2

## 1. 역할과 목적

당신은 이번 보완 구현자가 아닌 별도 감사자다. 선택한 R2-B/R4-B/R5-B × B0/L0/L1/L2의 회고적 V0–V3 및 R1–R5 보완이 명세대로 계산됐는지 평가한다. 모든 조건의 개선, 새 환경, 새 모델, 새 RT 또는 V4를 감사 통과조건으로 추가하지 않는다. 과학 결과가 MIXED여도 계산과 보고가 정확하면 ACCEPT_WITH_BOUNDARIES를 부여할 수 있다.

원격 기준 `ca8cb43777100a0f5fae53978c0e4096d49701ff`, 과거 감사 `daf9999057c0ac32ae0ca8be20021ae9f31d1d22`. `docs/research-governance/ROLE_AUDITOR.md`의 역할·계산 독립성 규칙을 따른다. 과거 pre-run 승인이나 원본 15503350 실행 복원을 소급 인증하지 않는다. 이번 사전평가 역시 독립 감사자 최종 서명이 아니다.

## 2. 정확한 입력과 접근

|입력|규모 및 SHA-256|
|---|---|
|DLP_PHYS_LINK_REPAIR_V2_20261102.zip|350036 bytes; 18a99461a245be53b46bcfa0c4ac1596383f74459b4f17dc981e5bb62e51d70d|
|DualLP_Physics_Link_Validation_RERUN_20261101.zip|219512794 bytes; d2c9ab428ae676579a79907451a7523615876d3075f24f6abe7ee279ba75f7b2|
|이전 감사가 읽은 DualLP_Physics_Link_Validation_20261101.zip|219499008 bytes; fda9f1c34e8f14471ea00238b3c24a269ed17acc59d5f9a0c7f6041df314aca3|
|LP_plus45_bank.npz|b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b|
|LP_minus45_bank.npz|39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9|

보완 자료는 사용자 Library `/Research/DualLP_Physics_Link_Repair_V2_20261102/`, RERUN은 `/Research/DualLP_Physics_Link_Validation_RERUN_20261101/`에 있다. FFD는 기존 run 41314489537의 artifact 13085624480/13086865783에서 회수했다. 실제 SHA가 기준이며 URL 접근성은 감사 시 다시 확인한다.

공개 GitHub 27파일만으로 132 raw trace/FFD까지 자동 확보되는 것은 아니다. 실제 감사자에게 위 원본 ZIP·은행 접근을 함께 제공한다. 접근 불가능한 입력은 해당 검사만 BLOCKED_EVIDENCE로 기록한다. 현재 결과를 재생하려고 새 RF를 생성하지 않는다.

## 3. 검사 순서

### A. 계보·보호 범위

원격 HEAD와 신규27/기존변경0/삭제0을 확인한다. 원본 MISSING, 사후 RETROSPECTIVE, 부분 게시의 범위를 기계판독 admission 및 publication receipt와 대조한다. 132 trace·원 score·원 source config의 전후 hash를 비교한다. 원 ZIP과 RERUN ZIP의 바이트가 다른 것은 정상이며, 데이터 내부의 동일성을 별도로 검사한다.

### B. R4 미닫힘을 먼저 처리

`01_PREAUDIT_VALIDITY_AND_OPEN_R4_KO.md`의 세 반례를 재현한다.

1. pose/time corruption 호출이 현재 반환값을 저장하지 않고 이전 `got`을 사용하는지 확인.
2. 동일 timestamp가 strict-time guard를 통과하는지 확인.
3. 평가분모 검사가 같은 식끼리의 항등비교인지 확인.

구현자에게 별도 수정 커밋을 요구하고 현재 반환값만 사용하도록 확인한다. 정상 입력은 오경보 없음, 오염 입력은 검출, 해당 검출기를 의도적으로 약화하면 음성시험 자체가 FAIL해야 한다. 순서 교환·단독 실행·Python -O에서도 fail-closed 검사가 유지돼야 한다. 누락/추가/중복 ID와 빈 표/NaN/분모 0을 다룬다. 검사 숫자 5288을 유지하는 것이 목적은 아니며 의미 있는 guard 추가에 따른 새 ID 매트릭스를 허용한다.

### C. R3 실제 평균 null

제출 `shadow_update`를 정답 함수로 재사용하지 않고, Cholesky 또는 별도 식으로 BB와 실제 mu_MB→mu_BB 치환의 state/P, innovation/S/K/NIS/mask, signed correction을 24배치/25088 packet에서 비교한다. gain만 같은 것은 평균 동일화 증거가 아니다. 평균 오염을 넣으면 innovation·state·signed 항이 달라짐을 확인한다. 평균 변경이 K/P를 바꾸지 않는 것은 올바른 구조이므로 P까지 달라져야 한다고 요구하지 않는다.

### D. 기존 결과와 재귀 정합성

144 논리 비교와 실제132 trace의 alias를 확인한다. BB fixed/self 12개 기준 trace 재사용을 독립144실행이라 부르지 않는다. 기존 17 수치열의 동일성, 역사적 CSV의864지표, B0/L2 CONTROL12비교를 확인한다. 기존 t>=30 전체 시간점의 score 정의, fixed mask 실제 배열, degrees/radians·cm/m 단위, NEES 및95% coverage를 독립적으로 재계산한다. 원 mean prediction을 대수 복원하는 것과 fresh ML inference를 구분한다.

### E. R5 분기 원장

144 reference/target 상세값을 원 NPZ에서 다시 구성한다. 첫 mean/R 차이, 첫 posterior차, 첫 mask차가 같은 시점일 필요는 없다. 원장 각 시점과 필드의 정의를 확인한다. 48 same-prior shadow 원장에서는 prior/P/J뿐 아니라 previous posterior lookup 상태도 같아야 한다. 조회 시점을 prior로 임의 변경하지 않는다. gate 원인을 주장하려면 최초 gate 차이의 실제 NIS·K·prior·R도 해당 원 trace에서 추출한다.

### F. 물리 관측–오차–갱신 연결

원 FFD와 H에서 signed ratio, 공통 first-path tap·포트·좌표·보간 조건을 재구성하거나 이전 감사의 동일 source hash/검사 범위를 명시적으로 상속한다. 9356 stable FD와52 transition을 모두 보고한다. 원 SourceFFD를 공유하면 공유 사실을 공개한다. 제안자의 결과표만 다시 읽고 물리적 독립 검증이라 부르지 않는다.

50,176 후보의 innovation=epsilon+delta_h와 signed K항을 재계산하고, 물리 packet3136개에 case/pose/time으로 정확히 연결한다. R6의 signed mean과 loss mean은 같은 분모로 비교해야 한다. 다른 group_type의 겹치는 집계를 독립 표본으로 합산하지 않는다. true-pose FD stable flag와 current prior의 active branch 안정성을 구분한다.

## 4. 최종 산출물

- AUDITOR_IDENTITY.json: actor, 별도 session/runner, 사전 역할 관계, shared code/helpers.
- AUDIT_INPUT_LOCK.json: 모든 입력·코드·config·run 및 원격 commit hash.
- INDEPENDENT_NUMERIC_CHECKS.csv: 직접 재계산한 값, 비교값, 허용오차, 분모.
- NEGATIVE_CONTROL_COUNTERTESTS.json: 정상·오염·검출무력화·순서변경 결과.
- SCOPE_AND_UNVERIFIED.md: 전수/표본/미검증 범위 및 이유.
- FINAL_AUDIT_VERDICT.json: contract_id, code_commit, repair_ids_closed/open, allowed_claims, prohibited_claims, verdict.

verdict는 ACCEPT_WITH_BOUNDARIES / REVISION_REQUIRED / REDESIGN_REQUIRED / BLOCKED_EVIDENCE 중 하나다. 독립 검증을 수행하기 전에는 PENDING을 유지한다. 현재 사전평가가 요청하는 것은 R4 QA의 제한 보완이지, EKF 모델 재설계가 아니다.

## 5. 허용될 수 있는 범위

12조건 Heading 개선, 8조건 XY 개선, R4의 한계, 지정 상수 대조와 lookup의 경로별 우열, 동일 BB-prior의 즉시효과와 재귀효과 불일치, 원 FFD 관측연산의 수치정합성은 검증 가능한 주장이다. 전체 누적인과, 특정 반사체 단일원인, 실제 하드웨어 noise calibration, 새 scene 일반화, missing model의 fresh inference는 증거가 없으면 주장하지 않는다. 그 추가 실험의 부재만으로 선택한 12조건의 회고적 수치 결과를 무효화하지 않는다.
