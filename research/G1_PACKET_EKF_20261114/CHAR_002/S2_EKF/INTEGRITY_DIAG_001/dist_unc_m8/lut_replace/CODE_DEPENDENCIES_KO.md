# LUT 대체 작업 — 코드 의존성과 실행 경로

각 stage의 `code/`에 있는 스크립트는 작업 공간의 절대 경로(`/home/claude/...`)에서 실행했다. 저장소에서 다시 실행하려면 아래 표의 저장소 사본을 해당 로컬 경로에 두면 된다. 해시는 실행에 쓴 로컬 파일과 저장소 사본의 SHA-256 앞 12자리이며, 모두 같다.

## frozen 모듈 (변경하지 않음)

| 로컬 경로 | 저장소 사본 | SHA-256 |
|---|---|---|
| `/home/claude/m8/m8_replay.py` | `dist_unc_m8/step3_fair/code/m8_replay.py` | 4069ec621458 |
| `/home/claude/m8/common.py` | `dist_unc_m8/step3_fair/code/common.py` | c5f58d9bb3be |
| `/home/claude/m8/run_m8s3.py` | `dist_unc_m8/step3_fair/code/run_m8s3.py` | 71141c09d5bb |
| `/home/claude/m8/krige_online.py` | `dist_unc_m8/step3_fair/code/krige_online.py` | 982ba96cfef7 |
| `/home/claude/m8cal/feats.py` | `dist_unc_m8/step3_sweep/dev_02/code/feats.py` | dc705ed86917 |
| `/home/claude/m8cal/cal_b.py` | `dist_unc_m8/step3_fair/code/cal_b.py` | ad14cac75515 |
| `/home/claude/m8cal/krige.py` (초모수 선정 절차) | `dist_unc_m8/step3_sweep/dev_02/code/krige.py` | 8aa66755d79c |
| M7 채점 `m7_assess.py` (common.py가 불러옴) | `m7_final_model_stage1/m7_assess.py` | d570ce4f3c1a |

## 이 작업에서 만든 모듈의 로컬 위치

| 로컬 경로 | 저장소 위치 |
|---|---|
| `/home/claude/lut0/` (h_ref.py, run_c0.py, s0id_refit.py 등) | `stage0/code/` |
| `/home/claude/lut1/` (emp_lut.py, stage1_*.py) | `stage1/code/` |
| `/home/claude/lut1/` (m8_replay_lut.py, run_s1.py, id_check.py) | `stage1/diag_s1/code/` |
| `/home/claude/lut2/` (pert.py, stage2_*.py, run_s2.py, judge.py, perseed.py) | `stage2/code/` |

## npy·npz 중간 산출물의 공개 형식

LFS 업로드가 막혀 있어 npy·npz는 CSV(gzip)로 바꿔 올렸다.

| 로컬 파일 | 공개 파일 | 열 |
|---|---|---|
| `lut0/ES_FFDREF_CORRIDOR.npy`, `lut2/ES_P*.npy`, `lut2/A_P*.npy`, `lut2/MU_LOSO_*.npy` | `stage2/STAGE2_STATION_LABELS.csv.gz` | station 행 7200개(SWEEP_FEATURES 행 순서), `e_s_*` 라벨, `a_*` 감도, `mu_loso_*` LOSO 평균 보정 |
| `lut0/S0ID_CAL.npz`, `lut2/CAL_P*.npz` | `stage2/STAGE2_ROUTE_CAL.csv.gz` | 보정(cal) × 궤적 × pose 순번, mu_r, mu_s, Rrr, Rss |
| seed별 `GROUP.json` | `stage1/diag_s1/groups_s1.tar.gz`, `stage2/groups_s2.tar.gz` | 원본 그대로 |

입력 packet(seed 10–29, 50–69)은 stage0의 `INPUT_INDEX_EXT_50_69.json`과 frozen 입력 생성 절차로 다시 만든다.
