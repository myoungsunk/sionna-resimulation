# POWER_JOINT — 최종 연구 검증 실행 전 패키지 (2026-10-16)

**PLAN FROZEN, NUMERIC EXPERIMENTS NOT RUN IN THIS BRANCH.** 다음 사용자 요청이 실행 지시일 때만 F0–F7 단계별 실제 수치 실험을 시작한다. 기존 원본 Joint4/S4/SR4/DR4/POWER_JOINT, FFD LUT, 이전 결과와 각 실패 감사 결과를 변경하지 않는다.

## 문서 탐색

| 파일 | 내용 |
|---|---|
| [00_MASTER_PLAN_KO.md](00_MASTER_PLAN_KO.md) | 연구 목표, 이미 닫힌 실험, 마지막 F0–F7 목록·시작 조건 |
| [01_HYPOTHESIS_LEDGER_KO.md](01_HYPOTHESIS_LEDGER_KO.md) | 12개 기존 확정/반증 사실 + 14개 검증 가능한 가설/반례/논문 주장 범위 |
| [02_EXPERIMENT_PROTOCOL_KO.md](02_EXPERIMENT_PROTOCOL_KO.md) | F0–F7 구현 근거, 비교군, 수식, 데이터 입출력, 반증 기준, PASS/FAIL |
| [03_CODE_AUDIT_CONTRACT_KO.md](03_CODE_AUDIT_CONTRACT_KO.md) | 원본 코드 Git blob/아카이브 SHA, clean module architecture, 수학·누수·일관성 테스트 |
| [04_SIMULATION_REQUEST_SPEC_KO.md](04_SIMULATION_REQUEST_SPEC_KO.md) | 원 FFD bank, R4/R5 시각 동기 입력, 독립 Sionna Full/LoS 장면 상세 사양 |
| [05_PAPER_STORY_KO.md](05_PAPER_STORY_KO.md) | 논문 스토리·제목·Claim Boundary, Figure/Table 구성, 외부 연구 근거 |
| [06_EXECUTION_RUNBOOK_KO.md](06_EXECUTION_RUNBOOK_KO.md) | G0→F0–F7 dependency DAG, 분기/중단/독립 재감사/최종 결과 보고서 |
| [07_EXPERIMENT_MANIFEST.json](07_EXPERIMENT_MANIFEST.json) | 기계 판독형 experiment IDs, 의존성, 입력 차단, 고정 원본 해시 |
| [08_VALIDATE_PLAN.py](08_VALIDATE_PLAN.py) | **문서/Manifest/소스 존재 조건 검사만 수행**, RF 연구 수치 미실행 |

## 핵심 결정

- 원래 POWER_JOINT는 *single-corridor empirical correction baseline*으로 보존.
- 새로운 모델은 원 FFD/LUT 극점 물리/보간 정합을 검증하고 변경 레이블을 다시 학습한 뒤에만 과학적 채택 가능.
- Native LoS Full-trained POWER 오보정은 기존 직접 재귀로 이미 확인된 실패. 새 방법의 가장 중요한 no-harm guard.
- \(C_{rs}\)의 Mount0/Mount45 이득 역전, Exp3 GT-only oracle의 전체 NEES 미정상화, Q4-R Prior \(P^-\) inflation 부작용은 숨기지 않고 모두 본문/부록 데이터에 포함.
- 독립 새 ray-traced Full RF 장면 없는 한 generalized/covariance-consistent Bayesian filter라는 주장 불가.
- SIM-A(원래 복소 FFD bank)와 SIM-C(새 독립 Full/Native LoS scene)는 최종 외부 검증의 **필수** 입력. SIM-B(R4/R5의 과거 실제 Gyro/Wheel 타임라인)는 archival R4/R5 재귀를 주장하려는 경우에만 필수이며, 새 완전한 SIM-C 장면에는 신규 time/controls가 있으므로 SIM-B가 없어도 독립 일반화 실험은 가능.

## Static preflight (NO numerical experiment)

~~~bash
python3 research/POWERJOINT_FINAL_20261016/08_VALIDATE_PLAN.py
~~~

Expected output: PLAN_CONTRACT PASS; F0/F6 input blockers explicitly remain; some R2 exploratory source-frozen pilots can be started on next execution instruction.

Scientific execution requires a **separate branch** and an explicit user instruction. See 06_EXECUTION_RUNBOOK_KO.md. All original J4/S4/SR4 baseline files remain untouched.
