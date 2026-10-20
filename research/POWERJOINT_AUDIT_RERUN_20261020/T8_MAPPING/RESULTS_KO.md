# T8 준비 상태

TECHNICAL: `NOT_EXECUTED` · 과학 판정: `NOT_ESTABLISHED`.

기존 audit는 T10 first-visit inventory이며 원 Tnone 전체 sequence의 행별 시간·pose 인증이 아니다. 위치≤1mm, body yaw≤.01°, antenna=body+45° 및 엄격한 timestamp·행순서·길이 인증 코드를 준비했다.

Python AST 및 JSON 구문 검사만 통과했다. RF·mapping 수치 계산, release download, 재귀 실행은 하지 않았다. 인증 실패 시 재귀는 `BLOCKED_INPUT`; 별도 geometry 인증을 통과한 pose에서만 정적 단일 RF 관측 비교를 허용한다.

## 주장하지 않는 것

정적 비교로 시간 바인딩 또는 Heading 개선, 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다.
