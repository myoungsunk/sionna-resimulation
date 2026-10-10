# A23 rev3: Q2·joint 및 제한 Sionna LoS-only 실행 보고서

2026-10-10. **추가 필터 1,650회와 LoS-only solver 2,056회 완료. Q2는 선택한 모형 내 요인 영향 지지, joint lag0 추가 효과는 불확정, 원 L2는 FAIL 재현. F01/F02 미해결 및 scientific_PASS=false 유지.** 모델 수정·채택·독립 일반화는 수행하지 않았다.

## 질문 → 기대값 → 고정 방법

Q2는 실제 range가 백색 대조보다 NEES를 키우는 현상을 편향·시간 상관·거리/tap 조건 구조로 구분해 묻는다. joint는 s와 range의 lag0 교차상관을 추가했을 때 독립 AR 모형과 다른 결과가 생기는지 묻는다. RF 범위는 사용자가 선택한 제한 Sionna LoS-only 신규 실행까지다.

실행 전 PLAN.json으로 R2-A m0, P0, SNR30, drift0/1/2, seed0–49를 고정했다. Q2 R1–R8 1,200회와 J1–J3 450회다. 이전 A0/M0/W0/Q1 1,650회는 재실행하지 않고 검증 결과를 복사·재사용했다. 통합 표는 22arm×3drift×50seed=3,300행이다.

L2는 원 lut_los_check.py의 seed20261007과 순차 uniform x∈[1,19]m, y∈[−0.7,0.7]m, yaw∈[−50,230]°로 8pose를 선택했다. 목록을 solver 전에 저장했다. 257주파수×8pose=최대2,056호출, 최대600초를 고정했다. max_depth=0, los=true, specular_reflection=false, refraction=false다. 원 판정 max|s_LUT−s_Sionna|≤0.005와 기존 LUT를 유지했다. sample·threshold를 유리하게 바꾸지 않았다.

모든 A23 arm의 R/Q/gate/prior/센서/초기화는 같다. range R=0.006857863713357258, s mismatch variance=0.025905641605086252, gate6.6349, pos_process_std0.01, dt0.2s, 평가 mask t≥30s(829sample/run)다. 기존 s 열잡음 처리도 유지했다. prior std는 [0.1,0.1,0.0872664626,0.0020943951,0.0104,0.0064]다. 생성/오프라인 진단의 truth 사용과 estimator 입력을 구분했고 estimator에 truth를 공급하지 않았다.

추가 대응 차이 bootstrap은 주 결과 평균을 본 뒤 고정한 **탐색적 후속 분석**이다. PAIRED_ANALYSIS_PLAN.json의 11contrast, seed20261010, 5,000resample을 사용했다. drift별 결과가 기본이며 3drift 평균 비교는 한 seed 안에서 먼저 평균해 50단위를 유지했다. 시간 sample을 독립 반복으로 취급하지 않았다. 폐쇄율0.8 제안은 승인 기준으로 사용하지 않았다.

## 코드·입력·환경·원본 보존

실행 revision은 f81b42d541fdf9a37b6868d4901c2a3bb9d8090e다. 자체 checkout codex/a23-execution-20261010에서 동결한 committed source/archive를 새 원격 디렉터리에 복사했다. archive SHA256은 14f970938fa971c581eb81fe1d4213a274ec0aa132f4a67ba47ef48ff297636f다. 다른 작업의 미커밋 sensor-v2를 사용하거나 변경하지 않았다. 핵심 구현은 scripts/drive_sim/structured_noise_control.py, drivesim/filters.py·experiment.py·sensors.py·observation.py·hs_lut.py다. source별 내용 해시와 최종 source/input/settings fingerprint는 RUN_MANIFEST_q2.json 및 joint manifest에 있다. 후속 두 run의 A0 gate는 passed다.

원 S6 source revision은 0d4588f79116e221d874307f233d69ff0b13d99c이며 이전 A0 150개가 세 지표 허용오차1e−9 이내로 일치했다. 이번에는 A0_CHECK와 A0/control/Q1 CSV 7파일의 원 실행 대비 내용 해시 불변을 REUSE_PRESERVATION.json으로 확인했다. A0 재현은 scientific PASS가 아니다.

| 입력 | SHA256 |
| --- | --- |
| H_R2_aA_m0.npy, 1303×257×2×2 | 1c40aea5ab7af87223f942c0727c0f6aabe7bd60e55a70c68c74d2c115750a51 |
| hs_lut_2deg.npy, 46×180×180 | 711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079 |
| S6 CSV | 16428ad0ce782193a90d6c0323fb4be05d6ea825bce835f08c62aea575765c13 |
| freqs_hz.npy | fe0bcfeb1426847ea090668845fe124482086d0510e38ebdb463609e2a1169f8 |
| LP_plus45_bank.npz | b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b |
| LP_minus45_bank.npz | 39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9 |

H/S6/timeline/rf_poses 원본은 /home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source/results/DRIVE_SIM_20261007/ 아래 S1 및 SNOWBALL_ROUTES_01a11669/S2/S6_routes다. LUT/metadata는 /home/KMS/COOL_DIJKSTRA_20261007_01a11582/source/results/DRIVE_SIM_20261007/S4/다. 실제 FFD bank는 legacy source 루트이며 원 BANK_MANIFEST와 대조했다. 파일명만 같은 입력을 채택하지 않았다. metadata·timeline·pose·sample·source 해시도 각 manifest에 있다. INPUT_PRESERVATION 및 L2 input_preserved=true로 읽은 원본 불변을 확인했다.

Snowball은 KMS 계정만 사용했다. 기존 image rt-dual-engine:s2-deps-r2-20260928, immutable ID sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f다. A23 환경은 Python3.11.15/NumPy2.4.6/pandas3.0.6, 4worker·BLAS/OMP/MKL1thread다. RF는 Sionna RT2.0.1/Mitsuba3.8.0/DrJit1.3.1, llvm_ad_mono_polarized, DrJit1thread다. 기존 runtime_packages를 참조했으며 설치·업데이트는 없었다. 원본 mount는 read-only다. Git 없는 runtime에는 이전 메타데이터 wrapper만 사용했고 모델·잡음·판정은 변경하지 않았다.

RF staging 실패 두 번을 보존했다. 1차는 corridor_sionna_run.py 누락으로 import 실패(exit1, solver0회), 2차는 manifest에 필요한 lut_los_check.py 누락(exit1, solver0회)이다. 누락된 RF-only helper 세 파일을 git show f81b42d:경로로 가져오고 전체 필요한 source 목록의 존재를 확인한 뒤 3차 실행했다. 식·adapter·threshold 수정이 아니며 계산 예산도 확대하지 않았다. RF_STAGING_AMENDMENT 두 기록과 실패 log/FAILURE/EXECUTION을 보존했다. Windows CRLF checkout과 committed blob의 byte hash 차이를 혼동한 준비 검사는 바로잡아 committed blob 그대로 사용했다.

## 실제 실행 상태와 비용

Q2 exit0·wall84.55초, joint exit0·32.15초, 통합 report exit0·6.67초다. 추가 필터 phase 합계123.38초다. 성공 RF는 한국시간13:55:07–13:58:38, wall211.22초·2,056호출·8pose, exit0이다. 앞의 staging 실패는0.12/6.27초·0호출이다. wall time은 합산 CPU 사용량과 다르며 전송/로컬 감사는 제외한다. CPU 합산 사용량은 측정하지 않았다. 정확한 명령·UTC timestamp·exit code는 EXECUTION 및 RF EXECUTION들에 보존했다.

원격 새 root는 /home/KMS/DRIVE_SIM_A23_Q2_JOINT_L2_20261010_01a12422다. 원격 파일382개·62,598,413bytes를 retrieved로 회수하고 모든 SHA256을 대조했다.

## Q2 — 실제 결과 → 판정 → 한계

R1은 편향+백색, R2는 영평균AR, R3는 편향+AR, R4는 empirical iid, R5는 clean잔차 평균 제거 후 시간정렬+새 추가잡음, R6은 거리구간 평균/분산, R7은 tap위치 구간 평균/분산, R8은 실제 range다. s는 모두 동일 백색 대조다. R6/R7은 평균과 분산을 동시에 바꾸므로 한 항만의 효과가 아니다. 거리 bin은 ≤5/(5,10]/>10m이며 최소5sample 미만은 전체 평균/분산 fallback이다. tap bin은 ((truth 3D distance+range_offset)/tap_spacing) mod1의4구간이다. 실제 first-path index 전환 셀이나 L1 노출과 같은 변수가 아니다. truth 거리 bin은 online 적용 검증 근거가 아니다.

아래 NEES/coverage/거절률은 seed평균, RMSE는 seed중앙값이다. 각 행 n=50이다. J1–J3 결과도 포함했다.

| arm | drift | 평균NEES | pose coverage | heading coverage | heading RMSE 중앙값° | 위치 RMSE 중앙값m | s 거절률 | range 거절률 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| J1_ar_indep | 0 | 240.214498 | 0.043064 | 0.273655 | 6.538329 | 1.064933 | 0.054306 | 0.052666 |
| J2_ar_corr | 0 | 237.851363 | 0.063788 | 0.267600 | 6.709638 | 1.015484 | 0.056912 | 0.054885 |
| J3_joint_block | 0 | 53.606161 | 0.218673 | 0.562147 | 2.757854 | 0.534806 | 0.026224 | 0.036960 |
| R1_bias | 0 | 8.386597 | 0.558118 | 0.931411 | 1.426767 | 0.199510 | 0.021809 | 0.073317 |
| R2_ar0 | 0 | 10.288823 | 0.594717 | 0.865211 | 1.554862 | 0.226455 | 0.021689 | 0.048926 |
| R3_ar1 | 0 | 16.010645 | 0.402171 | 0.892979 | 1.601912 | 0.229256 | 0.021737 | 0.047961 |
| R4_iid | 0 | 4.833091 | 0.829361 | 0.939059 | 1.421335 | 0.156432 | 0.021592 | 0.053607 |
| R5_realdem | 0 | 11.256686 | 0.528565 | 0.860965 | 1.710679 | 0.308676 | 0.022051 | 0.024632 |
| R6_distbin | 0 | 9.577345 | 0.638625 | 0.942702 | 1.362993 | 0.180398 | 0.021544 | 0.052425 |
| R7_tapbin | 0 | 8.023658 | 0.583860 | 0.939156 | 1.433492 | 0.193149 | 0.021785 | 0.073390 |
| R8_real | 0 | 10.445803 | 0.667865 | 0.944897 | 1.333393 | 0.183273 | 0.021713 | 0.026683 |
| W0_white_white | 0 | 3.292332 | 0.915296 | 0.932063 | 1.451478 | 0.164907 | 0.021641 | 0.100241 |
| J1_ar_indep | 1 | 245.673630 | 0.045476 | 0.245404 | 7.493794 | 1.214635 | 0.040169 | 0.047720 |
| J2_ar_corr | 1 | 264.631693 | 0.053004 | 0.224222 | 7.835830 | 1.262755 | 0.041761 | 0.048637 |
| J3_joint_block | 1 | 54.663509 | 0.236695 | 0.616454 | 2.969487 | 0.561465 | 0.024536 | 0.034741 |
| R1_bias | 1 | 8.244696 | 0.573969 | 0.903619 | 1.568681 | 0.209841 | 0.020121 | 0.072304 |
| R2_ar0 | 1 | 11.880976 | 0.556695 | 0.837949 | 1.846577 | 0.264519 | 0.020507 | 0.044946 |
| R3_ar1 | 1 | 14.795823 | 0.418384 | 0.869819 | 1.587323 | 0.263531 | 0.020121 | 0.044343 |
| R4_iid | 1 | 5.794468 | 0.758094 | 0.901375 | 1.523297 | 0.185481 | 0.020314 | 0.051773 |
| R5_realdem | 1 | 19.484596 | 0.447744 | 0.766828 | 2.128904 | 0.364037 | 0.020893 | 0.024801 |
| R6_distbin | 1 | 10.605367 | 0.601713 | 0.877033 | 1.685697 | 0.198009 | 0.020241 | 0.051435 |
| R7_tapbin | 1 | 8.185873 | 0.575006 | 0.903932 | 1.559777 | 0.219184 | 0.020169 | 0.071701 |
| R8_real | 1 | 12.602865 | 0.608299 | 0.862099 | 1.721552 | 0.212222 | 0.020217 | 0.026707 |
| W0_white_white | 1 | 6.490906 | 0.854934 | 0.888444 | 1.645341 | 0.193227 | 0.020097 | 0.097081 |
| J1_ar_indep | 2 | 234.328382 | 0.036502 | 0.265501 | 6.584567 | 1.136165 | 0.040917 | 0.054234 |
| J2_ar_corr | 2 | 246.775235 | 0.037129 | 0.246755 | 6.452257 | 1.077808 | 0.040434 | 0.054813 |
| J3_joint_block | 2 | 47.879513 | 0.150157 | 0.557973 | 3.378262 | 0.622782 | 0.021062 | 0.030591 |
| R1_bias | 2 | 9.923576 | 0.478456 | 0.878890 | 1.584133 | 0.231497 | 0.021182 | 0.073945 |
| R2_ar0 | 2 | 16.140396 | 0.509843 | 0.763281 | 1.728412 | 0.271990 | 0.021616 | 0.045983 |
| R3_ar1 | 2 | 33.801596 | 0.328637 | 0.790977 | 1.696273 | 0.290636 | 0.021978 | 0.045935 |
| R4_iid | 2 | 6.632341 | 0.724584 | 0.876429 | 1.650724 | 0.206539 | 0.020917 | 0.054789 |
| R5_realdem | 2 | 17.201647 | 0.385742 | 0.653583 | 2.551330 | 0.370333 | 0.022630 | 0.025766 |
| R6_distbin | 2 | 12.445784 | 0.573776 | 0.832931 | 2.043693 | 0.231319 | 0.021037 | 0.050712 |
| R7_tapbin | 2 | 9.762879 | 0.486176 | 0.876381 | 1.630750 | 0.229583 | 0.021086 | 0.073462 |
| R8_real | 2 | 12.253290 | 0.611315 | 0.820531 | 2.042767 | 0.219192 | 0.020941 | 0.026972 |
| W0_white_white | 2 | 5.332413 | 0.831508 | 0.822943 | 1.896482 | 0.206760 | 0.020989 | 0.099590 |

NEES subspace는 [x,y,heading], 자유도3이며 heading은 radian wrapping 후 계산한다. sample별 양측 경계0.2158/9.3484, pose95% coverage 상한7.8147, heading95% 상한3.8415(코드1.96std)를 사용한다. 상관된 시간 평균의 독립 chi-square PASS를 만들지 않는다. 전체 pre-gate/accepted-only NIS, rejection 및 상·하 tail은 per_drift.csv에 있다. gate 기준은 같아도 수용 결과는 달라질 수 있어 효과에 rejection도 포함된다.

주요 대응 NEES 차이의 탐색적 bootstrap95% 구간은 아래와 같다. 한 seed의3drift를 먼저 평균한50단위다. 전체 drift별 및 정확도/coverage/rejection 비교도 PAIRED_CONTRASTS.csv에 있다.

| 대응 차이 | 평균NEES 차이 | 95% 하한 | 95% 상한 |
| --- | --- | --- | --- |
| R1_bias-W0_white_white | 3.813073 | 2.228726 | 4.889537 |
| R2_ar0-W0_white_white | 7.731514 | 5.200241 | 10.714515 |
| R3_ar1-R1_bias | 12.684398 | 6.915828 | 21.667287 |
| R3_ar1-R2_ar0 | 8.765957 | 3.598417 | 16.018179 |
| R4_iid-W0_white_white | 0.714750 | -0.854752 | 1.758739 |
| R5_realdem-R8_real | 4.213657 | 1.421115 | 8.036780 |
| R6_distbin-W0_white_white | 5.837615 | 4.272791 | 6.913026 |
| R7_tapbin-W0_white_white | 3.618920 | 2.043932 | 4.686524 |
| R8_real-W0_white_white | 6.728769 | 5.464339 | 7.739112 |
| J2_ar_corr-J1_ar_indep | 9.680593 | -12.898735 | 38.610376 |
| J3_joint_block-J1_ar_indep | -188.022442 | -221.082224 | -155.984047 |

실제 range R8의 NEES는 drift별10.446/12.603/12.253, W0는3.292/6.491/5.332다. 이전 대화의 “4.6→12”를 동일 수치 재현이라고 표현하지 않는다. 이번 입력의 대응 평균 차이는+6.729 [5.464,7.739]다.

편향과 시간 상관 모두 선택한 합성 모형에서 영향을 만든다. 가장 명확한 조건부 편향 비교는 R3−R2(+8.766 [3.598,16.018])로 같은 AR잔차에 평균을 추가한 입력이다. 저장trace에서 range error 차이는 정확히0.05193997m 상수(표준편차약6e−16)다. 시간 상관 비교는 같은 평균/centered분산의 R3−R1(+12.684 [6.916,21.667])이다. 반면 R1−W0는 RMS가 비슷해도 평균/centered분산이 함께 달라지고 R2−W0도 분산이 같지 않아 순수 기여율로 해석하지 않는다. R3 자체는 실제 R8보다 큰 NEES를 만들어 모든 실패를 정량 설명하지 않는다.

R6/R7은 악화를 만들지만 물리적 거리/tap 원인이나 독립 기여율은 확정하지 않는다. R5−R8은 오히려+4.214 [1.421,8.037]이지만 “편향 제거가 나쁘다”로 일반화하지 않는다. R5는 clean잔차 정렬+새 추가잡음, R8은 원 noisy H 관측이므로 실제 입력에서 평균만 뺀 동일 counterfactual이 아니다. seed0/drift0에서 평균을 다시 더한 R5−R8 error 표준편차0.07021m가 남는다. CONTROL_DIFFERENCES.json에 확인했다. 부족한 통제를 명시하고 결과에 맞추는 코드 수정은 하지 않았다.

## joint — 달성 상관과 추가 효과

J1은 두 독립 편향AR, J2는 AR혁신 상관 추가, J3는 같은 block index로 s/range 함께 재표본화한다. block길이는50sample=10초다. J3−J1은 AR 대 block의 marginal/시간 구조도 바뀌므로 교차상관 단독 효과가 아니다.

J2 clean목표rho=0.5226266, 독립 수식의 혁신상관0.5969358, clipping0/150이다. range에 독립 추가잡음sigma0.05m가 들어가면 상관은 rho×sqrt(var_range/(var_range+0.05²))=0.4769965로 감쇠한다. noise_corr_pre에도 gen_noise의 이 추가잡음이 이미 포함된다. 달성pre0.477670·최종0.477360은 예상과 맞고 A0최종0.474815와 근접한다. clean0.523 대 최종0.477을 목표 미달로 잘못 판정하지 않는다. seed별3drift평균 입력상관 범위0.3964–0.5498이다. J3최종0.465617, J1최종−0.002342다.

J2−J1 NEES차이는+9.681 [−12.899,38.610]으로0을 포함한다. 이 표본과 모형에서 lag0 추가 효과의 방향/크기는 불확정이며 효과가 없다는 보편적 결론도 아니다. J3 NEES약48–55는 AR J1/J2약234–265보다 낮지만 실제 A0와도 다르며 상관 모델 해결을 뜻하지 않는다. 높은 lag와 상태정렬을 함께 재현했다고 주장하지 않는다.

아래 달성값은 실제 필터 입력의 run별 통계 평균이며 pooled 통계와 다르다.

| arm | range평균 | range분산 | rangeRMS | range lag1 | s lag1 | 교차상관 |
| --- | --- | --- | --- | --- | --- | --- |
| A0_real_real | 0.052960 | 0.015117 | 0.133872 | 0.662543 | 0.926575 | 0.474815 |
| J1_ar_indep | 0.051121 | 0.014645 | 0.131763 | 0.661720 | 0.920923 | -0.002342 |
| J2_ar_corr | 0.051654 | 0.014670 | 0.132112 | 0.661428 | 0.920923 | 0.477360 |
| J3_joint_block | 0.051204 | 0.014301 | 0.129414 | 0.610122 | 0.895962 | 0.465617 |
| R1_bias | 0.051588 | 0.014885 | 0.132497 | -0.000177 | -0.002967 | 0.003493 |
| R2_ar0 | -0.000819 | 0.014645 | 0.121507 | 0.661720 | -0.002967 | 0.001269 |
| R3_ar1 | 0.051121 | 0.014645 | 0.131763 | 0.661720 | -0.002967 | 0.001269 |
| R4_iid | 0.051271 | 0.014856 | 0.132134 | -0.000332 | -0.002967 | 0.001841 |
| R5_realdem | -0.000175 | 0.014925 | 0.122168 | 0.672203 | -0.002967 | -0.002419 |
| R6_distbin | 0.051496 | 0.014872 | 0.132384 | 0.214966 | -0.002967 | 0.005553 |
| R7_tapbin | 0.051570 | 0.014881 | 0.132472 | 0.000072 | -0.002967 | 0.003767 |
| R8_real | 0.052960 | 0.015117 | 0.133872 | 0.662543 | -0.002967 | -0.002354 |
| W0_white_white | -0.000210 | 0.017596 | 0.132703 | -0.001932 | -0.002967 | 0.002901 |

## L2 — 원 gate 재현과 계산 단계 분해

8pose의x/y/yaw와 s_LUT/s_Sionna는 원 저장 결과와1e−12 이내로 일치한다. 모든 주파수의path_count=1, H는finite다. **원 L2 max0.010448905755>0.005, 위반4/8, FAIL**이다. 실행 exit0와 gateFAIL은 별개다.

같은 pose에서 nativeSionna 실제거리, 직접LoS 실제거리, 직접LoS10m 채널을 저장했다. 동일 bank·frequency·singleTX column0·RX [+45,−45]·Hann·4Npadding·IFFT*N·leading edge0.3이다. 별도 numpy 관측 계산으로 s차이최대5e−16·power차이4.34e−18·tap모두일치를 확인했다. 직접/native 실제거리 s차이는 최대8.569e−7, H상대차이8.020e−5, nativedelay−기하delay 최대1.565e−15s다. 이8pose의 직접/native 대응은 잘 맞지만 원 LUT gate를 대체하지 않는다.

정확한 signed분해는 LUT−Sionna=(LUT−direct10)+(direct10−directActual)+(directActual−Sionna)다. 합과 원 차이의 오차는0이다.

| pose | 거리m | LUT−Sionna | LUT−direct10 | 10m−actual | actual−Sionna | actual tap | 10m tap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 2.370247 | -0.000586 | -0.000539 | -0.000048 | 0.000000 | 12 | 63 |
| 1 | 13.543198 | 0.005679 | -0.001568 | 0.007246 | 0.000001 | 87 | 63 |
| 2 | 2.927786 | -0.001200 | 0.000208 | -0.001408 | -0.000000 | 16 | 63 |
| 3 | 2.580564 | -0.008402 | 0.000210 | -0.008612 | -0.000001 | 14 | 63 |
| 4 | 8.492396 | 0.002811 | 0.002042 | 0.000769 | 0.000000 | 53 | 63 |
| 5 | 12.199786 | -0.010449 | -0.000162 | -0.010287 | 0.000000 | 78 | 63 |
| 6 | 4.540757 | 0.005972 | -0.001196 | 0.007168 | 0.000000 | 27 | 63 |
| 7 | 7.271683 | 0.002707 | -0.000595 | 0.003302 | -0.000001 | 45 | 63 |

위반pose1/3/5/6에서 거리와 유한 CIR tap처리 항이 큰 차이를 만든다. 최대 위반pose5는 LUT−direct10 약−0.000162, direct10−actual 약−0.010287, actual−Sionna 약+0.000000359다. 이번8pose의 direct10 보간 차이는 최대약0.002042로 원L1 max기준0.01보다 작지만 원500 L1을 다시 통과시킨 검사가 아니다.

directActual H를 (d/10)×exp[−j2πf(10−d)/c]로10m에 재정렬하면 저장direct10 H와 상대차이1.49e−13, s차이3.00e−15 이내로 같아진다. 같은 방향/FFD에서1/d amplitude는 s비율에서 상쇄되지만 주파수별 propagation phase에 따른 fractional delay와 first-path sampling은 s를 바꿀 수 있다. tap번호와 오류의 동시 발생만으로 추정하지 않고 채널 retiming로 분리했다. 이8pose의 계산 메커니즘 근거이며 모든 거리/각도/경계의 완전 분해는 아니다.

원L2 실패를 Sionna LoS물리식 자체의 오류로 단정할 근거는 이8pose에서는 약하다. fixed10m 처리LUT와 실제거리 관측의 일치 문제는 남는다. L1 극점/tap전환 결함도 미수정이다. R_s/noise확대로 실패를 무효화하지 않았다. 수정 후보는 거리·phase·tap를 함께 다루는 측정모델이며 별도 설계/L1·L2 검증 전 채택하지 않는다. full RF 다중경로·하드웨어·F02 인과 기여율은 이번 검사로 입증하지 않는다.

## 독립 검산·남은 범위·종료 판정

통합3300행은 누락0·중복0·실패0, 지표finite다. 지정seed0/1의132trace에서 전체6상태/6×6P/입력/innovation/수용mask를 보존했다. independentNEES/RMSE/coverage/pre·acceptedNIS/rejection 최대NEES차이2.58e−11, P최소고유값1.307e−8, 최대비대칭1.735e−17이다. 258,192log행의 NIS=innovation²/S를 대조했다. jitter/clamp를 추가하지 않았다. 나머지48seed의 전체P까지 검산했다고 확대하지 않는다. 같은seed/drift의 gyro/wheel/truth/time이22arm에서 동일함도 확인했다.

정확도/일관성·seed분포·worst-case·closure·NIS·거절률을 함께 보존했고 제외seed는0이다. 이번 새 H는 제한LoS-only8pose분만 별도 저장했다. full RF/productioncampaign·다른route/anchor/mount·독립held-out·새R_s추정·필터/관측모델수정·commit/push/merge는 수행하지 않았다.

**종료:** Q2·joint 실행 완료, 두요인의 조건부 영향 확인, 단독lag0효과 불확정, 원L2FAIL의거리/tap층 분해 완료. F01/F02와 scientific_PASS=false 유지. R5의 정확한 counterfactual 통제·독립조건 일반화·거리/tap 관측모델 수정 검증은 다음 범위이며 자동 시작하지 않는다.

## 근거와 명령

- [PLAN.json](PLAN.json)
- [PAIRED_ANALYSIS_PLAN.json](PAIRED_ANALYSIS_PLAN.json)
- [EXECUTION.json](retrieved/EXECUTION.json)
- [L2_EXECUTION.json](retrieved/L2_EXECUTION.json)
- [L2_ATTEMPT2_EXECUTION.json](retrieved/L2_ATTEMPT2_EXECUTION.json)
- [L2_ATTEMPT3_EXECUTION.json](retrieved/L2_ATTEMPT3_EXECUTION.json)
- [OUTPUT_MANIFEST.json](retrieved/OUTPUT_MANIFEST.json)
- [INPUT_PRESERVATION.json](retrieved/INPUT_PRESERVATION.json)
- [REUSE_PRESERVATION.json](retrieved/REUSE_PRESERVATION.json)
- [RF_STAGING_AMENDMENT.json](retrieved/RF_STAGING_AMENDMENT.json)
- [RF_STAGING_AMENDMENT2.json](retrieved/RF_STAGING_AMENDMENT2.json)
- [LEGACY_L2_CHECK.json](retrieved/LEGACY_L2_CHECK.json)
- [MANIFEST.json](retrieved/L2_ATTEMPT3/MANIFEST.json)
- [SAMPLES.json](retrieved/L2_ATTEMPT3/SAMPLES.json)
- [RESULT.json](retrieved/L2_ATTEMPT3/RESULT.json)
- [CHANNELS.npz](retrieved/L2_ATTEMPT3/CHANNELS.npz)
- [RUN_MANIFEST_q2.json](retrieved/OUTPUT/RUN_MANIFEST_q2.json)
- [RUN_MANIFEST_joint.json](retrieved/OUTPUT/RUN_MANIFEST_joint.json)
- [ARMS_q2.csv](retrieved/OUTPUT/ARMS_q2.csv)
- [ARMS_joint.csv](retrieved/OUTPUT/ARMS_joint.csv)
- [ARM_UNIT_STATS_q2.csv](retrieved/OUTPUT/ARM_UNIT_STATS_q2.csv)
- [ARM_UNIT_STATS_joint.csv](retrieved/OUTPUT/ARM_UNIT_STATS_joint.csv)
- [ARMS_REPORT_ALL.json](retrieved/OUTPUT/ARMS_REPORT_ALL.json)
- [VERIFICATION.json](VERIFICATION.json)
- [RF_VERIFICATION.json](RF_VERIFICATION.json)
- [TRACE_PAIRING.json](TRACE_PAIRING.json)
- [CONTROL_DIFFERENCES.json](CONTROL_DIFFERENCES.json)
- [JOINT_CORRELATION_CHECK.json](JOINT_CORRELATION_CHECK.json)
- [PAIRED_CONTRASTS.csv](PAIRED_CONTRASTS.csv)
- [L2_ERROR_DECOMPOSITION.csv](L2_ERROR_DECOMPOSITION.csv)
- [SEED_DISTRIBUTION.csv](SEED_DISTRIBUTION.csv)
- [per_drift.csv](per_drift.csv)
- [paired_closure_per_drift.csv](paired_closure_per_drift.csv)
- [verify_filter_outputs.py](verify_filter_outputs.py)
- [verify_rf_outputs.py](verify_rf_outputs.py)
- [paired_analysis.py](paired_analysis.py)

q2 (exit0):

```text
/opt/rt-env/bin/python /job/launch.py run --s1 /routes/source/results/DRIVE_SIM_20261007/S1 --h-dir /routes/source/results/DRIVE_SIM_20261007/SNOWBALL_ROUTES_01a11669/S2 --lut /legacy/source/results/DRIVE_SIM_20261007/S4/hs_lut_2deg.npy --lut-meta /legacy/source/results/DRIVE_SIM_20261007/S4/hs_lut_meta.json --bank-freqs /job/freqs_hz.npy --cases R2A --mounts 0 --drifts 0 1 2 --seeds 50 --seed0 0 --nproc 4 --trace-seeds 0 1 --out /job/OUTPUT --arms R1_bias R2_ar0 R3_ar1 R4_iid R5_realdem R6_distbin R7_tapbin R8_real --label q2
```

joint (exit0):

```text
/opt/rt-env/bin/python /job/launch.py run --s1 /routes/source/results/DRIVE_SIM_20261007/S1 --h-dir /routes/source/results/DRIVE_SIM_20261007/SNOWBALL_ROUTES_01a11669/S2 --lut /legacy/source/results/DRIVE_SIM_20261007/S4/hs_lut_2deg.npy --lut-meta /legacy/source/results/DRIVE_SIM_20261007/S4/hs_lut_meta.json --bank-freqs /job/freqs_hz.npy --cases R2A --mounts 0 --drifts 0 1 2 --seeds 50 --seed0 0 --nproc 4 --trace-seeds 0 1 --out /job/OUTPUT --arms J1_ar_indep J2_ar_corr J3_joint_block --label joint
```

report (exit0):

```text
/opt/rt-env/bin/python /job/launch.py report --csv /job/OUTPUT/A0_ARMS.csv /job/OUTPUT/ARMS_controls.csv /job/OUTPUT/ARMS_q1.csv /job/OUTPUT/ARMS_q2.csv /job/OUTPUT/ARMS_joint.csv --unit-stats /job/OUTPUT/A0_UNIT_STATS.csv /job/OUTPUT/ARM_UNIT_STATS_controls.csv /job/OUTPUT/ARM_UNIT_STATS_q1.csv /job/OUTPUT/ARM_UNIT_STATS_q2.csv /job/OUTPUT/ARM_UNIT_STATS_joint.csv --a0-check /job/OUTPUT/A0_CHECK.json --out /job/OUTPUT/ARMS_REPORT_ALL.json
```

RF 성공 command (exit0):

```text
/opt/rt-env/bin/python /job/l2_probe_attempt3.py
```

독립 검산(각 exit0):

```text
py -3.10 -X utf8 verify_filter_outputs.py
py -3.10 -X utf8 paired_analysis.py
py -3.10 -X utf8 verify_rf_outputs.py
```


원자료는 같은 디렉터리의 retrieved에 있다. 원격 OUTPUT_MANIFEST는 원격 원자료 해시이며 로컬 보고서/파생파일은 별도 LOCAL_OUTPUT_MANIFEST.json으로 추적한다.
