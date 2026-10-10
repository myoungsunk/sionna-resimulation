# DRIVE_SIM sensor-v2 구현·제한 검증·전체 재감사

판정: **구현 및 정해진 제한 실행 완료. 과학적 production 타당성 PASS 아님. scientific_PASS=false, F01/F02 OPEN 유지.** 이 문서는 구현한 동일 assistant의 자체 재감사이며 독립 심사자 검토라고 표현하지 않는다. 해석식/finite difference/동결 source 비교는 코드의 다른 계산 경로로 검산한 결과다.

## 1. 기준·보존

격리 checkout: `D:\SLAM_bot\artifacts\DRIVE_SIM_SENSOR_V2_20261008_01a11a01\checkout`. Branch `codex/sensor-model-v2-20261008`, HEAD `2337c33fe25917029c2aa95973e6ae7672386a5e`. 미커밋 수정의 정체성은 HEAD만으로 표시하지 않고 CHANGE_MANIFEST.json의 파일 hash로 식별한다.

시작 시 원격 새 branch는2337c33, 기존 claude/cool-dijkstra-hnznhm는768404e3716c47f323d2c26e9458731b077bc96e로 이동해 있었다. 추가19파일의 stat 및 filters/experiment diff를 확인했다(steering/residual 진단). 새 branch 기준은2337c33으로 유지했고 추가 변경을 가져오지 않았다. 새 원격 branch를 다시 생성하지 않았다.

이전 `codex/reaudit-20261008-01a119a7` checkout의 HEAD 및 9 tracked/2 untracked 변경은 보존했다. gate/G4/G3 수정도 무조건 복사하지 않았다. 해당 수정이 이 branch에 적용됐다고 주장하지 않는다. read-only로 과거 보고서를 참조했다.

clone의 LFS smudge가 누락 bank로 exit128이었고 skip-smudge로 pointer만 checkout했다. 이를 RF 데이터로 사용하지 않았다. 일반 sandbox helper는 setup refresh 문제 때문에 사용할 수 없었으므로 승인된 로컬 실행 경로를 사용해 Python/Git를 실제 실행했다. 환경 시작 실패와 코드 실패를 구분한다. 원본 sensors/observation/hs_lut/PREREG는 Git diff0이며 CRLF checkout과 Git LF blob 차이를 정규화해 확인했다. 자동 commit/push/merge, production 변경, RF 생성, robot/ROS/firmware 작업은 없다.

## 2. 구현 전후

| 영역 | legacy 유지 | sensor-v2 |
|---|---|---|
| 선택/seed | default legacy, 기존 RNG 그대로 | explicit version + namespace2201008/7 streams |
| dt | 기존0.2초 규약 | timestamp 차분, noise units/seed/config manifest |
| 센서 | 기존 aggregate 증분/unsigned/Euler | rawL/R angle, nominal geometry, signed increments, SE2 |
| scale/bias/slip | 기존 수치/샘플 slip | common/asymmetry 분리; fixed bias default/RW 별도; time/legacy-event |
| 초기화 | 기존 prior 규약 | pose exact 또는0.1m/5deg prior, calibration prior 분리 |
| wheelbase | e_b 없는6상태 | e_b0/알려진 외부 correction/unknown mismatch 명시, 새 상태 없음 |
| 공유 잡음 | 기존 독립 갱신 | EKF C=-GQB^T, wheel distance와 gyro 포함 |
| 필터 종류 | EKF/IEKF/UKF/GSF | EKF/direct-s만; 다른 조합은 오류 |
| 저장 | legacy 축약 반환 유지 | full6state/6x6P, innovation/R/S/status, slip/actual parameter, masks/provenance |
| metrics | 기존 common/coverage | 같은 summarize_output을 재사용, raw 반환 추가 |

low/mid/high 값은 그대로이며 실물 Waffle Pi 등급이 아니다. common scale0/RW0 중립 default를 유지한다. 단독·무오차·주요 두항 조합/all 조건, 별도 생성기/필터 JSON을 지원한다. 가정 예제는 assumptions로 명시했다. process slack을 증가시키지 않았고 v2에서는0만 허용한다. RF solver/antenna/LUT/게이트/σ를 튜닝하지 않았다.

수식·부호·단위·지원 경계·실행법은 [MODEL_CONTRACT.md](MODEL_CONTRACT.md), 결과 전에 고정한 조건은 [PREREG_V2.md](PREREG_V2.md)에 있다. 독립 ablation 추가 등 시점별 원문 hash를 EXECUTED_SOURCE/PREREG_*와 PREREG_SNAPSHOTS.json에 보존했다. MC48_final의 default 수치와 동일한 뒤 CONFIG condition 표시만 고친 evaluation_v2 source도 실행 당시 hash로 보존했다. 최초 MC48와 MC48_final의 runs.json은 byte-identical이다.

## 3. 실제 실행·검산

[COMMANDS.json](COMMANDS.json)에 명령/개별 exit를 저장했다. 모든 주 실행은 종료코드0이다. 예상된 거부는2, 첫 NaN 비교 테스트와 strict RF motion 검사는1로 보존했다. pytest는 설치되지 않아 기존 전체 pytest suite는 미실행이며 PASS로 세지 않았다. 대신 새 unittest와 frozen source 비교를 실행했다.

- unittest9 groups 통과. legacy 동일 input/seed의 센서 배열,4종 filter state/covariance/stats, 기존 metrics가5seeds에서 exact 일치.
- 정지/후진/제자리 회전/원호/yaw 경계의 무오차 SE2 적분1e-10 이내. known e_b=.0075 correction trajectory도1e-10 이내. timestep .1/.2/.4 같은 path endpoint 검산.
- 10m/v=.2 직선: gyro bias .05deg/s endpoint y=0.2181315456m; eps=.005 wheel-only y=0.8688791714m. 연속 원호식과 SE2 endpoint1e-9 이내. initial heading5deg 단독도검산. legacy Euler 차이 각각0.0008726m/0.0034799m를 별도 기록.
- finite-difference F/G/H/B max error 3.453e-10 < 사전2e-7.
- 공유 잡음 Gaussian4096 runs: covariance 상대오차4.33%, mean NEES5.9074(6상태 기준), coverage.94897; 사전 선형 기준 만족. C=0 표준 Joseph 환원 검산. 이것은 nonlinear localization PASS가 아니다.
-4096 independent runs × dt3종: gyro N²T, wheel AQLRA^T, biasRW sigma²T의15% variance 허용 내. slip count2025/1973/1985, expected2053.15/2048/2037.76에 대한6sigma 검산 통과. 시간 표본을 반복수로 세지 않았다.
- bias RW left-endpoint 규약과 continuous integral 차이는 bias_rw_discretization.json에 기록. 실물 PSD/대역폭 대응 미확인.
- 관측성 calibration columns rank: 정지1/일정속도 직선1/속도변화2/양방향 회전+속도변화3. 일정 속도 직선의 bias-eps confounding, SF 무감도를 보존한다. global pose 또는 실물 관측성 PASS가 아니다.
- missing/rejected/applied/disabled 구분, PSD/대칭성, raw matrices/masks를 검사했다. main672 EKF raw files의 min eigenvalue 약-2.83e-20(사전-1e-10 이내), 최대 비대칭1.39e-17(<1e-12). 부정 covariance를 clamp하거나 결과 gate를 완화하지 않았다.

## 4. 소규모 합성 평가

64초 fixed truth/dt.2, mid sensitivity, seeds200..247, exact/legacy-prior × e_b0/unknown .0075 ×6 methods =1152 runs. RF 없는 방법, ideal synthetic range 및 analytic ratio .6cos(phi_rx)를 구분한다. 실제 RF-derived s의 대체 검증이 아니다. synthetic ratio는 직접 heading 센서도 아니다. endpoint NEES/coverage는 seed 단위이고 시간 평균 NEES는 descriptive metric일 뿐이다. calibration fitting은0회.

생성 range sigma=.05m, 추정 range R은 기존 .05²+quantization+extra .05²를 그대로 보존했다. 따라서 synthetic range는 matched-R 검증이 아니다. fixed/ideal baseline의 covariance는 unavailable로 표시했다. 초기 pose는 exact에서도 calibration prior는 기존 값이다. 결과를 보아 tolerance/σ/process noise를 바꾸지 않았다.

| initial | wheelbase | method | common pos RMSE mean [m] | endpoint NEES mean | endpoint coverage95 |
| --- | --- | --- | --- | --- | --- |
| exact | matched | ideal_increments | 0.00000 | unavailable | unavailable |
| exact | matched | wheel_only | 0.15297 | unavailable | unavailable |
| exact | matched | wheel_distance_gyro_fixed | 0.06622 | unavailable | unavailable |
| exact | matched | wheel_gyro_online | 0.02074 | 3.639 | 0.8333 |
| exact | matched | online_range | 0.01867 | 3.241 | 0.9375 |
| exact | matched | online_range_s_ideal_ratio | 0.01724 | 3.534 | 0.9375 |
| exact | unknown | ideal_increments | 0.00000 | unavailable | unavailable |
| exact | unknown | wheel_only | 0.15319 | unavailable | unavailable |
| exact | unknown | wheel_distance_gyro_fixed | 0.06622 | unavailable | unavailable |
| exact | unknown | wheel_gyro_online | 0.02833 | 5.894 | 0.7292 |
| exact | unknown | online_range | 0.02553 | 5.292 | 0.7708 |
| exact | unknown | online_range_s_ideal_ratio | 0.02370 | 5.496 | 0.7500 |
| legacy-prior | matched | ideal_increments | 0.27088 | unavailable | unavailable |
| legacy-prior | matched | wheel_only | 0.30028 | unavailable | unavailable |
| legacy-prior | matched | wheel_distance_gyro_fixed | 0.27099 | unavailable | unavailable |
| legacy-prior | matched | wheel_gyro_online | 0.27256 | 3.080 | 0.9167 |
| legacy-prior | matched | online_range | 0.06559 | 2.735 | 0.9583 |
| legacy-prior | matched | online_range_s_ideal_ratio | 0.03884 | 3.640 | 0.9167 |
| legacy-prior | unknown | ideal_increments | 0.27088 | unavailable | unavailable |
| legacy-prior | unknown | wheel_only | 0.30017 | unavailable | unavailable |
| legacy-prior | unknown | wheel_distance_gyro_fixed | 0.27099 | unavailable | unavailable |
| legacy-prior | unknown | wheel_gyro_online | 0.27336 | 3.167 | 0.9167 |
| legacy-prior | unknown | online_range | 0.06659 | 3.064 | 0.8958 |
| legacy-prior | unknown | online_range_s_ideal_ratio | 0.04035 | 4.124 | 0.8750 |

RMSE와 일관성 판정은 별개다. 승인되지 않은 NEES≤6/coverage≥.90/accuracy≤1.25 등의 기준으로 PASS를 선언하지 않는다. 사전 정의된 수식 시험 통과와 위 empirical 수치의 scientific acceptance를 혼동하지 않는다.

### 공유 입력 상관 분리 진단

noise_pair만 활성화, 정확한 pose, e_b0/RF없음,48 identical input seeds. full C / gyro-only C / C=0은 각각 아래 결과다. 후자 둘은 진단용 독립 가정이며 production 옵션으로 노출하지 않았다.

| C mode | common RMSE m | endpoint NEES | coverage95 |
| --- | --- | --- | --- |
| full | 0.02011600 | 3.46828 | 0.875 |
| gyro-only | 0.02011870 | 3.46905 | 0.875 |
| none | 0.02013648 | 3.31136 | 0.875 |

이 조건의 RMSE 영향은 작다. 상관 처리의 필요성은 수식·독립 선형 검산으로 확인했으나 이를 production F02의 주원인 해결로 확대하지 않는다. wheelbase unknown 영향은 main paired cells와 독립 기하 검산으로 분리했다. 다른모델/경로/강한 slip 영향의 일반화는 미확인이다.

## 5. 실제 기존 RF 제한 평가

KMS만 사용해 접근한 기존 production H/LUT를 읽었다. H subset은201 selected pose_id, 약3.3MB이며 원본 H 전체 SHA가 original manifest와 일치한다. LUT 약11.9MB, 원본 meta/range bias, LP_plus45_bank.npz의 freqs_hz ZIP member만 가져왔다. 새 RF 계산/trace/H-store는 생성하지 않았다. hash/선택 ID/경로는 RF_INPUT/provenance.json 및 RF8_complete/manifest.json에 있다.

R1 y0/mount0/Tnone 첫201samples(40초),35dB assumption, seeds200..207, init2 ×wheelbase2 ×3 methods=96runs. 기존 frozen range offset은 재사용했고 새 calibration은 없다. sensor truth는 생성/평가용으로만 썼다. initial0 RF observation은 v2에서 수신 시 적용하며 legacy의 첫 sample update 생략 규약과 동일하다고 주장하지 않는다.

strict SE2 extraction이 기존 Euler path를 올바르게 거부해 첫 시도 중단했다. residual 최대0.000145997m를 기록하고 tolerance는 그대로 두었다. 명시적 legacy-euler increments로 기존 truth를 유지했으며 SE2 재적분 위치 차이 최대0.002719m를 평가용 mismatch 필드에 저장했다. 이 차이는 RF 오차와 다른 입력 규약 mismatch다. 원본 path를 수정하거나 무오차 정합 조건으로 표현하지 않았다.

| initial | wheelbase | method | common pos RMSE mean m | endpoint NEES mean | coverage95 |
| --- | --- | --- | --- | --- | --- |
| exact | matched | online | 0.10547 | 2.141 | 1.000 |
| exact | matched | online_range | 0.10792 | 2.617 | 1.000 |
| exact | matched | online_range_s_RF | 0.17679 | 99.890 | 0.125 |
| exact | unknown | online | 0.10482 | 2.325 | 1.000 |
| exact | unknown | online_range | 0.10707 | 2.798 | 1.000 |
| exact | unknown | online_range_s_RF | 0.17998 | 112.667 | 0.000 |
| legacy-prior | matched | online | 0.63735 | 4.554 | 0.750 |
| legacy-prior | matched | online_range | 0.19231 | 3.801 | 0.875 |
| legacy-prior | matched | online_range_s_RF | 0.08422 | 5.124 | 0.875 |
| legacy-prior | unknown | online | 0.63707 | 4.549 | 0.750 |
| legacy-prior | unknown | online_range | 0.19176 | 3.788 | 0.875 |
| legacy-prior | unknown | online_range_s_RF | 0.08364 | 5.303 | 0.750 |

정확한 초기화의 +RF s에서 NEES≈99.89/coverage.125로 불일치가 남는다. legacy-prior에서는 다른 양상이므로 둘을 합쳐 성공으로 표현하지 않는다. 이40초 subset은 일부 곡선의 heading 변화만 포함하고 전체 route/회전/probe 및 anchorB 일반성은 평가하지 않았다. F01 L1/L2 재검증을 하지 않았으며 작은 RF 연결 실행은 그 실패를 해소하지 않는다.

## 6. RF→observation→sensor→filter→metric 전체 재감사

RF trace/Jones/FFD/methodB H assembly는 수정0. 최초 독립 감사 revision155bf5a63558a4fba9ff02cd0da159c7636fb8d8과 그 보고서의 근거를 재사용한다. 이번에 solver/5630 trace/72000 production runs를 재실행한 것이 아니다. 과거 로컬 재감사 FULL_REAUDIT_20261008.md는2337c33+그 checkout의 미커밋 변경 기준이며 출처를 구분했다.

이번 source 확인: observation은 TX0, Hann/4N padding/IFFT×N, strongest RX의30% leading edge, 두 port의 같은tap power ratio, delay/(1028df)*c, detection mask 구조다. 실제 H subset에서 이 chain을 CPU로 실행했고 출력 observation을 측정치로만 EKF에 넣었다. s는 LUT geometry 함수이며 직접 yaw 관측이 아니다. 상기 actual/assumed/generator/prior/metric을 별도 필드·manifest로 추적한다.

| 지적 | 상태 | 이번 영향/증거 |
|---|---|---|
|F01 RF/LUT L1/L2|OPEN/기존 FAIL|.023972>.01, .0104489>.005는 과거 audit 증거; 이번 gate rerun 없음|
|F02 covariance|OPEN|실제 RF 제한 결과도 일부 NEES≈100; 생산 NEES 약44 해소 주장 없음|
|F03 G3 chronology|유지/영향 없음|strictFAIL/승인 relaxed/사후검사 한계; 새trace 없음|
|F04 path identity/full changes|OPEN|과거 gate diff 자동수입 없음; 전체 physical identity 재검토 안함|
|F05 anchorB worstcase parity|OPEN|이번R1/A subset 밖; 새RFparity 금지 범위|
|F06 calibration/evaluation 분리|기존OPEN/새run 분리|이번 fitting0/evaluation seeds 명시; frozen range offset의 과거 provenance 사용|
|F07 shared gyro/wheel/eb|v2 bounded 수정·검증, legacy유지|crossC/Jac/PSD/known-vsunknown/ablation; 6state 미지원 e_b unknown은 의도적 mismatch|
|F08 GSF PSD|legacy source보존|최초감사 이후 고친legacy규칙 유지; frozen regression4종; v2GSF 미지원|
|F09 probe fairness|기존PARTIAL|common metric 재사용; 새probe효과/예산claim 없음|
|F10 관측성|국소진단만|calibration rankSVD/직선confounding; global ambiguity 실물 미검증|
|F11 가설/강한 baseline|기존한계유지|fixed distance+gyro와wheel-only 포함; 과거H1-H7 통계 새계산 아님|
|F12 receiver/physical validation|미검증|upstream ROBOTIS만 확인; 실제 /odom/PSD/센서 실물 미확인|
|M01/M02 gate/coverage|현재baseline 상태 유지|이전checkout의추가G4/no-gate수정 미반영; 해결 주장 없음|
|M03 geometry/frequency|nominal확인/부분|official .033/.287, actualfreqmember; 생산양자화상수차이해소 주장 없음|
|M04 승인시각|UNKNOWN유지|과거chronology문서claim만 재사용|

원본 production source는 R1 1b9cf190244f91d0097a82106a02ec1dd5f53220, routes0d4588f79116e221d874307f233d69ff0b13d99c였다는 최초감사 증거를 그대로 구분한다. legacy 지금의 regression PASS는 그 과거72000runs를 재생성한 것이 아니다. 과거 대응문서의 syntheticE1을 완전한 matched-R proof로 쓰거나 held-out V0/V1이 사실상같다고 확대하지 않는다. 이전 재감사의 정정은 문서 출처로 재사용하되 새branch에 미커밋 정정파일을 복사하지 않았다.

RF range와 s의 공유 복소H-noise 상관 및 시간/기하잔차는 scalar sequential RF update에 남아있다. 이번 correction은 gyro/encoder predict-odom 상관에만 해당한다. slip은 heavy-tail이며 filter는 생성sliptruth를 받아 보정하지 않고 residual gate를 기록한다. Gaussian coverage 불일치의 모든 원인을 해소했다고 말할 수 없다.

## 7. 파일·위험·종료 경계

변경: sensors legacy파일불변; 새 sensor_v2.py/filter_v2.py/evaluation_v2.py, filters.py explicit dispatch, experiment.py 공유metrics/raw, 기존2launcher의명시적version, 새3CPUrunner, tests/test_sensor_v2.py, configs/sensor_v2/*.json, 독립results/SENSOR_V2_20261008/*. code-only diff는 REVIEW.patch, 정확한filehash는 CHANGE_MANIFEST.json. accepted주결과는 validation_verified.json/log, MC48_final/, RF8_complete/, CORRELATION_ABLATION/, raw_checks.json, PRESERVATION_AND_HASH_CHECKS.json. 초기실패/이전동일실행도삭제하지 않았다.

미실행/미지원: full pytest(환경에없음), v2IEKF/UKF/GSF/inverse, 추가calibrationstates, 지속/curve slip, fullproduction/LUTgate/anchorB worstcase/전체routeRF, hardware/실제odom설정, 실물noisePSD/교정분포. exact matched Gaussian 선형검산과실제RFscientificFAIL은 별개다.

다음에 필요한 검증은 별도 승인 연구 범위로만 제안한다: 독립 reviewer의correlation식/비선형경계검토, 실제RF잔차의시간구조및range-s공분산, 기존RFheldoutroute/anchorBsubset, 실물calibration/PSD/odom설정확인. 이번에는 자동으로 시작하지 않는다. **구현 완료, 제한 실행 성공, 과학적 production FAIL/UNKNOWN 유지**를 구분하고 종료한다.
