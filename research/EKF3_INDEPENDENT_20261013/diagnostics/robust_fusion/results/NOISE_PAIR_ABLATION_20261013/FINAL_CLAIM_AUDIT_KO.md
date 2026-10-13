# 실행 후 결과·주장 독립 감사

Reviewer: /root/ablation_audit. 판정: ACCEPT. 수정 요구 없음.

SUMMARY_KO.md의 RMSE·NEES·포함률은 FULL/POOLED_METRICS.csv와 일치한다. seed를 합친 7조건 모두 M1-A/M1-C가 악화했고, M1-B는 B_OLD·E1 각각4조건에서 악화됐다는 설명이 CASE_METRICS.csv와 일치한다. Bias RMSE 범위와 LoS s 분산/R0 비율도 원자료 요약과 일치한다.

M0/M1-C 각각252셀 parity 최대차이0, 허용치1e-8, 전체1008셀 종료코드0 및 실행753.447초를 확인했다. 표의 각 행은21셀·18603표본이며 독립 RF 표본으로 주장하지 않는다.

RF 변경은 평균·분산·Huber·gate 제거의 묶음으로 해석하고 Huber 단독 실패로 단정하지 않았다. LoS NEES 악화, E1 탐색적 한계, M2 미실행, scientific_PASS=false가 명시돼 있다. 제한된 결론을 막는 추가 결손 없음.

이 감사는 전체 실행·후처리 완료 및 EVIDENCE 분할 후 수행됐으며, 분할 ZIP 밖의 별도 최종 증빙이다.
