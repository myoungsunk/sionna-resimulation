# M2 replay 개입 정의 (결과 확인 전)

M2-pre가 Go이며 고정 선택 규칙에 따라 T=10초를 선택했다. k=1,2,3과 OFF를 BB/MB 10조건에 적용한다. 이 T는 같은 평가 trace를 보고 선택한 탐색적 파라미터이므로 독립 검증 성능으로 주장하지 않는다.

- 매 packet prior에서 기존 h/H/R/K를 계산하고 A_B 수용을 고정한다. 자연 gate, R/Q/평균 변경 없음.
- 누적 정보는 같은 (t-T,t] 창의 A_B 수용 range Jacobian H_r,xy^T H_r,xy/Rrr. 현재 packet도 수용이면 포함한다. 이전 packet의 당시 prior Jacobian을 저장한다.
- S_prev는 창 내 이전 packet에서 **실제로 적용한** 세계좌표 XY 측정 증분 합을 현재 prior 접선축에 투영한다. 원래 E1 증분을 재사용하지 않는다.
- 현재 예정 증분 δ는 joint K의 range+편파 두 열 전체로 계산한다. threshold=k*sqrt(u_t^T I^-1 u_t).
- [0,1]의 계수 gamma 중 |S_prev+gamma*δ_t|<=threshold를 만족하는 **가장 큰 값**을 사용한다. 원래 갱신이 한계 이내면1. 해가 없으면 양 끝0/1 중 |S|를 작게 만드는 쪽을 쓴다. 이미 한계 밖이어도 안으로 되돌리는 갱신을 억제하지 않는다. δ_t=0이면1.
- XY gain의 현재 접선 성분을 range/편파 두 열에서 gamma배로 줄인다. 반경 XY 성분 및 psi/bg 행은 유지한다. 수정 joint gain으로 Joseph 공분산 계산.
- full T가 확보되지 않거나 정보행렬 rank가 부족하면 gamma=1, 미적용 이유 기록. GT 또는 미래 입력 사용 없음. 거리 switch 추가 없음.
- 매 packet d_est, gamma, S_prev/after, threshold, sigma, rank, feasible 여부를 저장한다. 수용 여부는 전조건 A_B와 정확히 같아야 한다.
- OFF 10조건 E1 재현1e-10 후 k sweep. 합당한 gamma, gain 투영, Joseph, 거절 상태/P 불변 검산.
- M1과 동일①–⑤ 및 R4_aA 비악화 기준으로 판정. R5는 세 pass의 지표를 모두 기술한다.
