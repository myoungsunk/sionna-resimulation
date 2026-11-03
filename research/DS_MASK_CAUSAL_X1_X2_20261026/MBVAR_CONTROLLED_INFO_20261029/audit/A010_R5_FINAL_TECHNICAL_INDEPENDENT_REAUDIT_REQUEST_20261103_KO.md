# MBVAR-INFO-001 — R5 구현 완료 후보 / 독립 최종 재감사 정식 요청

**구분:** 독립 감사 요청서. 제출자는 IMPLEMENTER이며 감사자 승인 문서가 아님. **제안자 계약은 FINAL_PRE_FREEZE, A010 과학 계약은 DRAFT.**

## 고정 대상

- 대상 [Draft PR #18](https://github.com/myoungsunk/sionna-resimulation/pull/18). 기준 수정 운영 코드 SHA `de8b1f6c10a996afbf29d77daab97cc40f409a86`. 그 다음 SHA `0d840d12ab3c508d2fe3b5ce6a0a505f2d1e6ca2`는 `tests/test_a10_r5.py` 음성 검증만 추가. 이후에는 workflow와 감사 문서만 변경.
- 실제 통합 성공 [Actions #41596817031](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41596817031), artifact `13212989547`.
- 추가 음성/CSV 시험 [Actions #41596880906](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41596880906) / [CSV 100개 검증 #41597420058](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41597420058).
- DEV2 K1/K2 [#41593156279](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41593156279). K2의 5개 near-start를 5개 distinct minima로 바꾸어 쓰지 말 것.

## 독립 감사 필수 검사

1. R5 proposer JSON numeric policy와 `a10_r5.py`, `c3v5.py` 수정 코드를 Git SHA로 직접 검증. 운영 E′ 경로 `s1v5.py` blob이 변하지 않았는지 독립 대조.
2. 실제 C3 row마다 정확히 E′+9 truth-free starts 10개씩, 100개 CSV terminal key unique, source/policy SHA, final cost/state, F2 cap/steps, common `R5_CERT` probe descent를 원본 artifact로 검증.
3. CSV roundtrip `end_state` (length 4 JSON), `polish_hit_cap` (bool vs text) 타입을 직접 변형해 정상/오염 판정 비교. NaN/Inf, missing/duplicate start, 1-ULP SHA, probe descent, cap 우회 여부 검사.
4. K1/K2 archived DEV2 원본 SHA를 재검산하고 새 R5 인증 결과 10/10 해에 대해 초과 하강·cap 유무 확인. K2의 mode ambiguity를 과학적 유일 MAP 승인으로 취급하지 말 것.
5. `a10_r5.field_paired_conclusion_gate`의 H1/H2/H3/CAL/H4/H4_REPRO 수식이 기존 `s1v2.decide_v2`와 일치하는지 새 독립 계산기로 대조. Field-only 4000 bootstrap, 동일 resample index, 모든 원본 행 유지, 실제 가능한 start witness와 보수적인 bounds 구분.
6. 실제/인위적 대안으로 H/CAL sign·95% CI zero inclusion·PASS/FAIL/UNDETERMINED flip 양성 fixture를 확인하고 baseline CI zero-inclusion→exclusion 역방향도 검사. 한 arm 누락, 비SPD/full C10/NEES의 부정적 fixture를 실행해 자동 PASS가 불가능한지 검사.
7. 기존 C3/C3V4 실패, A008/A009/A010-P0, RUN_REQUEST, `contract_lock.py`, S_field 전체 split, historical holdout 결과 보존 확인. R5 성공 결과로 G5 FAIL을 소급 수정하지 말 것.

## 판정 요구

- auditor actor/session, original SHA, input/model reused functions, separate math code, raw artifacts/exec receipts, negative fixtures, CI 결과를 명시.
- R5 code acceptance와 전체 A010 science freeze 판정을 **반드시 분리**. 최종 독립 감사 판정은 `ACCEPT_WITH_BOUNDARIES`, `REVISION_REQUIRED`, `REDESIGN_REQUIRED`, `BLOCKED_EVIDENCE` 중 하나로 서명.
- DEV3/HOLDOUT2/RT는 타 actor의 독립 감사 승인 및 별도 FROZEN 계약 전까지 **NO-GO**.

현재 제출자 판정: `R5_IMPLEMENTATION_TECHNICAL_VALIDATED`, `INDEPENDENT_AUDITOR_SIGNED=false`, `A010_SCIENCE_DRAFT`.
