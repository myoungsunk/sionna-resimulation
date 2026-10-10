# 사전 기록의 표시 문구와 실행 소스 대응

원본 `EXECUTION_PLAN.json`은 덮어쓰지 않았다. `minimum_contiguous_blocks=3`은 표시 문구가 모호했다. 보정 전에 실행된 stage2의 소스 `fde444f708b99a54ea8baa90d82c13aeee6d543feb65dc50c28bff4081fd253f`에는 이미 `tables()`의 `len(set(ids//20))>=3` 규칙과 “NOT asserted independent” 주석이 있었다. 동일 바이트의 소스를 복원하고 receipt SHA256과 대조해 `STAGE2_EXECUTED_SOURCE.py.txt`로 보존했다.

실제 지원 조건은 표본 50개 이상이고, **20개 timeline sample마다 나눈 비중첩 구간 중 해당 cell 표본이 하나라도 있는 구간이 3개 이상**이다. 구간마다 해당 cell 표본 20개가 전부 있다는 뜻이 아니다. 서로 끊긴 잔차 run 3개 또는 독립 반복 3개라는 뜻도 아니다. 이 규칙은 독립성의 증거가 아니라 자료가 너무 적은 cell을 fallback시키기 위한 최소 지원 규칙이다. 결과를 본 뒤 표본 기준·분할·규칙을 바꾸지 않았다. 강한 시간 상관 때문에 이 표본 수를 독립 표본 수로 해석하지 않는다.

stage2 후 변경은 bootstrap에 median 집계와 해당 CI를 추가한 것이다. 원래 계획의 paired median 채택 조건을 구현하기 위한 집계 변경이며 stage2의 생성기·필터·수치 경로는 바뀌지 않았다. stage3–6은 현재 source `beed03a7977c50f9bab1155b83f12bf04abb2f01aa6803ecf42237b843a2bef2`로 실행했다. `SOURCE_CHANGE_RECEIPT.json`과 각 `STAGE*_RECEIPT.json`을 확인한다.

held-out 구간은 예측·갱신을 순차 수행하는 동일 route의 마지막 구간이다. 보정 구간의 측정도 앞선 필터 상태에 영향을 줄 수 있다. 서로 다른 RF 환경에서 새로 시작한 독립 route 검증이 아니다. table 추정에는 평가 잔차를 사용하지 않았고 pose_id 교집합도 없다. oracle 잔차 통계와 온라인 추정 상태 기반 table 조회는 분리한다.

STEP6 rejection/update 카운트는 전체 979-sample replay의 합이며, RMSE·NEES·NIS·innovation 통계는 지정한 평가 구간이다. 시간 표본을 독립 반복으로 취급하지 않는다. bootstrap은 하나의 고정 RF realization에 조건부인 독립 sensor/prior seed를 재표집한다.
