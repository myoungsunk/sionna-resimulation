# T3 준비 상태

TECHNICAL: `NOT_EXECUTED` · 과학 판정: `NOT_ESTABLISHED`.

SourceFFD는3상태 입력을 허용하며, 기존 core는3·4상태 필터를 모두 지원한다. 실제 SourceFFD Jacobian의 마지막0열만3상태 API에서 제거한다. 기존 predict_one/filter_one의 S3/J3/S4/J4 동작과 gate를 재사용한다.

요청한 네 CSV를 생성하는 runner, historical POWER1 RMSE·packet gate 재현 검사, 독립 scorer 및 구 LUT 변화 목록 코드를 준비했다. Native LoS/hybrid는 별도 ORACLE_DIAGNOSTIC 표기다. Hybrid는 Full-only mu/C를 네 셀에 고정한다. 미확보 E1 ZIP과의 정확한 동등성은 NOT_ESTABLISHED다.

Python AST·JSON 구문 검사만 통과했다. 수치 실행, 입력 다운로드, 표 수치 확정은 하지 않았다. T6 버전은 새 P1 파라미터 및 `range_model=SRC_TAP` manifest를 요구하며 기존 표를 덮어쓰지 않는다.

## 주장하지 않는 것

온라인 Full 방법과 Native LoS/hybrid의 동일 추론 조건, 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다.
