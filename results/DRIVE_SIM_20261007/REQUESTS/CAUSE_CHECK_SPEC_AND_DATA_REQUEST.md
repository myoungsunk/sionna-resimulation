# 원인 확인(A23 rev2) — 시뮬레이션 명세서 및 데이터 요청서

작성: Claude (작성자측). 브랜치 `claude/cool-dijkstra-hnznhm`. 이 문서는 사전 등록(A23)을 겸하며, 정의와 해석 규칙은 **본 실행 결과를 보기 전에** 고정한다. 실행은 사용자가 한다. 참조 구현 `scripts/drive_sim/structured_noise_control.py`, 테스트 `tests/test_structured_noise_control.py`.

**개정 이력.** rev1(`2dde8be`)에 대한 검토(2026-10-10)를 받아 실행 전에 rev2로 고쳤다. 실제 실행은 아직 없다. 반영 항목: ① A1 "완전 정합" 문구 삭제와 진짜 정합 대조군(M0) 추가, ② Q2 요인 분리 arm 확장, ③ 실제 range–s 교차상관을 쓰는 joint arm 추가와 변수별 난수 stream, ④ 달성 통계를 실제 입력에서 저장, ⑤ drift별 집계·실패 보존·seed 대응 신뢰구간·eval-mask NIS/거절, ⑥ 실행 범위·명령 수정과 Windows 지원, ⑦ A0/S6 재현을 필수 점검으로, ⑧ 해석 경계 정리.

## 0. 확인하려는 것과 답변 범위

과거 감사 01단계의 2×2(R2-A, 장착 0°, low drift, seed 4000–4023)에서 합성 range+합성 s는 heading 1.9°·NEES 4.6, 실제 s는 10°·NEES 100이었다. 합성 s의 잡음 크기는 실제 잔차와 비슷했으므로 **크기가 아니라 구조**가 원인일 수 있다는 가설을 시험한다.

- **Q1.** 실제 s 잔차의 어떤 성질(편향, 비가우시안 주변분포, 샘플 간 상관, 상태와의 정렬, range와의 교차상관)이 NEES 팽창과 정확도 악화를 재현하는가?
- **Q2.** 실제 range의 어떤 성질(편향, 상관, 주변분포, 구조 정렬, 거리 구간 평균, tap 위치 구간 평균)이 NEES를 키우는가?

**답할 수 있는 범위.** 위 성질별로 "넣었을 때 / 뺐을 때"의 대응 비교다. 이는 같은 경로의 잔차 통계로 만든 합성 재현이며 물리적 원인(멀티패스, tap 선택, LUT L1 오차)의 분리가 아니다. s 잔차에는 full RF와 LoS의 차이와 LUT의 L1 오차가 함께 들어 있다. 요인별 효과의 크기는 얻을 수 있어도 기여율 합산이나 단일 원인 확정은 하지 않는다. 필터 파라미터·R·gate·prior는 바꾸지 않는다.

## 1. 세 가지 기준 실험은 서로 다르다

| 기준 | 조건 | 수치 |
|---|---|---|
| 감사 01 2×2 | R2-A m0, low drift, seed 4000–4023, 그 harness의 초기화 | 합성/합성 NEES 4.6, 실제 s 포함 약 100 |
| 감사 01 6단계 | 거리 조건부 R, held-out mask(392개/seed) | NEES ≈ 321 |
| **이번 실험 A0** | production 필터와 R, drift 0–2, seed 0–49(또는 지정), t ≥ 30 s mask | 미정 |

세 값을 같은 수치로 비교하지 않는다. 이번 A0/A1 격차는 새 조건의 진단량이다.

## 2. 데이터 요청서

| # | 자료 | 구분 | 비고 |
|---|---|---|---|
| 1 | `H_<route>_a<anchor>_m<mount>.npy` ([n_pose, 257, 2, 2] complex). **R2-A m0**(필수), R2-A m45 등 | 필수 | Snowball `S2/`. 해시는 `UNCHANGED_H_S6_VERIFICATION.json`의 `H_hashes`와 대조 |
| 2 | `hs_lut_2deg.npy`, `hs_lut_meta.json` | 필수 | Snowball `S4/`. LUT SHA256 `711e12ee…a079` |
| 3 | 주파수축(`LP_plus45_bank.npz`의 `freqs_hz` 또는 `freqs_hz.npy`) | 필수 | 257개, SHA256 `fe0bcfeb…69f8`. 인자 `--bank-freqs` |
| 4 | `S1/routes/timeline_<route>_Tnone.csv` | 필수 | 저장소에 있음 |
| 5 | **S6 route 결과 `results_<route>_a<anchor>_m<mount>.csv`, 해당 manifest, S6를 실행한 source 커밋** | **필수(A0 재현 기준)** | snr_idx 매핑: S6는 SNR [30, 10]에서 snr_idx 0/1. 이번 실행은 SNR 30만 쓰며 snr_idx 0이다 |
| 6 | 실행 환경(커밋 해시, Python·NumPy·pandas 버전, OS) | 필수 | 스크립트가 `RUN_MANIFEST.json`에 자동 기록 |

필수 자료가 하나라도 없으면 실행하지 않는다(스크립트는 H 저장소가 없으면 즉시 중단하며, `--skip-missing`을 명시해야 나머지를 실행하고 건너뛴 조합을 목록에 남긴다).

## 3. 시뮬레이션 명세

**공통 조건.** 타임라인 P0, EKF `range_s_P0`, σ_mismatch `0.16095229605409875`, `pos_process_std` 0.01, 센서·초기 prior는 S6와 같음. SNR 30 dB. truth는 오차 계산과 합성 관측 생성에만 쓰고 필터에는 주지 않는다.

**난수·짝짓기 규약.** 센서·drift·초기 상태는 모든 arm이 (seed, drift)별로 공유한다(production run_unit과 같음). 합성 오차는 `default_rng([seed, drift, stream_id])`의 **변수별 독립 stream**(s 혁신, range 혁신, s 열잡음, range 추가 백색, 복원추출·블록 인덱스, joint 블록 시작점)에서 만든다. 같은 (seed, drift)에서 모든 arm이 같은 기본 혁신 벡터를 공통 난수로 써서 arm 간 차이가 표본 변동이 아니라 모델 차이를 반영하게 한다. drift가 stream 키에 포함되므로 drift마다 다른 realization을 쓴다.

**실제 잔차 시리즈(목표 통계).** 노이즈 없는 체인으로 케이스·장착별 P0 타임라인에서: `r_s = s_chain(H) − LUT(truth)`, `r_r = range_chain(H) − (3-D 거리 + range offset)`. t ≥ 30 s 구간의 평균 μ, 중심화 분산 v, RMS, lag-1 상관 φ, lag 1·2·5·10·25 상관, `corr(r_s, r_r)`(lag 0). 거리 구간(<5, 5–10, >10 m)과 tap 위치(4구간)별 range 잔차 평균·분산.

**기준(통제) arm.**
- **A0** 실제 s, 실제 range: production 관측 그대로.
- **W0** 영평균 백색, 분산 = 실제 잔차의 RMS²(range는 RMS² + 0.05²). 이전 문서의 A1. **필터가 가정하는 R과 다르므로 완전 정합 대조군이 아니다.**
- **M0** 필터가 가정하는 분산의 백색: s는 σ_mismatch² = 0.025906, range는 R_range = range_sigma² + range_quant_var + range_extra_sigma² = 0.0068579(필터 설정에서 읽음). 모델 정합에 가장 가까운 대조군이나 legacy 공유 gyro 입력과 EKF 국소 선형화가 남아 있어 NEES = 3을 보장하지 않는다. **W0·M0에는 통과 기준을 두지 않고 값을 보고한다.** 기준을 맞추려는 R·분산 조정은 금지한다.

**Q1 arm(s만 바꿈, range는 W0와 같은 백색).** S1 편향 + 백색(분산 v) / S2 영평균 AR(1)(v, φ) / S3 편향 + AR(1) / S4 실제 `r_s` 복원추출(편향·비가우시안 보존, 시간 순서 파괴) / S5 중심화 복원추출(편향 제거) / S6 실제 `r_s − μ`를 시간 정렬 그대로(구조·정렬 보존, 편향 제거) / S7 블록 부트스트랩(50샘플, 정렬 파괴) / S8 실제 s(range는 백색).

**Q2 arm(range만 바꿈, s는 W0와 같은 백색).** R1 편향 + 백색 / R2 영평균 AR(1) / R3 편향 + AR(1) / R4 복원추출 / R5 실제 `r_r − μ` 정렬 / R6 거리 구간 평균 + 구간 내 백색 / R7 tap 위치 구간 평균 + 구간 내 백색 / R8 실제 range(s는 백색). 모든 합성 range arm은 production이 더하는 0.05 m 백색 성분을 추가한다.

**joint arm.** J1 s·range 독립 AR(1)(편향 포함) / J2 s·range AR(1)의 혁신을 상관시켜 실제 lag-0 교차상관을 목표로 생성(`c = ρ(1−φ_sφ_r)/√((1−φ_s²)(1−φ_r²))`, 달성값을 보고) / J3 같은 블록 인덱스로 s와 range 잔차를 함께 부트스트랩(실제 교차상관 보존).

**측정 항목.** NEES 평균(기대 3), 하·상 tail, pose·heading 95% 커버리지, heading·위치 RMSE(t ≥ 30 s), eval mask(t ≥ 30 s)에서 s·range의 pre-gate NIS 평균, accepted-only NIS, 거절률. **격차 폐쇄율** = (arm − W0)/(A0 − W0)를 NEES와 heading RMSE 각각에 대해 seed 단위로 계산(한 seed의 drift 평균을 한 값으로 취급). 분모의 부트스트랩 구간이 0을 포함하면 폐쇄율을 계산하지 않고 "불안정"으로 표시한다. 폐쇄율의 95% 부트스트랩 구간은 seed 재표집(2000회, seed 20261008)이다. 시간 샘플은 독립 반복으로 세지 않는다.

## 4. 실행 범위와 명령

총 run 수 = (케이스·장착 수) × arm 수 × drift 수 × seed 수. `--dry-run`이 실제 수를 출력하고 종료한다.

| tier | arm 수(+ tier 0의 3개 포함) | R2-A m0만, drift 3, seed 50 |
|---|---|---|
| tier0(기준 3개) | 3 | 450 |
| tier1(Q1) | 11 | 1,650 |
| tier2(Q2) | 11 | 1,650 |
| tier3(joint) | 6 | 900 |
| all | 22 | 3,300 |

**권장 최소 실행: R2-A 장착 0°, tier1, seed 50 = 1,650 run**(참조 개발 환경에서 4프로세스 기준 run당 약 0.7 CPU초). 장착 45°와 다른 케이스는 이후 지시 시 추가한다.

```bash
D=results/DRIVE_SIM_20261007; OUT=$D/CAUSE_CHECK_A23
COMMON="--s1 $D/S1 --h-dir <S2> --lut <S4>/hs_lut_2deg.npy --lut-meta <S4>/hs_lut_meta.json --bank-freqs <freqs 파일>"
python scripts/drive_sim/structured_noise_control.py residuals $COMMON --cases R2A --mounts 0 --out $OUT
python scripts/drive_sim/structured_noise_control.py run $COMMON --cases R2A --mounts 0 --arms tier1 --seeds 50 --dry-run --out $OUT   # 실행 수 확인
python scripts/drive_sim/structured_noise_control.py run $COMMON --cases R2A --mounts 0 --arms tier1 --seeds 50 --nproc 4 --save-traces 2 --out $OUT
python scripts/drive_sim/structured_noise_control.py report --csv $OUT/ARMS.csv --unit-stats $OUT/ARM_UNIT_STATS.csv --s6-csv <S6>/results_R2_aA_m0.csv --out $OUT/ARMS_REPORT.json
```
Windows에서는 `spawn` 방식이 자동 선택된다(각 worker가 자기 상태를 다시 만든다). 인자: `--mounts`, `--drifts`, `--arms`(이름 또는 tier0~tier3·all), `--seed0`, `--skip-missing`, `--save-traces N`(seed < N인 run의 추정·공분산·오차·주입 오차 저장).

**산출물(회신 요청).** `RUN_MANIFEST.json`(인자, 커밋 해시와 dirty 목록, 버전, 입력 해시, 계획·완료 run 수, 실패 수), `ARMS.csv`, `ARM_UNIT_STATS.csv`(실제로 필터에 들어간 오차의 통계), `ARM_TARGETS.json`, `RESIDUAL_STATS.json`, `TRACES/*.npz`, `ARMS_REPORT.json`, 실행 로그.

## 5. 결과를 믿기 전 점검(실행자 확인)

1. **A0 = S6 재현(필수).** `report --s6-csv`가 같은 seed·drift·SNR 30의 `range_s_P0` 행과 heading RMSE, 위치 RMSE, NEES를 비교한다(허용 1e-9). 불일치하면 이후 결과를 사용하지 않고 원인을 조사한다: 코드 커밋, 환경, 난수 순서, 평가 mask, 입력(H·LUT·σ) 모두 후보이며 입력 차이로 단정하지 않는다.
2. **실제 오차 통계.** `ARM_UNIT_STATS`의 A0 행(열잡음·추가 백색 포함, t ≥ 30 s)을 `RESIDUAL_STATS`와 비교한다. 개발 환경 R2-A m0에서 s는 평균 0.0466, RMS 0.1789, lag-1 0.926(감사 STEP3: 0.0465/0.1791/0.927)으로 일치했다. range는 production이 추가 백색 0.05를 더하므로 lag-1이 낮아진다(0.664).
3. **합성 arm의 달성 통계.** `ARM_UNIT_STATS`의 합성 arm 값이 A0와 비교해 목표 성질을 갖는지 확인한다(AR(1)·joint arm의 s: lag-1 0.92 근방, J2의 교차상관 0.47 근방). 달성 통계를 맞추려고 seed를 고르거나 재시도하지 않는다.
4. **실패 run.** `n_failed`와 `failures`(case·mount·drift·arm별 수와 오류 메시지)를 확인한다. 0이 아니면 해당 arm의 평균은 무조건 해석하지 않는다.
5. W0·M0에는 NEES 통과 기준이 없다. 값만 보고한다.

## 6. 해석 규칙(어시스턴트 제안, 승인 전)

폐쇄율은 같은 케이스·장착 안에서 읽는다. 아래 구간은 과학 기준이 아니라 읽는 방법의 제안이다. 바꾸면 결과를 보기 전에 기록한다.

| 관찰 | 읽는 법 |
|---|---|
| S3 ≫ S1 ≈ S5, S2 ≈ S3 | 상관이 팽창을 만든다(편향 단독 효과는 작음). |
| S4가 S5보다 크고 S2·S3보다 작음 | 편향·주변분포 형태의 기여가 있다. |
| S6(정렬된 실제 구조, 편향 제거)이 S2/S3보다 크거나 작음 | 상태와의 정렬(비정상·기하 의존)의 기여. S7(정렬 파괴)과 비교한다. |
| S8 ≈ A0 | s가 지배적이고 range는 이 조건에서 부차적이다. |
| R6/R7이 R1·R3보다 큼 | 거리·tap 위치 의존 성분의 기여. |
| J2 vs J1, J3 | 교차상관의 기여(joint 부트스트랩 J3는 실제 정렬이 아니라 블록 단위 대응임). |

폐쇄율이 1을 크게 넘는 것은 합성 시간 구조가 실제보다 불리하다는 뜻이며 원인 확정이 아니다. 폐쇄율이 낮은 것은 이 통계로 포착되지 않은 구조(상태 의존, 고차 상관)가 있다는 뜻일 수도 있다.

## 7. 한계

- 같은 경로의 잔차로 합성 오차를 만드는 조건부 재현이며 독립 held-out 일반화가 아니다. 같은 복도·FFD·LUT.
- 합성 s는 가산 가우시안 또는 경험 재표본 모델이며 유계 전력비(s ∈ [−1, 1])의 물리 생성기가 아니다. S4·S5·S7·J3·R4는 경험 분포라 가우시안이 아니다.
- 합성 arm에서 NEES가 맞아도 모델이 고쳐졌다는 뜻이 아니다.
- eval-mask NIS·거절률은 EKF 경로에서만 기록한다(IEKF/UKF/GSF는 대상 아님).
- `scientific_PASS=false`, F01/F02 OPEN은 이 실험으로 바뀌지 않는다.

## 8. 개발 환경 사전 점검(증거 아님)

스크립트 검증용으로 로컬 R2-A m0에서 22 arm × 3 drift × 3 seed(198 run)를 한 번 돌려 파이프라인(arm 생성, 통계 저장, 트레이스, 보고, 분모 불안정 표시, 폐쇄율 구간)이 동작함을 확인했다. 표본이 너무 작아 결과로 인용하지 않았고 저장하지 않았다. 같은 실행에서 로컬 A0는 저장된 S6 행과 일치하지 않았다(9개 대응 run에서 heading RMSE 최대 차이 0.011°, NEES 최대 차이 14.6). 로컬 H 저장소가 Snowball의 것과 같다고 가정할 수 없고 원인은 조사하지 않았다. 이 불일치가 §5-①의 점검이 필요한 이유이다.
