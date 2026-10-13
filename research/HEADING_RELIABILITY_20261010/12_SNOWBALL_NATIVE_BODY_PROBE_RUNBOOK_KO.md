# Snowball Native RF 실행 절차 — 실제 noisy body probe (2026-10-11)

## 0. 상태 및 원본 보존

- 코드: `codex/noisy-probe-ekf-sionna-20261010`. **정확한 checkout HEAD SHA를 실행 당시 기록한다.**
- 사용자 배포 config (원본의 bank 경로 2개만 수정):
  `/home/KMS/DRIVE_SIM_BODY_PROBE_NATIVE_CONFIG_20261011_01a1289a/ekf_native_noisy_body_v1.snowball.json`
- 신규 출력(존재하면 새 번호 사용):
  `/home/KMS/DRIVE_SIM_BODY_PROBE_NATIVE_CONFIG_20261011_01a1289a/NATIVE_RUN_01`
- 이미 보존한 fixed-truth 대조군 53,280행은 절대 교체하지 않는다.
- 이번 조건 `range_only`, `slip_mode=neutral`은 **단일 station 실제 pose Sionna 실행 smoke/무결성 검증**이다. dual-LP s-based heading 개선·실물 slip robustness·최종 scientific_PASS의 증거가 아니다.
- 현재 문서 작성 시점에는 Snowball SSH에서 실제 runner/RT를 실행하지 않았다. `NATIVE_RUN_01` 성공이나 과학적 검증을 허위로 선언하지 않는다.

## 1. 실제 source checkout과 가상환경

소스 checkout 디렉터리는 배포자 설정을 따르며, 임의로 `/home/KMS` 아래 저장소 경로를 추측하지 않는다. 기존 working tree를 덮어쓰거나 force-reset하지 않는다. 소스 checkout에서:

```bash
git status --short
git rev-parse HEAD
git branch --show-current
python -V
python -c 'import importlib.metadata as m; print({p:m.version(p) for p in ["sionna-rt","mitsuba","drjit"]})'
```

코드가 구버전이면 최신 개발 브랜치를 별도 clean checkout으로 구성한다. config는 Snowball 작업 디렉터리에 이미 존재하므로 소스 변경/커밋 없이 읽는다. 실제 RT용 python (이전 기록의 `/opt/rt-env/bin/python` 등)을 활성화하고, plain `python`이 그 환경을 가리키는지 확인한다.

## 2. Native 전제 조건 검사 (Sionna/로봇/MC **미실행**)

```bash
set -euo pipefail
CFG=/home/KMS/DRIVE_SIM_BODY_PROBE_NATIVE_CONFIG_20261011_01a1289a/ekf_native_noisy_body_v1.snowball.json
OUT=/home/KMS/DRIVE_SIM_BODY_PROBE_NATIVE_CONFIG_20261011_01a1289a/NATIVE_RUN_01
RCPT=/home/KMS/DRIVE_SIM_BODY_PROBE_NATIVE_CONFIG_20261011_01a1289a/PREFLIGHT_01.json

python scripts/drive_sim/preflight_body_probe_native.py \
  --config "$CFG" --out "$OUT" --receipt "$RCPT"
```

이 스크립트의 성공은 **단지** 다음을 증명한다: 읽을 수 있는 bank와 manifest, manifest `npz_sha256` 일치, 두 FFD port의 257-bin 주파수축 일치, pinned native 패키지 버전, git working tree 및 새로운 output 경로, `range_only+neutral` 사양의 유효성. Sionna solver 계산이나 CIR parity 검증은 수행하지 않는다. `status=PREFLIGHT_PASS_NOT_EXECUTED`가 아니면 native run을 시작하지 않는다.

`--expected-head <검토 승인한 정확한 commit SHA>`를 추가하면 remote source revision이 바뀌었을 때 사전 검사에 실패한다. 실제 승인 SHA는 최종 GitHub HEAD를 별도 기록한다.

## 3. 실제 Native RF (preflight PASS 이후에만)

```bash
set -euo pipefail
CFG=/home/KMS/DRIVE_SIM_BODY_PROBE_NATIVE_CONFIG_20261011_01a1289a/ekf_native_noisy_body_v1.snowball.json
OUT=/home/KMS/DRIVE_SIM_BODY_PROBE_NATIVE_CONFIG_20261011_01a1289a/NATIVE_RUN_01
LOG=/home/KMS/DRIVE_SIM_BODY_PROBE_NATIVE_CONFIG_20261011_01a1289a/NATIVE_RUN_01_CONSOLE.log

test ! -e "$OUT" || { echo "OUTPUT_ALREADY_EXISTS: choose another run ID"; exit 2; }
python scripts/drive_sim/run_body_probe_v2_native.py \
  --config "$CFG" --out "$OUT" --execute-native 2>&1 | tee "$LOG"
```

명령은 기존 GitHub 코드의 native Sionna FFD + PathSolver를 실제 RF-fire 시각의 true XY/yaw+RX mount에서 호출한다. Solver를 시작하기 전에 bank hash를 재확인하며 고정 XY RF grid로 대체하지 않는다. 출력 디렉터리는 절대 재사용하지 않는다. 실패하면 `FAILURE.json`과 console log를 보존하고 **새 run 번호**를 사용한다.

## 4. 실행 후 읽기 전용 무결성 감사

```bash
python scripts/drive_sim/audit_body_probe_native_run.py \
  --out "$OUT" \
  --receipt /home/KMS/DRIVE_SIM_BODY_PROBE_NATIVE_CONFIG_20261011_01a1289a/NATIVE_RUN_01_AUDIT.json
```

필수 점검: `MANIFEST.json` 출력 SHA, `STATE_TRACE.npz`의 full P6 전 단계 및 PSD, EKF 예측 P6 재생 계산, physical oracle time/pose와 RF packet 정렬, 복소 `H_full` shape, dual LP P1/P2/s 항등식, RF 데이터와 posterior 일치. 이 감사에서 `STORED_TRACE_AUDIT_PASS_NOT_SCIENCE`가 나와도 실물 accuracy나 native FFD/LoS parity의 승인 근거가 아니다.

## 5. 범위별 판정

- 새 native H/LoS 생성 및 완료 trace: **실제 command 실행과 파일 검사 후에만 COMPLETE**.
- `range_only`: RF s는 *관측·저장만*, EKF의 s-based heading 보정은 **NOT_TESTED**.
- `slip_mode=neutral`: 물리적 slip event의 실제 위치 이동 효과는 **NOT_TESTED**. 휠 직경비·wheelbase를 run에서 샘플링하는 것과 물리 slip 검증은 다르다.
- `scientific_PASS=false`, `F01/F02=OPEN`: 그대로 유지. 추가 독립 FFD parity, full-P6 consistency/coverage, site/point covariance, 12case × seeds, cross-environment 자료를 갖춘 뒤 과학적 주장을 재검토한다.
