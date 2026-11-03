# MBVAR-INFO-001 / A010 — R5 최종 제안자 결정과 R6 산술 재검산 결과

**실행일:** 2026-11-03 · 역할 PROPOSER(계약 선택)/IMPLEMENTER(자료 제출) · **독립 감사자 아님**.

## R5 — 과학 설계 결정 확정

- 최종 제안자 결정 원문: `contracts/AMENDMENT-010-R5-PROPOSER-DECISION-FINAL-PREFREEZE-20261103.md`.
- 기계 판독형 수치 계약: `contracts/AMENDMENT-010-R5-PROPOSER-SPEC-V1.json`. 기존 F2 χ² `1e−3`, 최대 30단계, 기존 E′ 운영 추정기 유지, 9개 진단 start 고정, 공통 probe를 통한 같은 최종 정밀도 확인, 인증 불충분은 `UNRESOLVED_PRECISION`.
- 동일 start에서 나온 근접 대안 5개를 서로 다른 해/극솟값 5개로 호칭하지 않음. Clustering으로 물리 모드 수를 결정하지 않으며 진단 출발점 수와 field별 민감도만 보고.
- H/CAL 모든 유효 row 유지. 사전 선택된 field-block bootstrap B=4000/seed=20261029 및 지지/CI 방향 변화에 따른 sensitivity gate 동결. **메인 AMENDMENT-010은 여전히 DRAFT.**

## R6 — 기존 열린 자료의 helper-free SHA·수학 산술 검증 완료

- 검증 workflow: https://github.com/myoungsunk/sionna-resimulation/actions/runs/41586097494
- SHA: `9658ab900c128777a7ba938f6027572647d29d89`, status success; raw evidence: https://github.com/myoungsunk/sionna-resimulation/actions/runs/41586097494/artifacts/13207593389
- 체크아웃 코드(별도 standalone script): `audit/a010_r6_standalone_artifact_audit.py`; 생산 `a10_validation.py`, `c3v5.py`, `s1v5.py`의 수학 helper를 불러오지 않음.
- archived A010-P0 DEV2 canonical arrays 48개 dtype·shape·C-bytes SHA가 원본 manifest/ledger와 일치.
- S1V5 SMOKE 900/901 총 256개 배열, ZIP artifact 자체 SHA256 및 per-field ZIP SHA, per-array dtype/shape/bytes SHA 재검산 PASS.
- 실제 C3V5 optimizer boundary input hash 7배열×10행을 ZIP 원본 bytes에서 별도 구성: 10/10 일치.
- 저장된 4×4 C10 10행을 직접 Cholesky/SPD/자연척도 공분산 비교하고 `Xtrue`·앵커 회전으로 NEES4 재계산: 최대 절대 차이 `5.03774799653911e-11`.
- S1V5 vs C3V5 동일 10행의 cost·최종상태·전체 C10 저장 수치 차이는 0.
- C3V5 전체 72등록행 중 10행(누락 62)이므로 `G5_NUMERIC_REPLAY=FAIL`, A010 scientific PASS 및 full test로 승격 불가.
- 새 SHA에서 두 VM로 DEV2 K1/K2를 재생한 ZIP A/B를 직접 내려받아 원본 sha 검산·두 boot ID 차이, state/cost/full C10, NEES 검산. K1 cost diff 5.97e−13, C10 normalized diff 7.86e−14; K2 cost diff 6.25e−13, C10 normalized diff 1.17e−13.
- 원본 ZIP을 1바이트 변형한 음성 시험에서는 `ERR_R6_OUTER_ARTIFACT_SHA`가 발생해 fail-closed 동작을 확인.

## 증거 고정

| 객체 | SHA256 |
|---|---|
| R1–R4 SMOKE raw artifact ZIP | `e227582fb99e26e8d943404b409d33b37a72acaba8ee757443ccff141f9b239b` |
| DEV2 runner A ZIP | `3eaddbed37eddbe13572b74925ff67057fb0490e5dbd403d9370d666242b2fcc` |
| DEV2 runner B ZIP | `0ba7f8ed0b7d9a0ebd5ad14fd7c327337b2ad77f086a845cc77e1f85cecdc98c` |
| A010-P0 canonical input ZIP | `316efcc04946197cbb5c10417e3b6bfca3e4e8f5e4d3433535dfbba09b7bb9f3` |
| GEN manifest | `f031c293796906f0087d6c6b72c7099b27bd6d4fdb9b59135cacd459407fb516` |

## R6 완료 범위와 미완료 승인

**완료:** 기존 공개 가능 SMOKE·DEV2 증거의 전체 원본 배열 SHA 검산, optimizer input digest, 저장 C10 SPD·NEES 독립 산술, 2-runner 수치 일치 확인, 음성 해시 거부, 원본 FAIL 보존.

**완료로 주장하지 않음:** 비선형 MAP optimizer 전체를 타 구현으로 재실행하여 원래 Jacobian/Hessian에서 C10을 재도출하는 증명, DEV3 전체 1,080행 재생, R5 공통 precision 인증이 실제 전 행에서 통과했는지의 검증, 별도 독립 감사자의 서명. 따라서 R6 evidence-preparation은 완료됐지만 정식 `INDEPENDENT_AUDITOR_SIGNED=false`, `A010_SCIENCE_FROZEN=false`.

`PROPOSER_R5_DECISION_FINAL=true`; `R6_ARITHMETIC_EVIDENCE_PASS=true`; `R6_INDEPENDENT_AUDIT_SIGNED=false`; `DEV3/HOLDOUT2/RT=NO-GO`.
