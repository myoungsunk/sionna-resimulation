# 고정-truth Sensor-v2 noisy 회전 제한 대조군 — 완료 7케이스 보고

작성일: 2026-10-10. 사용자 승인 범위는 기존 고정-truth 회전 대조군이다. 실제 actuator/접지 slip이 참 XY/yaw를 바꾸는 모델, 하드웨어 운영 성능은 이번 실행에서 검증하지 않았다. 이 문서는 완료된 7케이스의 결과와 회수된 전체 P6 자료를 다룬다. 추가 native full RF 5케이스는 별도 진행 상태와 산출물로 구분한다. **통합 사양서 09 전체 완료나 scientific PASS를 뜻하지 않는다.**

## 질문과 기대값

저장된 전체 P6를 회수하고, 같은 초기 추정 상태와 prior에서 noisy gyro·wheel을 사용해 1/2/3점 RF 관측을 수행하면 어떤 정확도와 공분산 일관성이 나타나는가? 기대값은 기존 sensor-v2의 업데이트 식과 공유 입력 규약을 유지하고 각 단계의 상태·전체 공분산·관측을 추적할 수 있다는 것이다. RMSE 개선, NEES 정상화 또는 RF 모델 정합은 기대값으로 강제하지 않았다.

구동 모델이 없는 상태에서 본체의 실제 slip 이동을 발명하지 않았다. 참 XY는 고정하고 참 yaw는 저장된 RF pose의 yaw를 잇는 사전 정의 일정으로 회전한다. 센서 bias/noise/slip은 측정값에만 반영된다. 가속·감속 dynamics는 없다. 일정 속도 회전, 0.4초 정착, 원 heading 복귀까지 총 3.2초를 모든 arm에 동일하게 적용한다.

## 동결한 코드·입력·실행 환경

통합 사양서 revision은 `7fefdbbf6c4f36ebff72fb281bbbbc5900fffd25`, 경로는 `research/HEADING_RELIABILITY_20261010/09_COMBINED_HANDOFF_FULL_COV_AND_MOUNT_0_45_KO.md`다. 센서·필터 원 source는 `16d22fc3121963743cf7f1bf56233e00083c5518`, 보존 root는 `/home/KMS/DRIVE_SIM_HEADING_SENSOR_V2_20261010_01a124ff`다. `SOURCE_INTEGRITY.json`에서 원 source 105개 파일의 내용 해시가 원 SOURCE_MANIFEST와 일치했다. 소스 브랜치 이름을 실행 동일성 근거로 쓰지 않았다. 원 sensor/filter source는 수정하지 않았다.

새 실행 root는 `/home/KMS/DRIVE_SIM_NOISY_PROBE_20261010_01a125b3`, 신규 별도 harness는 이 전달본 `HARNESS/`에 있다. Docker image ID는 `sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f`, 센서 runtime은 Python 3.11.15 / NumPy 2.4.6 / SciPy 1.17.1 / Pandas 3.0.6이다. 실제 명령·시작/종료 시각·exit code·자원은 별도 `EXECUTION_RECEIPTS.json`에 보존한다.

LUT SHA256은 `711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079`, metadata는 `8773e79fbb39d07fd80605339a0752e6e4e5eb0658572f091e67395ab0fd5856`, 주파수축은 `fe0bcfeb1426847ea090668845fe124482086d0510e38ebdb463609e2a1169f8`다. 실제 LP±45 FFD bank는 각 약 237 MiB의 NPZ이며 LFS pointer가 아니다. 원 bank는 읽기 전용으로 사용하고 파일을 복제 게시하지 않았다. 원 경로와 hash는 `PRE_CORRECTION_ARCHIVE/INPUT_MANIFEST.json` 및 bank manifest에 있다.

실행 전 조건은 `PLAN.json`, `BODY_CONTROL_PREREG.json`, `BODY_STREAM_AMENDMENT.json`, `BODY_TASKS_existing7.json`에 보존했다. eval prior는 원 Tnone의 `keep`, `completed`, t≥30초 대응이며 truth를 초기화에 넣지 않았다. mount45에도 대응 mount0 RF-off prior를 동일하게 사용했으므로 실제 mount별 독립 주행 초기화 검증이 아니다. dt=0.2초, nominal 최대 회전속도25°/s, yaw offset은 저장본의 부호에 따라 [0,±10,±20] 또는 [0,±9.52,±19.04]도이다. hardware 제한 측정값이 아니다.

sensor seed 0–4, drift 0–2, nominal SNR30/10을 사용했다. 미래 센서 noise stream은 원 prior에 이미 반영된 과거 noise를 재사용하지 않도록 별도 SeedSequence로 고정했다. drift 정적 calibration draw는 원 규약을 유지했다. 같은 task의 arm 및 mount에는 같은 sensor/RF 기본 난수를 사용했다. 자세한 키는 `HARNESS/body_controls.py`의 `probe_rng`와 `key`에 있다. Q/R/gate/prior는 기존 설정을 유지했으며 새 receiver 열잡음의 사전 정의 분산만 nominal SNR에서 산출한다. measured-increment Q 근사, heavy-tail slip, unknown wheelbase 및 calibration 초기오차가 있으므로 완전 정합 Gaussian 대조군이라고 부르지 않는다.

## 방법과 실행 규모

원 5,250개 주행 RAW에서 각 station에 대응하는 pre/post 전체 상태·6×6 공분산을 회수했다. 96,750개 대응행 중 평가 prior가 있는 행은78,000, 평가 mask 밖은18,750이다. NOT_IN_TNONE는283,500개 run별 반복 대응행이며 독립 RF pose 수가 아니다. covariance invalid0이다. 원 `pre_rf_cov`는 after-odom/before-range다. 이를 새 이름으로 명시했고 원 after-odom/range/RF 값은 그대로 복사했다. predict-before-odom은 저장된 직전 posterior와 F/G/Q로 재구성한 **DERIVED** 필드이며 원 RAW에 직접 저장된 값처럼 표현하지 않는다.

새 시험의 7케이스는 R2-A-m0, R2-B-m0, R2-A-m45, R4-A/B-m0, R5-A/B-m0다. 원 5,070개 station×drift×seed×SNR task 중 4,050개는 대응 평가 prior가 없어 `NO_EVALUATION_PRIOR`로 보존했다. 이를0오차나 성공 run으로 채우지 않았다. 실제 34개 case-station, **16개 서로 다른 XY 위치**, 1,020개 유효 task ×6arm =6,120개 비교 run이다. 같은 corridor와 인접 XY이므로16개가 통계적으로 독립인 geometry라고 주장하지 않는다. sensor 반복 단위는5seed뿐이다.

A는 RF-off, B는 full RF range3개, C는 **B의 full RF range + native LoS s3개**, D는 full RF range+s3개다. G1/G2는 첫1/2개의 **range+s packet**만 사용하되 동일3.2초 clock을 유지한다. G3는 D와 정확히 동일하여 별도 실행하지 않았다. G1/2와 D의 차이를 s 관측 개수만의 효과로 해석할 수 없다. F/H의 correlated mixture 및 q_site/q_point는 구현하지 않았고 적용하지 않았다.

본 실행6,120개는 실패0이며 별도 C 수정 재실행1,020개 역시 실패0다. 실제 계산 run 수는7,140개(+파일 경로 확인 후 pilot6개)이고, **주 비교표는 C를 교체한6,120개**다. 재실행을 추가 seed나 독립 반복으로 세지 않는다. source 원 5,250회 주행은 다시 실행하지 않았다.

## 이번 harness 결함과 최소 수정

초기 별도 harness의 C는 `chosen=LoS`를 range와 s 모두에 적용했다. 사양서와 원 simulate.py의 C는 B와 같은 full RF range를 유지해야 한다. 따라서 초기 C는 사양서 C가 아니며 `C_LoS_RANGE_AND_s` 진단으로만 남긴다. 수정 전 source와6,120회 산출물은 `PRE_CORRECTION_ARCHIVE`에 불변 보존했다.

`C_ROUTING_CORRECTION_PREREG.json`을 먼저 기록한 뒤 `chosen=obsl if arm=='C' and m=='s' else obs`로 신규 harness만 수정했다. 센서·필터 원 source, Q/R/gate/prior 및 난수는 바꾸지 않았다. C만1,020회 다시 실행했고 독립 저장배열 검산도 수행했다. 수정된 C raw는 `C_CORRECTION_ARCHIVE`, 최종 비교표는 `SUMMARY_CURRENT/10_SPEC_ALIGNED_RESULTS.csv`다. 원 `10_PAIRED_FILTER_RESULTS.csv`와 원 요약표를 최종 사양서 비교로 혼용하면 안 된다.

## 실제 결과

다음은 nominal SNR30의 case×drift×seed 단위 station endpoint RMSE/NEES/coverage를 기술적으로 평균한 값이다. 서로 독립인105seed를 뜻하지 않고, full-route RMSE나 pooled sample RMSE도 아니다. 주 비교는 case/drift/SNR별 표와 seed 대응 차이표이며 극단값은 raw 및 stage 표에 보존했다.

| arm | heading RMSE 평균(°) | 위치 RMSE 평균(m) | pose NEES 평균(df3) | pose95% coverage | heading95% coverage |
|---|---:|---:|---:|---:|---:|
| A | 3.0180 | 0.7381 | 3.2085 | 0.9157 | 1.0000 |
| B | 3.5602 | 0.8400 | 13.6659 | 0.4881 | 0.8310 |
| C | 1.6393 | 0.4042 | 955.5227 | 0.5490 | 0.9214 |
| D | 3.8211 | 0.9578 | 1003.9818 | 0.3805 | 0.5957 |
| G1 | 3.4160 | 0.8487 | 386.8730 | 0.6833 | 0.8624 |
| G2 | 3.8216 | 0.9518 | 868.3915 | 0.4843 | 0.6857 |

C는 이 제한된 표에서 heading/위치 정확도가 좋아졌지만 pose NEES 약955.5 및 coverage 약0.549로 covariance 일관성이 확보되지 않았다. D는 RF-off A보다 정확도와 일관성 모두 악화된 기술적 결과다. 이 수치로 기존 거리 조건부 R의 NEES≈320.776에 대한 원인 기여율을 계산하지 않는다. 기존 장거리 주행과 이번 짧은 고정-XY 회전은 서로 다른 시험이다.

SNR10 결과, seed별 분포, 대응차이, NIS(pre-gate/accepted-only) 및 rejection은 `11_SPEC_ALIGNED_SEED_UNIT_METRICS.csv`, `12_SPEC_ALIGNED_CASE_DRIFT_SNR_ARM.csv`, `13_SPEC_ALIGNED_PAIRED_DIFFERENCES.csv`, `14_SPEC_ALIGNED_EVALUATION_STAGES_AND_UPDATES.csv`에 있다. third RF 직후와 복귀 후 endpoint를 구분했다. pose NEES는[x,y,heading]의3자유도, heading wrapping은radian으로 계산했다. 하·상 Gaussian 참고값0.215795/9.348404는 탐색적 양측 진단이며 새로운 승인 PASS gate가 아니다. 시간 sample이나 station을 독립 Monte Carlo로 취급하지 않았다.

## 검증이 입증하는 것과 입증하지 않는 것

저장배열의 독립 계산으로6,120 trace의520,200개 stage covariance와97,920개 transition/odom을 검사했고 위반0이었다. 수정 C1,020 trace의86,700개 stage covariance도 위반0이었다. SE(2) mean, F/G 전파, 공유 잡음 C=-GQBᵀ, joint innovation/gain/posterior 식, covariance 대칭/PSD 및 NEES를 원 필터 호출 없이 별도 계산했다. 입력/prior/clock의 arm 간 일치는 확인했다. 이는 **식 적용과 저장의 일치**를 입증하며 RF Jacobian의 물리적 정합이나 covariance의 통계적 calibration PASS가 아니다.

원 RF와 noise를 offline 복원해1,020묶음의 P1/P2/s/range/tap을 저장 packet과 대조했고 차이는0이었다. CIR amplitude와 noisy H는 `RF_RAW_RECONSTRUCTED.npz`로 전달한다. 이것은 시뮬레이션 데이터이며 실제 receiver에서 full CIR을 읽을 수 있다는 하드웨어 증거가 아니다. correction C는 동일 RF packet을 재사용한다.

receiver joint covariance는[s0,s1,s2,range0,range1,range2]6차원으로 centered ddof1 계산했다. 169 case-station에서 SNR별32 thermal 반복, MP 공간 추정148묶음, 자료 부족21묶음이다. 별도 검산에서486개 finite covariance의 PSD/centering 위반0이었다. **추정 가능성만 확인했으며 held-out predictive coverage는 검증하지 않았다.** 파일의 `validated`는 최소 표본을 충족한 추정 가능 flag, `independent_site_count`는 서로 다른 XY 수일 뿐 독립성 입증이 아니다. 열잡음 covariance는6개 관측이 모두 유한·검출된 반복에 조건부이며 per-draw missing mask는 저장되지 않았다. 이 조건부 선택 한계를 함께 읽어야 한다. Σ_sr는 온라인 EKF에 적용하지 않았다.

MP 보정은 같은anchor/mount에서 평가route와 동일XY를 제외한 distinct XY 평균 벡터를 사용하고 최소8위치를 요구한다. R2-A-m45의 다른route 자료가 없어 일부 추정이 불가능하다. 같은 corridor 공간 표본 간 상관은 남는다. full−nativeLoS 잔차에는 RF 체인/tap/방법 차이가 포함될 수 있어 물리적 다중경로만의 독립 정답이라고 부르지 않는다. 직접 FFD LoS와의 e_LUT 분해는 이번 noisy 대조군에서 재검증하지 않았다.

공유 gyro를 포함한 서로 다른 시점 pose의 교차공분산 및 pose–측정 상관이 검증되지 않았으므로 delta yaw 분산을 단순 P_i+P_0로 만들거나 Σ_probe를 반복 독립 적용하지 않았다. 따라서 F/H 공동추정, q_point/q_site, branch mixture posterior, geometry held-out 성능은 **NOT_IMPLEMENTED / NOT_INDEPENDENTLY_VERIFIED**다. 단순 full P6 확보와 joint covariance 사용 완료를 혼동하지 않는다.

## 자료 전달과 해시

수정 전 archive:913,611,329byte, SHA256 `d213f198e89afc28b0ce68ceffc9ddeb634ea32a69418985943f231f53ac1750`.
C correction archive:36,096,873byte, SHA256 `677fcf927659befad973c36fc4d76ffc292c703a4285d75590e62aee86053974`.
32MiB shard별 해시 및 결합 해시를 로컬에서 대조했고 모두 일치했다(`DOWNLOAD_INTEGRITY.json`)。 shard는 LFS pointer가 아닌 실제 bytes로 게시한다. 입력/출력 file별 SHA256은 각각 archive 폴더 manifest와 최종 `PUBLICATION_MANIFEST.json`에 있다. `.part-*`를 순서대로 이어 tar.gz로 복원한 후 별도 새 디렉터리로만 해제한다.

전달 범위는 station-matched P6 subset, 새 control 전체 trace·inputs·RF/CIR, 선택 full/LoS H, LUT/frequency/timeline, covariance 진단 및 실행 harness다. 원 약7.2GiB 주행 RAW_ARCHIVE.tar 전체는 원 Snowball 보관본에 보존되어 있으며 이번 GitHub shard에 전부 복제하지 않았다. FFD bank 원bytes 또한 외부 보존 입력이다. 전체 timeline 보관본·하드웨어CIR/수신 gain/noise-floor 측정·실제 actuator/slip dynamics가 필요한 항목은 별도 blocker다.

## 판정과 이후 범위

완료: 기존 P6 회수와 source 보존 확인, antenna/LoS 제한 preflight, 기존7케이스 fixed-truth noisy 대조군과 C correction, 저장배열 독립 수식 검산, receiver covariance/cluster2·4·8ns 진단 및 raw 회수.

부분 완료: mount0/45 대칭12케이스. 신규5nativeLoS는 생성 완료했지만 nativefull5와 모든 입력 parity가 승인된 전체 gate를 통과한 것은 아니다. 기존7 실행은 이를 앞서 수행한 제한 pipeline 진단이며 사양서12케이스 본격 비교 완료라고 확대하지 않는다. nativefull과 legacy MethodB H 사이 차이도 자동 interchangeability 증거가 아니다.

미수행: 실제 XY/yaw slip 이동·가감속 모델, full-route 재통합, head회전, F/H mixture, 새로운 geometry held-out, receiver gain/noise-floor 하드웨어 calibration, exact directLoS oracle e_LUT 재검산 및 모든 주파수 경로별 interaction 보존. 발견된 covariance/모델 한계를 noise나prior tuning으로 숨기지 않았다.

**F01/F02 OPEN, L1 FAIL, scientific_PASS=false 유지.** 이번 결과는 후속 joint covariance/측정모델 연구의 입력 자료이며 production·hardware 채택 근거가 아니다.
