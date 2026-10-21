# 간이 테스트 — Δs 크기에 따른 POWER 분산 재보정 (실행 전 고정, 2026-10-21)
평균(POWER1), 상태, gate(패킷 R), η=1, κ_bias=1 그대로. 분산만 \(|\Delta s_{+1}|\)에 따라 배율 조정.
- 2단(2LVL): train route Full의 \(|\Delta s_{+1}|\) 80분위 τ로 나누고, 각 구간에서 \(\kappa=\overline{r^2/V}\) (POWER1 잔차, train만). 상위: s 2.7–3.7, r 1.8–3.3 / 하위: s 0.36–0.63, r 0.61–0.70 (계획서 계산값).
- 5단(5BIN): train 5분위 경계별 κ.
Arms: BASE(POWER_DIAG), REF_POWER1, V2LVL_S(편파만), V2LVL_R(range만), V2LVL_SR(둘 다), V5BIN_SR.
보고(크기로): Full 14의 heading RMSE비·개선/악화·최악, NEES·coverage, xy RMSE비, L2 bias비, LoS(진단); 게이트/비게이트별 패킷 s95·r95·패킷 NEES(분산 calibration 확인). QA: BASE·REF_POWER1 재현.
