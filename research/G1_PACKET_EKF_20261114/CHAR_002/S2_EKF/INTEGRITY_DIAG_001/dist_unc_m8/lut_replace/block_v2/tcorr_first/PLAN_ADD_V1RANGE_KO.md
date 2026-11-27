# 추가 시험: V1 range + range KI (사전 고정, 2026-11-27)

| 항목 | 내용 |
|---|---|
| 동기 | S0-id range는 근·중거리 R_rr이 실제 잔차 RMS의 2.4–3.0배(k)라 반복 오차가 가려진다. V1 range는 k = 1.0–1.6이다 |
| 블록·필터 | SWB fullco, F2 경로(GM + c₀ KI, 1 m / 10°), 편파 μ_s = 0 — C0와 같음 |
| range | V1: μ_r = U3 HGB(sweep EXIST 특징, 균일 가중), R_rr = x열 제외 CV 평균제곱(ρ̂ bin 3개, sd 4.31 / 6.82 / 15.38 cm) |
| arm | V0 = V1 range 백색, V3 = V1 range + range KI (C3와 같은 f, ℓ_r: N1–N6에서 V1 μ_r 잔차로 추정) |
| 판정 | R2/R4/R5, B0, dev seed 10–29. V3 대 V0: N_I ≥ N_I(V0) − 1, 짝 비율 bootstrap 97.5% 상한 ≤ 1.10, 거울해 ≤ V0. 목표 pooled XY95 ≥ 0.90. C0(S0-id)와의 비교는 보고만 |
