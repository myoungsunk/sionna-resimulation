# R2-1: P5 재현성·온라인 관측 계약 감사

코드 위치: `results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/simulate.py` (동결 harness) + `p5_build_harness.py`(치환) + `p5_arm_ranges.py`.

## 1. seed가 바꾸는 것 / 바꾸지 않는 것 (코드 근거)
| 요소 | seed 의존 | 근거 |
|---|---|---|
| 센서 스트림(gyro/odom/wheel, drift 포함) | **예** | `V.generate(t,ds,dtheta,cfgsensor,seed)` (simulate.py:23) |
| 초기 pose 오프셋 | **예** | `V.rng(seed,'initial').normal(...)*p0_std` (:26) |
| RF 채널 H, 첫 경로 range/`s`/power/detected | **아니오** | `obs`는 `OBS/<case>_full.npz`를 읽을 뿐(:27). 이 npz는 `observe(H,freqs,None,None)`(잡음 없음)으로 케이스당 1회 생성 |
| range 측정 잡음 | **아니오 (0개)** | 관측 시계열에 어떤 난수도 더해지지 않음. 필터의 R(range_sigma 등)은 가정값일 뿐 |
| P5 arm별 range 보정 delta | **아니오** | `p5_arm_ranges.py`가 케이스당 npz 1개, 모든 seed에 동일 가산 |
| E1 보정 특징량 | noise-free H | `det_for()` → `cir_mag(H)` 잡음 없음 |
| 궤적 | 아니오 | route별 `MOTION_*.npz` 고정 |

⇒ 독립 단위는 "RF 시리즈 12개 × 센서 실현"이다. 128 seed는 센서·초기오차 반복이며, RF/range 잡음 실현을 늘리지 않는다.

## 2. 유효 표본 수 (`out_R2/P5_EFFECTIVE_SAMPLE_AUDIT.json`, `p5_effective_sample_audit.py`)
셀 = case × drift (36). 셀 내 128 seed.
| 비교 | 셀 간 ICC | 설계효과 | 유효 run 수 (명목 4,608) |
|---|---:|---:|---:|
| E_COND − B_OLD (pos RMSE) | 0.257 | 33.7 | 137 |
| BEST_PLUS_R_IAT − B_OLD | 0.403 | 52.1 | 88 |
| B_OLD − A_DR | 0.283 | 37.0 | 125 |
| E_COND − A_DR | 0.187 | 24.7 | 186 |
셀 수준 부호: E_COND<B_OLD 36/36, IAT<B_OLD 35/36, B_OLD>A_DR 23/36.
해석: 방향(E_COND가 B_OLD보다 낫다)은 셀 전반에서 일관되나, P5의 12조건 부트스트랩 CI는 RF 시리즈가 12개뿐이고 같은 scene·3 route라는 한계 안에서만 읽어야 한다. 128 seed로 CI가 좁아진 부분은 센서 반복의 효과다.

## 3. 온라인 관측 계약 (현 상태)
- 입력: 케이스별 고정 noise-free 관측 + 사전 계산된 delta. EKF에서 "수신 CIR → 특징량 → 보정"이 per-step 온라인으로 실행된 것이 아님.
- 따라서 P5는 "E1 보정이 정확하다고 가정한 range 입력의 영향" 평가이며 noisy-feature E1의 EKF 성능은 R2-3에서 새로 실행해야 한다.
- 대체 근거(부분): P4에서 E1을 noisy CIR(snr30/snr10)에 적용한 Full-RF RMSE 변화는 −16.7 %/−16.8 %로 noise-free(−17.2 %)와 유사 (`P4_SITE_BOOTSTRAP_CI.json`). 이는 range 수준 결과이며 EKF 수준이 아니다.

## 4. 재현 자산
- `tools/p5_confirm_driver.sh`: 재개 가능한 확증 driver(원본 그대로 복사, 경로는 세션 scratchpad 기준).
- 이미 있는 것: `P5_TRACE_SHA256_MANIFEST.csv`(chunk/arm SHA), `RUN_MANIFEST.json`.
- 여전히 없는 것: per-run 시계열 trace(용량 때문에 미저장). R2-3에서 range 입력·innovation·pose error만 압축 저장하는 옵션을 넣는다.
