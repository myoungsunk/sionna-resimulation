# Sionna 전체 재시뮬레이션 GitHub 업로드 목록

작성 2026-09-25. 목록 작성만 수행했으며 Git 저장소 생성·업로드·파일 이동·전체 RF 실행은 하지 않았다.

**GitHub 인계용 코드·계획 + 별도 필수 데이터 + 아직 구현해야 할 전체용 실행기**를 구분한다. 현재 목록을 올리는 것은 후속 개발 인계이며 곧바로 전체 재시뮬레이션 실행 가능함을 뜻하지 않는다.

- [실행 계획 및 누적 진행 로그](SIONNA_FULL_RESIM_PLAN_20260925_01a0d86d.md)
- [개별 파일 목록 CSV](SIONNA_FULL_RESIM_GITHUB_FILES_20260925_01a0d87a.csv): 절대 원본 경로, 배포 경로, 존재 여부, 바이트, SHA256, 용도 포함.
- W = `D:/codex/raytracing_modules/rt_cp_uwb`.

## 1. GitHub에 올릴 기존 파일

| 위치 — W 기준 | 포함할 파일/이유 |
|---|---|
| `reports/common/` | 실행 계획서, 이 업로드 안내서, 개별 파일 목록 CSV, CLAIM_BOUNDARY.md |
| 루트 | AGENTS.md, pytest.ini |
| `rt_cp_uwb_py/` | 모든 `.py`. __init__.py가 여러 모듈을 가져오므로 native 파일 몇 개만 분리하면 import가 깨질 수 있음 |
| `src/qclean_uwb/` | 모든 `.py`. 프로젝트 검증·보고 공통 코드 보존 |
| `scripts/g2_completion/` | CSV에 지정한 8개 기존 native 실행/후처리/형상 코드. 41행 전용 실행기는 참고이며 전체용이 아님 |
| `tests/` | CSV에 지정한 native channel/geometry/summary, scoped channel, RF closure 시험 5개 |
| `results/SIONNA_NATIVE_GEOMETRY_20260925_01a0d83b/` | 형상 revision 전체: 357파일, 약 24 MiB. mesh만 떼지 않고 계약·SHA manifest·증거·payload도 함께 보존 |
| `results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json` | noise/detector/solver/ports 설정 원본. rows는 41개이므로 전체용 입력으로 바로 사용 금지 |
| `results/SIONNA_G1_DESIGN_CLOSURE_20260923/SCENE_DRAFT.json` | 101장면 계열·크기·개방형 구분 참고 |
| `results/SIONNA_FULL_RESIM_20260925_01a0d86d/` | PLAN_INPUT_SNAPSHOT.json, PLAN_VALIDATION.json, PLAN_ARTIFACT_MANIFEST.json, REPORT_LINK_CHECK.log |
| `inputs/reference/COMMON_ENVIRONMENT_POSE_CONTRACT.json` | 아래 외부 경로의 STATIC9 원계약을 패키징 시 복사할 목적지. **현재 복사하지 않았음** |

STATIC9 원본은 `D:/codex/raytracing_modules/DRIVE_EXPORT_RT_DUAL_ENGINE_20260915/cp2_work_remote/COMMON_ENVIRONMENT_POSE_CONTRACT.json`이다. 코드 패키지의 일부 volume 모듈이 import 의존성으로 포함되더라도 실제 RF producer는 native Sionna만 사용한다.

## 2. 반드시 필요하지만 별도 전달할 큰 데이터

| 원본 위치 — W 기준 | 용량 | 내용 |
|---|---:|---|
| `results/SIONNA_G2_RX_RELOCATED_20260924_01a0d320_R2/` | 약 481.51 MiB | 네 L계열 INPUT.json, common LINKS/FRAMES.jsonl, 변경41행·이동26위치·입력 manifest. 이 폴더 전체 전달 |
| `results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/` | 약 1414.35 MiB | 6개 FFD NPZ와 BANK_MANIFEST.json |

일반 코드 이력과 분리해 Snowball에 직접 전송하는 구성을 권한다. Git LFS 등으로 관리하려면 별도 저장 정책을 선택하되, 이 문서는 서비스 용량·요금·제한을 판정하지 않는다. 어느 방식이든 CSV에 있는 SHA를 전송 전후 비교한다.

예정 원격 루트: `/home/KMS/SIONNA_FULL_RESIM_20260925_01a0d86d/input/`.
원본 데이터는 `input/source_inputs/`, FFD는 `input/bank/`, 정규화한 TARGETS 및 mesh는 staging 규약에 맞춰 배치한다. Snowball SSH 계정은 **KMS**만 사용한다. GitHub에는 비밀번호·개인키·개인 SSH 설정을 올리지 않는다.

## 3. 구현 후 추가해야 할 파일 — 지금은 없음

- `rt_cp_uwb_py/g2_full_inputs.py`
- `scripts/g2_completion/prepare_sionna_full.py`
- `scripts/g2_completion/run_sionna_full.py`
- `scripts/g2_completion/finish_sionna_full.py`
- `scripts/g2_completion/verify_sionna_full.py`
- `tests/test_g2_full_inputs.py`, `tests/test_g2_full_resume.py`
- `requirements-sionna-full-local.txt`: 실제 import/관련 시험으로 확인한 로컬 의존성. 현재 다른 campaign requirements를 그대로 재현 환경으로 선언하지 않는다.
- `runtime/sionna-full/RUNTIME_LOCK.json`: 이미지 digest, Sionna/Mitsuba/DrJit 버전, Python 경로, variant와 실행 방법.
- `config/sionna_full_paths.example.json`: repo root/입력/기하/bank/remote root의 환경별 경로 매핑. 비밀정보 제외.

Snowball에는 고정 Docker image가 확인됐다. digest는 `sha256:77244efd2cb92abfc3be258d97da2c76b4c91eeb29e1aeb50d7dc57ed72ad791`, Python은 `/opt/rt-env/bin/python`이다. 이는 GitHub에서 이미지를 내려받을 수 있다는 뜻이 아니다. 다른 서버에서 실행하려면 image 배포 또는 재현 가능한 Docker build recipe를 추가해야 한다.

## 4. 업로드 전에 필요한 경로 정리

1. 기존 manifest는 원본 SHA 증거로 보존하고 Windows 절대경로를 그 파일 안에서 치환하지 않는다.
2. 새로운 staging manifest가 원본 절대경로 → repo 상대경로/서버 경로를 대응시켜야 한다. old input manifest의 로컬 파일을 Snowball에서 직접 읽으려 하지 않는다.
3. 저장소 밖 STATIC9 파일을 지정 목적지로 복사하고 두 파일의 SHA 일치 기록. 이전 파일 이동·삭제 금지.
4. 전체 manifest의 165009개 대상·101장면·37500프레임을 구성한다. 기존 41행 CONFIG/실행기를 전체로 오인하지 않는다.
5. 깨끗한 checkout + 별도 데이터 배치 상태에서 import, 관련 시험, dry-run을 확인한다. 현재 파일 목록 점검은 clean checkout 실행 시험을 대신하지 않는다.
6. 로컬 경로는 이 인계 목록에 포함돼 있다. 공개 저장소로 배포할 경우 공유용 문서의 개인/서버 경로 표기를 검토하되 원본 증거는 보존한다.

## 5. 올리지 않아도 되는 항목

- 과거 모든 results 전체, 이전 RF/CIR 대용량 산출물, 실패 revision 전체.
- `.codex/`, 대화 로그, ledger DB, `__pycache__/`, `.pytest_cache/`, 로컬 가상환경, 개인키·자격증명.
- 현재 native 실행에 사용하지 않는 HFSS 프로젝트 원본·설계 archive 전체.
- 향후 전체 계산으로 생성되는 raw paths/CIR 전체는 코드 Git 이력 대신 별도 데이터 저장소에서 관리. GitHub에는 산출물 manifest·검증 receipt·실행 보고서 연결.

기존 과거 증거를 지우라는 뜻은 아니다. 이번 전달 묶음에서 제외한다.

## 6. 목록 집계와 다음 행동

- EXTERNAL_DATA: 25 files / 1895.86 MiB
- GITHUB: 536 files / 27.71 MiB
- IMPLEMENT_THEN_GITHUB: 10 files / 0.0 MiB

위 CSV 집계는 작성 시점 payload 기준이며, 이 안내서/CSV/검증 영수증 자체는 self-hash 순환을 피하려고 CSV 본문에서 제외한다. **이 세 파일도 reports/common에 함께 올린다.**

다음 행동은 이 목록으로 staging bundle을 만들거나 계획서 S0/S1의 전체용 실행기를 구현하는 것이다. 실제 push는 이번 요청에서 수행하지 않았다.
