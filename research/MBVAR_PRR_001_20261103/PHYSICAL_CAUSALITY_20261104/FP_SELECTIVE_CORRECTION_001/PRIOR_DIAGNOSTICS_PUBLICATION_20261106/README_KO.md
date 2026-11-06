# prior 분석·진단 게시 묶음

2026-11-06 KST. 기준 94b49a5abe8443b8eacf4a1e3600ad3d52b10e9f 이후의 로컬 분석·코드·계약·결과·검산·그림을 추가 게시한다.
기존 문서의 '로컬 저장/푸시 미수행'은 각 실행 당시 기록이다. 그 문구와 동결 결과를 소급 수정하지 않는다.

| 작업 | 결과/설계 | 증거 |
|---|---|---|
| 정보 출처·시간·독립성 | [Stage1](../PRIOR_PROVIDER_STAGE1_20261106/RESULTS_KO.md) | LINEAGE_CHECK.json, 재현 스크립트, 해시 |
| 개입·분할 설계 | [Stage2](../PRIOR_PROVIDER_STAGE2_20261106/DESIGN_KO.md) | DESIGN_MANIFEST.json, DESIGN_CHECK.json |
| 동적 근거 개입·별도 C-only | [결과](../PRIOR_EVIDENCE_R2_20261106/RESULTS_KO.md) | [계약](../PRIOR_EVIDENCE_R2_20261106/CONTRACT_KO.md), [C-only 계약](../PRIOR_EVIDENCE_R2_20261106/C_ONLY_CONTRACT_KO.md), RUN_001, HISTORY_001, CHECK_001.json |
| provider 적용 범위·수용 제안 | [활성화 구조](../PRIOR_EVIDENCE_R2_20261106/PROVIDER_ACTIVATION_CONTRACT_KO.md), [코드 기준 제안](../PRIOR_EVIDENCE_R2_20261106/PROVIDER_ACCEPTANCE_PROPOSAL_KO.md) | 1%·10%는 과거 제안 예시이며 채택·동결하지 않음 |
| P/M 입력 오차 민감도 | [결과](../PM_INPUT_SENSITIVITY_R1_20261106/RESULTS_KO.md), [그림](../PM_INPUT_SENSITIVITY_R1_20261106/SENSITIVITY.png) | [계약](../PM_INPUT_SENSITIVITY_R1_20261106/CONTRACT_KO.md), RUN_001, [검산](../PM_INPUT_SENSITIVITY_R1_20261106/CHECK_001/CHECK.json), POOLED.csv, SVG |

## 현재 판정

- prior 출처 점검 완료. 독립 절대 위치/Heading 근거 및 provider VALID 정당성은 미확보.
- 동적6,272×277=1,737,344행의 근거 개입 및 이력 보호68,992회 검사 완료.
- 별도 C-only6,320파형: 고정임계값2에서 오류1,015건 탐지0, 정상5,305건 오탐0. 탐지 실패를 보존.
- P/M 입력 민감도: 동적6,272×64×4=1,605,632행. 점수·가상flag·구간·집계 전수 자체검산 완료.
- 무개입 가상 P/M/PM 탐지25/22/35건, M/PM 오탐4건. 실제 provider 활성화나 E1-02 결과가 아님.
- 기존 E1 실패와 mapping 배제11,095건, VAB 주안 유지. VALID 강제 생성0, 선택tap=raw 유지.
- E1-02 및 E2 미실행. 권한·HOLD·생산 정책을 변경하지 않음. 독립 감사나 과학적 채택으로 승격하지 않음.
- 최신 범위는 static48을 prior 개입에서 제외하고 별도 C-only에 유지한다. 과거 Stage2의 static 계약대조 계획과 구별한다.

## 코드와 재현 범위

새 코드: scripts/run_fp_sc_evidence_r2.py, check_fp_sc_evidence_history_r2.py, verify_fp_sc_evidence_r2.py,
run_fp_sc_pm_sensitivity.py, check_fp_sc_pm_sensitivity.py, report_fp_sc_pm_sensitivity.py,
src/qclean_uwb/fp_sc/followup/input_sensitivity.py, tests/test_fp_sc_input_sensitivity.py.
Stage1의 inspect_lineage.py도 해당 결과 폴더에 포함한다.

실행 당시 code/input/contract SHA 및 명령은 각 RUN_RECEIPT/START/CHECK에 남아 있다.
이 묶음은 분석 산출물과 그 구현을 게시한다. 기존 대형 RF bank와 canonical 입력 payload를 중복 업로드하지 않는다.
새 checkout에서 재실행하려면 기존 manifest가 지시한 입력 payload를 별도로 확보하고 해시를 맞춰야 한다.
새 실험이나 재실행을 게시 작업의 일부로 수행하지 않는다.

PUBLICATION_MANIFEST.json은 이 게시에서 추가한 기존 분석·코드 파일의 SHA/크기를 기록한다.
과거 ARTIFACT_HASHES 이후 추가된 제안서도 이 게시 manifest에서 별도로 포함한다. 이전 해시 목록은 덮어쓰지 않는다.
