# MBVAR-PRR-001 — ONE-SHOT-RT-DATA-001
## 남은 Native Sionna RT 원시 데이터를 단 한 번의 서버 세션에서 수집하는 통합 요청서

**작성일:** 2026-11-05 KST  
**역할:** PROPOSER → Snowball/Codex IMPLEMENTER_SELF_RUN  
**실행 분류:** USER_AUTHORIZED_NONINDEPENDENT_EXPLORATORY  
**현재 상태:** 요청서 및 등록키 확정, 이번 작업에서 신규 RT 미실행  
**목적:** 반사경로→복소 H→FP/r/s 오염→EKF 갱신/공분산 과신을 추후 분석하기 위한 원시 RF를 한 번의 서버 작업으로 모두 수집한다. 계산 도중 물리적 해석·모델 선택·새 사례 선정 때문에 추가 서버 접속이 필요하게 만들지 않는다.

기준: PR #34의 과학 설계, PR #33의 원본 재현 성공 e69fcdd6123d3d056cd95ea210ac8eb732f17628, PR #35의 C3/SM2 G2·G3 고정 계약. 새 설계 때문에 기존 Full/LoS archive·S1–S3·C3V5/G5 또는 이전 실패 기록을 수정해서는 안 된다.

## 1. 정확히 무엇을 수집할 것인가

첨부 [ONE_SHOT_RT_EXTRACTION_LEDGER_20261105.csv](ONE_SHOT_RT_EXTRACTION_LEDGER_20261105.csv)의 **400개 task_id가 전체 신규 원장**이다. 기계 판독용 설계·예산은 [ONE_SHOT_RT_EXTRACTION_PLAN_20261105.json](ONE_SHOT_RT_EXTRACTION_PLAN_20261105.json)에 있다.

| 자료군 | 계산 대상 | 등록 작업 수 | Native solver 상한 |
|---|---|---:|---:|
| B0 | 원래 R4-B 6면 scene, pose 194·234, 각각 Full/Native LoS | 4 | 1,028 |
| B1 | 원래 R2/R4/R5의 나머지 13개 지정 pose, 각각 Full/LoS | 26 | 6,682 |
| SM1 | 이전 계획의 R4/R5 8개 시계열 창에서 B0/B1과 겹치는 pose 제외 후 추가 175 pose, 각각 Full/LoS | 350 | 89,950 |
| SM2-G3 | PR #35 승인된 잔여 20개 yaw 조건, 각 257-bin Full ray와 지정 3-bin 반복 | 20 | 5,200 |
| **총 상한** | 원래 6면 복도 190개 고유 pose ×2모드 + 기존 G3 잔여 20 yaw | **400** | **102,860** |

**실행 승인 숫자가 아니라 최대 제안 호출수다.** 유효한 raw가 이미 존재하면 반드시 자동 제외하고 실제 호출 상한을 줄인다. 반대로 자료가 없다는 이유로 등록되지 않은 pose/arm을 추가하면 안 된다.

### 1.1 원래 복도 15개 고정 진단 pose

- R4-B: **168, 172, 173, 194, 234, 500, 525, 729** — 8개.
- R5-B: **401, 465, 979, 980, 982, 983** — 6개.
- R2-B: **525** — 1개.

실제로 필요한 자료는 각각 **원래 6면 복도**의 전체 주파수 257개 × 수신 2포트 × 송신 2포트의 복소 H와 Full/LoS의 **개별 ray coefficient, tau, object/interactions, path offsets**다. 기존 BLOCK_C의 복합 H가 있다는 것만으로 ray 원시자료를 확보했다고 처리하면 안 된다. PR #33의 새로운 floor+콘크리트 plate 2-object scene은 원래 6면 장면이 아니므로 이 15개를 대체하지 않는다.

### 1.2 시계열 SM1 8개 창: 원본 타임라인에서 이미 pose 고정

| Route | 원래 계획 시간 s | 실제 pose_id | 표본 |
|---|---|---|---:|
| R4 | 0–15 | 0–75 | 76 |
| R4 | 33.0–35.2 | 165–176 | 12 |
| R4 | 59–61 | 295–305 | 11 |
| R4 | 99–105.4 | 495–527 | 33 |
| R5 | 79–81 | 395–405 | 11 |
| R5 | 92–94 | 460–470 | 11 |
| R5 | 132–135 | 660–675 | 16 |
| R5 | 195–198 | 975–990 | 16 |
| **합계** | | **186개** | **186** |

위 186개 중 기존 고정 15개와 겹치는 것은 11개(R4 168/172/173/500/525; R5 401/465/979/980/982/983)다. 추가 시뮬레이션용 신규 pose는 정확히 **175개**다. 전체 6면 복도 고유 pose는 15+175=**190개**로, Full/LoS 2모드×257bin이 필요하므로 총 **97,660 호출**이다.

pose_id는 저장된 원본 Tnone의 route/pose_id/time/XY/yaw를 키로 결합하여 추출했으며, 시간을 단순 5배 반올림해 추정하지 않았다. 모든 window 중 오염이 약하거나 zero effect인 구간도 데이터 수집에서 제외하지 않는다. R4 초기 0–15초는 기존 과학 설계에서 이미 선택한 창이며, 이번 일괄 수집에 포함한다.

### 1.3 PR #35 동일 위치 yaw: 기존 성공분은 제외

**이미 완료한 4개:** R4_168의 yaw 0°,180°, +35.7°, −35.7°. PR #35의 G2 CANARY_002는 DATA ACCEPT, 257×4 + 고정 세 bin 반복×4 = **1,040 기존 solver calls**. 이 데이터는 **절대 재실행하지 않는다**.

**아직 확보 여부를 확인해야 하는 20개:** G3_001/GO_G3_001.json 및 PLAN.json에 고정된 아래 다섯 좌표, 각 4 yaw. 확인 시점 GitHub에는 승인된 20개 G3 결과의 전체 BATCH_001 원시자료가 게시되지 않았다. **로컬에 이미 완전한 결과가 있다면 반드시 재사용·SKIP하라.**

| 고정 좌표 | (x,y,z) m | yaw (°) | 조건수 |
|---|---|---|---:|
| R5_982 | (1.521387, −0.338994, .45) | 0,180,+35.7,−35.7 | 4 |
| P10Yp | (10,+.35,.45) | 동일 | 4 |
| P10Yn | (10,−.35,.45) | 동일 | 4 |
| P139Yp | (13.9,+.35,.45) | 동일 | 4 |
| P139Yn | (13.9,−.35,.45) | 동일 | 4 |

G3는 한 yaw마다 **Full 257-bin solver 1회씩 + 지정 bin 0/128/256의 3회 반복 = 260 호출**이며 기존 PR #35의 producer/qa/GO/physics/input hash 그대로 실행한다. 원래 복도 B0/B1과 혼동해 추가 LoS 257-bin까지 **중복 실행하지 않는다**. G4의 h_s/Hpsi 모델 갱신 또는 다섯 번째 실제 yaw 추가는 본 배치의 대상이 아니다.

---

## 2. 서버 한 세션에서 중간 분석 없이 수행할 단계

**단일 관리 작업 ONE_SHOT_CAPTURE_001** 아래 두 source family를 분리한다.

- A ORIGINAL_CORRIDOR: PR #34 원래 R2/R4/R5 **6면** 복도 Full 및 Native-LoS ray source. 기존 scene/mesh/material/FFD/pose/257-bin/원본 archive SHA를 사용. PR #33 콘크리트 plate scene을 사용하면 안 된다.
- B PR35_SM2_G3: PR #35의 이미 잠긴 G3_001 20개 고정 XY/yaw Full+direct data source. 기존 PLAN/GO/code/input/WSL runtime/checksum/QA를 변경하지 않는다.

각 family는 별도 source lock, cache namespace, 작업 큐, 원시 출력 폴더를 사용한다. **계산은 한 서버 세션에서 수행할 수 있지만 서로 다른 source SHA를 조용히 섞을 수 없다.** 전체 작업 관리자는 두 family에 대한 작업 수와 공통 CPU/시간/저장 예산을 관리한다.

**S0 — PRE-EXTRACTION INVENTORY (0 RT calls).** 400키를 원본 CSV에서 로드하고 키 중복/소스 존재/FFD·mesh/solver·port/frequency SHA를 검증. 로컬 + GitHub 보관된 기존 모든 raw를 스캔하여 동일 source/key/scene/257bin/2×2/path metadata/QA SHA가 검증된 키는 SKIP_VALIDATED로 지정. 파일명만 같거나 composite H만 있으면 SKIP 안 된다. 이전 실패 원본은 별도 FAILURE로 보존.

**S1 — 엄격한 B0 CANARY (최대 1,028 calls).** 원래 R4 194/234의 Full·LoS 257-bin을 먼저 확보한다. 원본 archive 복소 H·port·geometry source와의 parity를 자동 검증. Native LoS strict 상대 L2 ≤1e−5, Full 상대 L2 ≤1e−3 및 ray closure 기준은 **원본 설계서에서 제안된 수치로 실제 solver 호출 전에 별도 잠금**한다. Full 제안치 등을 결과를 확인한 뒤 편의상 바꾸지 않는다. Common source mismatch 또는 hard parity FAIL 시 해당 family의 확대 STOP; 실패 raw는 보존한다.

**S2 — A 나머지 376개 task를 한 번에 queued.** 원래 고정 13개 pose의 B1 26 task + SM1 추가 175개 pose의 350 task. 재료·좌표계·시간축·소스 정보를 다시 결정하거나, '이 편파오염이 논문에 좋은가' 판단을 중간에 하며 멈추지 않는다. 실제 수치값과 관계없이 사전 목록의 모든 작업에 종결 상태를 부여한다. 경로 검증이 이뤄진 공통 source만 계속 사용한다.

**S3 — B G3 20 yaw task.** PR #35 G3 GO가 허용한 20개에서 RAW와 QA가 이미 ACCEPT된 키는 건너뛰고 미완 키에 대해서만 원래 소스를 실행한다. G2 네 yaw는 이 큐에 추가하지 않는다. A와 병렬 스케줄 가능하지만 source environment/OUTPUT을 독립 유지하고, 사용 CPU 코어·RAM·시간·호출수는 **중앙 예산 카운터를 공유**한다. B의 GO가 S1A 과학계약을 자동 승인한다는 의미는 아니다.

**S4 — 종료 후 원본 통합 송부.** 모든 400키에 PASS/FAIL/SKIP_VALIDATED/NOT_RUN_BUDGET/BLOCKED_SOURCE 중 정확한 상태를 기록해 **한꺼번에** ZIP 또는 tar+SHA로 제출. 원본 ray coefficients/delay, 복소 H, scene mesh, timestamp·pose·yaw, manifest, runtime, 실패 및 재시도 로그 전부 포함. GitHub Actions artifact만으로 완료 처리하지 말고 Git LFS 또는 장기 접근 가능한 원격 저장소를 확보하고 크기/OID/SHA를 검사한다. SERVER DONE은 **데이터가 영속적으로 업로드·조회된 후**에만 표시한다.

**중간 분석 금지:** 어떤 pose가 극단적이거나 효과가 없다는 이유로 새로운 좌표·각도·경로를 선택하지 않는다. RF path grouping, coherent H, FP/r/s, 모델/K/NEES 등 과학적 메커니즘 분석은 **모든 원본의 서버 수집이 끝난 다음 로컬 분석 단계**로 분리한다. 서버가 계산하는 것은 기술 QA와 source archive parity뿐이다.

---

## 3. 실패·중단·재사용 계약

- 원본 Full/Native-LoS H parity/mesh/bank/port/source phase dtype 등 **공통 계약 불일치**: 전역 NEW-RF STOP; 기존 정상 파일과 실패 파일을 그대로 업로드하고, 잘못된 source 아래 다른 수만 회 계산 금지.
- 한 키에서 nonfinite/path invalid/geometry collision/runtime timeout: 해당 key FAIL_RAW_KEEP, 원본 실패 로그 및 partial raw 저장. 동일 논문 결론에 그 키가 필수면 결과는 INCOMPLETE; 임의 인접 pose로 대체 금지. 이전 전체 실행의 parity FAIL을 기준 변경으로 구제하지 않는다.
- 별도 허가 없는 자동 retry 기본 **0회**. 실패 후 셀프 재시도·다른 설정으로 복구하는 것은 재현성이 아니라 다른 실험이다.
- 중앙 CPU/wall/disk/solver-call 제한에 도달하면 즉시 정지 후 아직 미실행인 키를 NOT_RUN_BUDGET으로 분모에 유지한다.
- 유효 raw 재사용에는 (route,scene/input SHA,pose,heading,mode,port,frequency grid,code/solver/FFD SHA,full ray offsets/valid/objects/coeff/tau/complex H shape, QA) **모두** 일치해야 한다. PR #33의 성공 floor/plate 8,224 calls와 PR #35 G2의 1,040 calls는 본 요청의 비용에 다시 포함하지 않는다.

### 3.1 예산 산술

원래 복도 190pose×Full/LoS×257=**97,660**. G3 잔여 20yaw×(257 Full+3 repeat)=**5,200**. **총 102,860 solver calls** (기존 raw가 없다고 가정한 상한).

이는 단순 '400번'의 solver 호출이 아니라 주파수별 257회가 필요하다는 의미다. 기존 PR #33 통제 scene 8,224회 /14분55초/4-worker는 **다른 장면의 실측 reference일 뿐** 원래 6면 scene에서 실행 속도를 보장하지 않는다. 서버의 총 RAM/VRAM·디스크/CPU/시간 제한은 결과값이 아니라 실행 전에 수치로 고정한다. 예상 원시 용량은 해당 원본 6면 canary의 실제 파일 크기×필요 key로 추정하고 한도 내에서만 확대한다.

실제 계산 승인 기록은 별도 승인된 실행 manifest에 (max_solver_calls, max_wall_hours, max_workers, CPU affinity, RAM/VRAM, storage GB, currency budget, max_retries, source SHA, approval time)을 모두 포함한다. **본 요청서는 이 예산을 대신 승인하거나 서버 RT를 호출하지 않는다.**

---

## 4. 모든 키에서 보존할 필수 원시 산출물

**SOURCE/KEY:** SOURCE_LOCK.json, original route scene mesh/material/pose/Tnone/timebase/FFD bank·solver/phase code SHA, 400-key work ledger, original PR #35 G2/G3 GO binding.

**COMPLEX CHANNEL:** 매 키의 full 257×2RX×2TX 복소 H, per-frequency ray coefficients a, tau_s, path IDs, path offsets, valid, object/interaction chain, incidence/arrival/departure angles가 있는 경우 원본 그대로. direct vs all-path contributions와 source comparator Full/Native LoS H (복합 archive 자체는 immutable).

**RF OBSERVATION:** 원본 FFT Hann/1028/30% FP 관례, 두 포트 r/s/FP, offset 적용 전후의 거리·GT·invalid 사유. 자료 생성과 동시에 핵심 원시 포맷 QA는 수행하되 편파 원인/경로 효과를 중간 분석하지 않는다.

**REPRODUCIBILITY:** 257-bin bin count, Full/LoS archive complex residual (max_abs/relative L2), raw per-ray→H closure, nonfinite, source SHA; G3 지정 3 bin 반복의 hash 및 source QA.

**PROVENANCE:** 각 key source revision, original pose/scene/port/bank/material hash, runtime, wall/CPU·I/O·메모리, 실패 때까지의 solver calls, SHA256, 원격 보존 경로.

필수 최종 파일:

| 파일 | 핵심 |
|---|---|
| ONE_SHOT_INPUT_LOCK.json | 독립 A/B source+FFD+scene/code/solver SHA 및 user budget |
| ONE_SHOT_ALL_KEYS.csv | **400키 전부**, raw/reused/failed/notrun, used calls, output SHA |
| RAW/ORIG6_* | 원본 6면 복도 모든 Full/LoS 257-bin complex H+ray |
| RAW/G3_* | G3 잔여 yaw Full/direct ray+지정 반복 |
| FULL_LOS_ARCHIVE_PARITY.csv | 실제 archive 대비 원본 pose별 수치 비교 |
| RAY_FIELD_CLOSURE_QA.csv | native ray 합성의 complex H 잔차 및 누락 |
| FAILED_SKIPPED_NOT_RUN.csv | 실패·유효 기존 raw·시간/예산 미실행 등 전체 |
| RUN_MANIFEST.json | source SHA·solver/worker·호출 수·시간/크기·QA 상태 |
| BUNDLE_SHA256.txt + DOWNLOAD_INDEX.json | 영구 원격 raw 재확인 및 전수 다운로드 지시 |
| HANDOFF_FOR_OFFLINE_ANALYSIS_KO.md | 확보된 데이터와 과학 분석 후속 항목 R0/C0-B/SM1/SM2/C1/C2 |

해당 출력이 없이 텍스트 통과 보고서 또는 몇 개의 summary CSV만 반환하는 것은 **DATA_EXTRACTION_COMPLETE가 아니다**.

---

## 5. Snowball / Codex 직접 전달 지시문

**역할: IMPLEMENTER_SELF_RUN — USER_AUTHORIZED_NONINDEPENDENT_EXPLORATORY.**

PR #34 과학 설계와 PR #35의 고정 G3 yaw GO를 읽고, ONE_SHOT_RT_EXTRACTION_LEDGER_20261105.csv의 **정확히 400키**만 수행한다. 임의로 source, pose, ray mode, yaw, threshold를 수정하지 않는다.

처음에 RT 0회 source audit·데이터 재사용 스캔으로 기존에 ACCEPT된 완전한 257bin raw는 제외한다. G2의 이미 수락된 네 yaw를 새로 실행하지 않고, 기존 PR #33 8,224회 통제 장면도 다시 실행하지 않는다. Full/LoS 복합 H만 있는 archive는 개별 ray 자료로 대체할 수 없다.

원래 R4 pose 194/234 Full+LoS의 1,028 solver-call canary를 먼저 수행해 엄격한 원본 H parity를 수치 검사한다. 통과하면 같은 서버 세션에서 나머지 B1 26 task, SM1 350 task 및 PR #35 미완 G3 20 task의 raw 데이터를 **중간 과학 분석 없이** 모두 생성한다. G3는 이미 완료·원본 SHA가 검증된 키를 건너뛴다.

전체 호출 상한은 **102,860** (이전 검증 raw가 모두 없을 때). 실제 상한은 validation에서 발견한 재사용 key의 solver-call 수만큼 축소한다. 사용자 승인한 정확한 CPU/시간/디스크 예산 없이 실행하지 않는다. 모델 소스 불일치면 전역 STOP, 단일 실패면 실패를 기록하고 정책에 따라 처리하되 실패를 지워서 성공으로 만들지 않는다.

모든 등록 키의 결과(PASS/FAILED/SKIPPED_VALID/NOT_RUN), 원시 257-bin 복소 H/경로 coefficient·delay·object·offset/FFT-FP/r/s, provenance SHA·원래 input·runtime·budget·failure log를 영구 보존한다. 마지막에 한 번의 압축 인계와 전체 SHA/index를 게시한 뒤 **데이터 수집 완료**를 보고한다. 그 전에는 논문의 인과·EKF 결과를 재해석하거나 새로운 필터를 개발하지 않는다.

**현재:** 요청서 DRAFT / 새 RT 미실행 / PR #35 G3 GO는 별개 선행 승인 / HOLDOUT2 SEALED.
