# MBVAR-INFO-001 — 구현 제안자 인수 패키지

- 버전: `DRAFT-0.1`, 2026-10-29.
- 상태: **PLAN_ONLY / NOT_PREREGISTERED / NOT_IMPLEMENTED / NOT_AUDITED**.
- 목적: (S0/S1) 합성 통제 환경에서 상관×관측기하의 **상태별 중복정보 기전 검증**, (R) 새로운 Sionna RT 장면에서 물리적 재현, (T) 전이와 진짜 미사용 holdout.
- GitHub 근거: `myoungsunk/sionna-resimulation`, 작업 시 baseline `research/mbvar-e2-e5-revalidation-20261029`의 정확한 commit SHA를 별도 lock. 기존 root `AGENTS.md` sha(blob) `eb0300e84ef43a37297eed74f2e7eb276ee7b5ba`에서 확인. HEAD는 변할 수 있으므로 branch 이름만 provenance로 사용 금지.
- 기존 root `AGENTS.md`는 CP-aware UWB q-clean 관련 규칙이므로 **절대 덮어쓰지 않는다**. `AGENTS_ROOT_APPEND.md`만 끝에 추가하도록 제안한다.
- 아직 `docs/research-governance/`는 확인한 기준 브랜치에 존재하지 않았다. 추가 전 재확인 필요.
- 별도 연구 폴더를 새로 만들며 기존 raw/frozen/results/report/archived 데이터는 변경하지 않는다.

## 추천 적용 순서 — **계획**, GitHub 미반영

1. Governance docs/role/templates/CLAIM_REGISTER와 root AGENTS **append**를 `research/mbvar-info-governance-20261029` (신규 브랜치)에서 review한다.
2. Reviewer가 수학·입력·pose 설계의 미해결 문제를 해결한 후 governance 문서 커밋을 동결. 커밋 전체 40-hex SHA를 `governance_commit`에 기록한다.
3. 그 커밋을 바탕으로 `research/mbvar-info-p0-...`를 만들고 proposer가 **DRAFT 계약(초안 SHA256 기록)**을 P0 사전 검사 목적으로 전달한다. 구현자는 `ROLE=IMPLEMENTER, PHASE=P0_PREFLIGHT, DRAFT_CONTRACT_SHA256=...`로 오직 입력·수학·가시성 검사만 한다. 이 단계에서는 성능 판정/대량 RF 실행 금지.
4. P0 검사가 증거를 만들어 `P0_TO_RESOLVE_*` 항목을 해결하면, proposer가 실행 계약을 **FROZEN**으로 바꾸고 full SHA256을 생성하며 독립 감사자가 사전 수용한다. S0/S1의 과학적 분석은 **그 이후에만** 가능하다. RT 전용 물질·비용 잠금은 별도 `P3_RF_AMENDMENT`를 P3 전에 서명한다.
5. P1/P2/P3/P4/P5/P6 각 단계에서 신규 run, manifest, evidence, reviewer 결과를 남긴 뒤 다음 단계로 진입한다. 소규모 RT canary 및 bulk P4/P5 모두 승인된 수치 예산 내에서만 수행한다.

## 파일별 용도

- `AGENTS_ROOT_APPEND.md`: 루트 AGENTS.md 뒤에 덧붙일 제안 문구. 파일 자체는 설치된 AGENTS.md가 아님.
- `docs/research-governance/COMMON_CONTRACT.md`: 위반시 실패하는 공통 규약.
- `ROLE_PROPOSER.md`, `ROLE_IMPLEMENTER.md`, `ROLE_AUDITOR.md`: 권한/금지/인도물 분리.
- `CLAIM_REGISTER.md`: 과거 E4·E5 및 신규 가설의 허용 표현.
- `templates/experiment-contract.md`, `templates/audit-report.md`: 빈 값 실패형 템플릿.
- `CI_REQUIREMENTS.md`: 기계적으로 검사할 contract와 검사 기준(아직 CI 구현 아님).
- `research/.../MBVAR_CONTROLLED_INFO_20261029/PLAN_P0_P6.md`: 역할별 단계 계획·장면·비용·신규 RF.
- `contracts/EXPERIMENT_CONTRACT_MBVAR-INFO-001.md`: **실험별 단일 실행 계약**. 초안 상태며 run 전에 P0 lock 필수.
- `SCIENCE_SPEC.md`: 수학, 데이터 의미, 오류 모델, 정보량 구현의 명시적 계약.
- `config/PLAN_PARAMETERS.json`: 사전 제안된 숫자 및 실험 조합. **코드가 아닌 제안 설정**; P0 통과 전 실제 실행 계약 불가.
- `config/MANIFEST_SCHEMA.json`: 실행결과의 필수 SHA, 단계, 역할 구분을 강제할 JSON Schema 제안.
- `TASK_HANDOFF.md`: 제안자·구현자·감사자에게 각각 전달할 복사 가능한 지시.

## 현재 출처/기존 실행의 표현 제한

- 2026-10-29 `E4`의 `H_TC=REJECT`는 ‘시간상관이 없다’가 아니라 ‘지정된 모든 경로와 보호 조건에서 시간상관 제거가 공통 해법’이라는 가설 실패.
- 원본 RT는 정적(noise-free) 채널에서 발생한 pose-dependent 구조이며, RF 관측에 **순수 시간 drift**가 실증된 게 아니다. 원시 z와 packet별 μ 및 ε의 pose 반복 불변성은 구분해야 한다.
- 기존 E5 정보행렬에는 정규화/동역학 관련 정정이 있어 과거 수치를 기하 등급 확정 근거로 쓰지 않는다.
- 기존 Corridor/Office O01–O03는 이미 개발에 사용된 사례이므로 독립 최종 시험이 아니다.
- 모든 예시 좌표·패턴·결정 임계치는 **계획 제안값**이며, 실제 장면 충돌/가시성/전력에서 P0/P3 검증 후 동결해야 한다.

## 검수 기준

- 모든 파일 Markdown/JSON 파싱 가능, 내비게이션 파일 경로가 실제 존재할 것.
- 실행 시 `git_sha`, `governance_commit`, `contract_sha256`, `input_lock_sha256`, `scene_hash`, `pose_ledger_sha256`, `solver_config_sha256`, `measurement_extractor_sha256`를 기록.
- 단계 종료 후 상태는 `PASS / FAIL / BLOCKED / NOT_RUN` 중 하나. CI 초록은 과학적 성공을 의미하지 않음.
- proposer-implementer-auditor 3역할의 **문서 분리 ≠ 사람/세션의 독립성**. 독립 감사자 별도 provenance 필요.

## 변경/검증 기록

이 ZIP은 원본 저장소에 push하지 않았고, 새로운 RF 계산이나 필터 실험을 수행하지 않았다. 문서의 placeholder는 빈 칸이 아니라 **단계 실행 전 확인이 필요하다는 명시적 중단 항목**이다.
