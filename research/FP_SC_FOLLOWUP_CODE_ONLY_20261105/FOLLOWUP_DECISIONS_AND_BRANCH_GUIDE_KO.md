# FP-SC 후속 단계 결정 사항과 GitHub 참고 안내

작성일: 2026-11-05 (KST)  
상태: DECISION_SUPPORT_ONLY / MANIFEST_NOT_FROZEN / SCIENCE_NOT_RUN  
코드 기준: [486f0b6c008e7a953ada75a03a941ffa46994985](https://github.com/myoungsunk/sionna-resimulation/commit/486f0b6c008e7a953ada75a03a941ffa46994985)  
범위: 실행 준비에 필요한 결정·증거·참조 위치 정리. 이 문서는 실행 승인서, 새 과학 계약 또는 preflight PASS가 아니다.

## 1. 현재 확인된 상태

- 수정 코드 2건과 테스트 전제 1건이 반영되었고, Windows Python 3.13.15 / NumPy 2.2.4에서 관련 합성 회귀 106개가 통과했다. Linux/WSL 또는 실제 입력 검증을 대체하지 않는다.
- MANIFEST_TEMPLATE.json은 code_files, baseline_sources, input_files, prerequisite_receipts, 모델 잠금이 비어 있고 모든 stage case_ids가 빈 목록이다. 환경 버전은 placeholder, mapping_reviewed는 false이다.
- APPROVAL_TEMPLATE.json은 execute_science=false이며 승인자·발급 시각·manifest/code 잠금 해시·허용 단계가 비어 있다.
- 로컬 E1 생산 8개 파일 및 검산 5개 파일의 등록 해시는 일치했다. 생산·검산은 6,320 waveform / 12,640 packet-mode 행이며 검산 문서의 생산 manifest/index 연결 해시도 일치했다. 이는 새 과학 PASS 또는 독립 ACCEPT가 아니다.
- 확인한 로컬 범위 D:/codex/FP_SC_E1_SNOWBALL_20261105/{repo,source}에서는 후속용 online.npz/evaluator.npz, 루트 FFD bank 2개, 후속 E1 브리지 receipt를 찾지 못했다. 전체 PC·다른 서버에 파일이 없다는 뜻은 아니다.
- 문서 게시에서는 코드·임계값·기존 증거·승인 파일을 변경하지 않고, 실제 preflight·RF·EKF·하드웨어·Actions를 실행하지 않는다.

## 2. 참고 브랜치와 고정 커밋

브랜치 HEAD는 이동할 수 있다. 아래 SHA는 작성 시 원격 확인값이며, 결정 기록에는 실제 사용한 SHA와 파일 해시를 함께 남긴다. 브랜치를 통째로 병합하거나 과거 승인을 재사용하라는 뜻이 아니다.

| ID | 브랜치 / 확인 SHA | 참고 목적과 한계 |
|---|---|---|
| B1 | [audit/fp-sc-e1e5-local-readiness-20261105](https://github.com/myoungsunk/sionna-resimulation/tree/audit/fp-sc-e1e5-local-readiness-20261105) — `486f0b6c008e7a953ada75a03a941ffa46994985` | 후속 실행 준비 코드 기준. readiness.py, contracts.py, runner.py 및 템플릿을 읽는다. 이 문서 커밋 이후에도 코드 기준 SHA는 왼쪽 값이다. |
| B2 | [implement/fp-sc-e1e5-code-only-20261105-chatgpt](https://github.com/myoungsunk/sionna-resimulation/tree/implement/fp-sc-e1e5-code-only-20261105-chatgpt) — `74df3c99e24a2455c430bf099020dad37db65a79` | 보존 원본 및 변경 비교. 실제 후속 준비는 B1 코드로 한다. |
| B3 | [implement/fp-sc-001-e0-20261105](https://github.com/myoungsunk/sionna-resimulation/tree/implement/fp-sc-001-e0-20261105) — `ce4ac73cae7debe3754c7b7b0b0008ca66fdbf5d` | E0 재현 계약, 입력·환경·코드 잠금, controls/noise 계보, proposer 인계. historical byte identity와 기능적 재현을 구별한다. |
| B4 | [implement/fp-sc-001-e1-run-20261105](https://github.com/myoungsunk/sionna-resimulation/tree/implement/fp-sc-001-e1-run-20261105) — `7707db1d69bc60b2c7cba591bac2508b611c64c9` | E1-01 후보 규칙, 분모, 별도 checker 및 실행 잠금의 출처. 후보 가용성은 FP 정정 성공·EKF 개선의 증거가 아니다. |
| B5 | [experiment/predicted-fp-duallp-pilot-20261105](https://github.com/myoungsunk/sionna-resimulation/tree/experiment/predicted-fp-duallp-pilot-20261105) — `c68dcdcdd01180617b827e1f6ebb58e6740a8e29` | 초기 탐색 pilot의 관측 정의·공개 seed10·평가용 LoS 분리·한계를 참고. pilot 정책이나 탐색 분산 바닥을 후속 정책에 자동 이식하지 않는다. |
| B6 | [research/ffd-source-p0p3-20261016](https://github.com/myoungsunk/sionna-resimulation/tree/research/ffd-source-p0p3-20261016) — `4b82e9801a1e065593fdd67a0f3ebd721ba29848` | FFD 소스 계보를 찾을 보조 참조. 이번 작업에서는 브랜치 존재/HEAD만 확인했으며 bank 실물 가용성·내용은 검증하지 않았다. B1 baseline_sources와 대조 후 사용한다. |

바로 읽을 파일:

- B1: [RUNBOOK_KO.md](https://github.com/myoungsunk/sionna-resimulation/blob/486f0b6c008e7a953ada75a03a941ffa46994985/research/FP_SC_FOLLOWUP_CODE_ONLY_20261105/RUNBOOK_KO.md), [MANIFEST_TEMPLATE.json](https://github.com/myoungsunk/sionna-resimulation/blob/486f0b6c008e7a953ada75a03a941ffa46994985/research/FP_SC_FOLLOWUP_CODE_ONLY_20261105/MANIFEST_TEMPLATE.json), [APPROVAL_TEMPLATE.json](https://github.com/myoungsunk/sionna-resimulation/blob/486f0b6c008e7a953ada75a03a941ffa46994985/research/FP_SC_FOLLOWUP_CODE_ONLY_20261105/APPROVAL_TEMPLATE.json), [EXPORT_SPEC_TEMPLATE.json](https://github.com/myoungsunk/sionna-resimulation/blob/486f0b6c008e7a953ada75a03a941ffa46994985/research/FP_SC_FOLLOWUP_CODE_ONLY_20261105/EXPORT_SPEC_TEMPLATE.json).
- B1 실제 검사: [readiness.py](https://github.com/myoungsunk/sionna-resimulation/blob/486f0b6c008e7a953ada75a03a941ffa46994985/src/qclean_uwb/fp_sc/followup/readiness.py), [contracts.py](https://github.com/myoungsunk/sionna-resimulation/blob/486f0b6c008e7a953ada75a03a941ffa46994985/src/qclean_uwb/fp_sc/followup/contracts.py), [runner.py](https://github.com/myoungsunk/sionna-resimulation/blob/486f0b6c008e7a953ada75a03a941ffa46994985/src/qclean_uwb/fp_sc/followup/runner.py).
- B3: [구현자 인계](https://github.com/myoungsunk/sionna-resimulation/blob/ce4ac73cae7debe3754c7b7b0b0008ca66fdbf5d/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_SELECTIVE_CORRECTION_001/PROPOSER_20261105/08_IMPLEMENTER_HANDOFF_KO.md). 같은 PROPOSER_20261105의 실행 계획·초안 계약과 E0_20261105의 잠금 파일을 함께 읽고 초안/실제 실행 증거를 구분한다.
- B4: [E1 README](https://github.com/myoungsunk/sionna-resimulation/blob/7707db1d69bc60b2c7cba591bac2508b611c64c9/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_SELECTIVE_CORRECTION_001/E1_20261105/README_KO.md).
- B5: [pilot 계약](https://github.com/myoungsunk/sionna-resimulation/blob/c68dcdcdd01180617b827e1f6ebb58e6740a8e29/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_PRIOR_PILOT_001/CONTRACT_KO.md).

## 3. 먼저 결정할 공통 사항

| ID | 결정할 질문 | 결정에 필요한 확인 | 반영할 파일/필드 | 참고 |
|---|---|---|---|---|
| D01 | 첫 준비 범위를 E1-02 한 단계로 할지, 어떤 연속 단계까지 할지? | 단계 DAG, 각 단계의 실제 입력·모델 보유 여부, 선행 HOLD 상태. 권장 시작점은 E1-02만의 준비이며 아직 선택/승인된 것은 아니다. | stage_config, 승인 stages / optional_stages | B1, B3 |
| D02 | 어느 호스트·저장소 root·Python/NumPy에서 점검할지? | 수정 소스 전체, baseline source 14개, 실제 payload 접근 가능성. Snowball을 선택할 경우 KMS 계정만 사용. | environment, code_files, baseline_sources, 실행 위치 기록 | B1 |
| D03 | 어느 원본 archive·controls·noise lineage를 사용할지? | 원시 H, pose/time, gyro/odom, original prior/P, means/R, truth, FFD의 실제 바이트. EXACT_ARCHIVE / A2_REMATERIALIZED / NEW_RECIPE_REALIZATION 구분. | 실제 EXPORT_SPEC, 입력 목록·해시·변환 계보 | B3, B4, B5, 보조 B6 |
| D04 | detector-domain mapping과 정책을 어떤 검토 근거로 고정할지? | 원본 거리 convention, mapping uncertainty, signed ratio, 현재 정책의 적용 범위. 숫자를 자동 조정하거나 과거 pilot 값을 대체하지 않는다. | mapping_reviewed, policy, policy_sha256 | B1, B3, B5 |
| D05 | E1의 비-PASS/HOLD 상태에서 탐색적 후속 계산을 허용할지? | E1 생산·별도 검산·실제 관측 gate를 읽고 허용 주장과 중단 지점 결정. 해시 일치만으로 PASS 승격 불가. | E1 bridge, prerequisite_receipts, exploratory_after_nonpass | B1, B4 |
| D06 | 공개/훈련/교정/봉인 데이터의 구획을 어떻게 유지할지? | case별 route/bias/channel/seed/split/noise/corpus/environment, 과거 노출 이력 | cases.metadata, seed_exposure_reviewed 및 근거 | B1, B3 |
| D07 | 누가 어떤 고정 manifest와 단계 범위를 승인할지? | 최종 manifest 바이트와 code lock digest, 현재 사용자 권한 범위 | actor, issued_utc, manifest_sha256, code_lock_sha256, stages | B1 |

선택되지 않은 항목은 미결정으로 둔다. 파일이 없으면 placeholder SHA·가짜 모델·GT bias=0 등으로 채우지 않는다.

## 4. 단계별 추가 결정과 준비 완료 조건

| 단계 | 추가로 결정할 사항 | 필요한 증거/준비물 | 중단·해석 경계 |
|---|---|---|---|
| E1-02 / E1-03 | 평가 case, 원본 clean/noisy 조건 및 stress 범위 | 실제 online/evaluator NPZ, 정확 timeline/pose, 원본 E1 bridge와 해시 잠금 | E1 후보 가용성을 정정 안전성으로 해석하지 않음. SEALED를 개발 단계에 사용하지 않음. |
| E2-01~04 | 고정 정책 평가인지 CAL-only 정책 탐색인지, P/M/history·신뢰도 평가 case | 정책 해시, CAL 구획, 동일 입력의 비교 설계와 판정 기준 | CAL 탐색 승자를 같은 실행에 자동 설치하지 않음. 정상 FP 보호와 rescue를 함께 판단. |
| E3-01/02 | 원래 관측/trace와 비교할 모집단·분해 범위 | archive prior/P, z, means/R, evaluator; 단계별 요구 배열 확인 | 기존 mean/R와 정정 후 관측분포가 같다고 가정하지 않음. |
| E3-03 | calibration_case_ids와 min_samples, target route별 학습 지원 | 다른 route의 동일 bias/channel/noise TRAIN 자료, TRAIN/CAL 구획. 기본 최소수 20을 임의 완화하지 않음. | preflight의 최대 가능 표본수 검사는 실제 stratum 지원이나 모델 적합 성공이 아님. |
| E3-04 | 같은 실행에서 만든 모델 사용인지 기존 모델 재사용인지 | case별 F00/F01/F11, 모델 서명·policy·target route·domain 일치, 원본 one-step trace | 같은 실행의 E3-03 생성 모델을 쓰면 해당 case가 생성 목록에 있어야 함. 그렇지 않으면 models_by_case와 input_files에 잠금. |
| E4-01 | 공개 개발 격자와 시작 상태의 실제 가용성 | R2/R4/R5 × B0/L2 × Full/Native_LoS × seed0~9 = 120 cases, t[0]=0; TRAIN/EXPOSED_DEV | seed10 예시 case 하나로 대체 불가. baseline과 전체 6-arm의 조건 일치 필요. |
| E4-02 | SEALED 노출 허용 및 기존 노출 이력 | 같은 12조건 × seed40~59 = 240 cases, t[0]=0, SEALED, seed_exposure_reviewed | 공개 seed를 봉인 자료로 재명명하지 않음. |
| E4-03 (선택) | 전체 파이프라인 route holdout의 범위 | outer_fold_policies / outer_fold_models_by_case, target route 학습 제외, 정책 SHA와 full_pipeline_holdout_reviewed, 노출 검토 | optional_stages 별도 범위. 일반 모델 재사용만으로 full-pipeline holdout 주장 불가. |
| E5-01/02 | 실제 실행 기기, 5 Hz arrival/sink 조건 및 장애 평가 범위 | 실제 hardware_id, 고정 모델·입력, 지정 기기에서의 실행 계획 | 기기 실행은 별도 승인. 합성 clock/CI 결과로 실기기 deadline PASS 불가. |
| E5-03 (선택) | 새 외부 환경과 개발/평가 domain 구획 | external_environment_contract 잠금, new_data_reviewed, 겹치지 않는 domain IDs, corpus=external | 기존 corridor를 새 환경으로 재명명하지 않음. optional_stages 별도 승인. |

E4의 독립 표본은 센서 seed 반복과 RF/환경 반복을 구별하여 해석한다. 회귀 검사 통과는 E4 성능·공분산 일관성·일반화 채택을 뜻하지 않는다.

## 5. E1 증거 연결과 수정 코드의 추가 요건

현재 확인한 로컬 증거 위치:

`D:/codex/FP_SC_E1_SNOWBALL_20261105/repo/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_SELECTIVE_CORRECTION_001/E1_20261105/RUN_SNOWBALL_20261105_0643/`

- 생산: RUN_001/RUN_MANIFEST.json 및 ARTIFACT_HASHES.json과 등록 payload.
- 별도 검산: REVIEW_001/E1_RESULT_REVIEW.json 및 ARTIFACT_HASHES.json과 등록 payload.
- 실행 root가 달라지면 동일 증거를 새 root 안에서 확보하고 해시를 재확인한다. 이 경로의 로컬 확인을 모든 브랜치/원격 위치의 가용성으로 확대하지 않는다.
- adopt-e1 결과는 HOLD_RESULT_REVIEW이다. 브리지와 source_files 4개 문서를 input_files에 잠그고 E1-01 prerequisite으로 연결해야 한다.
- 수정 코드에서는 production/review index의 실제 payload도 다시 검증한다. index JSON만 옮기면 충분하지 않다.
- 같은 호출에서 새로 실행하는 선행 단계는 HOLD receipt를 만든다. 다음 단계로 이어갈 때 필요한 exploratory_after_nonpass 승인을 미리 명시해야 한다. 과거 PASS receipt가 있더라도 새 실행의 HOLD를 대신할 수 없다.

## 6. 준비 순서와 승인 경계

1. D01~D07 중 첫 준비 범위에 필요한 항목을 결정 기록으로 확정한다.
2. 수정 커밋의 실행 root를 준비하고 baseline source 14개, 실제 FFD bank 2개 및 선택 case의 원본 payload를 읽기 전용으로 확인한다.
3. 실제 archive 변환 규격을 작성·검토한다. 형식 변환을 수행하려면 그 작업 범위에서 원본을 보존하고 새 출력 경로를 사용한다. 이 문서 작성에서는 변환하지 않았다.
4. E1 bridge 및 단계에 필요한 모델·외부 계약을 연결한다. 새 모델 학습은 준비 문서 작업에 포함하지 않는다.
5. 실제 입력·소스·코드 해시와 환경 버전을 담은 별도 실행 manifest를 완성하고 SHA256을 고정한다. base_sha의 역사적 기준값을 새 실행 코드 SHA와 혼동하지 않는다. 실행 코드 기준은 486f0b6c008e7a953ada75a03a941ffa46994985와 실제 code_files 해시로 명시한다.
6. 승인자는 완성된 manifest와 코드 잠금에 결속하여 단계·HOLD 이후 탐색 범위·optional 범위를 정한다. 현재 false인 승인 템플릿을 자동으로 true로 바꾸지 않는다.
7. 권한과 입력이 충족된 후에만 실제 preflight를 실행한다. 성공해도 결과는 PASS_LOCAL_PREFLIGHT_NO_SCIENCE이며 run은 별도 범위이다.

**현재 CLI의 제약:** preflight도 authorize()를 공유하여 execute_science=true를 요구한다. 따라서 “preflight만 확인” 요청으로 과학 실행 권한을 만들어서는 안 된다. preflight-only 승인 방식을 별도로 설계할지, 실제 실행 승인에 결속한 기존 CLI를 사용할지는 미결정이다. 이 문서는 승인 로직을 변경하거나 우회하지 않는다.

## 7. 다음 담당자가 남길 결과

- 결정 ID별 선택값·근거 문서·고정 SHA·미결정 항목.
- case와 입력별 실제 경로/크기/SHA256/shape/dtype/pose-time 정합·계보 목록.
- 완성 manifest 경로와 해시, 승인 파일의 실제 범위와 유효 필드.
- preflight를 수행했다면 명령·환경·종료 코드·상태·검사 범위. 아직 수행하지 않았다면 NOT_RUN.
- 과학 실행, 감사 완료, 결함 수정, 재검증, 채택을 각각 구별한다.

게시 범위는 이 문서 1개이다. 원본 브랜치·과학 증거·코드·승인 템플릿을 보존한다.
