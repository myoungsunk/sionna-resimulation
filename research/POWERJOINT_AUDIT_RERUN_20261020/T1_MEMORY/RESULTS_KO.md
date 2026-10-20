# T1 구현 감사 및 로컬 단위 시험

로컬 단위 시험 TECHNICAL: `TECHNICAL_PASS` · 동결 Actions 재귀 검증: `NOT_EXECUTED` · 과학 판정: `NOT_ESTABLISHED`.

구현 1 원본을 기반으로 실제 엔진 단위 시험과 9-arm 재귀 실행 코드를 준비했다. 구현 1은 확보 소스 범위에서 수학 시험을 통과한 정본 후보다. 동결 Actions runtime 시험과 기준 POWER1 재현 전에는 논문 수치 정본을 확정하지 않는다. 구현 2·3 소스는 `BLOCKED_INPUT`; 보고서 확인 사항과 미확인 항목은 `IMPLEMENTATION_DIFF.md`에 구분했다. 누락 소스 때문에 숫자 엔진을 새로 추정하지 않았다.

프로토콜 커밋 `a17a5eb` 확인 후 로컬 단위 시험을 실행했다. `UNIT_TESTS.csv` 및 `validation/UNIT_MANIFEST.json`이 실제 결과다. 기존 RF·신규 RF 재귀는 실행하지 않아 `CANONICAL_RESULTS.csv`가 없다.

| 시험 | 실제 값 | 기준 | 결과 |
|---|---|---|---|
| actual engine.run rho0 상태/공분산 최대차 | 4.440892098500626e-16 / 1.734723475976807e-17 | 각각 ≤1e-10 | PASS |
| gate 불일치 | 0 (accept/reject 모두 발생) | 0 | PASS |
| 정상상태 분산 상대오차 최대 | 1.0165004895271224e-16 | ≤1e-9 | PASS |
| actual single_update 500 MC correct-memory NEES / coverage | 1.088620836393551 / .934 | 원본과 ≤1e-9 / ≤1e-12 | PASS |

**환경 제한:** 실제 로컬 runtime은 Python 3.13.15 / NumPy 2.2.4 / pandas 2.2.3이다. 요청한 Python 3.13.5 / NumPy 2.3.5 동결 Actions 환경과 다르며 이번 로컬 실행의 BLAS thread 설정은 별도 기록하지 않았다. 이 결과를 동결 환경 검증으로 대체하지 않는다. 정적 AST/JSON 검사도 통과했다.

관리 실행은 2026-10-20 11:04:14–11:04:22 KST, run `8de1fe91-78e3-4889-9552-83846ade2615`, resource `1aff3432-3086-4ce0-a123-6c0b2ae925a4`, natural exit 0이다. finish 후 process/supervisor/job 부재와 소유 참조 0을 확인했다.

## 실행 계약

단위 시험: `python research/POWERJOINT_AUDIT_RERUN_20261020/T1_MEMORY/unit_tests.py --source-root source --out out/T1_MEMORY`.

재귀: `python research/POWERJOINT_AUDIT_RERUN_20261020/T1_MEMORY/replay.py --source-root source --bundle canonical_bundle.json --out out/T1_MEMORY`.

Source root에 pinned engine, `core.py`, SourceFFD와 bank 환경이 필요하다. 런타임은 기존 workflow의 Python 3.13.5, numpy 2.3.5 / scipy 1.17.0 / pandas 2.2.3 / scikit-learn 1.8.0, BLAS thread 1을 따른다. replay bundle의 mu/C/tau/fraction은 기존 7조건은 exact impl1 route-heldout fitter, 신규 9조건은 기존 세 route 전체 train-only fitter에서 준비해야 한다. T2 정본 control과 RF ID alignment를 입력 contract에 사용한다. GT 배열은 점수계산에만 전달한다.

기존 POWER1 gate 불일치 0 검증에는 역사적 trace도 필요하다. 요약 CSV의 gate 비율만으로 패킷별 동일성을 증명하지 않는다. 해당 trace 미제공 시 scorer/재귀 계산이 성공해도 MANIFEST의 technical은 `BLOCKED_INPUT`이다.

## 주장하지 않는 것

독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증, 정본 수치 확정, 구현 2·3의 시험 통과 또는 수치 차이의 원인 확정을 주장하지 않는다.
