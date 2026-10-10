# 원인 확인(A23 rev3) — 시뮬레이션 명세서 및 데이터 요청서

작성: Claude (작성자측). 브랜치 `claude/cool-dijkstra-hnznhm`. 이 문서는 사전 등록(A23)을 겸하며, 정의와 해석 규칙은 **본 실행 결과를 보기 전에** 고정한다. 실행은 사용자가 한다. 참조 구현 `scripts/drive_sim/structured_noise_control.py`, 테스트 `tests/test_structured_noise_control.py`.

**개정 이력.** rev1(`2dde8be`) → rev2(`8acb550`) → rev3(이 문서). rev3은 rev2 재검토(2026-10-10)에서 재현된 **A0/S6 검사의 거짓 PASS 두 사례**(seed 하나가 빠지고 다른 seed가 중복돼도 행 수가 같으면 PASS, 비교 지표 열이 없어도 PASS)와 그 외 보완 사항을 반영한 것이다. 실제 실험은 아직 없다. 변경: ① A0 검사를 독립 필수 단계(`check-a0`)로 분리하고 통과 전에는 다른 arm 실행을 차단, ② 요청 키 집합 기준의 완전성·중복·실패·지표 열·유한성 검사, ③ 입력·source·설정 해시의 동결(manifest), ④ 실패 시 drift별 결과를 기본으로 하고 대응 비교는 완전한 seed에만 적용, ⑤ 상세 trace 보강과 실패 직전 상태 보존, ⑥ NEES tail·range accepted-only NIS·J2 상관 기록, ⑦ 폐쇄율 상태 구분, ⑧ 실행 단계 분리와 A0 재사용.

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

## 4. 실행 순서 — A0가 통과해야만 다음 단계가 열린다

**요청 키 집합.** (route, anchor, lateral, mount, drift, SNR, seed)의 전체 곱을 실행 전에 확정한다. R2-A·장착 0°·drift 0–2·seed 0–49·SNR 30이면 **정확히 150개 키**다. 비교는 `baseline = range_s_P0`, `filter = ekf` 행에 대해 한다.

| 단계 | 명령 | run 수(R2-A m0, drift 3, seed 50) | 통과 조건 |
|---|---|---|---|
| 0 | `residuals` | 0 | 실제 잔차 통계가 감사 STEP3와 같은 수준 |
| 1 | **`check-a0`** | 150 | `A0_CHECK.json`의 `inference_valid = true`. 실패하면 종료 코드 2, 이후 단계 차단 |
| 2 | `run --arms tier0` (M0·W0) | 300 | A0 게이트 통과(자동) |
| 3 | `run --arms S1_bias … S8_real` (Q1) | 1,200 | A0 게이트 통과(자동) |
| 합계 | tier1 | 1,650 | |

Q2(tier2 R1–R8, 1,650 run)와 joint(tier3 J1–J3, 900 run)는 별도 범위이며 지시가 있을 때 추가한다. tier1만으로는 Q1에 답하고 Q2에는 답하지 않는다.

**`check-a0`가 하는 일.** A0만 실행해 `A0_ARMS.csv`·`A0_UNIT_STATS.csv`를 저장하고 저장된 S6 행과 비교한다. 다음 중 하나라도 있으면 `inference_valid = false`다.
- A0 또는 S6에서 요청 키가 **누락**되거나 **중복**됨(일대일 merge와 요청 집합 대조를 함께 사용: 누락이 중복으로 가려지지 않음)
- 실패 행(`error` 비어 있지 않음)
- 필수 열(키, `baseline`, `filter`, `heading_rmse_deg`, `pos_rmse_m`, `nees_mean`) 누락 또는 비유한 값
- 세 지표 중 하나라도 허용 1e-9 초과 차이
- timeline의 `pose_id`가 `rf_poses`의 (x, y, yaw)와 1e-6 이내로 대응하지 않거나 H 저장소 크기를 넘음
S6 CSV가 없으면 실행을 거절한다(`S6_CSV_REQUIRED`).

**게이트와 A0 재사용.** `run`은 같은 출력 폴더의 `A0_CHECK.json`이 유효하고, ① LUT·LUT meta·주파수축·source 파일·설정의 fingerprint가 같고, ② 이번 run의 케이스·장착별 H·timeline·rf_poses 해시가 같고, ③ 이번 run의 키가 A0 검사의 요청 집합에 포함될 때만 시작한다. 아니면 `A0_GATE_BLOCKED`로 종료한다. 개발용 `--allow-unchecked-a0`은 결과를 "추론에 사용 불가"로 표시한다. A0는 `run`에서 다시 계산하지 않고 `A0_ARMS.csv`를 `report`에 함께 넣는다.

**A0가 S6와 다를 때.** 입력 차이(H·LUT 해시)로 단정하지 않는다. 해시가 같다면 순서대로 확인한다: 코드 커밋과 source 해시 → 센서·R·Q·gate·prior 설정(`RUN_MANIFEST`의 `settings`) → 난수 키(`seed_keys`)와 snr_idx 매핑 → 평가 mask → 환경(NumPy 등).

**고정되는 증거(`RUN_MANIFEST_*.json`).** 인자, git HEAD·branch·dirty 파일 목록, Python·NumPy·pandas·OS, **입력 파일 해시**(H, 사용한 모든 timeline, rf_poses, LUT, LUT meta, 주파수축, S6 CSV), **실행 source 파일의 내용 해시**(filter·experiment·sensors·observation·hs_lut·trajectory·routes·pattern_apply·corridor·이 스크립트), **최종 적용 설정**(FilterConfig 기본값, 센서 잡음, drift 수준, `pos_process_std`, σ_mismatch, 적용 R, gate, prior, 평가 mask 정의, seed 키 구성, snr_idx 매핑), pose 대응 검사 결과, 계획·완료 run 수, 실패 수.

**실행 옵션.** `--cases`, `--mounts`, `--drifts`, `--arms`(이름 또는 tier0~tier3·all), `--seeds`, `--seed0`, `--label`(여러 번 나눠 실행해도 결과가 덮이지 않음), `--trace-seeds`(실행 전에 정한 소수 seed만 상세 저장), `--skip-missing`(`residuals`·`check-a0`·`run` 모두 같은 동작: 없으면 중단, 지정 시 건너뛴 조합을 목록에 기록), `--dry-run`. 필수 입력이 비어 있으면 `NO_INPUTS`로 거절한다. Windows에서는 `spawn`이 자동 선택된다.

```bash
D=results/DRIVE_SIM_20261007; OUT=$D/CAUSE_CHECK_A23
COMMON="--s1 $D/S1 --h-dir <S2> --lut <S4>/hs_lut_2deg.npy --lut-meta <S4>/hs_lut_meta.json --bank-freqs <freqs 파일>"
python scripts/drive_sim/structured_noise_control.py residuals $COMMON --cases R2A --mounts 0 --out $OUT
python scripts/drive_sim/structured_noise_control.py check-a0 $COMMON --cases R2A --mounts 0 --seeds 50 --s6-csv <S6>/results_R2_aA_m0.csv --out $OUT       # 150 run; 실패하면 중단
python scripts/drive_sim/structured_noise_control.py run $COMMON --cases R2A --mounts 0 --arms tier0 --seeds 50 --label controls --out $OUT                  # +300
python scripts/drive_sim/structured_noise_control.py run $COMMON --cases R2A --mounts 0 --arms S1_bias S2_ar0 S3_ar1 S4_iid S5_iid0 S6_realdem S7_block S8_real \
    --seeds 50 --label q1 --trace-seeds 0 1 --out $OUT                                                                                                         # +1,200
python scripts/drive_sim/structured_noise_control.py report --csv $OUT/A0_ARMS.csv $OUT/ARMS_controls.csv $OUT/ARMS_q1.csv \
    --unit-stats $OUT/A0_UNIT_STATS.csv $OUT/ARM_UNIT_STATS_controls.csv $OUT/ARM_UNIT_STATS_q1.csv --a0-check $OUT/A0_CHECK.json --out $OUT/ARMS_REPORT.json
```

## 5. 산출물, trace와 보고

**산출물(회신 요청).** `A0_CHECK.json`, `RUN_MANIFEST_*.json`, `A0_ARMS.csv`, `ARMS_<label>.csv`, `ARM_UNIT_STATS_*.csv`(실제로 필터에 들어간 오차의 통계), `ARM_TARGETS.json`, `RESIDUAL_STATS.json`, `TRACES/*.npz`, `ARMS_REPORT.json`, 실행 로그.

**trace(지정 seed만).** 전체 상태(6)와 6×6 공분산, 오차·NEES, 실제 센서 입력(자이로 증분, odom 거리·yaw 증분), 관측값(s, range, 검출 여부, 포트 전력), 주입 오차(`e_s`, `e_r`), 평가 mask, UWB 갱신별 기록 `(sample k, 갱신 전 NIS, 수용 여부, innovation, innovation 분산, R, 예측값, 측정값)`을 s와 range 각각 저장한다. 실행이 실패하면 **마지막 유효 상태와 6×6 공분산, 마지막으로 완료한 sample, 원래 오류 문장**을 저장하고 오류는 그대로 둔다(공분산 오류를 clamp나 jitter로 숨기지 않는다). 모든 run에는 요약 통계와 상태(오류 문장 포함)가 남는다.

**지표.** NEES 평균(기대 3), NEES **하·상 tail**(χ²(3)의 2.5%/97.5% 경계 0.215795283/9.348403604를 벗어난 샘플 비율; 시간 샘플은 독립 반복이 아니며 기술 통계), pose·heading 95% 커버리지, heading·위치 RMSE(t ≥ 30 s), s·range의 pre-gate NIS, **accepted-only NIS**, 거절률(eval mask). J2는 목표 교차상관, 혁신 상관(클리핑 여부 포함), 잡음 추가 **전** 달성 상관, 필터 입력 오차의 달성 상관을 구분해 기록한다.

**보고 구조.** (1) **기본: drift별 표**와 drift별 seed 대응 격차 폐쇄율. (2) 보조: drift를 평균한 seed 단위 분석 — 비교하는 arm·A0·W0가 **요청한 drift를 모두 성공한 seed에만** 적용하고, 제외한 seed와 사유를 보고한다(arm마다 다른 drift 수의 평균을 비교하지 않는다). (3) 실패 행은 보존해 case·mount·drift·arm별 수와 오류 문장을 보고한다. 실패한 arm의 성공 행 평균은 기술 통계로만 남는다. (4) A0 검사가 유효하지 않으면 보고서에 "추론에 사용 불가"를 표시한다.

**폐쇄율의 상태.** (arm − W0)/(A0 − W0)를 seed 대응 부트스트랩(2000회, seed 20261008)으로 계산한다. 분모 구간이 0을 포함하면 **보류**, 분모가 음수(A0가 W0보다 좋음)이면 **해당 없음**으로 표시하고 값을 내지 않는다. 폐쇄율이 1을 넘으면 "이 합성 모형이 실제보다 큰 악화를 재현했다"라고만 쓰며 시간 구조가 원인이라고 확정하지 않는다.

## 6. 결과를 믿기 전 점검(실행자 확인)

1. `A0_CHECK.json`이 유효하고 `RUN_MANIFEST`의 `a0_gate`가 `passed`여야 한다. `bypassed`이면 추론에 쓰지 않는다.
2. `A0_UNIT_STATS`의 A0 행이 `RESIDUAL_STATS`와 일치해야 한다(R2-A m0, 개발 환경 확인: s 평균 0.0466, RMS 0.1789, lag-1 0.926; 감사 STEP3 0.0465/0.1791/0.927). range는 production이 추가 백색 0.05를 더하므로 lag-1이 낮다(0.664).
3. 합성 arm의 필터 입력 오차 통계가 목표 성질을 갖는지 `ARM_UNIT_STATS`로 확인한다. 달성 통계를 맞추려 seed를 고르거나 재시도하지 않는다.
4. 실패 수와 `excluded_seeds`를 확인한다.
5. W0·M0에는 NEES 통과 기준이 없다.

## 7. 해석 규칙(어시스턴트 제안, 승인 전)

| 관찰 | 읽는 법 |
|---|---|
| S3 ≫ S1 ≈ S5, S2 ≈ S3 | 상관이 팽창을 만든다(편향 단독 효과는 작음). |
| S4가 S5보다 크고 S2·S3보다 작음 | 편향·주변분포 형태의 기여가 있다. |
| S6(정렬된 실제 구조, 편향 제거) vs S2/S3, S7(정렬 파괴) | 상태와의 정렬(비정상·기하 의존)의 기여. |
| S8 ≈ A0 | s가 지배적이고 range는 이 조건에서 부차적이다. |
| R6/R7이 R1·R3보다 큼 | 구간 평균과 **구간별 분산을 함께 바꾼** 효과이다. "구간 평균의 효과"만으로 해석하지 않는다. |
| J2 vs J1, J3 | 교차상관의 기여(J3는 실제 정렬이 아니라 블록 단위 대응). |

## 8. 한계

- 같은 경로의 잔차로 합성 오차를 만드는 조건부 재현이며 독립 held-out 일반화가 아니다. 같은 복도·FFD·LUT.
- 합성 s는 가산 가우시안 또는 경험 재표본 모델이며 유계 전력비의 물리 생성기가 아니다. s 잔차에는 full RF 차이와 LUT L1 오차가 함께 들어 있다.
- 합성 arm에서 NEES가 맞아도 모델이 고쳐졌다는 뜻이 아니다. 높은 폐쇄율은 모형이 악화를 재현했다는 뜻이며 단일 원인·기여율 확정이 아니다. 낮은 폐쇄율은 누락된 상관·기하 대응·고차 시간 구조 때문일 수도 있다.
- eval-mask NIS·거절률·갱신별 기록은 EKF 경로에서만 남는다.
- `scientific_PASS=false`, F01/F02 OPEN은 이 실험으로 바뀌지 않는다.

## 9. 개발 환경 점검(증거 아님)

- 로컬 R2-A m0 H 저장소로 `check-a0`를 돌리면 **실패(종료 코드 2)**한다: 6개 대응 run에서 heading RMSE 최대 차이 0.011°, 위치 최대 0.0064 m, NEES 최대 14.6. 로컬 H가 Snowball의 것과 같다고 가정할 수 없고 원인은 조사하지 않았다. 이 실패는 점검이 의도대로 작동함을 보여 준다.
- 통과 경로와 후속 단계는, A0 자신의 행을 "S6"로 대신 쓰는 **개발 전용 자기 일치** 입력으로만 시험했다(실제 S6가 아니다). 이 입력에서 seed가 누락되면 종료 코드 2로 차단됨을 확인했다. 후속 단계(`run`)는 통과 후에만 시작되고 A0 게이트가 `passed`로 기록됨을 확인했다.
- 거짓 PASS 두 사례(누락 seed를 중복으로 대체, 지표 열 누락)와 실패 행·비유한 값·미세 불일치·키 부족·fingerprint/입력/키 커버리지 불일치를 회귀 테스트에 넣었다(`tests/test_structured_noise_control.py`, 9개 통과).
