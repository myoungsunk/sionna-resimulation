# 클라우드에서 실제 차체 probe native RF 실행

기준 개발 commit `9e7c3f3881c4e383ceca74c814182a95fb12f387`의 기본 모델을 유지한다. Snowball 경로·접속·기존 서버 image에 의존하지 않는다. 본 변경은 실행 준비이며 실제 RF 및 과학적 성능 결과가 아니다. `scientific_PASS=false`, F01/F02 OPEN을 유지한다.

## 포함한 설정과 실행 도구

- `configs/body_probe/ekf_native_noisy_body_v1.cloud.json`: 기본 JSON의 bank 경로를 실행 시 해석하고 동결 해시 계약을 추가했다. 나머지 모델·seed·Q/R·prior·neutral slip·mount 0도·range_only는 그대로다.
- `configs/body_probe/FFD_BANK_MANIFEST.json`: 원 manifest를 전체 바이트 그대로 복사했다. 원 결과를 수정하지 않았다.
- `scripts/drive_sim/run_body_probe_v2_cloud.py`: 인자 또는 환경변수로 경로를 해석하고 실제 bank 해시와 LFS pointer 여부를 확인한다. 검사를 통과해야 기존 native runner를 호출한다. 기본 호출은 사전 검사뿐이다.
- `configs/body_probe/requirements-native-cloud.txt`: source의 sionna-rt 2.0.1 / Mitsuba 3.8.0 / DrJit 1.3.1을 고정한다. NumPy 1.26.4 / SciPy 1.14.1도 명시한다. 이는 클라우드 실행 환경 정의이며 과거 캠페인의 전체 환경 동일성 주장과 다르다. 전이 의존성의 실제 설치 버전은 `pip freeze`로 보존한다.
- `docker/body-probe-native.Dockerfile`: Linux amd64 CPU/LLVM 환경. 빌드 검사는 backend import만 수행하며 PathSolver를 호출하지 않는다.

## 1. source와 실제 FFD 자료 확보

Linux cloud terminal에서 실행한다. 연구 결과 archive 전체를 받지 않고 필요한 source와 설정만 체크아웃한다.

```bash
export GIT_LFS_SKIP_SMUDGE=1
git clone --filter=blob:none --no-checkout --single-branch \
  --branch codex/noisy-probe-ekf-sionna-20261010 \
  https://github.com/myoungsunk/sionna-resimulation.git
cd sionna-resimulation
git sparse-checkout init --cone
git sparse-checkout set src scripts configs tests research .github docker
git checkout
# git-lfs가 설치되어 있어야 한다. 실제 LP±45 두 파일만 받는다.
git lfs install --local
unset GIT_LFS_SKIP_SMUDGE
git lfs pull --include="LP_plus45_bank.npz,LP_minus45_bank.npz" --exclude=""
git rev-parse HEAD
```

이미 승인된 자료 저장소에 NPZ가 있으면 LFS 다운로드 대신 `--bank-dir /data/ffd`를 사용한다. 해당 폴더에 아래 두 파일이 있어야 하며 파일명이 같은 것만으로 채택하지 않는다. LFS 인증·quota 또는 자료 권한 문제는 클라우드 제공자 측에서 해결해야 한다. 다운로드 실패 시 실행을 중단한다.

| 자료 | SHA256 |
|---|---|
| LP_plus45_bank.npz | b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b |
| LP_minus45_bank.npz | 39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9 |
| FFD_BANK_MANIFEST.json | 6ed46d657a70560a391fc574462d4a64826df3f3c6a90cef497db56deea68ea6 |

이 SHA는 앞선 L1의 동결 입력과 같은 bank라는 뜻이며 안테나 물리 정확성·LoS parity 또는 하드웨어 검증 완료를 뜻하지 않는다.

## 2. Docker CPU 환경과 사전 검사

대용량 결과·bank를 이미지에 넣지 않는다. 필요한 Git 경로만 build context로 전달한다. 아래 명령은 Linux amd64 Docker host를 대상으로 한다.

```bash
git archive HEAD src scripts configs docker | \
  docker build --platform linux/amd64 -t body-probe-native:cloud-v1 \
  -f docker/body-probe-native.Dockerfile -
mkdir -p cloud_outputs
docker image inspect body-probe-native:cloud-v1 > cloud_outputs/IMAGE_INSPECT.json
docker run --rm --entrypoint python body-probe-native:cloud-v1 \
  -m pip freeze > cloud_outputs/ENVIRONMENT.txt
# repo root 대신 실제 NPZ 두 파일이 있는 data folder도 사용할 수 있다.
docker run --rm --cpus 4 --memory 16g \
  -v "$PWD:/data/ffd:ro" \
  body-probe-native:cloud-v1 --bank-dir /data/ffd
```

기본 명령은 asset 검사와 기존 runner의 사전 검사만 실행한다. bank 누락·LFS pointer·SHA 불일치·설정 오류면 비정상 종료하며 RF 계산은 시작하지 않는다. 단, 사전 검사 통과도 PathSolver 실행 성공의 증거는 아니다.

## 3. 명시적으로 실제 native 실행

사전 검사 뒤 새 output 이름으로만 실행한다. 물리 구동·센서·EKF·실제 pose의 full/LoS 채널 생성은 다음 명령에서 처음 시작된다.

```bash
docker run --rm --cpus 4 --memory 16g \
  -v "$PWD:/data/ffd:ro" -v "$PWD/cloud_outputs:/outputs" \
  body-probe-native:cloud-v1 --bank-dir /data/ffd \
  --out /outputs/NATIVE_RUN_01 --execute-native \
  > cloud_outputs/NATIVE_RUN_01.log 2>&1
echo $? > cloud_outputs/NATIVE_RUN_01.exit_code
```

`NATIVE_RUN_01.config.json`을 결과 디렉터리 옆에 보존한다. 기존 output 또는 해당 config 파일이 있으면 덮어쓰지 않고 차단한다. native runner가 기존 규약대로 trace, 실제 pose, RF packet, full/LoS 복소 H, 실패 기록과 manifest를 저장한다. Docker version과 image ID/digest, ENVIRONMENT.txt, 로그·exit code·resolved config도 함께 보존한다.

Docker 없이 검증된 native 환경을 사용할 때:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r configs/body_probe/requirements-native-cloud.txt
# Linux LLVM backend가 별도로 필요하다. source는 llvm_ad_mono_polarized를 사용한다.
export FFD_BANK_DIR=/data/ffd
# 선택 사항: 원 manifest를 별도 자료 경로에서 제공할 때
# export FFD_BANK_MANIFEST=/data/ffd/BANK_MANIFEST.json
python scripts/drive_sim/run_body_probe_v2_cloud.py
python scripts/drive_sim/run_body_probe_v2_cloud.py \
  --out /outputs/NATIVE_RUN_01 --execute-native
```

## 범위와 검증 한계

이번 변경은 portable 설정·실행 도구다. 단위 테스트의 작은 가짜 bank 바이트는 해시/차단/호출 순서 검사에만 쓰며 RF 증거로 인용하지 않는다. 실제 PathSolver, 새로운 구동 성능 비교, held-out 평가, q_site/q_point 혼합 추정기와 cross-angle 공분산 검증은 실행하지 않았다. 기본 range_only에서는 s의 EKF 갱신을 하지 않는다. s 진단 모드와 LUT 설정은 별도 계약이다. 실행 후 성능이 나빠도 파라미터를 자동 조정하지 않는다.
