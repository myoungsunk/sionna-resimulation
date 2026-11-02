# A010 독립 사전 감사 인계서 — 새 K1/K2 두 runner 검증

**제출 역할: IMPLEMENTER. 이 문서는 독립 감사 서명이 아닙니다.**

## 원문 자료

- 기준 수정 구현 `implement/mbvar-info-a010-d2-d3-d4-d6-20261102`, Git SHA `2bc262715ccf51ae0212af988e5a1973478c8540`
- 기존 C3 `40992589158` FAIL, C3V4 `41005158792` FAIL, A010-P0 forensic 수치 검증 범위 기존 DEV2 4 keys
- 새로운 evidence workflow `.github/workflows/mbvar-a010-two-runner-prefreeze-20261102.yml`
- 재생/비교 소스 `code/a10_cross_runner_replay.py`, 음성 시험 `tests/test_a10_two_runner_protocol.py`

## 1차 독립 감사 체크리스트

1. Source/Contract: frozen A008/A009/A010-P0, original experiment contract, RUN_REQUEST, `contract_lock.py` Git blob SHA unchanged; no non-DRAFT AMENDMENT-010.
2. Frozen input: GEN manifest, canonical ZIP, array ledger, factor and recorded code source hashes recheck. Both jobs must be same current code/manifest/input SHA.
3. Runner separation: compare job IDs, runner names, Linux boot UUIDs, CPU/BLAS/platform. Same CPU architecture is allowed but **two VM jobs** must be independently executed.
4. Math: independently reconstruct original pair's 4x4 C10, check symmetry/SPD, normalized full upper-10, NEES and angle wrap, and raw optimizer objective from source code (do not blindly trust helper).
5. Mode: evaluate the truth-free starts; truth-start/oracle only for diagnostic scoring, not source estimator or mode choice. No claim that 9 starts exhaust global modes.
6. Gate scope: 2 archived DEV2 keys versus 1,080 expected future full rows; report scientific limitations and reject any A010 science PASS from two-key proof.
7. Data partition: entire historical S_field preserved, only DEV3 added in an un-applied DRAFT; no held-out results accessed.
8. Replay source and artifacts: use independent calculator, download raw artifact hashes and attach an audit verdict with actor/session, separate implementation identity.

## Required verdict

`ACCEPT_WITH_BOUNDARIES`, `REVISION_REQUIRED`, `REDESIGN_REQUIRED`, or `BLOCKED_EVIDENCE` under ROLE_AUDITOR. No provisional implementer signature may substitute for this.

**Current signature:** `INDEPENDENT_AUDITOR_SIGNED=false`; `A010=SCIENCE_DRAFT`, `DEV3/HOLDOUT2/RT=NO-GO`.