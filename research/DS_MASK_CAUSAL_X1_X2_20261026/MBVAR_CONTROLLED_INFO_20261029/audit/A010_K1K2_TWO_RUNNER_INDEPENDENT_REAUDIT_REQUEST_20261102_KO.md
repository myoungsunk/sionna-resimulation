# MBVAR-INFO-001 — DEV2 K1/K2 2-runner PASS 이후 독립 감사 요청

**이 문서 제출자는 구현자입니다. `INDEPENDENT_AUDITOR_SIGNED=false`. 반드시 별도 감사자가 소스와 숫자를 재검증하십시오.**

## 감사 대상 고정

- 실행 SHA: `4dece4c63ef62e046366e6c062f63a21ad89e05f`, [GitHub Actions #41453446631](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41453446631). 보고서 추가 commit과 구분.
- 원본 증거 세트: [Runner A](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41453446631/artifacts/13146625587), [Runner B](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41453446631/artifacts/13146352094), [비교 결과](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41453446631/artifacts/13146137245).
- 입력 ZIP SHA256 `316efcc04946197cbb5c10417e3b6bfca3e4e8f5e4d3433535dfbba09b7bb9f3`, GEN MANIFEST SHA256 `f031c293796906f0087d6c6b72c7099b27bd6d4fdb9b59135cacd459407fb516`.
- 두 runner의 VM boot ID는 다르며 raw evidence의 runner_name/job, CPU/BLAS/OS 정보도 대조할 것.

## 독립 감사자 8항목

1. 해당 커밋의 Git blob 직접 읽기: original FROZEN A008/A009/A010-P0, contract_lock, RUN_REQUEST, C3/C3V4 FAIL 증거 불변 확인.
2. 원본 artifact 3개를 다운로드하고 receipt JSON의 원본 bytes SHA를 독립 재계산. 비교 job의 GitHub Actions 로그·체크아웃 source SHA와 대조.
3. archived K1/K2 canonical input zip과 배열 48개(dtype/shape/bytes) 원본 ledger 재확인. 기존 DEV2 외 field 접근 없음 확인.
4. 최적화 알고리즘에서 참값·oracle truth-start로 operational solution을 선택하지 않는지 독립 코드 경로를 통해 확인. `ORACLE_CORR_BATCH`는 합성 reference라는 점 별도 명기.
5. 기존 수학 helper를 사용하지 않는 별도 계산으로 최종 4×4 C10, 고유값, 조건수, 회전된 에러 및 `NEES4` 재도출; 모든 10개 upper entries와 state 비용차 재계산.
6. K2의 대안해 5개를 재평가하고 동일 objective/solver precision의 truth-free start 비교 및 cost-gap과 d_ref 규칙 확인. 각 대안해 MSE/P/NEES 변화와 과학적 해석 위험 확인.
7. D2 Σ field별 원본 및 1e-10 cross-field equivalence, D3 gate-ID allowlist, D4 legacy FAIL/dual verdict, D6 entire S_field snapshot/no old HOLDOUT resurrection 재검사.
8. 독립 감사의 최종 상태를 `ACCEPT_WITH_BOUNDARIES`/`REVISION_REQUIRED`/`REDESIGN_REQUIRED`/`BLOCKED_EVIDENCE` 중 하나로 기록, 감사 actor/session, 독립 재계산의 코드, input/source SHA, signature 명시.

## 동결 전 판단 규칙

이 단계의 좁은 2-runner 기술 PASS로 A010 전체 science lock 동결 권한이 발생하지 않음. 독립 감사자의 실제 서명과 proposer 최종 승인 전까지 `A010=SCIENCE_DRAFT; DEV3/HOLDOUT2/RT=NO-GO`.