# FP-SC-001 E1-02~E5: 로컬 실행 준비 감사 및 최소 수정

- 감사 기준: `74df3c99e24a2455c430bf099020dad37db65a79`
- 수정 브랜치: `audit/fp-sc-e1e5-local-readiness-20261105`
- 감사 목표: 사용자가 **직접** 실행할 때 불필요하게 발생하는 경로·계약·모델·메모리·재시도·증거 오류를 사전에 차단
- 불변조건: 기존 E0/E1-01, 후보 탐색 임계값, SourceFFD/원본 W0, E2 정책 수치, E3 모델 수식, E4/E5 과학적 판정 기준 수정하지 않음
- GitHub Actions: 이번 감사에서 직접 생성/호출/재실행하지 않음
- 새로운 실제 RF / 전체 EKF / 실기기 5 Hz 과학 검증: **실행하지 않음**

## 1. 코드에서 확인된 직접 실행 결함

| 우선순위 | 원본 증거·문제 | 실제 실행 영향 | 적용한 보수적 수정 |
|---|---|---|---|
| P0 | E1-01 `RUN_MANIFEST.json`에는 `stage, status, actual_waveforms, actual_packet_mode_rows`가 있으나 후속 `prerequisite()`는 `study_id, execution_status, numerical_qa_pass, scientific_gate`를 요구함 | 별도 재검산까지 완료돼도 원본 E1 receipt를 직접 등록하면 단계 진입 실패 | `adopt-e1` CLI: 원본 6320/12640, 생산·검산 파일 SHA, 별도 검산 결과 확인 뒤 `HOLD_RESULT_REVIEW` prerequisite 생성. 원본 PASS로 위조하지 않음 |
| P0 | 기존 runner는 stage의 모든 `case_ids`를 `cache`에 먼저 적재하고, E4에서는 각 case의 `traces` 전체를 `e4_results`에 저장 | 120/240-case 격자·여러 단계 연속 실행 시 메모리 증폭·OOM 위험 | 모든 stage의 원본 CFR case를 1개씩 로드/폐기; CAL 정책검색도 case 단위 처리; E3-03 학습 case도 순차 처리; E4 집계에는 metrics만 보유 |
| P0 | CAL 정책검색이 `cache[cid]` 접근을 전제 | streaming으로 변경할 때 CAL 정책탐색 KeyError 가능 | 27개 고정 CAL 제안을 case 하나에 대해 계산한 후 다음 case로 진행하여 캐시 의존성 제거 |
| P1 | 단계별 실제 case·model·선행 근거 검사가 실행 중 부분적으로 뒤늦게 발생 | 긴 계산 뒤 모델 누락, 잘못된 route/domain/시간축·grid 발견 | `preflight`: approval/manifest/원본/입력/code SHA, stage 순서, 선행 receipt, 모델 세트 F00/F01/F11 및 각 모델 서명, route/bias/channel/noise, E4 120/240 grid, NPZ t/pose_id 검사 |
| P1 | E3-03 route-heldout 학습 데이터는 후반에 fit 오류가 확인될 수 있음 | 이미 훈련기·case 변환 계산을 수행한 뒤 학습 경로 부재로 중단 | TRAIN의 다른 route이면서 같은 bias/channel/noise인 후보 최대 표본수가 최소 요구수보다 적으면 사전 중단. bin별 실제 표본 유효성은 과학 실행에서만 확인 |
| P1 | 실패 시 상위 `ARTIFACT_HASHES.json` 작성 이전에 재예외 | partial 파일의 바이트 추적이 어려움 | 실패 시 `FAILED_PRESERVED` manifest와 기존 파일의 해시목록 작성 |
| P1 | 저장 감사기는 registry의 목록만 검사하고 실행 상태와 미등록 파일 전체성을 확인하지 않음 | 불완전 출력이 잘못된 PASS로 해석될 위험 | 실패·부분 실행은 SHA 검사 후 `HOLD_INCOMPLETE_RUN` 처리; 누락·미등록 파일은 오류 |
| P2 | CLI 예외 처리에서 파일 미존재 등 OSError가 일관된 BLOCKED 형식이 아님 | 사용자에게 불필요한 traceback | 유효성·I/O 예외는 `BLOCKED`와 exit code 2로 표시. 계산 중 예상 못한 예외는 로그 보존 및 예외 출력 유지 |

## 2. 신규 기능

- `src/qclean_uwb/fp_sc/followup/readiness.py`: E1-01 증거 브리지 + preflight
- `scripts/fp_sc_followup.py preflight`: 계산 전 SHA·모델·입력/시간축·격자 검사
- `scripts/fp_sc_followup.py adopt-e1`: 원본 E1 증거를 안전하게 후속 선행증거 형식으로 변환
- `tests/test_fp_sc_manual_readiness.py`: 총 10개의 실행 준비·결정적 gzip 저장·증거 보존 회귀 테스트

기존 `runner.py`, `audit.py`, `RUNBOOK_KO.md`에는 필요한 부분만 국소적으로 수정했다.

## 3. 반드시 유지할 승인 경계

1. E1-01 `numerical_qa_pass`는 E2 정정 성공의 증명이 아니다. 새 `adopt-e1` 결과는 반드시 `HOLD_RESULT_REVIEW`.
2. 후속 단계는 별도 `execute_science=true` 승인 및 정확한 manifest/code/input/environment lock을 요구한다. 승인 템플릿 기본값 `false`는 바꾸지 않았다.
3. 선행 과학 HOLD 이후 탐색적 계산은 명시적인 `exploratory_after_nonpass`에 한정한다.
4. E3 보정 모델의 반례·stratum 부족을 임의의 기본값으로 대체하지 않는다.
5. E4-02 SEALED, E4-03 outer-fold 및 E5-03 외부환경은 각각 별도 노출/정책/데이터 조건을 요구한다.
6. 기존 E0의 원래 R4/R5 제어입력 historical byte-identity 미해결 문제는 그대로 남는다.
7. 실제 5 Hz 실기기 데드라인, RF 물리 예측·선택 수치 개선은 본 코드 감사로 승인하지 않는다.

## 4. 검산 범위·상태

- **확인한 것:** GitHub 커밋 및 22개 원본 변경 파일 목록, 실제 코드 경로의 계약 불일치, 메모리 적재 구조, E2 CAL 캐시 참조, 실패 산출물 검산 조건, source B37 Git blob 고정값.
- **변경한 것:** 상기 로컬 실행 관리 기능과 열 개 합성 회귀 검사의 소스.
- **이번 환경에서 실행하지 않은 것:** 새 regression 10개와 전체 기존 92개에 대한 실제 Python 시험, 720/1440 arm-trajectory, SourceFFD/RF, 로봇/실기기 측정. 테스트 코드의 존재를 `PASS`로 선언하지 않는다.
- **권장 판정:** `STATIC_CODE_AUDIT_AND_PATCH_PUBLISHED / LOCAL_QA_PENDING / SCIENCE_NOT_RUN`. 사용자는 `RUNBOOK_KO.md`의 회귀 명령과 `preflight`를 자기 환경에서 실행해야 한다.

원본 SHA 잠금이 변경되거나 환류 테스트가 실패하면 이번 패치는 준비 완료 상태로 간주하지 않는다.
