# 편향 지배 regime 지표 — case 수준 탐색 (2026-10-21, 사후 분석)
표: results_tradeoff/REGIME_CASE_TABLE.csv (14 case-bias). 라벨: DEFL_S heading RMSE비.
- GT 지표 중 가장 잘 구분: 실제 heading RMSE ÷ 필터 heading σ(err/σ). DEFL_S 개선 case R4 B·R5 A 4.35–5.02, 나머지 1.00–2.35 (R5 B B0는 0.994로 사실상 무변화, err/σ 1.45). Spearman −0.73. 기준 heading RMSE 단독은 −0.24(R2 A M0 1.84°가 regime 아님).
- 온라인 후보(필터 σψ, 게이트 비율, 수용률, innovation 백색성, Δs 예측 편향, 예측 push/σ): 완전 분리 없음, |Spearman| ≤0.65.
- Oracle 상한(case 단위 GT regime, 임계 3은 사후): "regime이면 MIX(또는 DEFL_S), 아니면 INFL_R" → heading 0.964–0.972(11–12/14 개선, >10%악화 0, 최악 1.026), 거리오차 0.955(12/14), radial 0.944–0.950. INFL_R 단독: 0.994 / 0.975 / 0.972.
