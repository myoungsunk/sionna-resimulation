# 저장된 블록 — SWB-O, SWB-C, SWB-C0

각 arm의 블록을 sweep 없이 다시 쓸 수 있게 데이터로 저장했다. [load_blocks.py](load_blocks.py)로 CSV만 읽어 재구성하면 원래 코드와의 최대 차이가 SWB-O 2.8e−12, SWB-C 1.3e−10이다(Office 영역 무작위 2,000 pose).

| arm | 블록 | 보간·대응 | 분산 표 | 거리 보정 | 평균 보정 |
|---|---|---|---|---|---|
| SWB-O | [SWB_O_COEFS.csv](SWB_O_COEFS.csv): Office LoS station 25곳의 36 yaw 곡선 조화 계수 19개 | (x, y) Delaunay 선형, 껍질 밖은 가장 가까운 station | [TABLE_SWB_O.json](TABLE_SWB_O.json) (station 하나 제외) | [RANGE_CAL_T1.csv](RANGE_CAL_T1.csv) (Office sweep) | 없음 |
| SWB-C | [SWB_C_COEFS.csv](SWB_C_COEFS.csv): Corridor 40열 × 5줄의 거리별 처리 후 station 곡선 조화 계수 | Corridor 좌표에서 x 3차 spline, y 선형. Office pose는 (10 ± ρ, 0, ψ)로 대응 | [TABLE_SWB_C.json](TABLE_SWB_C.json) (Corridor 완전 열 제외) | RANGE_CAL_T1.csv (Office sweep) | 없음 |
| SWB-C0 | SWB-C와 같음 | SWB-C와 같음 | TABLE_SWB_C.json | [RANGE_CAL_T0.csv](RANGE_CAL_T0.csv) (Corridor sweep) | 없음 |

**조화 계수 정의.** ψ 표본은 −180°부터 170°까지 10° 간격 36개이고, 계수는 numpy rfft의 k = 0..18이다. 곡선은 s(ψ) = Σ_k w_k·Re(c_k·e^{ik(ψ+π)}), w = [1, 2, …, 2, 1] / 36으로 계산한다.

**필터 연결.** F2 재생 코드(`m8_replay.py`)는 바꾸지 않는다. 예측값과 Jacobian만 `stage0/code/h_ref.py`의 SwapS로 교체한다. 세부는 [BLOCK_CONFIGS.json](BLOCK_CONFIGS.json)에 있다.

| 파일 | 내용 |
|---|---|
| [save_blocks.py](save_blocks.py) | 이 폴더를 만드는 스크립트 |
| [load_blocks.py](load_blocks.py) | CSV만으로 블록을 재구성하고 원본과 비교하는 스크립트 |
