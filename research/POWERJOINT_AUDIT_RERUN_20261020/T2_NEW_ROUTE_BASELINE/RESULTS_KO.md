# T2 준비 상태

TECHNICAL: `NOT_EXECUTED` · 과학 판정: `NOT_ESTABLISHED`.

정본 센서 설정은 source request의 전체 .25s motion과 실제 RF pose_id subset, exact Sensor-v2 builder·잡음·RNG·초기 오차다. 저장 CSV의 6자리 반올림에 대해서만 원래 legacy-euler lateral 허용오차를 2um로 명시적으로 변경하고 residual을 보존한다. 이 범위를 넘으면 geometry를 고치지 않고 중단한다.

`prepare_new_route`와 `build_canonical_controls`, source receipt 검증, seed0–4×B0/L0/L1/L2 sensor-preparation CLI를 준비했다. Python AST·JSON 구문 검사만 수행했다. 입력 다운로드, 센서 수치 생성, RF 수치 변환, POWER 학습, baseline 재귀는 하지 않았다.

O03 `los_exists=false`를 원본대로 보존하며 flags 미복원 시 `BLOCKED_INPUT`이다. 신규 POWER train은 R2/R4/R5 전체로 고정하므로, R4/R5만 쓴 과거 Chain F와의 차이를 센서 차이 하나로 해석하지 않는다.

## 주장하지 않는 것

정본 수치 확정, 센서·RF 하드웨어 실증, motion-noise 반복의 독립 RF 또는 독립 장면 해석, 정규화 Bayesian posterior를 주장하지 않는다.
