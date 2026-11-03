# 논문 제IV장 IEEE 캡션 및 표 반영 가이드

**고정 원본:** `b32fb7bf8f366823be32670400bf17ac18a714d8` / **그림 커밋:** `bc573d2395ed16b69cc7a7790a847c0e665afdd9`.

### Fig. 7 — 경로·채널 관측 변화
R1 직선 왕복 경로에서 Anchor B의 위치와 Full–LoS-only 관측 차이. (a) 참 궤적, (b) 거리 관측 차이, (c) 정규화 전력차. (c) 패널 아래 수직 눈금은 첫 경로 검출 tap이 달라진 시점을 나타낸다. 두 차이의 세로축은 극단값과 작은 오차를 함께 표현하기 위해 **signed asinh 변환**을 사용하며 눈금은 원래 단위이다. N=917.

### Fig. 8 — 보정 전 관측오차 분석
Full 채널에서 직접경로 관측모델을 기준으로 계산한 보정 전 거리·편파 오차의 참 수평거리 구간별 평균과 표준편차. (a) 거리 평균, (b) 거리 표준편차, (c) 편파 평균, (d) 편파 표준편차. t≥30 s, 767개의 유효 관측을 pre-gate로 분석하였다. 가로축은 **거리 구간 범주**로, 구간 너비는 동일하지 않다.

### Fig. 9 — LoS/Full 재귀 추정 성능
동일 4상태 SourceFFD 일반 EKF에서 LoS-only와 Full 관측에 대한 (a) Heading RMSE와 (b) XY RMSE. B0 및 L2 조건별 767개 평가 시점(t≥30 s), 게이트에서 거부된 시점까지 포함한다. 관측오차 평균과 추가분산은 적용하지 않았다.

### Table A — 보정 전 관측오차
`TABLE_R1B_OBSERVATION_ERRORS.csv`: 동일 767개 pre-gate 관측의 직접경로·Full 및 Full−LoS 차이. 거리 단위 cm, 편파 무차원. 식 e0=Full−h(GT), Δz=Full−LoS, e_los=LoS−h(GT).

### Table B — 첫 경로 tap 그룹
`TABLE_R1B_TAP_DIFFERENCE.csv`: 두 채널에서 검출한 tap의 일치 여부에 따른 거리·편파 차이. 이 그룹은 채널 및 경로 조건도 함께 달라질 수 있으므로 tap 변화의 단독 인과효과를 뜻하지 않는다.

### Table C — 측위 RMSE
`TABLE_R1B_EKF_RMSE.csv`: LoS-only/Full B0·L2의 Heading·XY RMSE 및 자체 게이트 수용·거부. t≥30 s 전체 767개 시점.

**논문 배치:** IV-A Fig7, IV-B Fig8 및 Table A, IV-C Fig9 및 Table C. Tap 그룹 Table B와 주행 phase별 Table D는 보조자료로 활용하고 본문에 모두 반복해 넣지 않는다.

**원본 time-domain plot:** `../p2_p3/figures/R1_HEADING_XY_TIME_AND_RMSE.svg`. 위 Fig9와 별도로 보존된 원본 추이 그래프이다.
