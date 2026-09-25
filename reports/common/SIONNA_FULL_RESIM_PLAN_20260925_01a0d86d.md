# Sionna 전체 환경 재시뮬레이션 실행 계획 및 진행 원장

- 계획 ID: `SIONNA_FULL_RESIM_20260925_01a0d86d`
- 작성일: 2026-09-25 KST. 상태: **PLAN_READY / IMPLEMENTATION_NOT_STARTED / FULL_RUN_NOT_STARTED**.
- 목적: 다른 Codex 작업이 이 문서만 읽고 입력 준비, 구현, Snowball 실행, 결과 회수와 검증을 이어갈 수 있게 한다.
- 이번 요청은 계획서 작성이다. 이 문서의 작성은 전체 계산 실행 완료나 G2 PASS를 뜻하지 않는다.
- 이후 담당자는 **이 문서 맨 아래 진행 로그에 추가**한다. 기존 로그를 삭제하거나 실패를 성공으로 덮어쓰지 않는다.

## 1. 작업 범위와 확정된 방향

전체 101장면에서 최신 TX/RX와 Sionna용 형상으로 RF를 새로 계산한다. 계산은 **Snowball / KMS**에서 수행하고 로컬은 입력·설정·코드 기본 검증, 결과 회수, 소비 확인에 사용한다. 대량 H→CIR·검출 후처리도 Snowball에서 수행한다.

전파 엔진은 수정하지 않은 Sionna RT 2.0.1 PathSolver/FieldCalculator. 자체 volume/TRT 전파 모듈은 생산 실행기에 연결하지 않는다. 기존 결과·원자료·Stage 7/8·이전 revision은 보존한다. 최종 감사·봉인, G3, 분류기 학습·OOF·논문 성능 판정은 이 계획의 실행 범위 밖이다.

## 2. 전체 대상: 실제 파일에서 집계한 수량

| 입력 계열 | 링크/위치 수 | 입력 위치(아래 R 기준) |
|---|---:|---|
| L1 | 12,000 | `R/inputs_v6/L1/INPUT.json` |
| L1multi | 12,000 | `R/inputs_v6/L1multi/INPUT.json` |
| L2static | 3,000 | `R/inputs_v6/L2static/INPUT.json` |
| L2multi | 6,000 | `R/inputs_v6/L2multi/INPUT.json` |
| C1_static | 6,000 | `R/common/LINKS.jsonl` |
| C1_multi | 6,000 | 동일 |
| C3 | 120,000 | 동일 |
| STATIC9_NATIVE_OVERLAY | 9 | 아래 STATIC9 계약의 trajectory.samples |
| 합계 | **165,009** | 생산 165,000 + 개방형 기준 위치 9 |

공통 동적 프레임은 `R/common/FRAMES.jsonl`의 **37,500개**이며 별도 RF 링크 수에 더하지 않는다. 모든 입력의 scene_id 합집합이 새 형상의 **101장면**과 일치함을 확인했다. 계열 사이에 같은 장면이 있으므로 계열별 장면 수를 더하지 않는다.

STATIC9 원계약은 이상적 Jones 응답·3주파수·무잡음이다. 이번 101장면 전체 운용에서는 **같은 형상·위치·자세에 공통 FFD/257주파수/합성 운용점을 적용하는 새 overlay**를 만든다. 이를 원계약의 재현 또는 기존 analytic 검증 PASS로 표시하지 않는다. `source_contract`와 `operating_contract`를 별도 기록하고 clean 채널도 보존한다. 이 변경은 전체 환경을 동일 운용점으로 재계산하기 위한 계획상의 명시적 처리이다.

현재 41행 refresh는 전체 중 일부일 뿐이다. 이번 전체 campaign은 그 결과에 의존하지 않고 165,009개를 새로 계산한다. 기존 실행을 강제로 종료하거나 기존 결과를 복사해 완료 수에 넣지 않는다. 과거 6,939 등 다른 campaign의 숫자를 이 대상에 임의로 더하지 않는다.

## 3. 실제 원본·참고 파일 위치

모든 로컬 경로의 루트 W는 `D:/codex/raytracing_modules/rt_cp_uwb`이다. 약어는 이 문서에서만 쓰며 manifest에는 해석된 경로와 SHA256을 적는다.

- **R — 최신 RX 보정 전체 입력:** `D:/codex/raytracing_modules/rt_cp_uwb/results/SIONNA_G2_RX_RELOCATED_20260924_01a0d320_R2`
  - `inputs_v6/{L1,L1multi,L2static,L2multi}/INPUT.json`
  - `common/LINKS.jsonl`, `common/FRAMES.jsonl`
  - `CHANGED_LINKS.json`: 보정 대상 41행. `MOVES.json`: 26개 물리 RX 위치.
  - 이 폴더는 전체 입력을 포함한다. `RelocatedInputs.rows`는 41행만 반환하므로 전체 manifest 작성에 그대로 쓰지 않는다.
- **G — 실제 실행할 101장면 형상:** `D:/codex/raytracing_modules/rt_cp_uwb/results/SIONNA_NATIVE_GEOMETRY_20260925_01a0d83b`
  - `SCENE_MESH_MANIFEST.json`, `SIONNA_SCENES/`, `MODEL_CONTRACT.json`, `FINAL_MANIFEST.json`, `STATUS.json`
  - 상태 `NATIVE_SLAB_GEOMETRY_PASS`: 326mesh / 25,438삼각형. 72기둥은 중공 콘크리트 판재. 고체 기둥의 RF 등가 주장은 하지 않는다.
  - `CONFIG.json`의 rows는 41개뿐이다. **이 rows를 전체 입력으로 사용하지 않는다.**
- **B — Eφ 비반전 FFD bank:** `D:/codex/raytracing_modules/rt_cp_uwb/results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank`
  - 6개 `*_bank.npz`, `BANK_MANIFEST.json`. 실제 CONFIG의 bank_sha256과 대조한다.
- **C — 운용 설정 참고:** `D:/codex/raytracing_modules/rt_cp_uwb/results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json`
  - noise/detector/solver/ports를 이어받되 상태 문구의 producer_bound 등을 성공 증거 없이 승격하지 않는다.
- **STATIC9 위치·자세 원계약:** `D:/codex/raytracing_modules/DRIVE_EXPORT_RT_DUAL_ENGINE_20260915/cp2_work_remote/COMMON_ENVIRONMENT_POSE_CONTRACT.json`
- **형상별 분류 참고:** `D:/codex/raytracing_modules/rt_cp_uwb/results/SIONNA_G1_DESIGN_CLOSURE_20260923/SCENE_DRAFT.json`
- **이번 집계와 입력 SHA:** [PLAN_INPUT_SNAPSHOT.json](../../results/SIONNA_FULL_RESIM_20260925_01a0d86d/PLAN_INPUT_SNAPSHOT.json)

기존 재사용 코드(물리 계산은 native runtime의 기본 동작 유지):

| 파일 — W 기준 | 역할/주의 |
|---|---|
| `scripts/g2_completion/sionna_native_runtime.py` | native RF·FFD 결합; 기본 stop=41, 출력 파일 ID와 range 인자를 전체용으로 점검 |
| `scripts/g2_completion/run_native41_refresh.py` | 전송·Docker·결과 회수 참고. 41행/14lane 고정이라 전체 실행에 직접 사용 불가 |
| `scripts/g2_completion/finish_sionna_native41.py` | H 합산·CIR·검출·소비 검증 참고. 41행 assert 제거한 신규 전체용 구현 필요 |
| `scripts/g2_completion/summarize_native41_refresh.py` | 경로 통계·분류 미정·소비 binding 참고. 전체용 streaming 구현 필요 |
| `rt_cp_uwb_py/g2_native_channel.py` | native a/tau 합산, SHA 및 채널 소비 |
| `rt_cp_uwb_py/g2_scoped_channel.py` | ARMS 및 observe; 기존 운용점으로 CIR/잡음/검출 |
| `rt_cp_uwb_py/g2_native_summary.py` | 경로 요약 참고; 기존 41행 binding과 구분 |
| `rt_cp_uwb_py/l1_l2_rf_synthesis.py` | historical_mount_frames: L계열 기존 자세 의미 보존 |
| `rt_cp_uwb_py/c1_c3_geometry.py` | panel_corners: 동적 판재 생성 |

## 4. 새 폴더와 생성할 파일

**로컬 campaign:** `D:/codex/raytracing_modules/rt_cp_uwb/results/SIONNA_FULL_RESIM_20260925_01a0d86d`

**Snowball campaign:** `/home/KMS/SIONNA_FULL_RESIM_20260925_01a0d86d` — 계획 경로, 작성 시점 미생성.

```text
로컬 campaign/
  PLAN_INPUT_SNAPSHOT.json       # 이번 계획의 실제 집계·원본 SHA (생성됨)
  PLAN_VALIDATION.json           # 계획 링크·수량·문구 확인 (계획 작성 단계)
  PLAN_ARTIFACT_MANIFEST.json    # 계획 초기본 SHA; 이후 로그 추가 시 과거 SHA 보존
  00_inputs/                    # 아래부터 실행 단계에서 생성
    CONFIG.json                 # 공통 물리·운용 설정, rows는 manifest 참조
    TARGETS.jsonl               # 전체 165009개 타깃, canonical key/pose/frame
    TARGET_CENSUS.json          # 계열·장면·frame 결속 및 중복/누락 검사
    INPUT_MANIFEST.json         # 원본, 코드, config, FFD, 기하 SHA
    BATCHES.jsonl               # batch_id, target IDs, count, config/input hash
    dynamic/                   # 모든 필요한 frame의 판재, frame hash 기반 이름
    STATIC9_OVERLAY_CONTRACT.json
  01_local_checks/              # 기본 테스트·배치 dry-run·입력 검증 로그
  02_remote_receipts/            # 서버 identity/version/load/disk/staging 증거
  03_pilot/                     # 대표 실행 요약·시간/저장량 측정·자원 계획
  04_progress/                  # 회수한 STATUS, 완료/실패/재시도 목록
  05_results/                   # 회수한 원본 NPZ 및 후처리 결과, 배치별 보존
  06_validation/                # 전체 coverage, SHA, consumer, 숫자 검증
  07_reports/                   # 실행 보고서·데이터 설명·최종 실행 상태

Snowball campaign/
  input/                        # 입력/기하/FFD, 컨테이너 read-only mount
  code/                         # 실행 시점 코드 snapshot, SHA 고정
  batches/<batch_id>/attempt_001/
    raw/                        # target별 native 원본, RUNTIME/STATUS
    production/                 # H/CIR/검출/파생값
    logs/                       # stdout/stderr와 시간, exit code
    MANIFEST.json               # 배치 산출물 SHA
    COMPLETE.json               # 검증 성공 후에만 원자적으로 생성
  controller/                   # 제출/중단재개 상태와 소유 job PID/container ID
  exports/                      # 검증된 분할 archive와 SHA, 전체 단일 ZIP 금지
```

위 예정 폴더/파일은 존재한다고 가정하지 않는다. `PLAN_INPUT_SNAPSHOT.json` 이외 입력·실행 산출물은 단계별 생성한다. 로컬과 서버 root는 manifest에 별도 필드로 두며 Windows 절대경로를 컨테이너에서 직접 열지 않는다.

**신규 구현 예정 파일 — 아직 없음:**

- `W/rt_cp_uwb_py/g2_full_inputs.py`: 전체 타깃 정규화·자세·frame 연결, native 입력 전용.
- `W/scripts/g2_completion/prepare_sionna_full.py`: 전체 대상·배치·payload 작성 및 로컬 검증.
- `W/scripts/g2_completion/run_sionna_full.py`: stage/pilot/launch/status/resume/collect 제어.
- `W/scripts/g2_completion/finish_sionna_full.py`: 서버 batch별 후처리·검증·완료 receipt.
- `W/scripts/g2_completion/verify_sionna_full.py`: 전체 coverage·SHA·생산 소비 확인.
- `W/tests/test_g2_full_inputs.py`, `W/tests/test_g2_full_resume.py`: 전체 입력·배치/재개의 핵심 회귀.

기존 41행 실행기를 덮어쓰지 않고 신규 전체용 진입점을 추가한다. native runtime 수정이 필요하면 전체용 snapshot을 별도 보존하고 최소한의 I/O·range 변경만 한다. 엔진 변경이나 경로 재사용 최적화는 본 계획의 기본 전제가 아니다.

## 5. 고정할 계산 계약

- runtime: Sionna RT 2.0.1 / Mitsuba 3.8.0 / DrJit 1.3.1, `llvm_ad_mono_polarized`.
- Docker image: `sha256:77244efd2cb92abfc3be258d97da2c76b4c91eeb29e1aeb50d7dc57ed72ad791`.
- 컨테이너 Python: `/opt/rt-env/bin/python`. 호스트 python3는 구버전이므로 전체 후처리를 호스트 환경에서 실행하지 않는다.
- solver: max_depth=3, samples_per_src=100000, max_num_paths_per_src=1000000, seed=20260924, synthetic_array=true.
- 직달·정반사·투과 ON; diffraction/edge_diffraction/diffuse_reflection OFF. 탐색 완전성·full-wave 정확성 주장은 하지 않는다.
- 주파수: `6250400000 + 1950000*k Hz`, k=0…256. 실제 bank 배열과 정확히 대조.
- CP=[RHCP,LHCP], LP_AXIS=[LP_X,LP_Y], LP_DIAG=[LP_plus45,LP_minus45]. 각 2×2, 총 **12 port pairs**. 그룹 간 24개 조합은 미계산이며 zero 신호로 오인되지 않도록 valid mask/arm별 저장을 사용한다.
- incident 1 W/active mode, 290 K, NF 6 dB, ENBW 1.95 MHz, coherent averages=64. 하드웨어 보정값이 아닌 합성 운용점.
- 잡음: `noise_var_H_bin=4.856640061591484e-16`, 동일 link/frame/replicate의 CP/LP 잡음 짝 유지. seed key에 batch/attempt/arm을 넣지 않는다.
- Hann·1028tap CIR. 기존 observe와 같은 정규화/지연축/검출 알고리즘을 사용하고 raw H 및 clean/noisy CIR 모두 저장.
- 20,000회 잡음 검증의 기존 `executed=false`를 완료로 바꾸지 않는다. 이번 결과를 경험적 오탐률 적격성 입증으로 표현하지 않는다.

## 6. 단계별 실행 지시와 종료 조건

### S0 — 최신 입력 확정 (로컬, RF 호출 0)

1. 입력 snapshot SHA와 현재 파일 대조. 달라졌으면 자동으로 최신 파일을 채택하지 말고 변경 원인을 기록해 새 입력 revision을 만든다.
2. 네 L계열 전체 links, common LINKS/FRAMES, STATIC9 samples를 TARGETS.jsonl로 정규화한다. family/case_id/anchor_id/unit_id/frame/epoch_id/replicate 등 원본 키를 보존하고 canonical JSON의 SHA256으로 target_id를 생성한다. 빠진 optional field는 명시적 null로 구분한다. 목록 index나 RX 좌표만으로 ID를 만들지 않는다.
3. 41행은 R의 보정 좌표가 CHANGED_LINKS와 일치해야 한다. 나머지 전체 입력도 동일 R에서 읽고 이전 좌표로 fallback하지 않는다. TX와 RX 모두 닫힌 방 내부·재료/표면 외부 조건을 확인한다. 개방형 STATIC9는 허용 사유를 기록한다.
4. common은 (unit_id,frame)으로 FRAMES를 연결하고 canonical_scene_hash, RX tag_pose와 링크 위치를 확인한다. 이동 판재를 **전체 관련 frame**에서 생성한다. 기존 41행 payload의 12개 판재만 복사하지 않는다.
5. L계열은 historical_mount_frames, common은 기존 yaw 의미를 보존한다. STATIC9는 quaternion wxyz를 명시적으로 변환한다. 모든 회전행렬 RᵀR≈I, det≈+1. 안테나가 기본 identity로 바뀌지 않도록 대표 원본과 대조한다.
6. mesh와 scene material을 G에서만 읽는다. old source_row에 남은 RF 레이블/기하를 생산 입력으로 채택하지 않는다.

종료: 165009개 unique target, 101장면 누락 0, 37500 common frame 결속, RX 수정 41행 확인, 비유한 좌표/회전·잘못된 frame·금지 위치 차단 0. 예상과 다른 개수는 필터로 맞추지 않고 원인을 기록한다.

### S1 — 전체 실행기와 로컬 기본 검증 (로컬, RF 호출 0)

- 전체 165009행을 메모리에 모든 RF 배열과 함께 올리지 않는다. scene/frame 단위 재사용 가능한 입력을 묶고 stream/batch 처리한다.
- 41 고정 assert/range/chunk, family_case_id만 사용하는 파일명, 3-depth reshape 가정, 운영체제 경로를 점검한다. depth=3 고정 계약은 명시 검증한다.
- 타깃별 원본 쓰기를 임시 파일→같은 파일시스템 원자 rename으로 완료한다. 실패 시 attempt를 새로 만들고 partial output과 로그를 보존한다.
- 완료 판정은 파일 존재가 아니라 config/input/runtime/output SHA + 검증 receipt이다. 재개는 완료된 target만 건너뛴다. 설정 변경은 새 revision으로 분리한다.
- 단위시험: 모든 계열 파싱, 수정41 결속, frame mismatch 거부, STATIC9 quaternion, key 충돌, 끝 batch 누락, 빈 경로 정상 신호, partial/손상 결과 재개 거부, 같은 noise seed 유지.
- 관련 기존 native/summary/scoped 시험 + 아래 기본 repository 검사를 수행한다. 전체 느린 회귀는 변경 범위에 따라 실행 여부를 명시하며 이전 통과 숫자를 이번 결과로 재사용하지 않는다.

종료: dry-run coverage 165009/165009, 새 테스트/관련 회귀 통과, staging payload SHA·예상 산출물 목록 작성. 이 단계에서 FULL_RUN_COMPLETE를 쓰지 않는다.

### S2 — Snowball 준비와 대표 end-to-end 실행

- `ssh -o BatchMode=yes -o PasswordAuthentication=no Snowball`로 KMS 확인. root fallback·비밀번호 저장 금지.
- CPU/load/RAM/disk와 기존 작업을 확인한다. 이번 확인 시 /home 여유 701G였지만 실행 직전 다시 측정한다.
- 고정 Docker image 존재와 컨테이너 runtime 버전을 대조. 컨테이너 사용자 UID/GID는 `id` 실측값 사용. input/code는 읽기 전용, output만 쓰기 허용.
- B의 6개 bank를 이번 campaign input/bank에 SHA 검증하여 준비한다. 이전 41행 remote 폴더에 영구 의존하지 않는다.
- 로컬 연결 종료에도 지속되도록 서버 controller를 nohup 등으로 실행하고 PID·container ID·명령·로그 위치를 기록한다. 로컬 SSH 연결 수명에 전체 계산을 묶지 않는다.
- 대표 subset은 family 7종, STATIC9 9종, 가구·중공 기둥·유리/투과·동적 판재·보정 RX를 포함하는 결정론적 목록으로 작성한다. 시작 32행을 목표로 하되 필요한 특성 누락 시 최소한으로 추가한다. full 257 bins / 3 arms로 실행한다.
- 기존 native LOS fixture로 FFD/방향·편파 결합을 확인하고 대표 H→CIR→검출→consumer를 끝까지 확인한다. 새 물리 모델 연구나 과도한 수렴 campaign은 추가하지 않는다.
- 초깃값은 **2 container × 4 threads**. 실제 다른 작업 부하·throughput/RAM을 보고 최대 8 container를 상한 제안값으로 조정한다. CPU 할당과 DrJit thread 수 모두 명시한다. 8개 실행은 자동 보장값이 아니다.

종료: 대표 실행·consumer 통과, 모든 필요한 장면 특성 포함, `CAPACITY_PLAN.json`에 측정 초/row·bytes/row·메모리·전체 예상량·배치/동시성 결정 기록.

### S3 — 전체 계산 (Snowball)

- 기본 호출량 **165009×257×3 = 127,221,939회**. 이는 현재 알고리즘의 계획량이며 smoke/retry는 별도 집계한다. 동일 설정 pilot 결과가 완전하면 본 campaign의 완료 target으로 포함하여 중복 계산하지 않는다.
- 시간 예상은 warm-up과 실측 aggregate rows/hour로 산정한다. 단일 행의 최단 시간으로 전체 ETA를 낙관 계산하지 않는다. 저장량은 raw+production+archive 중복과 local 여유를 포함해 산정한다.
- batch 크기는 pilot 후 고정한다. 초기 제안 16 targets/batch, 목표 15–60분 및 메모리 한도 내에서 조정; 한 장면/프레임을 가능한 묶되 count를 바꾸지 않는다.
- 여유 공간에 맞는 bounded queue로 계산→후처리→분할 전송한다. 보존용량이 부족하면 새 batch 제출을 멈추고 부족량을 보고한다. 무단 삭제나 저장 정보 축소는 하지 않는다.
- 일시적 작업 실패 자동 재시도는 최대 2회(총 3 attempts). NaN/좌표 mismatch/SHA drift 등 결정론적 실패는 반복하지 말고 원인·영향 target을 기록한다. 실패한 target을 통계에서 조용히 제외하지 않는다.
- 각 batch 후 STATUS 집계: expected/completed/failed/running/pending, 실제 solver 호출, elapsed, bytes. 165009 unique target 완료 전 전체 완료 상태 금지.

### S4 — 후처리·저장·회수 (대량 처리는 Snowball)

타깃별 보존:

- native a/tau/valid, interaction event, object/primitive ID, path vertex, departure/arrival 방향(저장 또는 재구성 정의), runtime/source SHA.
- 모든 257주파수×3 arms의 경로 원본. path index는 **주파수 내부 식별자**이며 주파수 간 같은 index가 같은 경로라는 가정 금지.
- complex128 H 합산, clean/noisy CIR, 주파수/지연축, port 순서/valid mask, noise seed·variance, 검출 상태·ToA proxy, 실제 geometric distance, endpoint/rotation/frame.
- LoS 여부·반사/투과 횟수·비간섭 경로 전력비·지연 통계. 전력비 정의를 interference 포함 채널 전력비와 혼동하지 않는다.
- NoLoS는 native 유효 LoS의 기하 기준; 주파수/arm 불일치는 점검 대상으로 기록. RD-LoS/HB-near-delay/HB-prior는 null+DEFERRED_BY_USER 유지. 나중에 계산할 수 있도록 경로/CIR을 상세 보존.
- 계산 실패는 COMPUTATION_FAILED, 무신호/미검출은 MISSED_OR_NO_SIGNAL 등 계약된 상태로 구분한다.

배치 manifest와 archive SHA를 서버에서 생성하고 로컬 회수 후 다시 대조한다. 서버 원본 삭제는 이 계획에 포함하지 않는다. 저장공간 문제는 사전 용량 계획으로 해결하며 자동 정리하지 않는다.

### S5 — 전체 완료 확인과 생산 입력 연결 (로컬 기본 + 서버 전체 검사)

1. target set equality, 101scene coverage, bin/arm/port 개수, 중복/누락/실패 0, 모든 원본·코드·출력 SHA 확인.
2. 서버에서 모든 타깃의 H 경로 합산·유효 수치·CIR 및 noise pairing 확인. 로컬에서는 회수 SHA와 모든 계열/형상 대표 샘플을 실제 소비 함수로 읽기 확인한다.
3. `PRODUCTION_BINDING.json`에 이번 CONFIG/TARGETS/geometry/bank/source manifest hash 및 데이터 저장 root를 명시한다. 기존 기본 입력을 덮어쓰지 말고 새 binding을 명시적으로 선택하게 한다.
4. 실제 consumer가 보정 RX, 새 geometry와 이번 결과를 읽는지 readback receipt에 기록한다. 역사적 label을 새 RF 결과에 조용히 붙이지 않는다.
5. `07_reports/EXECUTION_REPORT_KO.md`, `DATA_GUIDE_KO.md`, `RUN_STATUS.json` 작성. 수량·파일 위치·테스트·실패/재시도·변경/이동·미완료를 적고 이 계획서 로그에 연결한다.

종료 상태는 `FULL_NATIVE_SIMULATION_COMPLETE_UNSEALED`로 제한한다. 이는 명시된 Sionna 모델/설정 아래 전체 산출·소비 완료이며, 자동으로 G2 최종 PASS·봉인·탐색 완전성·하드웨어 정확성을 의미하지 않는다.

## 7. 명령과 재개 순서

### 지금 바로 사용 가능한 읽기/기본 검증 명령 (PowerShell)

```powershell
Set-Location 'D:/codex/raytracing_modules/rt_cp_uwb'
Get-Content -Raw 'reports/common/SIONNA_FULL_RESIM_PLAN_20260925_01a0d86d.md'
Get-Content -Raw 'results/SIONNA_FULL_RESIM_20260925_01a0d86d/PLAN_INPUT_SNAPSHOT.json'
ssh -o BatchMode=yes -o PasswordAuthentication=no Snowball whoami
py -3.10 scripts/00_inventory.py --check
py -3.10 scripts/01_build_manifest.py --check
py -3.10 scripts/02_validate_dataset.py
py -3.10 scripts/06_build_reports.py --check-links
```

### 구현할 CLI 계약 — 아래 파일은 아직 없으므로 현재 실행하지 않는다

```powershell
$campaignRoot = 'D:/codex/raytracing_modules/rt_cp_uwb/results/SIONNA_FULL_RESIM_20260925_01a0d86d'
py -3.10 scripts/g2_completion/prepare_sionna_full.py --campaign-root $campaignRoot --dry-run
py -3.10 scripts/g2_completion/prepare_sionna_full.py --campaign-root $campaignRoot --write-inputs
py -3.10 scripts/g2_completion/run_sionna_full.py --campaign-root $campaignRoot --stage
py -3.10 scripts/g2_completion/run_sionna_full.py --campaign-root $campaignRoot --pilot
py -3.10 scripts/g2_completion/run_sionna_full.py --campaign-root $campaignRoot --launch
py -3.10 scripts/g2_completion/run_sionna_full.py --campaign-root $campaignRoot --status
py -3.10 scripts/g2_completion/run_sionna_full.py --campaign-root $campaignRoot --resume
py -3.10 scripts/g2_completion/run_sionna_full.py --campaign-root $campaignRoot --collect
py -3.10 scripts/g2_completion/verify_sionna_full.py --campaign-root $campaignRoot
```

`--resume`는 원격 활성 controller가 있으면 중복 제출하지 않고 그 상태를 반환해야 한다. `--collect`는 배치별 전송을 재개할 수 있어야 한다. 서버 controller가 `finish_sionna_full.py --campaign-root <server-root> --batch-id <id> --attempt <n>`를 컨테이너 안에서 호출한다. CLI 구현이 이 계약과 달라지면 **실행 전에 이 절을 수정하고 변경 이력을 추가**한다.

## 8. 다음 작업이 처음 해야 할 일

1. 본 문서와 PLAN_INPUT_SNAPSHOT을 읽고 현재 SHA·진행 로그 확인.
2. 이 campaign의 원격 controller 존재 여부부터 확인하여 중복 실행 방지. 별도 41행 작업과 혼동 금지.
3. 현재 단계는 **S0/S1 미실행**이다. 전체 입력 정규화와 신규 전체용 실행기 구현부터 시작한다.
4. 기하 자체의 재설계·옛 volume 모델 연구·기존 실패 campaign의 재실행으로 돌아가지 않는다.
5. 실제 완료한 단계만 체크하고 산출물·명령·결과를 아래에 추가한다.

## 9. 단계 체크리스트

- [x] 계획 작성: 실제 전체 입력 집계, 101장면 대응 및 입력 SHA 기록
- [ ] S0 전체 TARGETS / 입력·좌표·자세·동적 frame 검증
- [ ] S1 전체 실행기 / 로컬 기본 검증 / dry-run
- [ ] S2 Snowball staging / 대표 실행 / 시간·저장량·자원 결정
- [ ] S3 전체 RF 재계산
- [ ] S4 전체 H·CIR·검출·경로 상세 저장 및 회수
- [ ] S5 전체 coverage / 생산 소비 / 실행 보고서
- [ ] 최종 감사·봉인 — **본 계획 실행 범위 밖, 자동 수행 금지**

## 10. 진행 로그 — 아래에 계속 추가

### 2026-09-25 — 계획 초기본 작성

- 요청: 다른 작업이 이어갈 수 있는 구체적 계획 작성. 전체 재시뮬레이션 위치 Snowball, 로컬은 기본 검증.
- 수행: 전체 입력 읽기 집계, 165000+9개/101장면/37500frame 확인; 현재 코드의 41행 제한 확인; KMS 접속·Docker image 존재 확인.
- 신규 산출물: 본 계획서, PLAN_INPUT_SNAPSHOT.json, PLAN_VALIDATION.json, PLAN_ARTIFACT_MANIFEST.json.
- 변경·이동: 신규 문서/계획 증거만 추가. 기존 입력·코드 변경 0, 파일 이동/삭제 0.
- 전체 RF 호출: **0회**. 이번 계획의 원격 폴더·새 실행기·전체 산출물은 아직 생성하지 않음.
- 다음 행동: S0/S1 전체 TARGETS 준비 및 실행기 구현.

### 후속 기록 양식 (복사해서 아래에 추가)

```text
### YYYY-MM-DD HH:mm KST — 담당 작업 ID / 단계 / 상태
- 실행 목적·이전 로그와 달라진 점:
- 실제 명령 및 실행 위치(로컬/Snowball/container):
- 입력/코드/config SHA 및 batch/attempt:
- 결과: expected / completed / failed / pending, 이번·누적 RF 호출:
- 산출물 절대경로와 receipt:
- 검사/시험 결과와 실행하지 않은 검사:
- 실패 원인·재시도·모델/설정 변경(없으면 없음):
- 파일 변경/이동 및 원본 보존:
- 원격 controller PID/container ID와 로그 위치:
- 다음 정확한 명령/작업, 남은 제한:
```
