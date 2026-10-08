# 사무실 시뮬레이션: 스노우볼에서 실행하는 방법

이 폴더는 **실행 직전까지** 준비한 계획입니다. 시뮬레이션은 스노우볼에서 직접 돌립니다. 브랜치는 `claude/office-e-layout`입니다.

## 무엇을 돌리나

- 방 10 × 12 × 2.7 m, 큐비클 덩어리 12개(3열 × 4개), 책상 24개(두 개씩 등을 맞대고 +x / −x를 봄), 칸막이 12장, 앵커 천장 (5.0, 2.2).
- 태그 위치 35곳(`positions_all.txt`, 걷는 경로를 1.5 m 간격으로 잡은 것), 위치마다 yaw 0°–180° 10° 간격 19개, 주파수 257개(6.2504 GHz + k·1.95 MHz).
- 위치 35곳 중 25곳은 기하상 LoS가 열리고 10곳은 막힙니다(`RUN_PLAN.json`).
- 솔버 설정은 복도와 같습니다: `max_depth` 3, LoS + 정반사 + 굴절, 회절·산란 끔, 시드 20260924.

## 스노우볼에 필요한 것

1. 브랜치 받기: `git fetch origin claude/office-e-layout && git checkout claude/office-e-layout`
2. **Git LFS 파일:** `git lfs pull`. 러너가 `LP_plus45_bank.npz`, `LP_minus45_bank.npz`(저장소 루트, FFD 뱅크)를 읽습니다.
3. 저장소에 이미 있는 입력(추가로 받을 것 없음):
   `scripts/g2_completion/sionna_native_runtime.py`, `results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json`,
   `results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/BANK_MANIFEST.json`
4. Python 환경: `sionna-rt==2.0.1`, `mitsuba==3.8.0`, `drjit==1.3.1`, numpy, scipy (이 세션의 검증 환경과 같은 버전). 결과 receipt에 버전이 기록됩니다.
5. 환경 변수 `PYTHON`에 위 패키지가 있는 파이썬을 지정합니다.

## 실행 순서

```bash
export PYTHON=<sionna-rt 2.0.1이 있는 python>

# 1) 장면과 LoS 검증 (약 1분): Sionna의 LoS 경로가 기하 판정과 같은 위치에서 나오는지
$PYTHON scripts/corridor_sionna_run.py --scenario office --geom-check --out results/OFFICE_RUN_20261008/geom_check
#    기대: {"positions": 35, "sionna_clear": 25, "geometric_clear": 25, "mismatches": 0, ...}

# 2) 시험 실행: 위치 6곳(LoS 3 + 막힘 3), 시간을 재 보는 용도
POSITIONS=results/OFFICE_RUN_PLAN_20261008/positions_pilot.txt OUT=results/OFFICE_RUN_PILOT CORES=4 bash scripts/office_run.sh
python3 scripts/office_verify_outputs.py --run-dir results/OFFICE_RUN_PILOT --expect 6

# 3) 전체 실행: 35곳 (끊겨도 같은 명령으로 이어서 돕니다)
CORES=4 bash scripts/office_run.sh
python3 scripts/office_verify_outputs.py --run-dir results/OFFICE_RUN_20261008 --expect 35
```

`office_run.sh` 환경 변수: `POSITIONS`, `OUT`, `CORES`(동시 프로세스 수, 기본 4), `BIN_STRIDE`(주파수 bin 건너뛰기, 기본 1), `DEADLINE_MIN`(이 시간 뒤에는 새 위치를 시작하지 않음).

## 시간 추정 (이 세션의 3-bin 시험 기준, 확정치 아님)

- PathSolver 호출 1회가 약 0.43–0.5 초입니다. 복도(0.17–0.27초)보다 약 2배 느립니다. 물체가 42개로 늘었기 때문입니다.
- 위치 하나(257 bin × 19 yaw = 4883회)가 코어 하나에서 약 35–40분입니다. 35곳이면 코어 약 21–23시간, 4코어로 약 5.5시간입니다.
- `BIN_STRIDE=4`면 약 1/4(4코어로 약 1.4시간)이지만 아래 주의를 보세요. 시험 실행(위 2번)의 `median_seconds_per_call`로 다시 어림하는 것이 좋습니다.

## 주의

- **bin을 건너뛰면 분석 코드가 달라져야 합니다.** 기존 분석(`contribution_cir`을 부르는 코드)은 257개 bin의 고정 주파수 격자를 가정합니다. `BIN_STRIDE`를 1이 아닌 값으로 돌리면 npz의 `freqs_hz`를 읽도록 분석 코드를 바꿔야 합니다. 복도와 같은 분석을 그대로 쓰려면 `BIN_STRIDE=1`로 돌리세요.
- **경로 파일(`*_sweep.npz`)은 위치당 수십 MB입니다.** 저장소에는 올리지 않고(`.git/info/exclude`), 채널 `*_H.npy`와 `*_receipt.json`만 커밋하는 방식이 복도와 같습니다.
- **재질은 가정입니다.** 칸막이 chipboard 0.04 m, 책상 wood 0.03 m. 바닥·천장 concrete 0.2 m, 바깥 벽 plasterboard 0.0125 m.
- **분석 코드는 아직 없습니다.** 복도 분석의 반사 그룹 분류(이미지법)는 복도 전용이라 사무실에서는 경로가 닿은 물체 이름(npz의 `objects_cat`)으로 나눠야 합니다. LoS가 막힌 위치는 각도 모델이 적용되지 않으므로 따로 다뤄야 합니다.

## 출력

위치마다 `OUT/office_x{x}_y{y}/` 아래에: `*_H.npy` (yaw, bin, 수신 포트 ±45°, 송신 포트 ±45°), `*_sweep.npz`(경로 전체), `*_receipt.json`(설정, 버전, 해시, 시간), `scene/`(PLY 장면), `SETUP_SNAPSHOT.json`(설정 해시).
