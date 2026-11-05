# E1-02 단일단계 준비 상태 — 읽기 전용 검토

판정: **NOT_READY / HOLD**. 기준 HEAD ba8d978acce3a41d113a2021b0e26e911d21ba71. 역할 AUDITOR(동일 작업자 자체 검토, 독립 감사 아님). 질문 FP-SC-E1-02-READINESS: 후보 도달 검증 이후 입력/mapping/모델/권한이 실제 E1-02 실행기로 결속됐는가?

사용자 범위: 상태 확인과 잔여 준비 정리. E1-02/E2 실행 금지. 코드·승인·기존 결과는 수정하지 않았고 이 보고서만 추가했다. COMMON_CONTRACT/ROLE_AUDITOR를 적용하며 지침은 이전 bridge 자체검토와 동일 로컬 RESEARCH-GOVERNANCE-v1이다.

## 현재 확인

1. 후보 생성·도달: SELECTOR_REACH_R2의 세 관문 PASS 보존. 그러나 runner.run은 `OriginalAdapter(root)`만 생성하고 revision_evidence를 주입하지 않는다. 현재 실행하면 VAB가 아니라 원래 생성기 경로가 선택된다.
2. 실행 경로: study.e1_detection은 C/P/M/PM을 labelled(detect_only=True)로 호출한다. labelled는 teacher_forced=True를 설정하지만 engine.open_loop는 실제 select, native_support, TrustedHistory.observe를 호출한다. 정정 결과를 평가에 적용하지 않는 detection 단계여도 계산 경로는 순수 집합 진단이 아니다. VAB를 주입하면 현재 개정 select/history guard에서 중단된다. SyntheticSelectionProbe를 실제 데이터 허가로 재사용하면 안 된다.
3. 원본 입력: E1 INPUT_LOCK의35개 파일을 현 로컬에서 SHA256 재검증,35/35 일치. 이는 기존 RF/후보 입력의 준비이며 canonical online/evaluator/controls/prior 자료의 준비를 뜻하지 않는다.
4. canonical 입력: 현 로컬 repo 및 인접 source에서 online.npz/evaluator.npz와 실행용 study_manifest/approval의 표준 파일명 검색 결과 없음. 고정486f0b6의 MANIFEST_TEMPLATE은 코드/입력 잠금이 비어 있고 E1-02 case_ids=[], 환경 placeholder다. 다른 이름/다른 저장소의 준비 상태를 확인했다고 주장하지 않는다.
5. mapping: 기존 E0 DETECTOR_MAPPING_REVIEW의 판정은 RESOLVED_DEFINITION_AND_STATIC_NATIVE_MAPPING_ONLY. static24조건을 확인했지만 dynamic prior-error, uncertainty support, wrong/overconfident prior, online causality는 미검증이고 E1_02_through_E5_GO=false다. 현재 native_support는7점 x/y/yaw stencil, sigma scale2, slack0.15m를 사용한다. 이것은 검토·보장된 confidence region이 아니다. contracts.authorize는 mapping_reviewed boolean만 검사하므로 실제 mapping recipe/근거 해시 결속이 추가로 필요하다.
6. 모델/소스: runner.SOURCES_REQUIRED14개 중 로컬에11개가 미물질화 상태. SourceFFD 소스와 FFD bank는 현재 Git tree에 있지만 로컬 두 LP bank 파일은 없다. 알려진 Snowball KMS의 `/home/KMS/codex_runs/FP_SC_R1_20261105/repo`에서도 두 bank와 scripts/fp_sc_followup.py가 없음을 읽기 전용 확인했다. 다른 서버 checkout 전체를 조사하지 않았다.
7. 실행 entry: scripts/fp_sc_followup.py는 현 HEAD tree에도 없으며, 고정 후속 소스486f0b6에는 존재한다. pinned entry를 명시적으로 가져오고 code_paths 잠금을 갱신해야 한다. 기존 R1 staging은 전체 E1-02 runtime 준비 상태가 아니다.
8. 모델 구분: E1-02에는 원본 SourceFFD/native detector 모델이 필요하다. readiness.MODEL_STAGES는 E3-04/E4/E5이고 E1-02를 포함하지 않으므로 F00/F01/F11 보정모델의 학습·배포는 E1-02 선행 필수조건이 아니다. 여기서 E3 학습을 시작할 이유가 없다.
9. 선행 receipt: E1-02는 contracts.DEPENDENCIES상 E1-01에 의존한다. 기존 adopt_e1은 원본 E1-01을 HOLD_RESULT_REVIEW로 유지하며 후보 R1/bridge R1/reach R2를 새 결속으로 받아들이지 않는다. 기존 실패를 PASS로 덮어쓰지 않고 개정 증거의 별도 acceptance/continuation 경로가 필요하다.
10. 권한: 고정 APPROVAL_TEMPLATE은 execute_science=false, stages=[], actor/manifest/code 해시 null이다. 현재 사용자 지시도 실행 금지다. 준비 승인이나 과거 후보 진단 승인을 E1-02 실행 승인으로 취급할 수 없다. 실제 승인·manifest 쌍이 없으므로 현재 authorize/preflight를 통과했다고 기록하지 않는다.

## 실행 전 준비 순서

1. E1-02의 VAB·모드·EXPOSED_DEV case 목록·분모·Policy·판정·중단 조건을 먼저 동결한다. detection-only의 점수/원본-tap 이력 의미를 명확히 하고 정정·closed-loop/E2 호출0을 검사한다. E2용 전체 정정 정책의 채택과 E1-02 검출 실험 허가는 구분한다.
2. 원래 실패와3개 개정/도달 결과를 별도 선행 증거에 연결한다. 현재 dependency 해석을 문서·코드와 일치시키고 과거 FAIL/HOLD는 유지한다. nonpass exploratory 경로를 쓴다면 그 성격을 명시하며 자동 우회하지 않는다.
3. 고정 소스·CLI·FFD bank를 지정 runtime에 물질화하고 LFS payload/hash를 확인한다. exact Python/NumPy와 code lock을 새 manifest에 결속한다. 이를 위해 모델 학습이나 RF 생성은 필요하지 않다.
4. canonical online/evaluator 파일을 동결 원본에서 별도로 준비한다. Hrf/t/pose_id/controls/x0/P0/z/mu/R/D/prior/Pprior, source frequency/RX 순서·정규화·noise variance, 정확한 timeline join과 prior 시점(측정 전)을 확인한다. evaluator truth/clean_H는 온라인 입력과 분리하고 누락 값을 추정해 채우지 않는다.
5. 동적 detector-domain mapping 및 support 폭/slack의 근거를 검토한다. mapping_reviewed=true만 쓰지 말고 recipe/hash/한계·수용 기준을 마련한다. 동적 검증에 별도 계산 실행이 필요하면 그것은 계획으로 구분하고 이번 검토에서 실행하지 않는다.
6. runner가 VAB/SelectionBinding을 명시적으로 선택하도록 연결하고, E1-02 detection-only에 한정된 실제 데이터 경로와 원본-tap 이력 조건을 구현·검사한다. ready boolean 또는 합성 probe로 우회하지 않는다. 기존 calibrated-safe model/threshold라고 주장하지 않는다.
7. 사용자에게 실제 실행이 승인된 뒤에만 stages=["E1-02"]로 제한한 approval을 정확한 manifest/code hash에 결속한다. E1-03/E2 이후 단계는 허용하지 않는다. 준비 검사는 데이터/스키마/해시만 다루는 read-only preflight로 구분하고, 단일단계 종료 후 결과 검토에서 멈춘다.

## 코드 근거

- followup/runner.py: code_paths, SOURCES_REQUIRED, run의 adapter 생성 및 E1-02 dispatch.
- followup/data.py: ONLINE_ARRAYS, load_case, export_archive.
- followup/contracts.py: authorize, prerequisite, DEPENDENCIES, Policy.
- followup/readiness.py: adopt_e1, preflight, MODEL_STAGES.
- followup/study.py: labelled, e1_detection; engine.py: open_loop.
- E0_20261105/audit/DETECTOR_MAPPING_REVIEW.json의 limitations/stage_boundary.
- Git object486f0b6의 research/FP_SC_FOLLOWUP_CODE_ONLY_20261105/MANIFEST_TEMPLATE.json 및 APPROVAL_TEMPLATE.json.

이번에 실행한 것은 코드·문서·파일 존재 확인 및 기존35개 입력 해시 검사뿐이다. E1-02/E2, 새 RF, 모델 로딩/학습, mapping 수치 실험, approval 변경은0이다.
