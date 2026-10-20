## 2026-10-20 사후 적용성 정정

구현1/canonical의 현재 지위는 검증된 실행 기준이다. 구현2·3은 DEFERRED_SOURCE_UNAVAILABLE이며 원본 비교·동등성 검증을 완료한 것으로 간주하지 않는다. 파일명 CANONICAL_RESULTS.csv와 역사적 정본 표기는 원문 식별자로 보존한다.

아래는 보존된 당시 보고 내용이다. 현재 해석은 이 사후 정정을 우선한다. 원래 숫자 CSV·DECISION·사전 등록 파라미터는 변경하지 않았고 원문 bytes/SHA는 후속 S0_CORRECTIONS/ORIGINALS와 VALIDITY_INDEX.json에 보존했다.

---

# T1 시간기억 정본 재실행 완료

TECHNICAL_PASS. 기존 7조건 × 4 bias × 9 arm=252행과 신규 9조건 × 4 bias × 9 arm=324행을 합쳐 CANONICAL_RESULTS.csv 576행을 보존했다. 구 주로는 route-heldout, 신규 주로는 기존 R2/R4/R5 전체 학습과 T2 정본 seed0 센서를 사용했다.

사전 등록 판정 NOT_ESTABLISHED; 채택 기준 FAIL. MEMORY의 Heading RMSE가 POWER1보다 10% 초과 악화된 셀은 14/64 (21.875%), heading95 개선은 60/64 (93.750%)다. 전체 셀별 결과는 MEMORY_CRITERION.csv에 남겼다. R5 A M0 B0는 4.556146 → 8.764142°로 악화가 남는다.

기존 수학 시험 500회 NEES=1.0886208364, coverage=.934; RF rho0 상태 최대 차3.997e−14, 공분산7.772e−16, gate 불일치0. 과거 POWER1 B0 RMSE 최대 차1.262e−13°, 독립 scorer2.274e−13. 신규 6개 작업도 수학 시험과 독립 scorer를 통과했다(T2 CHECKS/UNIT_TESTS_BY_ROUTE). 신규 저장 trace 36개도 run39361490496에서 모든 시점의 물리 4차원 POWER1/MEMORY_RHO0 parity를 직접 검증했다. 최대 상태 차=3.249e-14, 공분산 차=5.135e-16, gate 불일치=0. UNIT_TESTS_NEW.csv와 여섯 artifact receipt에 보존했다. 모델·RF를 재실행하지 않았다. 신규 기존 정본과의 역사적 gate parity는 존재하지 않으며 T2 자체를 첫 정본으로 고정한다.

기준 구현은 원본3fc70f2280471954f1a0673009812ad75437d9ea이며 실제 실행 엔진 파일 hash/코드 revision은 MANIFEST와 각 artifact receipt에 보존했다. 구현2·3은 원본 미확보 BLOCKED_INPUT, 문서 재구성은 미시험이다. 이전 보고서의 FALSIFIED_FOR_TESTED 표현은 lock의 otherwise=NOT_ESTABLISHED와 달라 정정했다. 원문은 RESULTS_OLD_SUPERSEDED_KO.md에 그대로 남겼다.

기존 run39358085399/artifact12236825429, 신규 run39359952488/6개 artifact. trace NPZ는 Actions에만 보존한다.

## 주장하지 않는 것

범용 기억 모델 승인, 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다. 구현2·3 숫자·코드를 인증하지 않는다.
