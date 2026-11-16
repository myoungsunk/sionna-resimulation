# 앵커 B · B0 · +45° E0 재생

R2·R4·R5의 seed 10 Full H를 사용했다. `__online.npz`는 Full H 관측과 고정 제어 입력을 담고, `__evaluator.npz`는 LoS H와 채점용 참 자세를 담는다. `__calibration.npz`는 거리 HGB 및 POWER_DIAG 보정값을, `__e0_trace.npz`는 W0 재생 결과를 보관한다.

| 궤적 | 패킷 수 | E0 gate 수용 | +45° 재귀 최대 정규화 차이 | Gate 불일치 |
|---|---:|---:|---:|---:|
| R2 | 979 | 801 | 0 | 0 |
| R4 | 742 | 726 | 0 | 0 |
| R5 | 1,415 | 1,349 | 0 | 0 |

0°의 보정 입력과 E0 trace를 기존 동결본에 대조했다. +45°에는 기존 동결 E0 trace가 확인되지 않아, 같은 SourceFFD를 쓰는 원본 W0와 별도로 구현한 예측·갱신·shadow gate를 비교했다. 기존 경로 제외 방식으로 학습된 거리 HGB를 불러와 0°에서 보정값을 재현한 뒤 +45° RF 특징에 적용했다.

- 입력 해시와 판정 기준은 [RUN_CONTRACT.json](RUN_CONTRACT.json)에 기록했다.
- 기존 HGB 모델의 커밋과 해시는 [CALIBRATION_MODEL_LOCK.json](CALIBRATION_MODEL_LOCK.json)에, 0°에서의 보정 재현 결과는 [CALIBRATION_PARITY.json](CALIBRATION_PARITY.json)에 기록했다.
- 0° 및 +45° 대조 결과와 생성 NPZ의 SHA-256은 [PARITY_RESULTS.json](PARITY_RESULTS.json)에 기록했다. NPZ 원본은 Git LFS에 있다.

## 생성과 검증

실행한 코드는 [prepare_mount45.py](prepare_mount45.py), [calibration.py](calibration.py), [e0_reference.py](e0_reference.py)다. [기존 O30 추출 코드](../prepare_s2_extensions.py)와 [0° E0 대조 코드](../replay_s2.py)를 가져다 쓴다. 동결 계약에 적힌 원본 RF, 자세 격자, P2 보정 자료, FFD 관측 모델과 안테나 bank는 파일별 해시가 일치해야 한다. 생성 코드는 해당 자료를 기존 `D:/SLAM_bot` 작업 환경에서 읽는다.

원래 작업 환경에서 다시 생성하려면 세 스크립트를 `D:/SLAM_bot/artifacts/` 아래 새 실행 폴더에 놓고 그 폴더에서 다음 명령을 실행한다. Python과 패키지 버전은 두 parity 결과에 기록돼 있다. 거리 HGB를 읽을 scikit-learn 1.7.2는 실행 폴더의 `runtime_sk172/`에 설치한다.

```powershell
$env:OMP_NUM_THREADS = '1'
$env:OPENBLAS_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
python -B -m pip install --only-binary=:all: --no-deps --target runtime_sk172 scikit-learn==1.7.2
python -B -X utf8 prepare_mount45.py freeze
python -B -X utf8 calibration.py models
python -B -X utf8 calibration.py predict
python -B -X utf8 prepare_mount45.py run
```
