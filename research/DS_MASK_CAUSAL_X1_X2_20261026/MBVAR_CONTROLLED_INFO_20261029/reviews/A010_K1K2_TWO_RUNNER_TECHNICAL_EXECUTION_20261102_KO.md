# MBVAR-INFO-001 — A010 DEV2 K1/K2 두 runner 기술 재현 결과 (2026-11-02)

**판정: `K1_K2_TWO_RUNNER_TECHNICAL_REPLAY_PASS / A010_SCIENCE_DRAFT / INDEPENDENT_AUDIT_PENDING`.**
**역할 `IMPLEMENTER`, 이 문서는 감사자 독립 서명이 아닙니다. DEV3/HOLDOUT2/RT: NO-GO.**

## 1. 소스와 실행 증거

- 기술 CI [#41453446631](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41453446631): 모든 4개 job 성공 (prefreeze-guard, replay a, replay b, paired-check).
- **실행에 사용한 immutable source Git SHA:** `4dece4c63ef62e046366e6c062f63a21ad89e05f`; 이후 보고서용 commit이 추가돼도 이 실행 SHA를 변경해 기록하지 않습니다.
- Frozen scientific experiment contract SHA256: `68d73bd22bf467625559f3092433f250cbe91cb2fef011f92151975975b00f34` (변경 없음).
- 원본 A010-P0 DEV2 canonical zip SHA256: `316efcc04946197cbb5c10417e3b6bfca3e4e8f5e4d3433535dfbba09b7bb9f3`.
- 원본 GEN MANIFEST SHA256: `f031c293796906f0087d6c6b72c7099b27bd6d4fdb9b59135cacd459407fb516`.
- 원본 RUN_REQUEST / contract_lock / A008 / A009 / A010-P0 / A010 DRAFT 등 7개 보호 Git blob 일치.
- 새 소스·계약 사전시험: 22 passed; DEV3·HOLDOUT2·reserve 입력 생성, 판정, RT 실행 0건.

## 2. 동일 입력의 정확한 두 runner 결과

| Case | Runner A objective χ² | Runner B objective χ² | Class v3.1 | Truth-free near alternatives |
|---|---:|---:|---|---:|
| K1 | 107.64949922627513 | 107.64949922627453 | LOCAL_MIN_CERTIFIED | 0 / 0 |
| K2 | 121.78148729702882 | 121.78148729702819 | CONVERGED_SMOOTH | 5 / 5 |

- 두 case 모두 objective cost 차이는 1e-12보다 작음. 최종 비교 job `numerical.n_rows=2`, `n_fail=0`, `pass_=true`.
- 동일 source_git_sha·원본 manifest·ZIP·array ledger 및 per-case input SHA. Linux boot UUID 서로 다름.
- `same_best_start=true`, `same_class=true`, `same_mode_starts=true`, full C10 10개 상삼각·SPD·자연 state SD 정규화·log10 condition·NEES4의 동결 전 공학적 허용오차 내 일치.
- `source_code_sha256` 딕셔너리(코드·테스트·감사 Python 파일)도 두 runner가 동일.
- **주의:** 서로 다른 hosted VM으로 실행되었지만 CPU *모델*이 서로 다르다는 증거는 아님. 독립 감독자가 계산한 결과도 아님.

## 3. 원본 증거 및 byte 해시

- [Runner A 원본 artifact](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41453446631/artifacts/13146625587) / 수집된 receipt SHA256: `e53a2f75b5cd6f14be9b1d544ba7243bcdb5a3507bb145f53d892ccb4f987cfa`
- [Runner B 원본 artifact](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41453446631/artifacts/13146352094) / 수집된 receipt SHA256: `88b6e4ee8558ebcc4675ebbf981cc670a82b6550af0b962ea77fe41911e6cbc3`
- [두 실행의 비교 artifact](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41453446631/artifacts/13146137245) / `TWO_RUNNER_COMPARISON.json`: `status=TECHNICAL_REPLAY_PASS`; `distinct_linux_boot_ids=true`.
- Receipt SHA 값은 비교 job이 각 `REPLAY_RECEIPT.json` 원본 파일에 계산한 해시로서 artifact ZIP의 해시를 뜻하지 않는다.

## 4. K2 해석 한계

기존 DEV2 K2는 비용이 거의 같은 truth-free 근접 대안해 5개를 서로 다른 두 runner에서 동일하게 보고했다. 따라서 **재현성 PASS ≠ 상태 MAP 해의 유일성**이다. 이 값은 사전에 알려진 forensic DEV2 key에 관한 재현·식별성 증거이며 새로운 DEV3 가설 지지를 뜻하지 않는다.

## 5. 남은 사전 동결 블로커

1. **독립 감사자 미서명:** 다른 actor/session에서 raw artifact를 직접 받아 hash/수학·코드·gate-ID·split·통계 경계를 독립 검증해야 함.
2. **과학 계약 DRAFT:** main AMENDMENT-010에 최종 전체 lock/code hash 및 proposer+auditor 승인이 아직 없음.
3. **DEV3 전체 SOLVER_REPRO 미완료:** K1/K2 두 DEV2 key 교차 runner 성공만으로 C3V5의 전체 G5_NUMERIC_REPLAY `SOLVER_REPRO`를 PASS로 바꾸지 않음.
4. **K2 mode 민감도:** 근접 대안해 대체가 field-paired state error, MSE, posterior C10, NEES 및 H-tests 주장 방향에 미치는 영향 독립 검토 필요.
5. **DEV3 20–29·HOLDOUT2·RT:** 여전히 실행 금지. 사용자·제안자·독립 감사자의 후속 별도 서명 필요.

**IMPLEMENTER 판정:** 기술적으로 `ACCEPT_FOR_INDEPENDENT_AUDIT_REQUEST` (과학적 `SUPPORTED`/`SCIENCE_PASS` 아님).