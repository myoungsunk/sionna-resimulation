# 원인 확인(A23) — 시뮬레이션 명세서 및 데이터 요청서

작성: Claude (작성자측), 대상 브랜치 `claude/cool-dijkstra-hnznhm`. 이 문서는 사전 등록(A23)을 겸한다. 아래 정의와 해석 규칙은 **본 실행 결과를 보기 전에** 고정한다. 실행은 사용자가 직접 한다(Snowball 또는 H 저장소가 있는 환경). 코드는 `scripts/drive_sim/structured_noise_control.py`(참조 구현), 테스트는 `tests/test_structured_noise_control.py`.

## 0. 확인하려는 것

감사 01단계의 2×2(R2-A, 장착 0°, P0)에서 **합성 s + 합성 range**는 heading 1.9°·NEES 4.6, **실제 s**를 넣으면 heading 10°·NEES 100이었다. 합성 s의 잡음 크기(σ 0.161)는 실제 잔차 RMS(0.179)와 비슷하다. 따라서 **크기가 아니라 구조**(편향, 샘플 간 상관, 비정상성)가 원인이라는 가설이 남는다.

- **Q1.** 실제 s 잔차와 같은 통계(편향, 분산, lag-1 상관)의 합성 오차만으로 NEES 팽창과 정확도 악화가 재현되는가? 재현된다면 어떤 성질(편향·주변분포·상관·비정상성)이 필요한가?
- **Q2.** 실제 range가 NEES를 4.6 → 12로 키우는 이유는 편향, 상관, 거리·tap 위치 의존 중 무엇인가?

이 실험은 원인 분리용 대조군이며 필터 성능의 증거가 아니다. 어떤 필터 파라미터도 바꾸지 않는다.

## 1. 데이터 요청서

우선순위 1은 필수, 2는 권장이다. 모두 읽기 전용으로 사용한다.

| # | 자료 | 용도 | 위치(예) / 확인 |
|---|---|---|---|
| 1 | `H_<route>_a<anchor>_m<mount>.npy` (shape [n_pose, 257, 2, 2], complex) — **우선순위 1: R2-A m0, R2-A m45**, 2: R2-B, R5-A, R5-B, R4-A, R4-B (각 m0, m45) | 실제 관측(채널) | Snowball `S2/`. 해시는 `SNOWBALL_ROUTE_RUNS/01a11669/g3_recheck_20261008/UNCHANGED_H_S6_VERIFICATION.json`의 `H_hashes`와 대조 |
| 2 | `hs_lut_2deg.npy`, `hs_lut_meta.json` | LoS-only 예측 s, range offset(`range_bias.mean_m`) | Snowball `S4/`. 감사 보고서의 SHA256 `711e12ee…a079`(LUT)과 대조 |
| 3 | 주파수축: `LP_plus45_bank.npz`(키 `freqs_hz`) 또는 `freqs_hz.npy` (257개, 6.2504~6.7496 GHz, 간격 1.95 MHz) | CIR 변환 | SHA256 `fe0bcfeb…69f8`(freqs_hz.npy)과 대조. 인자 `--bank-freqs` |
| 4 | `S1/routes/timeline_<route>_Tnone.csv`, 필요 시 R1 `S1/timeline_y<lat>_Tnone.csv` | truth 궤적 | 저장소에 있음 |
| 5 | (권장) S6 결과 `results_<route>_a<anchor>_m<mount>.csv` | A0 재현 점검(§4-①) | `S6_routes/` |
| 6 | 실행한 코드 커밋 해시, Python·NumPy 버전, 실행 머신 | 재현성 | 결과 폴더에 `ENV.txt`로 |

H 저장소가 없는 조합은 건너뛴다. 최소 구성은 R2-A m0 한 가지(감사 01·02 단계와 직접 비교 가능)이다.

## 2. 시뮬레이션 명세

**공통 조건(모든 arm 동일).** 경로·앵커·장착 = 케이스별, 타임라인 `P0`(프로브 없음), 센서·초기 prior·필터 설정은 S6 route 실행과 같다(`pos_process_std` 0.01, `--mismatch-sigma 0.16095229605409875`, drift 0·1·2, SNR 30 dB 한 가지, seed 0–49). 필터는 EKF `range_s_P0`(range + s + odom heading). 한 케이스·장착당 8 arm × 3 drift × 50 seed = 1200 run. truth 위치·heading은 오차 계산과 합성 관측 생성에만 쓰고 필터에는 주지 않는다.

**실제 잔차 시리즈(arm의 목표 통계).** 노이즈 없는 채널 체인으로 케이스·장착마다 P0 타임라인에서 계산한다.
- `r_s = s_chain(H) − LUT(truth)` (LoS-only LUT 예측과의 차이)
- `r_r = range_chain(H) − (3-D 거리 + range offset)`
- 통계는 t ≥ 30 s 구간에서: 평균 μ, 중심화 분산 v, RMS, lag-1 상관 φ(중심화), lag 1·2·5·10·25 상관.

**arm 정의.** s와 range를 각각 아래 모델로 바꾼다. 합성 값은 `LUT(truth)`(s) 또는 `3-D 거리 + offset`(range)에 오차를 더해 만들고, s에는 필터가 가정하는 열잡음을 더한다. 필터의 R(σ_mismatch 포함)은 모든 arm에서 같다.

| arm | s | range | 의도 |
|---|---|---|---|
| A0 | 실제 | 실제 | 생산 관측(기준). S6 재현 점검 대상 |
| A1 | 백색 N(0, RMS_s²) | 백색 N(0, RMS_r² + 0.05²) | 모델 일치 대조군(감사 01단계 합성+합성과 같은 종류) |
| A2 | 실제 `r_s`에서 복원추출(시간 순서 파괴) | 백색 | 편향·비가우시안 주변분포만 보존, 상관 제거 |
| A3 | 편향 μ + AR(1)(분산 v, 계수 φ) | 백색 | 편향 + 상관(실제 통계 일치) |
| A4 | 실제 `r_s`의 블록 부트스트랩(블록 50샘플=10 s) | 백색 | 실제의 비정상·상태 의존 구조 일부 보존 |
| A5 | 백색 | 실제 range | range 단독 효과 |
| A6 | 백색 | 편향 + AR(1) + 0.05 백색 | range의 구조화 오차 |
| A7 | AR(1) | AR(1) | 둘 다 구조화 |

모든 arm은 같은 (seed, drift) 쌍에서 센서 draw·초기 상태를 공유한다. 합성 오차의 달성 통계(평균·분산·lag-1)를 `ARM_ACHIEVED_STATS.json`으로 저장하고 목표(`ARM_TARGET_STATS.json`)와 대조한다.

**측정 항목(arm·케이스·장착별).** pose NEES 평균(기대값 3), pose 95% 커버리지(기대 0.95), heading 95% 커버리지, heading RMSE 중앙값, 위치 RMSE 중앙값, `s`·range 갱신 거절률, s의 NIS 평균. **격차 폐쇄율** = (arm − A1)/(A0 − A1) (NEES와 heading RMSE 각각). 1이면 실제와 같은 크기의 악화를 재현, 1 초과는 과대 재현이다.

## 3. 실행 명령과 산출물

```bash
D=results/DRIVE_SIM_20261007; OUT=$D/CAUSE_CHECK_A23
# (a) 실제 잔차 통계와 range 진단 — Q2 자료 (분 단위)
python scripts/drive_sim/structured_noise_control.py residuals --s1 $D/S1 --h-dir <S2> --lut <S4>/hs_lut_2deg.npy --lut-meta <S4>/hs_lut_meta.json \
    --bank-freqs <freqs 파일> --cases R2A R2B R5A R5B --out $OUT
# (b) arm 실행 — Q1 (R2A 하나에서 4 프로세스 기준 십여 분)
python scripts/drive_sim/structured_noise_control.py run --s1 $D/S1 --h-dir <S2> --lut <S4>/hs_lut_2deg.npy --lut-meta <S4>/hs_lut_meta.json \
    --bank-freqs <freqs 파일> --cases R2A R2B R5A R5B --seeds 50 --nproc 4 --mismatch-sigma 0.16095229605409875 --out $OUT
# (c) 요약
python scripts/drive_sim/structured_noise_control.py report --csv $OUT/ARMS.csv --out $OUT/ARMS_REPORT.json
```

회신 요청 파일: `RESIDUAL_STATS.json`, `ARM_TARGET_STATS.json`, `ARM_ACHIEVED_STATS.json`, `ARMS.csv`, `ARMS_REPORT.json`, 실행 로그, `ENV.txt`(커밋 해시·버전), 사용한 H·LUT 파일의 SHA256 목록. `RESIDUAL_*.npz`(원 시리즈)도 있으면 함께.

## 4. 결과를 믿기 전 점검(실행자 확인)

1. **A0 재현:** A0의 행(SNR 30, drift 0–2, seed 0–49)이 S6 route 결과의 `range_s_P0`·ekf 행과 동일해야 한다(같은 코드 경로·시드). 같지 않으면 입력(H, LUT, σ, 코드)이 다르므로 이후 결과는 무효다.
2. **잔차 통계 대조:** R2-A m0의 `RESIDUAL_STATS`가 감사 01단계 STEP3와 거의 같아야 한다(s: 평균 0.0465, RMS 0.1791, lag-1 0.927; range: 평균 0.0519, RMS 0.1232, lag-1 0.804; 상관 0.523, n = 829). 개발 환경(로컬 H)에서 이미 소수 셋째 자리까지 일치함을 확인했다.
3. **합성 오차 달성 통계:** `ARM_ACHIEVED_STATS`의 AR(1) arm이 목표 평균·분산·lag-1을 ±10% 안에서 재현해야 한다(개발 환경 R2-A m0 확인: 목표 φ 0.927, 달성 0.928).
4. **A1이 모델 일치 대조군으로 동작:** A1의 NEES가 3~6, 커버리지가 0.85 이상이어야 한다. 아니면 필터나 합성 생성기 문제를 먼저 본다.

## 5. 해석 규칙(어시스턴트 제안, 사용자 승인 전)

격차 폐쇄율 기준(NEES와 heading 각각, 같은 케이스·장착 안에서). 아래 구간은 제안이며 바꿔도 된다. 바꾸면 결과를 보기 전에 기록한다.

| 관찰 | 해석 |
|---|---|
| A3(편향 + AR1)의 폐쇄율 ≥ 0.8 | 실제와 같은 통계의 편향·상관 오차가 팽창을 설명한다. 다음 단계는 상관 오차 모델(Gauss-Markov 상태 또는 시간 상관 R)이다. |
| A2(주변분포만)가 대부분을 재현 | 상관이 아니라 편향·분포 형태가 원인이다. 다음 단계는 편향 보정 또는 측정 비선형 보정이다. |
| A3는 0.8 미만이나 A4(블록)가 더 크게 재현 | 정상 AR(1)로 표현되지 않는 비정상·상태 의존 구조가 있다. 위치·각도 의존 모델이 필요하다. |
| 모든 arm이 0.3 미만 | 잔차 통계만으로는 설명되지 않는다. 오차와 필터 상태·기하의 결합(예: 민감도 낮은 구간의 오차)을 별도로 봐야 한다. |
| A5·A6·A7이 A1 대비 NEES를 크게 키움 | range 오차의 구조가 독립 원인이다. |

폐쇄율이 1을 크게 넘는 경우(과대 재현)는 합성 AR(1)이 실제보다 불리한 시간 구조를 갖는다는 뜻이며 "원인 확정"이 아니다.

## 6. 한계

- R2-A·R5-B 등 선택한 케이스·장착의 결과이며 환경 일반성은 없다. 같은 복도·FFD·LUT를 공유한다.
- 합성 s는 가우시안 가산 오차 모델이며 유계 전력비의 물리 생성기가 아니다(s ∈ [−1, 1]을 클리핑하지 않았다).
- 상관을 가진 오차를 넣는 것은 원인 후보를 시험하는 것이지 필터 수정이 아니다. NEES가 맞아져도 모델이 고쳐졌다는 뜻이 아니다.
- 필터의 σ_mismatch, gate, prior, process noise는 바꾸지 않는다. 비교를 통과시키기 위한 조정은 하지 않는다.
- `scientific_PASS=false`, F01/F02 OPEN은 이 실험으로 바뀌지 않는다.

## 7. 개발 환경 사전 점검(증거 아님)

스크립트 검증용으로 로컬 R2-A H 저장소에서 소수 seed(arm당 6 run)만 돌려 코드가 동작함을 확인했다. 이 수치는 표본이 너무 작아 결과로 인용하지 않으며 저장하지 않았다. 잔차 통계와 합성 오차 달성 통계의 일치만 §4의 ②③ 항목으로 기록한다.
