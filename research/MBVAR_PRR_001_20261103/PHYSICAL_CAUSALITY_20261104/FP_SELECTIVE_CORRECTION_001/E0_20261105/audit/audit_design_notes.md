# FP-SC-001 E0 별도 검토자 설계 검토

- 작성 역할: `SAME_SESSION_SEPARATE_REVIEWER` (`/root/design_audit`). 구현 담당과 분리된 agent이나 같은 작업 세션의 팀 구성원이다. 외부 독립감사자 또는 독립 승인자로 표시하지 않는다.
- 확인 범위: 첨부 패키지 10개 파일의 본문/JSON/CSV 및 9개 manifest 항목의 실제 bytes SHA256 일치. 동결 원전 `observation.py`와 `S1/online.py` 전체를 GitHub에서 직접 열람했다. RF/CIR/controls/trace payload는 아직 읽지 않았다.
- 원 계획 SHA256: `84d7506c208d98449ec1591949dea4d1f2e6646c6d415724d4e3638d3b556361`.
- 초안 계약 SHA256: `8bdb513aca707848354241fcc56f7be0c563103e50bfcd2d073abbfc1ce4453b`.
- 검토 상태: **E0 구현을 준비할 설계는 충분하다. 실행 범위·입력·코드·환경을 구체화한 E0 계약을 별도 동결하고 검증한 범위만 실행할 수 있다. 현재 원 초안 전체의 null/false를 일괄 PASS로 변경해서는 안 된다.**

## 1. 사용자 지시와 원 초안의 관계

최신 사용자 지시는 “계획대로, 구현 - 실행 - 깃허브 푸시하도록”이다. 따라서 첨부 작성 시점의 `is_execution_authorization=false`, `owner stage approval` 미기입은 사용자가 아무 실행도 승인하지 않았다는 현재 사실이 아니다. 최신 지시의 원문과 시점, 해석한 범위를 새 실행 문서에 기록하고 작업을 진행한다. 원 제안 패키지는 이력을 위해 원 bytes 그대로 보존한다.

사용자 승인은 코드/데이터 정합성을 입증하지 않는다. 새 계약의 코드·입력 hashes, 과학적 중단 조건, 실패 결과를 보존해야 한다. 새 RT, 선택 실험 외 추가 cross-route/새 물리환경 실험은 기본 범위에 포함시키지 않는다. 감사자 이름만 바꾸거나 기존 scorer를 재실행한 결과를 `INDEPENDENT_ACCEPT`로 바꾸지 않는다. 별도 구현의 산술 검산이 있으면 그 범위만 명시한다.

## 2. E0에 맞게 해소할 초안의 범위 문제

`blocking_fields_before_any_run`는 selector threshold/trust transition/POLICY_SPEC/CAL·SEALED split까지 모두 요구하지만 §5는 selector 이전의 E0이다. 따라서 **E0 전용 amendment**에서 다음을 분명히 한다.

| 항목 | E0에서 필요한 동결 |
|---|---|
| POLICY_SPEC | `NO_CORRECTION_BASELINE_REPRODUCTION_ONLY`; 새 후보·선택·학습 없음. 후속 selector 필드는 E0 비적용 사유 명시 |
| SPLIT_MANIFEST | 공개 원본 재현에 사용하는 route/bias/channel/seed/pose/timestamp와 노출 이력. CAL/SEALED는 실행하지 않음 |
| METRIC_SPEC | 네 거리 정의, reference validity, aggregate 분모, absolute/relative parity 허용오차, NaN 비교 규칙 |
| RUN_MATRIX | E0-01~04의 실제 source와 개수. G4 static 24조건, dynamic 3,136 pose, Full/LoS·B0/L2 및 보유 noisy baseline의 세부 범위를 각자 명시 |
| INPUT_LOCK | 실제 bytes SHA256/size/array keys/shape/dtype/ports/frequency grid. 미수신은 BLOCKED_DATA 또는 PAYLOAD_UNVERIFIED |
| ENV_LOCK | Python/NumPy/FFT/BLAS·thread·RNG 종류/seed/배치 크기·source 코드 blobs |
| CODE/AUDIT | 실행 코드 및 별도 checker의 실제 SHA 또는 동결된 source manifest. 아직 작성 안 된 checker를 존재한다고 기록하지 않음 |

E0에 불필요한 E2 최적 임계값을 먼저 정해야 한다고 작업을 멈출 이유는 없다. 반대로 E0가 부분 완료됐다는 이유로 누락된 dynamic/noisy/MB_VAR 검증을 통과 처리할 수 없다.

## 3. 필요한 E0 구현과 산출물

### E0-01: 수신기와 MB_VAR 무처치 재현

1. 원본 수신기와 별도 산술 구현을 같은 실제 입력에서 비교한다. index/strong RX/detected/mask는 exact. r/s/power/phase convention과 NaN 위치를 확인한다.
2. 기본 chain: selected TX column → complex per-bin/RX noise → Hann → 길이 4N zero-pad → IFFT×N → RX별 magnitude maximum 중 최댓값 RX → 그 RX 진폭 peak의 30% 이상인 **첫** tap → 두 RX를 같은 tap에서 읽어 signed s.
3. 반드시 amplitude 30%와 power 30% 음성 대조, tie rule, RX 순서/부호, zero-CIR, 한 포트 null, NaN/invalid를 점검한다. 이 단계는 원 수신기 동작 보존과 입력/평가 유효성 판정을 분리한다.
4. MB_VAR W0 no-op는 원 `z/muBASE/muMB/R/D/P0`, controls `ds/gy/dt/x0`, model/FFD/spec를 사용한다. t=0부터 `prior/Pprior/h/H/mu/Rvar/Reff/K/nu/S/mask/x/P` 전체를 비교한다. source 출력 summary만 다시 계산하는 것으로 필터 parity를 대체하지 않는다.
5. `baseline_parity.csv`는 case/field/row_count/discrete_mismatch/finite_mismatch/max_abs/max_normalized/tolerance/status를 포함한다. 실행하지 못한 분기는 NOT_RUN/BLOCKED로 별도 행을 둔다.

### E0-02: 네 거리와 detector-domain mapping

필요한 packet별 열은 최소 `r_geo`, `r_det_full`, `r_det_los`, original `h_r(xGT)`, original `h_r(x_minus)`, 원래 bias 및 `mu_r` 항목, filter convention에 맞춰 계산한 `r_corrected`, `r_state`, `n0`, `nL0`, detected/reference_valid이다. 모든 거리의 단위와 기준점(태그 안테나 위치/높이, anchor B 3D, lever arm 유무)을 기록한다.

- `r_det = c*n/(1028*1.95MHz)`이며 tap 간격 0.14955225880474907m는 물리 분해능 또는 오차 보장치가 아니다.
- `r_det - r_geo`, `r_det_full-r_det_los`, `h_r(xGT)-r_geo`, 실제 보정 후 오차와 state radial error를 분리한다.
- `r_corrected = z_r-mu_r`라고 임의로 정의하지 않는다. SourceFFD/los_range_bias 및 model h_r가 이미 포함하는 offset을 확인하고 중복 차감하지 않는다.
- 원 `los_range_bias`는 flat-spectrum synthetic LoS의 `[2,16)`m, 0.01m grid에서 평균 detector offset을 계산한다. 실제 FFD direct-only 채널의 yaw/주파수 응답과 동일하다고 가정하지 않는다.
- direct-only sub-tap sweep 및 G4 정지 yaw 결과로 nearest rounding과 실제 leading-edge support의 차이를 보여준다. 이를 검증하기 전 `r(n)±Δr/2`를 올바른 detector support라고 채택하지 않는다.
- 동일 모집단/route/bias/channel별 bias, MAE, RMSE, absolute-error p95/p99/max, |error|≤4cm 및 ≤1tap 비율을 산출한다. valid/unknown/undetected 수와 전체 수를 맞춘다.

### E0-03: G4 24조건 oracle/rounding 재현

원본 24개의 같은 CIR·pose를 사용한다. `n0/nL0/round(h_r(xGT)/Δr)`와 예측 range ±0.04m만 변화시킨 결과를 다시 계산한다. 주장된 12/24→22/24 및 -4/0/+4cm=20/22/8을 실제 원자료와 비교하되, 기존 수치에 맞추려고 threshold/rounding/분모를 바꾸지 않는다. rescue/harm/unknown row를 모두 보존한다.

24조건은 6XY×4yaw의 정지 대조다. 시간적 4cm 이동이나 DR tracker, online prior 성공으로 표현하지 않는다. `ORACLE_REPRODUCTION.json`에 원 summary와 재계산 비교값, 실제 읽은 file/bytes/rows 및 불일치 이유를 넣는다.

### E0-04: 원시 payload/noise/clock/split 준비도

- 실제 H/CIR payload, pose/timeline, 원 gyro/odom/initial condition, prior/P, mu/R, FFD bank, environment를 항목별 검증한다. LFS pointer를 array로 읽지 않으며 OID 일치와 실제 object hash를 구별한다.
- 모든 dynamic joins는 `(route,channel,pose_id,timestamp)`와 bias/seed 원천을 사용한다. 979/742/1,415 counts, unique keys, monotonic clock, dt, missing/reordered/duplicate rows를 확인한다. G4는 순차 timeline으로 연결하지 않는다.
- 기존 noisy array가 없으면 원 RNG/seed/dtype/draw shape·순서/noise variance를 복원하고 기존 z/index/detected와 parity를 확인한다. 원 seed만 같고 draw 순서가 다른 것은 같은 noise replay가 아니다.
- 복원이 불가능하면 기존 noisy 재현 분기는 BLOCKED이며, 새로운 noise는 새 realization이라고 명시할 때만 별도 manifest에 둘 수 있다. clean payload가 있다는 이유로 noisy replay 가능 PASS를 주지 않는다.
- `SPLIT_MANIFEST`에서 기존 seed0–29 공개 이력과 CAL30–39/SEALED40–59가 이미 쓰였는지 저장소 증거를 기록한다. 사용 이력 미확인은 미사용 증명이 아니다. SEALED 데이터를 실행하거나 보고 threshold를 고르지 않는다.

## 4. 원 코드 직접 열람에서 확인한 구현 함정

### 수신기

`observation.py` blob `4182f97eb5b564e941786043dbc43eb78f8e84cf`:

- `cir_batch`는 IFFT 결과에 N=257을 곱한다. FFT 길이 1028을 곱하면 동일 chain이 아니다.
- noise는 `rng.standard_normal(h.shape)` 전체 real draw 다음 전체 imag draw다. batch 크기/호출 분할이 바뀌면 같은 seed에서도 실현이 달라질 수 있다.
- clean zero-CIR에서는 `peak=0`, threshold=0이라 기존 `detected=True`, `tap=0`, `range=0`, `s=NaN`가 나올 수 있다. **무처치 parity에서는 이 동작을 보존하되 reference_valid는 false로 둔다.** 수신기를 몰래 수정한 뒤 원본 parity라고 하지 않는다.
- first-path power에는 energy-s 방식의 thermal subtraction이 없다. `rx_energy_s`의 다른 정의를 tap s에 적용하지 않는다.

### MB_VAR

`S1/online.py` blob `6c584a631ebefdf9576b88730cfe842bf34140a9`:

- BASE shadow는 자신의 predicted state/P와 `muBASE`로 gate를 계산한다. MB_VAR prior gate로 바꾸면 baseline이 달라진다.
- sigma_b는 MB_VAR **이전 posterior**의 수평 rho에서 계산한 뒤 predict한다. xp에서 계산하면 timing convention이 달라진다.
- W0라도 R[1,1]에 sigma_b²가 더해지며, 원 packet R와 최종 Reff를 구별해야 한다.
- Joseph는 accepted mask=false이면 K=0, x/P는 prior로 유지한다. pre-mask gain과 stored masked K를 섞지 않는다.
- latency_ns는 비결정적이므로 수치 no-op equality 대상에서 제외하되 별도 환경/운용 결과로 보존한다.

## 5. 차단 사유와 정상적인 해소 방법

| 사유 | 판정/조치 |
|---|---|
| 최신 사용자 지시는 있으나 원 초안 GO=false | 작업 중단 이유가 아님. 새 E0 scope 문서에 authorization provenance 기록 |
| selector threshold 미정 | E0에서 비적용으로 명시. E1/E2 진입 전 별도 동결 |
| 실제 RF bytes 없음 | 해당 source BLOCKED_DATA. 정확 path/OID/size/schema와 필요한 E0/E1 branch 요청서 생성 |
| FFD/controls/mu/R 없음 | 수신기/정적 검증은 가능한 만큼 실행. MB_VAR parity 및 E1+ 관련 branch는 PARTIAL/BLOCKED |
| detector-domain mapping 미해결 | HOLD_MAPPING_UNRESOLVED. 후속 prior selector 성공 주장 금지 |
| no-op tap/mask/state 불일치 | FAIL_PARITY, 오류 원인 기록·수정·새 code hash. 허용오차를 사후 완화하지 않음 |
| code/checker/env/input hash 없음 | 실행 전 구체화. 원 proposal SHA만으로 actual execution lock을 대체하지 않음 |
| noisy RNG 재현 실패 | clean/noisy 분리. 새 noise를 원 trace parity라고 표시하지 않음 |
| 같은 세션 분리 agent 검토 | 실제 독립 산술 범위는 기록하되 external independent acceptance로 과장하지 않음 |

## 6. 권장 E0 판정표

`E0_RECEIVER_PARITY`, `E0_MBVAR_PARITY`, `E0_RANGE_MAPPING`, `E0_G4_ORACLE`, `E0_RAW_ACCESS`, `E0_NOISE_REPLAY`, `E0_CLOCK_JOIN`, `E0_SPLIT_EXPOSURE`를 각각 PASS/FAIL/BLOCKED/NOT_RUN으로 둔다. 한 개 composite PASS로 부분 미실행을 숨기지 않는다.

**다음 단계:** 모두 필요한 데이터와 mapping이 확인되면 E1의 후보 생성/정상 보호 시험을 구체화할 수 있다. E0 일부 결과만 있으면 가능한 증거를 게시하고 구체적 차단 조건을 남긴다. E1 또는 E4를 완성했다고 주장할 근거는 아직 없다.
