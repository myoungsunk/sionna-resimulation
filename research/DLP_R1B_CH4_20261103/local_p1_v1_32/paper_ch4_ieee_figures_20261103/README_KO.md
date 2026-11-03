# R1/Anchor B IEEE 제IV장 그림·표 준비

원본 데이터 고정 커밋: `b32fb7bf8f366823be32670400bf17ac18a714d8`; `research/DLP_R1B_CH4_20261103/local_p1_v1_32/p2_p3/results/`의 P2/P3 결과에서 생성. 기존 실험 결과는 변경하지 않음.

- **Fig. 7**: R1 궤적 및 Full−LoS 관측 차이(917 poses). (b)(c)는 signed asinh 세로축, 눈금은 원래 단위이며 큰 값도 포함. 그림 아래 tick은 두 채널의 first-path tap mismatch.
- **Fig. 8**: 보정 전 Full 오차(직접경로 모델 참값 대비)의 거리 구간별 평균/중심화 표준편차. t≥30 s, 767 pre-gate poses, GT 수평거리 bin. 거리 bin은 가로축에서 범주형이고 실제 폭이 서로 다름.
- **Fig. 9**: 동일 4상태 SourceFFD EKF의 무보정 LoS/Full Heading·XY RMSE, B0/L2, t≥30 s, gate 거부시점 포함.

데이터: `PLOT_R1B_TIME_SERIES.csv`(917), `PLOT_DISTANCE_BIN_STATS.csv`(12 bin×component). 표는 이어지는 커밋에서 추가.

SVG의 문서상 폭은 **7.10in(IEEE 2-column)**. 벡터 그대로 인쇄 가능. 원본 실험 시간추이 `../p2_p3/figures/R1_HEADING_XY_TIME_AND_RMSE.svg`는 기존 P3 폴더에 별도 보존.
