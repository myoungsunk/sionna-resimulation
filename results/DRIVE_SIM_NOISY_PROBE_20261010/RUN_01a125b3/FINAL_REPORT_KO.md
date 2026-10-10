# Sensor-v2 고정-truth 회전 대조군: 최종 실행·데이터 전달 보고

2026-10-10. 실행 완료, 자료 검산, 게시를 구분한다. 사양서 전체 완료나 물리적 로봇 성능 PASS를 선언하지 않는다. F01/F02 OPEN, L1 FAIL, `scientific_PASS=false`를 유지한다.

## 범위와 질문

사용자는 기존 고정-truth 회전 대조군을 승인했고, 남은 RF와 세 실행을 마무리해 게시하고, 없는 초기 상태·공분산을 재생성하도록 요청했다. 이후 자원 정책을 최대에서 중간 수준으로 변경했다. 이번 결과는 정해진 XY/yaw 궤적에서 센서 오차를 생성하는 제한 시험이다. 실제 actuator 가감속, wheel-ground slip이 true XY를 바꾸는 운동, 실제 로봇 운영 검증은 수행하지 않았다. F/H 공동 신뢰도 모델도 구현·실행하지 않았다.

## 코드·입력 동결과 보존

사양서 브랜치 `codex/probe-mixture-reliability-20261010`, 기준 `7fefdbbf6c4f36ebff72fb281bbbbc5900fffd25`, 통합 문서 `research/HEADING_RELIABILITY_20261010/09_COMBINED_HANDOFF_FULL_COV_AND_MOUNT_0_45_KO.md`를 기준으로 했다. 실제 센서 소스는 `16d22fc3121963743cf7f1bf56233e00083c5518`의 Snowball 저장 소스이며, 105개 source manifest 항목의 내용 해시가 일치했다. 원 센서·필터 소스, Q/R/gate, 기존 RAW, 사전등록은 변경하지 않았다. 신규 계측과 correction은 이 실행 디렉터리의 별도 harness에 한정했다.

- 작업: `/home/KMS/DRIVE_SIM_NOISY_PROBE_20261010_01a125b3`; SSH 계정 `KMS`.
- 기존 센서 데이터: `/home/KMS/DRIVE_SIM_HEADING_SENSOR_V2_20261010_01a124ff`.
- 기존 RF 7케이스: `/home/KMS/DRIVE_SIM_POST_A23_SUPPLEMENT_20261010_01a12449/BLOCK_C`.
- route: `/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source/results/DRIVE_SIM_20261007/S1/routes`.
- 실제 FFD bank: `/home/KMS/COOL_DIJKSTRA_20261007_01a11582/source/LP_plus45_bank.npz`, minus45; bank 자체는 외부 보존 입력이다.
- LUT SHA256 `711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079`; metadata `8773e79fbb39d07fd80605339a0752e6e4e5eb0658572f091e67395ab0fd5856`; 주파수 `fe0bcfeb1426847ea090668845fe124482086d0510e38ebdb463609e2a1169f8`.
- 원 주행 RAW tar SHA256 `96398a070d12e4613c29e2bcd40df5088a49ecb806556971ecf3790703116b75`는 원 위치에 보존했다. 약 7.2 GiB 전체 주행 archive를 이번 Git 자료에 복제하지 않았다. 전달 범위는 선택 주행 시점의 공분산·센서 입력, 신규 준비/프로브 전 단계 trace이다.
- 환경 image `rt-dual-engine:s2-deps-r2-20260928`, image SHA256 `18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f`; 센서 Python 3.11.15, NumPy 2.4.6, SciPy 1.17.1, Pandas 3.0.6. 실행별 정확한 command/image/state/cpu/memory는 `SUMMARY_FINAL/EXECUTION_RECEIPTS.json` 및 archive의 receipt에 저장했다.

## 왜 오래 걸렸고 어떻게 완료했는가

초기 native full RF는 solver당 1 thread, 케이스 병렬 5개로 시작해 host 자원을 충분히 사용하지 못했다. 7,200초 제한에서 3케이스가 완료되고 R5 두 케이스가 부분 저장 상태로 종료됐다. 이 최초 실패와 부분 H를 보존했다. solver thread를 64로 늘린 별도 재시도는 기존 주파수와의 재현 guard에 실패해 채택하지 않았다. thread 변경이 원인이라는 물리적 확정은 하지 않는다.

최종 방식은 solver 자체를 원래 1 thread로 유지하고 주파수별 계산을 독립 process로 병렬화했다. 사용자 변경에 따라 우리 job CPU 상한을 64로 낮췄다. 약 6,382% CPU 사용을 확인했다. 다른 연구 job은 변경하지 않았다. R5-A/B의 0·128번 bin, 총 4개 겹침 계산은 복소 H 상대 오차 0이었다. 이 guard 뒤 136개 누락 주파수 batch를 계산해 약 235.25초에 완료했다. threshold나 RF 물리 설정을 완화하지 않았다.

최종 추가 RF 5케이스는 R2-B m45, R4-A/B m45, R5-A/B m45이며 전부 완료됐다. 이 완료는 사용한 계산 설정의 결과 확보를 뜻한다. Method A/B 동등성, L1/L2 전체 gate, 안테나 하드웨어 검증을 뜻하지 않는다. 원 7케이스 RF와 신규 native 5케이스의 생성 계통 차이는 보존한다. 신규 native 설정은 depth 3, samples 100000, max paths 1000000, synthetic array, LoS/specular/refraction 켬, diffraction/edge/diffuse 끔, seed 20260924이다.

센터 주파수의 경로 지연·계수·interaction/object 자료를 보존했지만 모든 주파수의 face/type label을 저장했다고 주장하지 않는다. 기존 부분 결과의 미저장 prefix path-count는 `-1`로 남겼다. 최초 부분/실패 registry와 최종 유효 registry `NATIVE_FULL_EFFECTIVE_STATUS_FREQUENCY.json`를 분리했다.

## 없는 초기 상태·공분산을 어떻게 만들었는가

74개 route station group 모두 기존 Tnone 궤적에서 같은 XY에 대응했고 최대 XY 차이는 6.40975e-7 m였다. 2 anchor × 3 drift × 5 seed = 2,220개 prior 항목 중 480개는 기존 유효 저장 posterior를 재사용하고 1,740개는 새로 만들었다. pose truth를 초기 추정값으로 대체하지 않았다.

신규 prior는 같은 XY에 가장 가까운 기존 RF-off after-odom 추정 상태·P6에서 시작했다. 필요한 대기 후 원래 sensor-v2로 yaw 정렬과 0.4초 정착을 수행해 절대 시각 30초 이후 prior를 만들었다. preparation sensor random stream은 별도 suffix 919로 동결했고 기존 drift calibration draw는 유지했다. 준비 과정의 truth는 offline 정답·명령 기하에만 사용했다. 대기·정렬 중 UWB는 껐다. Q/R/gate를 바꾸거나 정확 truth로 reset하지 않았다.

새 prior는 원 전체 주행을 그대로 다시 생성한 초기 조건이 아니다. `NEW_RF_OFF_WAIT_AND_YAW_ALIGNMENT`로 표시하고, 기존 `LEGACY_SAVED_POST_ODOM`, `LEGACY_MATCHED_PRIOR`와 모든 통계에서 구분한다. prior/P6, preparation trace, F/G/Q/C/S/H와 원 source hash가 각 항목에 있다. 독립 posterior 식 검산의 허용오차 1e-10과 PSD 검사를 통과했다.

## 프로브 실행과 최소 correction

seed 0–4, drift 0–2, SNR 30/10, route R2/R4/R5, anchor A/B, mount 0/45를 사용했다. A(RF off), B(range), C(full range+LoS s), D(full range+full s), G1/G2(첫 1/2 packet) 6 arm을 같은 센서 입력과 초기 prior로 비교했다. G3는 D의 alias이며 별도 실행으로 세지 않는다. 최대 25 deg/s, dt 0.2초, 같은 세 waypoint와 복귀 clock을 사용했다. 고정-truth slip은 센서 생성 오차이고 실제 XY 이동이 아니다.

기존 7케이스의 첫 C 구현은 LoS range까지 사용해 사양과 달랐다. 원 데이터를 보존하고 C만 1,020회 재실행해 full range+LoS s로 바로잡았다. 추가 실행의 첫 harness에서는 metadata 변수 이름이 예측 상태 변수와 충돌해 IndexError가 발생했다. 실패 partial trace를 보존했다. `_v2` 복사본에서 metadata 변수만 수정했으며 6 arm pilot에서 실패 전 A trace와 배열이 정확히 같음을 확인했다. 별도 RF raw recovery의 첫 launch는 잘못된 route volume 경로로 종료됐고, 확인된 원 route root를 mount한 두 번째 launch에서 성공했다. 필터 수치 오류를 clamp/jitter로 숨긴 수정은 없다.

최종 주 분석은 기존 correction 후 6,120회와 추가 47,160회, 합계 53,280행이다. 키 누락/중복·실패 0, 위치/heading/NEES finite를 확인했다. 이는 53,280개 독립 seed가 아니다. 반복 seed는 5개뿐이며 station/time/anchor/mount가 독립 통계 표본이라는 가정을 하지 않았다. 별도 최초 C·pilot·실패 시도를 최종 53,280행에 추가해 중복 집계하지 않았다. 추가 실행 시간은 container 및 driver receipt를 따르며 결과를 맞추는 tuning은 하지 않았다.

## 실제 결과와 검증이 입증하는 범위

추가 47,160개 arm trace의 4,008,600개 단계 공분산에 대해 원 필터를 다시 호출하지 않는 별도 배열 계산으로 SE2 prediction, 공유 입력 `C=-GQBᵀ`, innovation S, correlated Joseph update, NEES, 동일 입력/clock 및 단계 PSD를 확인했다. 32개 slice 모두 exit 0, 위반 0이었다. 이 결과는 저장 trace의 계산 일치를 지지하며 분포적 일관성이나 RF 모델 적합성을 증명하지 않는다.

7,860개 추가 packet group의 원 H와 동결 thermal stream에서 RF raw를 offline 복원했다. 원 packet의 P1/P2/s/range/tap과 차이는 0이었다. 이는 저장 값 대응 검산이며 신규 RF solver 실행이 아니다. 원본 noisy H, CIR amplitude, thermal innovation, port 순서와 선택 tap을 보존했다.

다음 표는 SNR30, case×drift×seed 단위 station endpoint RMSE를 평균한 기술 통계이다. full-route RMSE나 5-seed 신뢰구간 판정으로 해석하지 않는다. 상세 seed 분포, NIS pre-gate/accepted-only, rejection은 `SUMMARY_FINAL/FINAL_SEED_PRIOR_KIND_METRICS.csv`에 있다.

| prior | arm | heading RMSE deg | position RMSE m | pose NEES df3 | pose coverage |
|---|---|---:|---:|---:|---:|
| LEGACY_MATCHED_PRIOR | A | 3.001 | 0.693 | 3.46 | 0.909 |
| LEGACY_MATCHED_PRIOR | B | 3.460 | 0.750 | 10.92 | 0.598 |
| LEGACY_MATCHED_PRIOR | C | 1.729 | 0.441 | 3557.61 | 0.673 |
| LEGACY_MATCHED_PRIOR | D | 2.999 | 0.784 | 3051.99 | 0.584 |
| LEGACY_MATCHED_PRIOR | G1 | 3.050 | 0.787 | 501.32 | 0.730 |
| LEGACY_MATCHED_PRIOR | G2 | 2.825 | 0.728 | 1605.05 | 0.684 |
| LEGACY_SAVED_POST_ODOM | A | 3.018 | 0.738 | 3.21 | 0.916 |
| LEGACY_SAVED_POST_ODOM | B | 3.560 | 0.840 | 13.67 | 0.488 |
| LEGACY_SAVED_POST_ODOM | C | 1.639 | 0.404 | 955.52 | 0.549 |
| LEGACY_SAVED_POST_ODOM | D | 3.821 | 0.958 | 1003.98 | 0.380 |
| LEGACY_SAVED_POST_ODOM | G1 | 3.416 | 0.849 | 386.87 | 0.683 |
| LEGACY_SAVED_POST_ODOM | G2 | 3.822 | 0.952 | 868.39 | 0.484 |
| NEW_RF_OFF_WAIT_AND_YAW_ALIGNMENT | A | 3.145 | 0.570 | 7.30 | 0.862 |
| NEW_RF_OFF_WAIT_AND_YAW_ALIGNMENT | B | 3.832 | 0.639 | 13.77 | 0.686 |
| NEW_RF_OFF_WAIT_AND_YAW_ALIGNMENT | C | 1.986 | 0.425 | 12.98 | 0.728 |
| NEW_RF_OFF_WAIT_AND_YAW_ALIGNMENT | D | 3.635 | 0.702 | 18.61 | 0.640 |
| NEW_RF_OFF_WAIT_AND_YAW_ALIGNMENT | G1 | 3.510 | 0.653 | 10.27 | 0.778 |
| NEW_RF_OFF_WAIT_AND_YAW_ALIGNMENT | G2 | 3.650 | 0.685 | 13.69 | 0.694 |

작은 RMSE와 올바른 공분산은 별개다. 표의 큰 NEES와 낮은 coverage를 PSD 검산 PASS로 덮지 않는다. NEES subspace는 [x,y,heading], df3이다. 하/상 tail 0.215795/9.348404는 기술 통계용 chi-square 경계이며 새 scientific PASS 기준을 승인한 것이 아니다. prior별·case별 평가를 유지하고 과신의 인과 기여율을 이번 데이터만으로 확정하지 않는다. 기존 NEES≈321은 다른 production/조건부-R 실험이므로 동일 기준값으로 비교하지 않는다.

## 전달 파일과 미완료 항목

- `PRE_CORRECTION_ARCHIVE`: 처음 7케이스 원 데이터 및 correction 전 증거.
- `C_CORRECTION_ARCHIVE`: 사양에 맞춘 C 재실행 원 데이터.
- `RF_PRIORS_ARCHIVE`: 추가 native RF, 실패 재시도, 최종 H 및 새 prior/preparation trace.
- `ADDITIONAL_CONTROLS_ARCHIVE`: 추가 47,160회 전체 x6/P6, Predict→Odom→Range→RF 단계, 입력·innovation·R/S/NIS·수용 상태·mask·oracle, 복원 RF raw, 독립 검산 및 harness.
- `SUMMARY_FINAL`: 최종 53,280행, seed/prior별 요약, 최종 receipt·검산 결과.
- `VERIFY_UNPACK.py`: shard→joined archive→각 payload 파일의 해시를 검사하고 지정한 새 폴더에만 추출한다. `PACKAGE_MANIFEST.json`, `OUTPUT_MANIFEST.json`의 경로·크기·SHA256으로 대응한다. shard 최대 32 MiB이며 LFS pointer로 대신하지 않는다.

전체 원 주행 archive와 FFD bank는 외부 원본 경로 및 해시로 추적하며 Git에 전부 복제한 것으로 표현하지 않는다. 추가 5케이스의 Sigma_probe 독립 calibration/coverage 검증, 시점 간 pose covariance 및 pose–measurement 교차공분산, F/H q_point/q_site/heading posterior 공동 추정은 미실행이다. 기존 7케이스 Sigma 추정의 PSD/표본 조건 검사는 추정량의 적격성 확인이며 coverage 검증이 아니다. native LoS−LUT 차이를 독립 FFD 직접 LoS의 e_LUT라고 부르지 않는다.

다음 작업에는 cross-time covariance 검산과 F/H 공동 추정 구현 및 분리 calibration/evaluation 설계가 필요하다. 이번 실행에서 자동 시작하지 않았다. 실제 차체 운동과 하드웨어 성능도 미검증이다. 실행·업로드 완료를 F01/F02 해결, L1 PASS, scientific PASS로 확대하지 않는다.

표시 필드 정정: 원 archive의 `coverage95_worst` 필드는 최대 coverage를 담았다. 최종 별도 `FINAL_CONTROL_SUMMARY_CURRENT.json`에서 최소/최대 필드를 명시했다. 원 측정·필터·CSV 값은 변경하지 않았고 원 JSON은 보존했다.

