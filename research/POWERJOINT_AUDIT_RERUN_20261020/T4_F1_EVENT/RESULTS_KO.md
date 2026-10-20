# T4 F1 이벤트 진단 준비 상태

TECHNICAL: NOT_RUN. 과학 판정: NOT_ESTABLISHED.

고정된 10개 이벤트와 D1–D6, 원래 POWER1, skip의 실행 코드를 준비했다. 아직 수치 재귀나 RF 진단을 실행하지 않았다. protocol 커밋과 T1/T2 정본 입력에 대한 baseline parity가 선행되어야 한다. 기존 skip 개선량은 배경값이며 정본 재실행 값으로 제시하지 않는다.

F1 판정은 전역 t≥30 s를 사용한다. 신규는 전체 motion 샘플, 기존은 원래 RF 샘플이며 신규 RF-only 비교도 별도로 제공한다. 고정 유익 이벤트 전체에 같은 진단의 안전성을 요구하는 보수적인 판정이다. 개입은 ORACLE_DIAGNOSTIC이다. D4의 비양정 공분산은 보정하지 않고 오류로 보존한다.

## 주장하지 않는 것

독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다. 구현·구문 검사는 F1 지지 증거가 아니다.
