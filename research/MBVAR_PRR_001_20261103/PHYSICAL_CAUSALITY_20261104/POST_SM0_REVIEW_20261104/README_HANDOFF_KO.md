# READ ME — PRR RT SM0 성공 이후 실험 설계·요청

**제출일:** 2026-11-04 · **역할:** USER_AUTHORIZED_NONINDEPENDENT / PROPOSER

## 2026-11-05 통합 서버 데이터 수집 요청 — 최신 실행 원장

[ONE_SHOT_SIMULATION_DATA_EXTRACTION_REQUEST_KO.md](ONE_SHOT_SIMULATION_DATA_EXTRACTION_REQUEST_KO.md) — 중간 과학 분석 없이 원래 6면 복도 Full/LoS와 PR #35 고정 yaw의 남은 원시자료만 한 번의 서버 세션에 수집하는 최신 실행 요청서.

- [ONE_SHOT_RT_EXTRACTION_LEDGER_20261105.csv](ONE_SHOT_RT_EXTRACTION_LEDGER_20261105.csv): 정확히 400개 실행 task_id. R2/R4/R5 190개 고유 복도 pose × Full/LoS = 380, PR #35 G3 20개 yaw = 20.
- [ONE_SHOT_RT_EXTRACTION_PLAN_20261105.json](ONE_SHOT_RT_EXTRACTION_PLAN_20261105.json): 기존 raw 제외 전 최대 102,860 PathSolver 호출(1028+B1 6682+SM1 89950+G3 5200), 원본/scene 분리 및 계산 예산/중단 조건.
- [ONE_SHOT_RT_KEY_LEDGER_QA_RECEIPT_20261105.json](ONE_SHOT_RT_KEY_LEDGER_QA_RECEIPT_20261105.json): GitHub Actions #41947190271 원본 3개 Tnone과 PR #35 G3 PLAN/GO 비교, 400개/102,860회 read-only PASS. Sionna RT 호출 0회.

**이 최신 요청은 단계별 실행을 기다리며 서버를 여러 번 사용하는 대신, 전체 원본 키를 사전에 확정해 중복 없이 일괄 *데이터 생성*하는 방식이다.** 과학적 분석 순서는 아래 기존 설계가 유효하다. PR #35의 R4_168 G2 4 yaw는 이미 DATA ACCEPT이므로 다시 생성하지 않는다. G3 20 yaw는 실행 승인 문서가 있지만 이 요청에서 원본 로컬/원격 SHA를 확인하기 전에는 완료라고 단정하지 않는다.

## 판정

- PR #33 @ e69fcdd: C00 8/8 PASS, C01/C10/C11 24/24 PASS, 16 pose-scene 구성의 2회 반복 complex H 해시 일치, 8,224 native PathSolver calls 성공.
- [원본 보존 자료](../NEW_RT_DATA/SM0_GITHUB_ONEBIN/snowball_20261104/): 성공 151 파일, 이전 실패 19 파일, 원본 실패 별도 압축본.
- [Read-only GitHub Actions #41815490532](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41815490532): 원본 raw tar와 151+19 파일 SHA/32 H·ray closure, repeated H, original archive LoS, FP/r/s 대조 PASS. 현 실행에서 Sionna RT 추가 호출 0.
- 기술 판정은 ACCEPT_WITH_BOUNDARIES. 새 SM0 통제 장면 4 pose가 원본 6면 corridor의 경로별 원인, 시간 상관 또는 EKF 과신을 증명하지 않는다.

## 문서 읽는 순서

1. [RT_NEXT_PHASE_SCIENCE_DESIGN_KO.md](RT_NEXT_PHASE_SCIENCE_DESIGN_KO.md) — 원본 진단 질문, 긍정/음성 대조, R0/SM0-B/SM1/SM2 및 C1/C2 순서, 주장 한계.
2. [SIMULATION_REQUEST_SM0B_SM1_SM2_KO.md](SIMULATION_REQUEST_SM0B_SM1_SM2_KO.md) — Snowball/Codex가 바로 복사해 실행계획을 만들 수 있는 source hash, 고정 pose, raw 산출물, numeric QA, 예산 및 fail-closed 지시.
3. [NEXT_RT_PHASE_CONTRACT_DRAFT_20261104.json](NEXT_RT_PHASE_CONTRACT_DRAFT_20261104.json) — 기계 판독용 6개 단계, 원본 bank/source SHA, 15 pose 원장, 수치 QA, 신규 호출 예산(현재 승인=0).
4. [verify_snowball_evidence.py](verify_snowball_evidence.py) — 읽기 전용 독립 byte/복소 H·path·FFT 수치 재검산 코드. 생산 RT solver import·호출 없음.
5. [POST_SM0_EVIDENCE_VERIFICATION_RECEIPT_20261104.json](POST_SM0_EVIDENCE_VERIFICATION_RECEIPT_20261104.json) — 통과한 GitHub Actions의 실제 151+19 SHA 및 32 H/ray 검증 결과를 영구 기록한 JSON.

## 다음 작업의 정확한 우선순위

**R0 (0 new RT calls)**: 이미 성공한 32개 raw H와 경로를 재사용하여 C10/C11 각각에서 C01 FLOOR를 뺀 효과를 분석. 194/234 양성, 500/525 무효과를 모두 포함.

**SM0-B0 (신규 RT 1,028 calls — 별도 승인 필요)**: 원래 R4-B pose194/234의 진짜 6면 scene Full/LoS + per-ray 원본 archive 재현. 두 pose PASS 이후에만 SM0-B1을 확대.

**SM0-B1 (6,682 calls)**: 원래 R2/R4/R5 고정 15 pose에서 나머지 13개 원본 ray metadata. 전체 7,710 calls; 추가 반복은 별도 승인.

**SM1 (calls TBD)**: R4 33.0–35.2초, R5 195–198초의 timestamp/pose_ID ledger를 원본에서 생성하고 원래 ray를 시간 순서로 연결. 5초 평균은 1m 이동을 포함할 수 있으므로 현재 위치의 RF 인과 지표로 사용 금지.

**SM2a (≤2,570 calls)**: R4 pose168에서 *같은 XY* 5 yaw×Full/LoS, Collision/scene/source parity 선행.

**C1/C2 (0 RT)**: 기존 저장된 Full/LoS와 동일 EKF prior/gain/gate, 자연 재귀 history를 사용한 거리 vs 편파 오염 기전 분석. 새 필터 성능 채택은 이 요청 범위가 아님.

모든 새 RT 호출은 사용자 명시 self-approval 수치 계약이 필요하며, 기존 HOLDOUT2, DEV3 C3/G5, 과거 S0/S1–S3 실패 기록을 변조하지 않는다. 사후 선택 hotspot이며 독립 과학 검증으로 표기하지 않는다.
