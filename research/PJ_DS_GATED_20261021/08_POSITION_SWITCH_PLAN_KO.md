# 위치·갱신 단위 선택(switching) replay — 실행 전 고정 (2026-10-21)
기본 필터 = INFL_R(큰 |Δs| range 분산 상향, 항상). 선택기가 켜진 패킷에서만 편파 하향(작은 |Δs| 패킷 \(V_s\times\kappa^{lo}\)) 추가. 결정은 results_series/SWITCH_DECISIONS.csv.gz에 미리 저장(필터 상태와 무관).
위치 구간 = 0.5 m x-bin 1회 통과(전 구간 860개, 중앙값 13 패킷·2.4 s).
| 선택기 | 정의 | 성격 |
|--|--|--|
| SW_ORACLE_SEG | 구간에서 MIX 시계열 heading MSE < INFL_R | GT 상한 |
| SW_EOS3 | 구간 INFL_R 국소 err/σ > 3 | GT regime |
| SW_POSMAP | 다른 두 route에서 그 x-bin의 평균 이득<0 | 온라인(위치지도, route-heldout) |
| SW_I_ABSDS_40 | 인과 EMA(τ=40 s) |Δs₊₁| 임계, 임계·방향은 다른 두 route에서 | 온라인(Δs) |
| SW_I_PUSH_40 | 인과 EMA(τ=40 s) Δs 예측 heading 이동 크기 임계 | 온라인(Δs+HGB) |
비교: BASE, INFL_R, MIX(항상). 보고: heading·거리오차·radial 비(대 INFL_R, 대 BASE), 개선/악화 개수, NEES. 위치지도는 GT x로 bin을 매겼다(온라인에서는 추정 위치; 오차 수 cm ≪ 0.5 m).
