# MBVAR-INFO-001 / P3-RT-SELF-VERIFY-001 — Sionna RT 직접 실행·시뮬레이션 검증 요청서

**작성일:** 2026-11-04 (KST)  
**역할:** PROPOSER → IMPLEMENTER_SELF_RUN / USER_AUTHORIZED_NONINDEPENDENT  
**상태:** 검증 요청서 DRAFT, 계산 미실행 (RT solver calls = 0)  
**원본:** PR #26 사용자 승인 A010 내부 탐색 동결, PR #23 pre-P3 준비서, SCIENCE_SPEC §6–7, EXPERIMENT_CONTRACT E5/G4/G5, COMMON_CONTRACT  
**외부 감사:** 요구하지 않음(사용자 직접 계산), 단 공식 독립 감사나 확인적 결과라고 표시하지 않음  
**출력 원칙:** 입력/코드/설정 및 실패 결과를 원본 그대로 보존. 새 시뮬레이션으로 이전 C3/G5 FAIL 소급 수정 금지.

## 0. 바로 처리할 두 트랙

| 트랙 | 현재 증거 | 당장 할 일 | 금지 |
|---|---|---|---|
| S — 기존 S1→C3 재현성 | S1V5 DEV3 1,980/1,980, QA PASS (GitHub Actions #41769652106); C3V5 1,080행 재생 중 ERR_A010_TRUTH_ONLY_REPLAY | C3에서 어긋난 TRUTH_ONLY 배열 이름·dtype·shape·SHA·최대 오차를 분해하고 원본 S1 receipt와 비교. 기술 원인 규명/명시적 수정 계약 이후 동일 SHA 조건으로 재검증 | 확인 없이 SHA 검사 완화, S1 truth 재작성, 누락행 삭제, G5 자동 PASS |
| R — 신규 Sionna RT 물리 메커니즘 | pre-P3 계약 초안만 존재, 실제 scene/material/solver/extractor/budget 미동결 | 이 요청서에 따라 입력 잠금 → 극소규모 C00 DIRECT → 동일 키 C01 FLOOR 및 C10/C11 plate 대비 → RF 잔차/탭/정보량 분석 | 미고정 입력으로 대규모 RT, 정적 RT에서 시간 상관 추정 단정, 독립 검증·실측 결과라고 주장 |

C3 재생과 P3 RT는 **서로 다른 과학 트랙**이다. C3 오류를 새로운 RT 실행으로 덮지 않는다. 사용자께서는 로컬에서 자체 RT 계산을 진행할 수 있지만, 결과가 연구 증거가 되려면 실행 전에 아래 RT 입력·파라미터·수량을 고정하고 실행기에서 fail-closed로 검증한다.

## 1. 연구 질문과 입증 가능한 주장

**1차 목표:** 같은 안테나·anchor·pose·solver 조건에서 C00 직접파, C01 바닥 반사, C10 평행판 반사, C11 경사판 반사가 복소 채널 H, first path, 거리 r, signed port-power ratio s 및 위치 추정 오차에 어떤 변화를 일으키는지 **측정 가능한 물리량으로 설명**한다.

- 원인 단계: 반사 경로의 추가·변화 → 복소 H의 진폭·위상·지연·각도 → CIR 및 tap/first-path 추출 → r, s 오차의 편향·분산·공간적 변화 → 추정기 갱신 및 불확실성의 차이.
- 구분: (i) 실제 LoS 가림, (ii) 반사파와 직접파 간 간섭, (iii) first-path index 변경, (iv) FFD 두 포트 편파 반응, (v) RF 오차 평균 및 분산, (vi) 게이트 선택 효과를 **서로 다른 진단 표**로 보고한다.
- 같은 장면을 바꿀 때 mean, variance, tap, LoS 등이 동시에 변할 수 있으므로 **RT 장면 변경을 correlation-only intervention으로 주장하지 않는다**.
- 정적 Sionna RT의 반복 pose는 동일한 deterministic channel을 만들며, **시간 OU/동적 센서 드리프트를 입증하지 못한다**. 동적 시계열은 물체 이동과 시각별 별도 scene hash/물리 변화가 명시적으로 도입될 때만 다룬다.
- 유효한 부정적 결과(반사 차이 미약, FP 전환 없음, EKF 악화)도 그대로 보존한다. 전 사례 성능 향상은 목표가 아니다.

## 2. 사전 입력·계산 계약 (P3-R0, RT 호출 0회)

계산 전 다음 요소를 코드 또는 설정 파일에서 **확정값과 SHA256**으로 기록한다. 값이 없으면 MISSING으로 표시하고 C00도 실행하지 않는다.

| 잠금 대상 | 필요한 필드/기준 | 현재 상태 |
|---|---|---|
| 기하/장면 | room mesh, world origin, 단위 m, 바닥·벽·plate 지오메트리, object/LoS blocking, scene family/variant | RT 실제 mesh SHA 미제공 |
| 재질 | 복소 유전율·전도도·표면 반사/산란 모델, 주파수 의존성, 재질별 material SHA | 미고정, 임의 숫자 대입 금지 |
| 안테나·좌표계 | anchor_xyz_m, robot_z_m, pose_xy_m, yaw_deg, mount_deg, port basis 및 LP±45° FFD orientation | 기존 Track S 참조 A=(2,2,2.65)m, robot z=.45m, mount=0°; RT scene과 실제 일치 여부 검증 전 재사용 금지 |
| FFD source | LP+45/−45 bank의 원본 SHA, SourceFFD 적용 코드 SHA, port/phase/order | 기존 FFD INPUT_LOCK SHA256: 28de7b01c9ef29175a7f5920b12ad700488c22f0b64eb9b5e0f4797eaa88d9ee. 이는 **과거 소스 잠금**, 새 RT 장면의 승인 증거가 아님 |
| Ray solver | Sionna 및 Python/Mitsuba 버전, solver backend, max_depth, samples, diffraction/scattering flags, frequency grid | 실제 실행환경에서 기록, 값을 추정해 채우지 않음 |
| RF extractor | complex H→CIR(257-bin convention)→tap→거리 r(m)·signed s(−1~1), 시간 원점·offset 적용 위치·first-path threshold, extractor SHA | 기존 소스 동등성 미검증. 과거 OFF=0.5315983906250129m는 적용 부호/지점 검증 전 새 RT에 자동 반영하지 않음 |
| 실험단위 | scene_family, scene_variant_id, anchor_id, trajectory_id, pose_id, rf_seed, sensor_seed, fold_id | calibration vs evaluation을 **scene variant 단위**로 분할; 동일 장면의 pose/anchor/seed는 독립 RT 실현이 아님 |

기존 code/rt_keys.py의 14개 REQUIRED 키를 모두 정확하게 채워 rf_cache_key()를 생성한다. pose_key()만으로 RF 캐시를 공유하지 않는다. scene/material/solver/FFD/extractor 중 하나라도 달라지면 새 RF key이다.

P3-R0 제출물: P3_RT_LOCK.json, SOURCE_SHA_LEDGER.json, SCENE_VARIANT_SPLIT.json, P3_RT_KEY_LEDGER.csv, EXTRACTOR_CONVENTION.md, PRE_P3_SELF_APPROVAL.json. 외부 감사자 이름이나 서명을 대신 생성하지 않는다.

## 3. 제안하는 최소 시뮬레이션 조합

기존 실험계약의 **canary 상한은 288 unique scene×anchor×pose 구성**이다. 사용자 직접 실행을 위한 **제안 초기안**은 다음과 같다(기본 승인값이 아님).

| 요인 | 최소 제안 | 의도 |
|---|---|---|
| 고정 anchor | 1개: 원본 좌표계와 정합 확인된 anchor A | 위치·경로 혼합을 피함 |
| 사전 고정 pose | 4개: 근거리/원거리/고·저 관측 민감도 또는 동일 pose의 yaw 대조 | 결과를 보고 고르지 않음 |
| Scene arm | C00_DIRECT, C01_FLOOR, C10_PARALLEL_PLATE, C11_OBLIQUE_PLATE | 동일 기하·안테나·solver 기반 paired contrast |
| 고유 RT key 상한(초기안) | 4 poses × 4 scenes × 1 anchor = **16** | ≤288 전체 canary 제한 이내 |
| 재현성 반복 | 각 key 동일 source/settings로 2회 결정론적 재실행 (선택) | 최대 **32 solver calls**; 같은 장면 반복은 독립 물리 표본이 아님 |
| 추가 장면 | C12 재질 변화, C20 room variation | 초기 canary 통과 전에는 포함하지 않음 |

32 calls는 **검증 요청서의 제한적 제안 수치이지 사용자 계산 예산 승인 기록이 아니다**. 직접 실행자는 실제 실행 직전에 PRE_P3_SELF_APPROVAL.json에 GPU/CPU 종류, 수량, 실행 wall-clock 상한, solver 호출 상한(실패·재시도 포함), RAM/VRAM·저장용량, 금액(로컬이라도 외부 비용 0원 여부)을 채워 승인 시각과 함께 잠근다.

### 단계별 진행

**P3-R0 — 정적 입력 검사(NO-RT).** Mesh 좌표계, FFD 포트·mount 변환, 최소·최대 범위, 직접 경로 존재 여부와 모든 해시·예산·split을 확인. 실패하면 STOP.

**P3-R1 — C00_DIRECT.** 고정된 4개 pose에서 direct-only 복소 H를 저장. geometry ray distance와 phase/delay, 2×2 port mapping, signed ratio s, first-path index를 LoS SourceFFD 기준에 맞춰 검증. 동일 key 2회 결과의 complex H 해시와 정량차를 기록. RF-01 numeric tolerances는 **최초 RT 결과를 보기 전에** 설정해야 한다.

**P3-R2 — C01_FLOOR.** R1과 같은 4 pose/anchor/solver/FFD/주파수 설정, floor 유무만 계약대로 변경해 H_direct/H_full, path count, delay, first path의 차이 기록. 장면 물리 조건 변경에 따른 H 변화이지, covariance-only 관측은 아니다.

**P3-R3 — C10_PARALLEL_PLATE / C11_OBLIQUE_PLATE.** 사전 기록된 plate 위치·각도·재질을 사용. C00/C01과 pose pair가 1:1로 일치해야 하며, shadow/blocked/FP switch 시점과 포트별 진폭·위상·지연을 원본 그대로 보존. 계산이 실패한 pose를 제외한 평균을 결과로 삼지 않는다.

**P3-R4 — 관측 오류·정보량 연결.** 각 scene/pose에서 epsilon_RF(q)=g(H_FULL(q))−h_LOS(q)를 산출하고 r/s의 mean/bias, marginal variance, cross-covariance, pose-distance/yaw separation별 잔차 차이·FP switch를 분석. 서로 다른 scene_variant가 충분히 생성되기 전에는 통계적 공간 상관 길이·신뢰구간을 확정하지 않는다. 참 Σ를 알고 있는 합성 S1 oracle을 실제 RT에서도 관측 가능한 모델인 것처럼 사용하지 않는다.

**P3-R5 — 측위 영향(조건부).** source/validity 및 학습/검증 scene split이 준비된 경우에만 기존 4-state 추정기에 실제 R 기반 µ/R을 **calibration variant에서만 추정해 고정**한 후 동등한 mask/controls로 비교한다. XY·rad/tan·heading RMSE, full 4×4 P/NEES4, nominal 95% coverage, NIS, per-arm failure counts를 보고. R5 단계는 필수 RT canary 승인 조건이 아니며 선행 통계 요건이 없으면 BLOCKED_INSUFFICIENT_SCENES.

## 4. 수치 승인·음성 시험

- DATA-01: 동일한 (scene, anchor, pose, solver, FFD, extractor) key에 대한 복소 H byte/hash 동일성 또는 **사전 기재된 환경 간 허용오차**와 실제 max_abs/max_rel/phase error 모두 보고한다. 단순 float 반올림으로 차이를 삭제하지 않는다.
- RF-01: direct-only C00 경로수·위상·delay·복소 H가 pinned analytic baseline과 물리적으로 일치하는가? 실험 전 설정한 absolute/relative 기준과 pass/fail 비교. 기준 미정이면 BLOCKED_TOLERANCE, 0.1% 등의 임의 허용오차 생성 금지.
- RF-02: invalid geometry, nonfinite H, 포트 재배열, first-path/tap 문제, r/s physical domain 위반(s∉[−1,1]), 미확인 shadow/LoS mismatch 발생 시 원시 로그 보존 및 STOP.
- MATH-02: 필요한 곳에서 covariance 대칭성·PSD. 기존 수학 계약 canary N≤32인 경우 정규화 대칭오차 ≤1e−12, 최소 고유값 ≥−1e−10×최대 고유값을 기준으로 독립 산술 검산. jitter는 계약값이 없으면 임의 추가하지 않는다.
- LEAK-01: scene_variant_id가 calibration / evaluation에 중복되지 않음. 동일 scene에서 path·anchor·sensor-seed만 바꾸어 독립 variant로 세지 않는다.
- 물리 음성 대조: 동일 pose/scene 반복은 동일 deterministic H; plate가 없는 C00에 reflection bounce가 있으면 scene 구성과 라벨 불일치로 STOP; 무효 first path, 반사 path index 변화는 기록하고 가려내지 않음.
- 통계 결론: 작은 4-pose canary 결과에 대해서는 **PHYSICAL_NUMERIC_PILOT**만 판정한다. correlation 모델 유효성, 일반적인 개선, 시간 상관을 확정하지 않는다.
- 실패 중단: 입력 SHA/scene/port/units 오류, payload 누락, 세션 판별불가, solver timeout/메모리 초과, 사용자 승인 호출수 또는 시간 상한 초과 시 즉시 중단하고 남은 key는 NOT_RUN으로 보존한다.

## 5. 산출물과 최소 CSV/JSON 명세

1. **INPUTS**: P3_RT_LOCK.json, SOURCE_SHA_LEDGER.json, SCENE_VARIANT_SPLIT.json, CONFIG_SNAPSHOT.json, P3_RT_KEY_LEDGER.csv (모든 14개 key SHA, 실행 순서, 상태).
2. **RAW RF**: complex H_FULL, H_DIRECT (가능하면 2×2 port×frequency bins), CIR/tap/FP metadata, delay/angles, reflection_count, LoS flag, FFD pattern, scene material and geometry SHA. 단순 PDF/그림만 제출 금지.
3. **OBS**: OBS.csv의 각 행에 scene_family, scene_variant_id, anchor_id, trajectory_id, pose_id, timestamp(실제 동적 시에만), x/y/ψ truth, r_true_m, r_obs_m, s_obs, h_r/h_s, eps_r/eps_s, FP tap, validity, missing_reason, RF cache key.
4. **VERIFY**: P3_NUMERIC_QA.json, C00_DIRECT_PARITY.csv, P3_SCENE_PAIRED_CONTRASTS.csv, REPEAT_IDENTICAL_POSE_HASH.csv, SOURCE_INPUT_BYTE_HASHES.json, FAILED_KEYS.csv, RUNTIME_BUDGET.json.
5. **MOTION / FILTER** (P3-R5 수행 시): SAME_MASK_LEDGER.csv, FRAME_YAW_TF_QA.json, POSTERIOR_FULL_C10.csv, INNOVATIONS_NIS.csv, METRIC_BY_SCENE.csv, H_CAL_VALIDITY.json. 기준행 소거 금지.
6. **REPORT**: GATE_DECISIONS.json, CAUSAL_LIMITATIONS.md, RUN_MANIFEST.json; 소스 SHA, pinned simulator/extractor 버전, 실제 runner/hardware, 실패 케이스·실패 이유와 원본 SHA, 다음 단계의 명시적 GO/NO-GO.

필수 판정 이름: SOURCE_VALIDATED, DIRECT_PARITY_PASS/FAIL, FLOOR_MATCHED_PASS/FAIL, PLATE_MECHANISM_OBSERVED/NOT_OBSERVED, INCONCLUSIVE_INSUFFICIENT_SCENES, BLOCKED_SOURCE/GEOMETRY/TOLERANCE/BUDGET, NUMERIC_PILOT_PASS/FAIL. 과학 효과는 SUPPORTED/MIXED/NOT_SUPPORTED/INCONCLUSIVE를 별도로 둔다.

## 6. 직접 실행자에게 전달하는 지시문 (Codex/Snowball용)

> 역할: IMPLEMENTER_SELF_RUN, 계약 MBVAR-INFO-001 / P3-RT-SELF-VERIFY-001, 과학적 독립 감사 없음(USER_AUTHORIZED_NONINDEPENDENT). 기존 저장소의 science source·생성된 S1/C3 데이터를 변경하지 말 것.
>
> 1. 원본 SCIENCE_SPEC, EXPERIMENT_CONTRACT, RT_KEYS schema, PR #23 pre-P3 proposal을 읽고 source/mesh/material/FFD/solver/extractor 전체 SHA와 numeric budget을 먼저 제시한다.
> 2. 누락된 필드는 채웠다고 가정하지 말고 BLOCKED를 출력한다. 예산이 정해지지 않았으면 solver를 호출하지 않는다.
> 3. 잠금이 충족되면 C00 DIRECT 극소 canary → C01 FLOOR → C10/C11 reflector 순서로 **동일한 4개 pose×anchor key**를 paired 계산한다. 실제 계산이 진행될 때마다 호출수·실행시간·메모리·파일 SHA와 실패/STOP을 기록한다.
> 4. 각 complex H는 2×2 포트와 원본 frequency/bin/frame conventions를 보존한다. source FFD analytic C00 parity에 실패하면 P3-R2/R3로 진행하지 않는다.
> 5. 일치하는 scene/pose 간 H, FP, r/s와 covariance/추정기 영향으로 이어지는 메커니즘을 분리해 비교한다. static RT로 시간 OU를 입증한다고 쓰지 않는다.
> 6. 모든 raw/manifest/failed records를 원본으로 남기고, 결과를 USER_AUTHORIZED_NONINDEPENDENT_EXPLORATORY로만 보고한다. 외부 감사자가 승인한 것처럼 기록하거나 DEV3·HOLDOUT2·RT 승인 범위를 서로 전용하지 않는다.

## 7. 현재 시작 전 체크

- [x] S1V5 DEV3 성공 및 원본 아티팩트 확인 (1,980/1,980, 0 failed/STOP).
- [ ] C3V5 1,080행 원본 truth hash 재생 오류 원인 규명, 기존 실패 보존.
- [ ] Sionna RT scene/material/pose/port/frequency/extractor 정확한 source SHA 완성.
- [ ] DIRECT analytic parity **사전 수치 기준** 설정.
- [ ] 직접 실행자가 사용할 최대 solver 호출수, wall time, hardware, VRAM/storage, 사용자 비용 상한 기입.
- [ ] 실행 계약 해시와 C00 canary 4 pose의 불변 ledger 확정.
- [ ] 계산 후 raw outputs·실패를 포함한 전수 technical QA.

**결론:** 외부 감사자를 새로 구할 필요 없이 직접 계산·재현성 확인을 진행할 수 있도록 계약과 검증 요청을 구성하였다. 다만 이 문서 자체는 실제 RT 계산 승인이나 PASS 증거가 아니다. 사용자가 자신에게 적용할 수치 계산 상한과 정확한 RT 입력을 확정한 뒤에만 P3 solver를 실행하고, 결과는 비독립 내부 탐색 데이터로 구분한다.
