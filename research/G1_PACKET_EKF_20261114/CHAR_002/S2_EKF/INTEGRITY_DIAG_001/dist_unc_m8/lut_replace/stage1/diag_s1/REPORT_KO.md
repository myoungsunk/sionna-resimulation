# Stage 1 진단 재생 — S1-h, S1-a, S1 (개정 02 B2, 판정 아님)

| 항목 | 내용 |
|---|---|
| 지위 | **DIAGNOSTIC_ONLY.** S1은 정적 관문 FAIL로 확정됐다(개정 02 B2). 이 재생은 LUT 대체의 영향을 수치로 나누는 용도다. 확정 seed 50–69는 쓰지 않는다 |
| 입력 | Corridor, dev seed 10–29, B0와 L2_GYRO_ARW, 궤적 R2·R4·R5 |
| 보정 | 셋 모두 S0-id 보정(라벨 s_full − h_FFD, S0-id V 표, S0-id 라벨 kriging, S0 초모수) |
| 비교 기준 | S0-id F2SKRWV (`lut0/out_c0/C03`) |
| 결론 | **S1의 손실은 거의 전부 h(예측값과 Jacobian) 교체에서 온다. 감도 a 교체는 영향이 없다** |

## 1. arm 정의

| arm | EKF의 h와 Jacobian | GM 적재와 R 표의 감도 a |
|---|---|---|
| S0-id | FFD | FFD |
| S1-h | EMP (K = 8, J = 6) | FFD |
| S1-a | FFD | EMP |
| S1 | EMP | EMP |

H2와 H2S는 FFD로 재생했다(개정 01 A4).

**hook 항등 검사.** `m8_replay_lut.py`는 `m8_replay.py`를 복사해 `a_fn` 인자 하나만 더했다. hook을 넘기지 않은 재생과 FFD의 a를 돌려주는 hook을 넘긴 재생 모두 원본과 bit 단위로 같다(B0 seed 10, R2·R4·R5, trace 전 필드). → [ID_CHECK_A_FN.json](ID_CHECK_A_FN.json)

## 2. 결과 (S0-id 대비 seed 짝 비율, 20 seed)

| 조건 | arm | N_I | N_J (H2S) | 거울해 | XY 비율 중앙값 / 97.5% 상한 | heading 비율 중앙값 / 97.5% 상한 | pooled Pose95 평균 |
|---|---|---|---|---|---|---|---|
| B0 | S0-id | 16 | 16 | 0 | 1 | 1 | 0.928 |
| B0 | S1-h | 0 | 0 | 0 | 1.62 / 1.72 | 1.70 / 1.86 | 0.732 |
| B0 | S1-a | 16 | 16 | 0 | 0.995 / 0.998 | 1.000 / 1.005 | 0.927 |
| B0 | S1 | 0 | 0 | 0 | 1.63 / 1.73 | 1.76 / 1.91 | 0.726 |
| L2 | S0-id | 16 | 16 | 0 | 1 | 1 | 0.925 |
| L2 | S1-h | 0 | 0 | 0 | 1.61 / 1.67 | 1.70 / 1.79 | 0.738 |
| L2 | S1-a | 16 | 16 | 0 | 0.996 / 0.999 | 1.001 / 1.004 | 0.924 |
| L2 | S1 | 0 | 0 | 1 | 1.62 / 1.69 | 1.71 / 1.88 | 0.734 |

궤적별 20 seed 합산 RMSE (B0, XY cm / heading °):

| arm | R2 | R4 | R5 |
|---|---|---|---|
| S0-id | 9.80 / 1.61 | 6.68 / 1.05 | 7.43 / 1.30 |
| S1-h | 17.92 / 2.68 | 7.23 / 1.30 | 9.34 / 1.56 |
| S1-a | 9.80 / 1.62 | 6.66 / 1.05 | 7.40 / 1.30 |
| S1 | 17.98 / 2.69 | 7.11 / 1.30 | 9.58 / 1.66 |

L2도 같은 양상이다. → [S1_DIAG_JUDGE.csv](S1_DIAG_JUDGE.csv), [S1_DIAG_PERSEED.csv](S1_DIAG_PERSEED.csv)

## 3. 해석

- **원인은 h다.** S1-a는 S0-id와 사실상 같다(비율 1.00). S1-h와 S1은 거의 같다. 따라서 S1의 손실(N_I 16 → 0)은 EMP의 예측값 h_emp에서 온다.
- **정적 결과와 같은 방향이다.** LOSO에서 h_emp − s_LoS RMS는 근거리 0.035, 중거리 0.069다. S0-id 라벨(s_full − h_FFD)로 만든 평균 보정은 이 차이를 알지 못한다. 그래서 innovation에 보정되지 않은 계통 오차가 남는다. 정적 z_s 포함률(근거리 0.52)의 실패가 필터에서 Pose95 0.73으로 나타난 것이다.
- **R2에서 가장 크다.** R2의 XY RMSE는 9.8 → 17.9 cm로 늘고, R4는 거의 그대로다.
- **함의.** EMP LUT의 감도(부호, 크기)는 필터에 쓸 만하다. 남은 문제는 h의 계통 오차를 라벨이 흡수하지 못한다는 것이다. 이는 Stage 3(라벨 s_full − h_emp)이 다루는 구조다. Stage 2 2b가 같은 흡수를 FFD′로 먼저 시험한다.

## 4. 파일

| 파일 | 내용 |
|---|---|
| [code/m8_replay_lut.py](code/m8_replay_lut.py) | `a_fn` hook을 더한 재생 복사본 |
| [code/run_s1.py](code/run_s1.py) | 진단 재생 |
| [code/id_check.py](code/id_check.py) | hook 항등 검사 |
| [code/judge.py](code/judge.py), [code/perseed.py](code/perseed.py) | 비열등 계산(§9 규칙), seed별 표 |
| [groups_s1.tar.gz](groups_s1.tar.gz) | seed별 원본 GROUP.json 40개 |
| RUN.log | 실행 로그 |
| [SHA256SUMS](SHA256SUMS) | 이 폴더 파일 해시 |

코드의 로컬 경로와 저장소 사본의 대응은 [../../CODE_DEPENDENCIES_KO.md](../../CODE_DEPENDENCIES_KO.md)에 있다.
