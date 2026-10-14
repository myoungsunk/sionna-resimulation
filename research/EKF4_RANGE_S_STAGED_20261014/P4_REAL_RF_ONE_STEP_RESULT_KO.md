# P4 실제 RF 동결 one-step 기술 결과 및 제한

GitHub [Run 38557692205](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38557692205), source `9826b2cc09863728ca580e2aac1ea7774d6f1919`. 사전 소스 감사 GO, P0 39 frozen input/pose parity PASS, one-step representative 산출 PASS. [원본 artifact 11889904798](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38557692205/artifacts/11889904798) SHA256 `d958106252921947a521eb4617e35b8e52f20ee285fbb50aef7645392da120a4`.

R2_aA_m0, noise_pair seed0, t>=30에서 균등하게 고른 대표 12 시점/채널. 원 H/LoS·2° LUT·관측기·R0 `Rs=.0081, Rr=.0068578637, Rsr=0, offset=-.531598...` 불변. **각 시점은 같은 4-state DR prior로 시작**; full-route RF 재귀가 아니다. 공동 vs frozen linear sequential parity 최대 LoS `8.8818e-16`, Full `2.2204e-16`. 따라서 '관측 계산 순서 자체가 이득'이라는 가설은 지지되지 않음.

| 채널 | 대표 시점 | joint gate 거절 | MAP local 미수렴 | 나머지 accepted |
|---|---:|---:|---:|---:|
| LoS | 12 | 0 | 2 | 10 |
| Full | 12 | 2 | 2 | 8 |

MAP local 미수렴: LoS t=30.0/180.4, Full t=30.0/180.4. R3는 matched synthetic에서 수렴했지만 **동결 LUT의 실제 비선형/보간 매끈함에서 여전히 문제가 있음**. NIS=0.01–0.05처럼 작은 사례에서도 큰 MAP gradient (약 .00345, .00547, .01699, .11605)가 남았다. **이 건은 P2의 near-roundoff 1e-8 사례와 다르므로 원인을 확인하지 않은 채 허용치를 변경하거나 같은 솔버 패치를 사용하면 안 된다.** 이를 P5/P6의 해당 MAP 경로 numerical validity 위험으로 보존하고, 동일 데이터를 사용하는 EKF4의 실행·평가 자체는 차단하지 않는다.

P4는 12 시점×2채널의 제한된 기술 검증이다. 정확한 posterior/독립 재현성과 독립 scene 일반화는 미확정, scientific_PASS=false. 미래 P5 다봉 reference TV0.387 failure는 별도 numerical claim BLOCK. P6 R0 국소 가우시안 재귀를 별도 코드와 사전 감사로 실행하더라도 P4 MAP 미수렴을 성공으로 덮지 않음.
