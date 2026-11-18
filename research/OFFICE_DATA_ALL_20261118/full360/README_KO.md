# Office 35개 정지 위치의 전 방향 RT sweep

실행 ID: `OFFICE_RT_360_20261118_100030`  
질문 ID: `OFFICE-35-FULL360-001`

기존 Office의 35개 정지 위치를 그대로 사용해 각 위치에서 10° 간격으로 전 방향을 새로 추적했다. 기존 데이터의 양의 각도 결과도 재사용하지 않고 다시 계산했다. 기존 데이터는 보존했다.

| 항목 | 결과 |
|---|---|
| 관측 yaw | −180°부터 +180°까지, 10° 간격, 위치당 37행 |
| 고유 RF yaw | −180°부터 +170°까지, 위치당 36개 |
| 전체 규모 | 고유 RF pose 1,260개, 관측 1,295행 |
| 주파수 | 257개 bin 모두 직접 trace |
| 생산 trace 호출 | 323,820회 |
| H 배열 | `H_full.npy`, `(1260, 257, 2, 2)`, `complex128` |
| 시작 / 종료 | 2026-11-18 19:04:45 / 20:00:58 KST |
| 생성 및 원본 기준 검증 | 3,372.592초, 약 56분 13초 |
| 결과 파일 크기 | 379,685,352 bytes, 약 379.7 MB; 동결 source 제외, 로컬 안내·전송 확인 파일 추가 전 |
| H 배열 파일 크기 | 20,724,608 bytes |

−180°와 +180°는 같은 물리 pose다. +180° 관측 행은 −180°의 `pose_id`와 `h_row`를 참조하며 `endpoint_alias=true`로 표시했다. 따라서 37행의 관측 표와 36개의 RF pose 표를 구분해서 읽는다.

## 원본 설정과 출처

- 원본 소스 커밋: `819fa93b152ca3cdf66297af09ff073880bd9d9b`.
- 원본 Office 생성기, 형상, 재질, FFD, 환경을 유지했다. Anchor O0=(5, 2.2, 2.65) m, 수신 높이 0.45 m, mount 0°다.
- 주요 solver 값: `refraction=true`, `max_depth=3`, `samples_per_src=100000`, `max_num_paths_per_src=1000000`, `seed=20260924`; LoS와 정반사를 활성화했다. 전체 값과 해시는 `RUN_CONTRACT.json`에 있다.
- Sionna RT 2.0.1 / Mitsuba 3.8.0 / DrJit 1.3.1의 기존 이미지에서 실행했다.
- `complex128`은 H 저장 형식이다. 생성기 내부 연산 정밀도는 원본 구현을 유지했다.
- 실행 시작과 끝에 동결 소스 92개 파일의 SHA-256을 확인했다. 약 496 MB의 소스·FFD 사본은 Snowball의 실행 폴더 아래 `source/`에 보존했다. 전송 아카이브에서는 해당 사본만 제외했다.

## 파일 읽기

- `rf_poses.json`: H 행별 station, 위치, yaw, 원본 trace 파일과 해당 yaw index.
- `SAMPLES.json`: −180°~+180° 순서의 관측 표와 H 행 참조.
- `traces/S01/neg/S01_neg_sweep.npz` 같은 파일: 해당 H를 생성한 동일 trace의 원시 경로 목록. 각 chunk의 H·receipt·장면 파일도 같은 폴더에 있다.
- `RUN_MANIFEST.json`, `RUN_SUCCESS.json`, `logs/`: 실행 시간, 명령, 소스 해시, 로그.

```python
import json
from pathlib import Path
import numpy as np

root = Path(__file__).resolve().parent  # 이 폴더에 읽기 스크립트를 둘 경우
H = np.load(root / "H_full.npy", allow_pickle=False)
samples = json.loads((root / "SAMPLES.json").read_text(encoding="utf-8"))
H_observed = H[[row["h_row"] for row in samples]]
# H_observed.shape == (1295, 257, 2, 2)
# station별로 묶으면 (35, 37, 257, 2, 2), yaw −180°~+180°
```

## 검증 결과

- `PILOT_VALIDATION.json`: 원본과의 사전 대조 PASS.
- `VALIDATION.json`: 원본 runcheck의 기준을 유지한 70개 chunk 전부 PASS, issue 0건. 경로에서 H를 재합성하는 검사와 집계 H의 chunk 일치 검사 포함.
- `ORIGINAL_OVERLAP_CHECK.json`: 기존 35개 위치 × 0°~170°의 복소 계수 647,640개가 배열·바이트 해시 모두 일치. 최대 절대 차이 0. pose·관측 표 검사도 PASS.
- `RESULT_SHA256.json`: 실행 결과 파일의 해시 목록.
- `LOCAL_TRANSFER_CHECK.json`: 아카이브 SHA-256과 결과 3,399개 파일의 해시를 로컬에서 확인, PASS.

Snowball 실행 폴더: `/home/KMS/OFFICE_RT_360_20261118_100030/`.

이 기록은 새 데이터 생성, 원본 기준 검증, 전송 확인의 결과다.
