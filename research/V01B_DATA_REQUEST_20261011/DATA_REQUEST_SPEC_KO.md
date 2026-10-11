# V01b 데이터 요청 사양서 — 레거시 H 5개 복구 또는 12조건 Native 재생성

2026-10-11. 대상: Stage A / V01b (전파 생성계통 동등성). 기준: `origin/codex/abc-gated-resume-20261011` @`9a6bc0cd`. 기계가 읽는 항목은 `REQUEST_MANIFEST.json`, 보내기 전 점검은 `verify_delivery.py`. **이 문서는 요청서이며 V01b 결과가 아니다. Stage B는 계속 비활성이다.**

## 1. 무엇이 막혀 있는가
- 신규 Native H 5개는 확보·SHA 검증이 끝났다(`R2_aB_m45`, `R4_aA_m45`, `R4_aB_m45`, `R5_aA_m45`, `R5_aB_m45`).
- 이들과 **같은 조건의 과거 Method-B(레거시) H 5개**가 저장소·LFS·연결된 Drive에서 복구되지 않았다(LFS 5/5 `404`, Drive 검색 결과 없음, 전체 Git 이력 조사는 120 s 제한으로 미완료).
- 레거시 7개(`R2_aA_m0`, `R2_aA_m45`, `R2_aB_m0`, `R4_aA_m0`, `R4_aB_m0`, `R5_aA_m0`, `R5_aB_m0`)와 Native 5개는 **서로 겹치는 조건이 없어서** 지금 상태로는 같은 조건에서 두 생성계통을 비교할 수 없다. 혼합 12개를 동등하다고 선언하지 않는다.

## 2. 요청 옵션과 권장 순서
| 순위 | 옵션 | 사용자께 요청하는 것 | 필요한 환경 | 장점 | 위험 |
|---|---|---|---|---|---|
| 1 | **A. 원본 5개 파일** | 정확한 `H_*_m45.npy` 5개 (총 약 114 MB) | 없음 (파일 전달) | 가장 빠르고 증거가 가장 강함. SHA 일치가 곧 증명 | 원본이 더 이상 없을 수 있음 |
| 2 | **B. 레거시 ray-trace 입력 5세트** | `traces_R2_aB`, `traces_R4_aA`, `traces_R4_aB`, `traces_R5_aA`, `traces_R5_aB` 디렉터리 | 일반 Python (Sionna 불필요). `rf_b_apply.py`와 LP±45 FFD 뱅크는 저장소에 있음 | 결정적 재생성. 기대 SHA와 비트 단위로 대조 가능 | trace 크기가 클 수 있음. 부동소수 재현성(수치 라이브러리 버전) |
| 3 | **C. 12조건 Native 재생성** | Native 환경에서 7개 조건 추가 생성 (아래 4절) | Sionna PathSolver 환경 (이 세션에는 없음) | 하나의 생성계통으로 통일. 과거 파일 의존 제거 | 계산 비용이 가장 큼. 장면·버전 식별 필요 |

판단 규칙: A가 되면 B, C는 불필요하다. A가 불가능하면 B(자가 검증 포함)를, B도 불가능하면 C를 진행한다. B는 `m45`가 `traces + --mount 45`만으로 만들어진다는 레거시 명령(`MOUNT_CASE_MATRIX.json`의 `full_method`)에 근거한다. **trace가 실제로 남아 있는지는 저장소에서 확인되지 않았다**(저장소에는 `S2/traces_*`가 없다). 이 점은 사용자 확인이 필요하다.

## 3. 옵션 A·B 사양

### 3.1 요청 파일 (옵션 A)
| 조건 | 파일 | SHA256 | shape | 바이트 |
|---|---|---|---|---:|
| R2_aB_m45 | `H_R2_aB_m45.npy` | `fb229e187f9498025847ca550e061d3ab2cd82624f1c6e20ed9b78a5e7a60f75` | 1303×257×2×2 | 21,431,872 |
| R4_aA_m45 | `H_R4_aA_m45.npy` | `5eabb1e44677bdf82630cdf9eea43cad729af2459b9b790d246310d62b725724` | 922×257×2×2 | 15,165,184 |
| R4_aB_m45 | `H_R4_aB_m45.npy` | `3f76d713edccf90ed1d20c8e0f65064add3ca5c5340b56d11c1f391ca81c791d` | 922×257×2×2 | 15,165,184 |
| R5_aA_m45 | `H_R5_aA_m45.npy` | `1e2c2f36c8d4945e3868c418875b6f08e459c669bcdad981318daf4521ecfbc2` | 1883×257×2×2 | 30,971,712 |
| R5_aB_m45 | `H_R5_aB_m45.npy` | `8f0d87f213a04d6861d6de12f557ce5ce4ae2ba369b9c94e49496bc4f3e154e9` | 1883×257×2×2 | 30,971,712 |

형식: NumPy `.npy`, `complex128`, noise-free, 헤더 128 바이트. 파일명이 달라도 **SHA256이 일치하면** 수용한다.

### 3.2 옵션 B 요청 항목
1. `traces_R2_aB`, `traces_R4_aA`, `traces_R4_aB`, `traces_R5_aA`, `traces_R5_aB` (원래 경로는 `…/SNOWBALL_ROUTES_01a11669/S2/`). 디렉터리 전체와 파일 목록 SHA256.
2. 재생성에 쓰인 `rf_b_apply.py`가 저장소 버전과 같은지에 대한 확인(저장소 버전은 `scripts/drive_sim/rf_b_apply.py`).
3. 가능하면 당시 Python/numpy/scipy 버전.

**자가 검증(수용 조건)**: 같은 trace 디렉터리로 `--mount 0` 출력을 먼저 만들어, 저장소에 이미 검증된 m0 SHA와 일치해야 한다(5개 trace 모두 m0 H가 저장소에 있다). 일치하지 않으면 그 환경에서 만든 m45는 수용하지 않는다. 그 다음 `--mount 45` 출력의 SHA가 3.1의 기대값과 일치하면 원본 복구로 인정한다. SHA가 일치하지 않고 수치 오차만 있는 경우는 **자동으로 수용하지 않으며** 별도 승인 사항이다.

## 4. 옵션 C 사양: 12조건 Native 재생성
대상 12조건 = 3경로 × 2앵커 × 2마운트. Native가 이미 있는 것은 5개이고, **추가 생성 대상은 7개**다.

| 조건 | 포즈 수 | 상태 |
|---|---:|---|
| R2_aA_m0, R2_aA_m45, R2_aB_m0 | 1303 | 생성 필요 |
| R2_aB_m45 | 1303 | Native 있음 (`0169155f…75d5`) |
| R4_aA_m0, R4_aB_m0 | 922 | 생성 필요 |
| R4_aA_m45, R4_aB_m45 | 922 | Native 있음 (`2587edcd…ab82`, `3ac3dffb…8226`) |
| R5_aA_m0, R5_aB_m0 | 1883 | 생성 필요 |
| R5_aA_m45, R5_aB_m45 | 1883 | Native 있음 (`55c886b6…a6376`, `d56b8168…97d2ccf7`) |

입력 고정값: 포즈 파일 `rf_poses_R2/R4/R5.json`(저장소 `S1/routes/`; SHA는 매니페스트), 주파수 257 bins, Δf 1.95 MHz(`freqs_hz.npy` SHA256 `fe0bcfeb…1169f8`), LP+45/−45 FFD(`LP_plus45_bank.npz` `b29ae471…453b`, `LP_minus45_bank.npz` `39729fe9…eb9`).
기존 Native 영수증의 solver 설정: `max_depth 3`, `samples_per_src 100000`, `max_num_paths_per_src 1000000`, `synthetic_array true`, LOS·정반사·굴절 켬, 회절(edge 포함)·산란 끔, `seed 20260924`, `threads_per_solver 1`.

산출물(조건마다): `H_full.npy`와 `H_LoS.npy`(같은 포즈 순서, shape `[포즈, 257, 2, 2]`, complex128), 포즈→행 대응 영수증(`rf_poses_sha256`와 함께), 입력 SHA·명령줄·seed·소요시간·실패 기록. R5처럼 시간 제한에 걸린 조건은 주파수 구간을 나눠 생성하되 겹치는 구간의 상대 복소 오차를 영수증에 남긴다(기존 Native R5가 이 방식).

**사용자 환경에서 채워주실 항목**(저는 알 수 없고 추측하지 않는다): Sionna/Mitsuba/DrJit/Python/OS 버전, 장면 파일 이름과 SHA256, 안테나 배열 기하와 mount 회전 규약의 출처, 기존 Native 5개의 LoS-only H 존재 여부.

## 5. 수용 기준 (사전 고정, 결과를 보기 전)
- 옵션 A/B: 5개 파일의 SHA256 일치 → 해당 조건에서 레거시 vs Native를 **모든 저장 포즈**에서 비교. 기준: 전체 채널 상대 복소 오차 ≤ 1e-3, |Δs| ≤ 0.01, first-path tap 동일. 7개 조건이나 일부 포즈로 축소하지 않는다.
- 옵션 C: 12개 모두 같은 solver·같은 입력으로 생성되었음을 영수증으로 확인하고, V01 관측기 parity(42조건)를 새 H에 대해 다시 통과해야 한다. 기존 레거시 대비 정확도 비교는 목적이 아니다.
- 어느 옵션이든 혼합 7+5를 동등하다고 선언하지 않는다. 수치 기준은 결과를 본 뒤 바꾸지 않는다.

## 6. 전달 방법
- 저장소의 LFS 서버는 이 세션에서 업로드가 거부(`Forbidden`)되었으므로 **LFS 경로(`*.npy`/`*.npz` 푸시)를 쓰지 않는다.**
- 권장: Drive 링크 또는 GitHub Release 자산, 파일당 95 MB 이하로 분할 가능. 함께 `SHA256SUMS.txt`(`sha256sum` 출력 형식)를 보낸다.
- 보내기 전에 `python verify_delivery.py <폴더>`로 3.1의 5개를 점검한다(읽기 전용; 모든 파일이 `PASS`여야 종료코드 0).

## 7. 회신 양식
```
선택한 옵션: A / B / C
A: 5개 중 확보한 파일: [ ] R2_aB_m45 [ ] R4_aA_m45 [ ] R4_aB_m45 [ ] R5_aA_m45 [ ] R5_aB_m45
   전달 위치:           verify_delivery.py 결과: ALL_PASS / NOT_ALL_PASS
B: trace 확보: [ ] R2_aB [ ] R4_aA [ ] R4_aB [ ] R5_aA [ ] R5_aB   당시 환경 버전:
C: 가능한 환경(GPU/CPU, 시간): 장면 파일(이름/SHA256): Sionna/Mitsuba/DrJit/Python 버전:
   Native LoS-only H 존재: 예/아니오 (5개 각각)
```

## 8. 이후 절차
데이터가 오면 SHA·형식을 먼저 검증하고, 기준(5절)대로 V01b를 판정한다. V01b가 통과해도 Stage A 전체 PASS가 아니다: V02는 범위 한정 판정(PASS_IN_ENVELOPE)이며 `HIGH_*` prior 명세 결정과 게이트 승인이 별도로 필요하다. `stage_B_allowed`는 사용자 승인 전에는 바꾸지 않는다.

## 9. 하지 않는 것
레거시 7 + Native 5 혼합을 동등으로 간주하기, 일부 포즈나 7케이스로 범위 축소, 누락 파일을 다른 파일로 대체해 SHA를 맞춘 것처럼 기록하기, 추정으로 H를 합성하기, 격리된 조기 Stage B 결과 사용.
