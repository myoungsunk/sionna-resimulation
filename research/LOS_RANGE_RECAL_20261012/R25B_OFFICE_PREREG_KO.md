# R2-5b 사전등록 — 오피스 scene에서의 P4(c) 전이 시험 (결과 확인 전 동결)

동결 시각: 이 문서 커밋 시점. 시험 코드 `r25b_office_p4c.py`는 이 문서와 함께 커밋되며 결과 산출 전에 변경하지 않는다.

## 데이터 (새 시뮬레이션 없음)
`claude/office-e-layout`의 `results/OFFICE_SNOWBALL_20261008_819fa93/full35_stride1`: 사무실 10×12×2.7 m, 책상 24개(윗판 한 장)·칸막이 12개, 앵커 (5.0, 2.2, 2.65), 35 위치 × yaw 19 × 257 bin, PathSolver 170,905회. LP±45° bank SHA·solver 설정(max_depth 3, 회절·산란 off, seed 20260924)은 복도 학습 데이터와 동일. 기하 LoS 점검: 열림 25 / 막힘 10, 불일치 0. 이 데이터는 P3/P4 적합·선택에 쓰인 적이 없다. 단, 위치 간격 1.5 m의 coarse 격자이며 H만 있고 경로 라벨은 없다.

## 모델 (동결, 재적합 없음)
`P3_FROZEN_MODEL.json`의 chosen=E1_on_B(all-route 계수)와 B_old(−0.5316 m 오프셋). 검출 임계, 특징량, mount=0(yaw 스윕), 주파수 격자 모두 학습과 동일. 진값 range = ‖앵커 − 태그 안테나(z=0.45)‖ (기하 거리).

## 판정 (사전 동결)
- **Primary**: LoS-clear 25 위치, noise-free, 위치 클러스터 부트스트랩(4000, seed 20261012). 통과 = 점추정 ≤ −10 % **그리고** 95 % CI 상한 < 0 (E1 vs B, RMSE 상대변화). 클러스터는 위치 25개(yaw 19개는 위치 안에서 평균).
- **Secondary(기술, gate 아님)**: snr30, snr10 (잡음 CIR, 고정 seed); LoS-blocked 10 위치(첫 경로가 LoS가 아니므로 기하 거리 진값과의 오차는 NLoS 편향 포함. E1은 이 상황을 위해 학습되지 않았음); 전체 35 풀링.
- **보고 의무**: B의 평균 오차(오프셋 이전성), 거리 구간별 오차, 위치별 상대변화 분포(개선이 소수 위치에 몰렸는지).
- **판정어**: 통과 → `ONE_NEW_SCENE_TRANSFER_PASS` (일반화 확립 아님; scene 1개, 클러스터 25개). 미통과 → `SCENE_TRANSFER_FAIL` 또는 `INCONCLUSIVE`(CI가 0을 포함). 어느 경우에도 `scientific_PASS` 불변.
- 결과가 나쁘더라도 기준·모델·데이터 선택을 사후 변경하지 않는다.
