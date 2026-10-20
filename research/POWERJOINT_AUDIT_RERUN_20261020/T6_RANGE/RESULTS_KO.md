# T6 준비 상태

TECHNICAL: `NOT_EXECUTED` · 과학 판정: `NOT_ESTABLISHED`.

SourceFFD가 실제 검출기 range를 이미 `diag['native_range']`에 반환하는 것을 소스로 확인했다. `SourceTapRange`는 이를 그대로 사용하며, range Jacobian은 tap 불변 셀에서 0이다. tap 전환점에서는 미분이 정의되지 않는다. 세부 해석은 `DESIGN_KO.md`를 따른다.

`PROTOCOL_LOCK.json`, 정확한 adapter, Native LoS 9,519점 잔차·FD 실행 코드를 준비했고 Python AST/JSON 구문 검사만 통과했다. 프로토콜 커밋 확인 전 RF 수치 계산은 하지 않았다. P1 재학습, 재귀 POWER1, Native LoS 안전성 수치는 아직 없다.

## 주장하지 않는 것

낮은 검출 잔차만으로 재귀 개선, detector tap 전환점의 미분 가능성, 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다.
