# Sionna 전체 재시뮬레이션 — 실행 전 전체 감사 (S0 이전)

- 대상 계획: [SIONNA_FULL_RESIM_PLAN_20260925_01a0d86d.md](SIONNA_FULL_RESIM_PLAN_20260925_01a0d86d.md)
- 감사 스크립트: `scripts/g2_completion/audit_sionna_full_preflight.py` (읽기 전용, RF 호출 0회, 입력 파일 수정 0)
- 기계 판독 결과: `results/SIONNA_FULL_RESIM_20260925_01a0d86d/00_preflight_audit/AUDIT.json`, `MANIFEST.json`
- 실행 위치: GitHub checkout `myoungsunk/sionna-resimulation` (Linux, Python 3.11, Git LFS 8개 객체 pull 완료)
- **판정: `NOT_READY_FOR_FULL_RUN`** — BLOCKER 5 / FAIL 2 / WARN 7 / PASS 22 / INFO 4

입력 데이터 자체(수량, 장면, frame 연결, 보정 RX, 기하, FFD, 잡음 설정)는 계획서와 일치합니다. 막히는 부분은 **전체용 실행기가 아직 없다는 점**, **동적 유전체 판재 모델이 정해지지 않은 점**, **checkout의 runtime 코드가 검증에 쓰인 코드와 다르다는 점**입니다.

## 1. BLOCKER — 전체 실행 전 반드시 해결

| ID | 내용 | 필요한 조치 |
|---|---|---|
| **C8** | common 링크 132,000개 중 **98,980개가 동적 판재를 사용**하고, 관련 frame은 **28,120개**입니다(41행 payload는 12개). 그중 **9,380 frame이 `dielectric` `blockage_panel`(εr=12, tanδ=0.35, 두께 정보 없음)**입니다. 현재 `sionna_native_runtime.make_scene()`은 모든 `dynamic_panel`을 ITU metal 1 mm로 고정하고, `RelocatedInputs`는 PEC가 아니면 `UNSUPPORTED_DYNAMIC_OBJECT`로 중단합니다. | **사용자 결정 필요:** 유전체 판재의 native Sionna 표현(RadioMaterial εr=12, σ=2π·f·ε0·εr·tanδ 또는 주파수 고정값, 두께 값)을 확정한 뒤 S0에서 계약으로 기록합니다. 금속으로 처리하면 물리적으로 틀린 결과가 되므로 허용하지 않습니다. |
| **A6** | `scripts/g2_completion/sionna_native_runtime.py`, `finish_sionna_native41.py`의 내용이 업로드 목록 CSV 및 PLAN_INPUT_SNAPSHOT의 SHA와 다릅니다(CRLF 차이로 설명되지 않음). 형상 검증 기록(`RUNTIME_READBACK`)의 `source_runtime_sha256=9dc7dfa5…`와도 다릅니다. | Windows 원본(`D:/codex/.../scripts/g2_completion/`)과 비교해 어느 쪽이 맞는지 확정합니다. 원본을 다시 올리거나, 변경을 새 revision으로 기록합니다. |
| **A2** | 6개 FFD bank NPZ가 계획상 위치 `results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/`에 없습니다. 파일은 **저장소 루트**에 있고 SHA는 정확히 일치합니다(A3). | 이동 또는 복사는 AGENTS.md 규칙에 따라 dry-run 계획을 먼저 작성한 뒤 수행합니다. 또는 전체용 path map(`config/sionna_full_paths.example.json`)이 루트 위치를 가리키게 합니다. |
| **H1** | 기존 실행기에는 41행 전용 제한이 15개 있습니다. `--stop` 기본값 41, `CONFIG.rows`만 읽음, 출력 폴더 재사용 금지(재개 불가), NPZ 비원자적 저장, DrJit thread 4 고정, `range(0,41,3)`, `pathsolver_calls==31611`, 이전 원격 bank 경로, UID 1001:1001 고정, `rows==41` assert, `RelocatedInputs`의 41행 전용 동작, 저장소에 없는 이전 결과 폴더 의존(`SIONNA_G2_SCOPED41_V3_…`) | 계획서 S1의 신규 전체용 진입점에서 해결합니다(기존 41행 실행기는 덮어쓰지 않음). |
| **H2** | 전체용 파일 7개(`g2_full_inputs.py`, `prepare/run/finish/verify_sionna_full.py`, 테스트 2개)가 아직 구현되지 않았습니다. | S0/S1 구현 |

## 2. FAIL / WARN

| ID | 상태 | 내용 |
|---|---|---|
| A1 | FAIL | 업로드 목록 571행 중 내용 불일치 3건: 위 코드 2건과 `reports/common/CLAIM_BOUNDARY.md`. 나머지 55건은 **CRLF→LF 변환만 다르고 내용은 동일**합니다(EXACT 497, CRLF_ONLY 55, LFS 데이터는 pull 후 EXACT). |
| B1 | FAIL | PLAN_INPUT_SNAPSHOT 원본 SHA 26건 중 24건은 일치(EXACT 8, CRLF_ONLY 10, 루트 bank 6)하고, 불일치 2건은 A6과 같은 파일입니다. |
| A3 | WARN | bank NPZ가 루트에 있습니다(A2 참조). |
| A4 | WARN | 계획서, 업로드 안내서, CSV, 검증 JSON이 루트와 `reports/common/`에 중복되어 있습니다. 진행 로그는 `reports/common/` 쪽에만 추가했습니다. 루트 사본 정리는 dry-run 계획을 거친 뒤 수행합니다. |
| A5 | WARN | 로컬 검사용 의존성 목록이 없습니다. 실제로 필요한 패키지는 numpy, scipy, scikit-learn, shapely, pytest입니다. |
| E3 | WARN | STATIC9 C0 빈 장면 3개는 mesh가 0개라 `scene.edit(add=[])` 경로를 탑니다. pilot에서 동작을 확인해야 합니다. |
| G6 | WARN | CONFIG에 Windows 절대경로(`bank_root`, `geometry_root`)가 들어 있습니다. 전체 CONFIG에는 로컬/서버 root 대응이 필요합니다. |
| H3 | WARN | H 합산은 `paths.a × exp(-j2πfτ)`(절대 주파수)로 계산합니다. LOS fixture는 진폭과 τ만 따로 확인하므로, 다중경로 위상 규약을 검증하는 **2-path(PEC 바닥) 해석해 fixture**를 pilot에 추가하는 것을 권장합니다. |
| T1 | WARN | `pytest`: 32 passed, 3 failed. 실패 3건은 모두 `tests/test_g2_scoped_channel.py`가 저장소에 없는 `results/SIONNA_G2_P1_SIMPLE_CONTRACT_20260924_01a0d1b0/POWER_NOISE_CONTRACT.json`을 읽기 때문입니다(코드 결함 아님, 인계 누락). |

## 3. PASS — 계획 수치 재현 확인

- **C1/C2:** 대상 165,009개(L1 12,000 / L1multi 12,000 / L2static 3,000 / L2multi 6,000 / C1_static 6,000 / C1_multi 6,000 / C3 120,000 / STATIC9 9). (family, case_id) 중복 0.
- **C3:** 대상 scene 합집합 101 = 형상 manifest 101(L 60 + C 32 + STATIC9 9). 누락 0, 미사용 0.
- **C4/C9:** 좌표 모두 유한값. TX–RX 거리 0.520–48.805 m. 닫힌 장면의 TX/RX가 모두 방 bounding box 내부.
- **C5/C6/C7:** FRAMES 37,500행, canonical_scene_hash 재계산 불일치 0. common 링크 132,000개 → frame 37,500개 연결 누락 0, RX≠tag_pose 0, scene_hash 불일치 0. `rx_azimuth_deg`(최대 720°까지 unwrap된 값)와 frame yaw는 mod 360에서 일치.
- **C10/C11:** CHANGED_LINKS 41행 모두 R 입력에 새 RX 반영, 이전 좌표 잔존 0, common 15행에 `rx_relocation` 표시. NATIVE41 CONFIG 41행과 일치.
- **D2/D3:** 서로 다른 common yaw 9,953개에서 회전행렬 RᵀR=I, det=+1. `historical_mount_frames({})`가 NATIVE41 CONFIG의 회전행렬을 재현. STATIC9 quaternion 18개 모두 단위 norm이며 identity.
- **E1/E2/E4:** mesh 326개 / 삼각형 25,438개, 모든 SHA 일치. 재질(concrete, plasterboard, glass, metal, chipboard, wood, brick, EPS4)은 모두 6.2504–6.7496 GHz에서 ITU-R P.2040 유효 범위. 형상 FINAL_MANIFEST 356개 출력 drift 0.
- **F1/F2:** FFD bank 6개의 SHA가 BANK_MANIFEST 및 CONFIG와 일치. 주파수가 `6250400000+1950000k`(k=0…256)와 비트 단위로 일치. 형상 257×181×361, 전부 유한값. 포트 순서 일치.
- **G1/G2/G4/G5:** `noise_var_H_bin=4.856640061591484e-16`과 검출 임계 `2.106615e-07`을 원식으로 재계산해 일치. solver 블록이 계획 §5와 동일. 형상 revision CONFIG와 NATIVE41 CONFIG의 물리·운용 블록 동일. geometry manifest/contract SHA는 CRLF 기준으로 일치.
- **B2:** 165,009 × 257 × 3 = **127,221,939** PathSolver 호출(계획과 일치).

## 4. INFO — 결정 또는 기록이 필요한 사항

- **D1 L계열 자세:** L 33,000행 모두 `tag_orientation_deg=[0,0,0]`이고 source_row에 boresight/azimuth 키가 없습니다. 따라서 전부 기본 자세(TX 보어사이트 −z, RX yaw 0)가 적용됩니다. 기존 41행과 같은 의미인지 S0에서 명시적으로 확인합니다.
- **F3:** phi 격자가 −180…180(361)이라 360° 열이 0°와 중복됩니다. BankPort의 wrap/clip 처리는 이 격자에서 정상입니다.
- **G3:** `detector.statistical_validation.executed=false`, `noise.producer_bound=false`, `hardware_calibrated=false`. 전체 실행 보고서에서도 이 상태를 올려 적지 않습니다.
- **H4 용량:** target 하나당 PathSolver 771회(257 bin × 3 arm)입니다. 기하는 주파수·arm과 무관하지만 계획상 엔진 최적화는 하지 않으므로, S2 pilot의 실측 rows/hour로 ETA를 산정합니다.

## 5. 이번 작업 보고 (AGENTS.md Done Definition)

1. **변경한 파일:** 신규 `scripts/g2_completion/audit_sionna_full_preflight.py`, 신규 본 보고서, `reports/common/SIONNA_FULL_RESIM_PLAN_20260925_01a0d86d.md` 진행 로그 추가(기존 내용 수정 없음), 신규 `.gitignore`(`__pycache__`, `.pytest_cache`).
2. **이동한 파일:** 없음.
3. **의도적으로 건드리지 않은 파일:** 모든 입력(R, G, B, STATIC9), 기존 실행기와 runtime, 루트 중복 문서와 루트 bank NPZ, 테스트.
4. **실행한 검사:** 감사 스크립트 전체(pytest 포함). `scripts/00_inventory.py`, `01_build_manifest.py`, `02_validate_dataset.py`, `06_build_reports.py`는 **이 저장소에 없어 실행하지 못했습니다**.
5. **생성 산출물:** `results/SIONNA_FULL_RESIM_20260925_01a0d86d/00_preflight_audit/AUDIT.json`, `MANIFEST.json`(명령, 코드 SHA, 입력 SHA, git HEAD).
6. **남은 위험:** 동적 유전체 판재 모델 미정, runtime 코드 출처 불일치, 전체용 실행기 부재, Snowball 상태(부하, 디스크, Docker)는 이 환경에서 확인 불가.
7. **다음 권장 명령:**
   `python scripts/g2_completion/audit_sionna_full_preflight.py --out results/SIONNA_FULL_RESIM_20260925_01a0d86d/00_preflight_audit`
   → BLOCKER 해결 후 다시 실행해 `READY_FOR_S0`를 확인한 다음 S0/S1 구현을 시작합니다.
