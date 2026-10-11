# A–B–C–D 단계별 상세 실행 계획 및 최신 검증 현황

**기준: 2026-10-11 KST**  
브랜치: codex/abc-gated-resume-20261011  
확인 HEAD: 62905b07e26860fea98d688c10701d74e7878059  
기준 구현: codex/p0-close-p1-factorial-20261011 @ 3bfcae6715bac5a933cc3b8336b6e6fad846c58a  
최종 연구 상태: scientific_PASS=false, 채택 알고리즘 미확정.

## 0. 총괄 및 선후관계

- A / P0 = V00–V03: 원본 RF 대응, 관측기, 발생계통, 센서–필터 정합, pole-safe LoS 모델의 물리/수학 검증. 현재 **NOT_ALL_PASSED**.
- B / P1 = V04–V10: Range·dual-LP·공분산 원인 분리, 모델 보정 및 best validated passive RF 기준선 확정. 현재 **NOT_RUN_AFTER_A**.
- C / P2 = V11–V13: 진짜 Native RF + 실제 제동·회전 + 오염 공동 posterior + 매시점 EKF 주행 재개, 12조건 정책평가. 현재 **NOT_RUN_FOR_FULL_POLICY**.
- D / P3 = V14–V15: 독립 geometry 및 하드웨어 가능성, 연구 결론과 재현가능한 최종 모델 선정. **NOT_RUN**.

순서: **A 필수 Gate → B에서 일관성/신뢰도 입증 → C Native 실제 구현 효과 → D 일반화 검증**. GitHub Actions 성공·소스 작성·PSD·mock test PASS는 과학적 성능 PASS와 다르다. 기존 38124202873·38124280840 조기 B 결과는 격리 유지한다.

## A — P0 전제 복구

### V00 | PASS — RF pose/time/channel index 대응

19,038 RF 요청, 원래 7케이스에 대해 time/timeline_k/pose_id/H 행/XY/yaw/mount/anchor/source SHA를 독립 대조했고 불일치 0. 수정된 전체 이력 128seed에서 별도 Cholesky NEES 재계산 최대 차 3.55e-15. 근거 38120812381, 38126674932. 과거 잘못된 배열 접두 인덱스로 평가한 128seed 결과는 결론에서 제외한다. **후속 단계의 매 RF 호출마다 동일 검증을 자동 실행**한다.

### V01a | PASS — 동일 RF H 입력의 receiver observer parity

동일 입력 42조건, 4,032 sample에서 branch 간 s 차이 0, 공통 first-path tap 일치. 기본 common first-arrival gate를 4/8/16 zero-padded tap으로 고정한다. 과거 5/9/17 tap 결과와 섞지 않는다. 주파수·Hann·IFFT×4·강한 RX 30% 진폭 leading-edge·두 RX 공유tap·receiver noise 및 검출기 offset을 manifest로 고정.

### V01b | BLOCKED — 12조건 RF 생성계통의 full-channel parity

검증된 것은 **구형 Method-B 7개 full H와 신규 Native 5개 full H 각각의 provenance**다. 신규 Native 5개는 잃어버린 파일이 아니다. 비교해야 할 **이전 Method-B의 45° H 다섯 개 원본 바이트**가 없다. SHA 대상은 REQUIRED_LEGACY_COUNTERPARTS.json 참조. LFS exact lookup 38130108660에서 다섯 개 모두 HTTP 404; 역사 commit 조회 38131058250은 timeout으로 전체 이력 검사 미완료.

완료 경로 1: 과거 원본 5개 exact SHA 회수 후 동일 frequency/pose/port/anchor/mount 복소 H 및 FP tap/s 동등성 검사. 완료 경로 2 (현재 더 실행가능한 대안): 동일 핀 고정 Native solver + FFD/scene로 **12개 전체 full/LoS H를 통일 재생성**하고 구형 비교자료를 역사적 참고자료로만 보존. 프리레지스터 기준 상대 H 오차 최대 1e−3, 절대 s 차 0.01, FP tap 동일 (의미 있는 source 동일성 비교가 가능할 때). 12개 source 동일성 없이 7+5를 통합 결과로 승인하지 말 것.

### V02 | FAIL — sensor-v2 기본 모델의 통계적 정합

128개의 새로운 독립 seed(640–767), 14 모드, 원 추정기/공동 상태입력 cubature+GH9 후보 2개 = **3,584개 재실행**. 0/12/24/48초 체크포인트에서 기존 추정기 45/56, 후보 46/56만 통과(후보 10개 FAIL). 48초 LARGE_IDEAL_RANGE 평균 pose NEES 기존6.662, 후보5.065, family 상한3.820. 고드리프트 및 prior 조건 실패를 제거하거나, 사후 R/Q만 늘려 PASS로 만들지 않는다.

남은 실험:
- V02a initial error: 정확한 Gaussian P0, 기존 signed prior 및 bias/scale 초기화 정의 분리.
- V02b generator: gyro bias, gyro SF, wheel ratio/wheelbase, physical slip, 공유 gyro–wheel 입력잡음 교차항을 각각 off/on.
- V02c estimator: 원 EKF 선형화와 cubature/GH9, 외란 상태 분포, correlated process update의 차이를 matched-seed로 평가.
- V02d 새 명시적 sensor distribution 계약이 불가피하면 새 버전/commit/해시를 만들고, 원 실패자료를 그대로 남긴 상태에서 전체 독립 검증 재수행.

Exit: 운영에 사용할 모든 사전등록 모드의 평균오차, empirical pose covariance/P, NEES, 95% coverage에서 familywise 기준 통과. 이상적 RF에도 실패한 기본 정합을 multipath의 문제로 돌리지 말 것.

### V03 | PASS_IN_DECLARED_SCOPE — Native FFD 극점과 Jacobian

pole-safe 모델: CARTESIAN_FIELD_DEG4_CORE2_BLEND2_3_FP_V2, 계수 SHA 87a38e9cc221244cb8b6ca08ba59afd2090bb64594d486b020c694d06dc76a5e.
- 기존 9,519 LoS 회귀 및 독립 FFD 1,120점 검증.
- 9개 near-pole 기존 LUT s RMS .339094 → 수정 모델 .0006082.
- 새 Native 6곳 최대 |s 차| .000983652(실행 38126804417).
- 실제 SHA-검증 FFD로 구한 미분값과 모델 Jacobian의 24개 비교(실행 38130986616): 최대 Jx .001830/m, Jy .008695/m, Jheading .001617/rad. 사전등록 한계 .01 각각 통과.

제한: 여섯 독립 지점과 정의된 LoS 관측 조건에서의 통과다. V01b의 source-consistent 12개 full H 및 전체 경로 과학적 결과까지 승인했다는 뜻이 아니다.

**A 종료 Gate:** V01b source 계통 통과 + V02 필수 통계적 정합 통과가 반드시 필요. V00·V01a·V03은 검증된 입력 버전으로 보존한다.

## B — P1 원인 분리: V04–V10 (A 통과 전 과학적 결과 미실행)

### V04 | Range RF chain 원인 분해
같은 pose/yaw/FFD에서 (i) ideal geometry direct range, (ii) native direct LoS first arrival, (iii) full multipath first arrival, (iv) 별도 10/30dB thermal noise를 교차 비교. 출력: 고정 receiver offset, 잔여 평균편향과 검출 index, 조건부 분산, MSE, 거리·수신전력·yaw·mount별 편향 및 time-lag. 같은 2–3각 공통 FP tap과 4/8/16 gate ratio를 보존한다.

### V05 | Range-only 경쟁 오차 모델
기준 IMU+wheel, 기존 range-only, train-route 조건부 bias 평균, 분산보정, AR1 평균정보량 근사, Gauss–Markov range-bias augmented EKF, Schmidt/consider bias 모델을 동일 seed/trajectory로 비교. 단일 앵커에서 radial 위치와 range bias의 식별성(정보행렬 rank, 최소 singular value)을 검사. 성공: 위치 RMSE·NEES·95% coverage·NIS whiteness 동시 개선. R을 과도하게 키워 range 정보를 버리는 방법은 별도 대조로만 사용.

### V06 | Range × LP s 원인 격리
등록된 3 Range 타입(ideal/native LoS/full) × 4 s 타입(none/perfect-model/original direct LoS/full) =12 factorial arms + no RF와 s-only full =14. 초기 old7 × 3drift × 4seed ×14=**1,176개 full-route filter run**. 동일 P0, source, sensor RNG, timestamp, original pose_id, range covariance. Truth-based perfect s는 오직 oracle 대조로 사용, online quality 입력으로 절대 사용하지 않는다. Stop-probe G1/G2 보조시험은 range 관측 3회 모두 고정하고 s만 1/2/3회로 바꿔 오염 영향과 정보량 분리.

### V07 | 다중경로 RF 오차 공간·각도 공분산
같은 XY에서 range0/1/2, s0/1/2의 full−LoS/LoS−LUT error를 따로 계산; diagonal, off-diagonal, firstpath tap 공유, firstcluster s, thermal-only covariance 및 model/site bias covariance 구분. 169 case-station은 독립 환경 169개가 아니므로 route/unique XY 단위 재표본화와 신뢰구간 필요.

### V08 | 시점 간 full pose×RF 공분산
V00에서 교정한 정확한 pose-ID를 매 시각 적용하고, F/G/Q/C/K의 error transition으로 P_ij를 재구성한다. 독립 sensor/RF seed로 centered Cov(e_i,e_j), cross Cov(e_i,v_j), bias-inclusive E[e_i e_j^T]를 검증한다. 기존 잘못된 H-array-prefix를 사용한 128seed 비율/편향은 원천 폐기. 최소 128seed를 한 장소가 아닌 다수 station/mount에서 독립 확인하고 full cross-time innovation whiteness 평가.

### V09 | Observability와 과신
단일 앵커의 radial/tangential gauge, straight/turn/zigzag 경로, 고정·확장 range bias state의 rank 테스트. 매 tick 위치·heading 오차와 P6의 Schur decomposition, range Kpsi, radial eigenaxis와 실측 MSE/P를 비교. 일부 매우 작은 P가 진짜 독립 정보에 의해 생겼는지, correlated bias를 독립관측으로 과신한 것인지 분리.

### V10 | q_r/q_s/q_site/q_point 예측 calibration
각기 다른 확률 목표: range abs error 내 포함, 실운용 prior선택 RF heading good5, site 공통 multipath 위험, 점별 편파 mismatched. Train site/route와 holdout을 물리적으로 분리하고 Brier·AUROC·ECE·high-confidence wrong·risk-coverage·no-match 및 hardware firstcluster availability를 검증. 가장 성능이 좋은 passive 기준선을 **동일 source의 RMSE+NEES+coverage+false accept**로 선정. 통과 못하면 C의 과학적 baseline 선정은 보류.

**B 종료 Gate:** Range/s bias+cross covariance model이 물리적·통계적으로 정합하고, 실제 운영 위험확률이 heldout에서 보정됐으며, 같은 물리경로의 최선 passive baseline이 고정되어야 한다. 현재 B status는 NOT_RUN_AFTER_A이다.

## C — P2 실제 Native Active Probe: V11–V13 (B 통과 전 공식 실험 미실행)

### V11 | Causal integration
기존 native plant/sensor 6-state EKF/FFD channel, 검증된 pole-safe h/J, range bias/R, quality model과 site-point correlated estimator를 하나의 실제 controller로 연결한다.
매 0.2s IMU+wheel→유효 range→**RF s 적용 전** q 평가→정상 high confidence s 갱신/low confidence 시 보류→물리적으로 BRAKE/SETTLE→새 정지 XY·antenna lever arm에서 fresh s0→body yaw 새로 1–2각 s1/s2→state- and time-aware joint posterior(q_site,q_i,full P6)→센서 추정으로 기존 heading 복귀→계속 drive. 주행 중 trigger s를 정지 s0로 재사용하지 않는다. Truth only RF solver/evaluator에 접근; inference truth leak 금지.

### V12 | Native 짧은 실제 연속 구간 통과
기록 필수: 실제 RF 기반 trigger, time, measured yaw/gyro/wheel, x_trigger vs x_stop, slip XY/antenna lever arm, every RF packet ID and source H/FFD SHA, correction x6/P6 before & after, first resumed state prediction. 단위테스트/예약 trigger는 PASS 근거가 아니다. 의도된 위험 구간과 정상 구간 각각에서 event-state 순서를 실제 native RF로 재현하고, 추가 thermal/gyro independent seed 재확인. 모든 probe 뒤 실제 frame/timestamp를 보존한다.

### V13 | Full-route Native 12 조건
같은 Native solver/source × (R2,R4,R5)3 × anchor(A,B)2 × mount(0,45)2=12. Info-only 시험은 같은 실제 trajectory/time에 offline filter policies를 replay, policy-effect 시험은 controller가 실제 probe stop/time을 결정하며 driven trajectory를 다시 생성; 섞지 않는다.
Baseline: RF off, best passed range-only, best validated passive RF s, naive s, SHAM(동일 정지·회전·settling·3개 range 시간 및 수치, extra s만 OFF), 2point/3point, optional cluster-prior 3point. Report progress-matched heading/xy RMSE/P95, pose NEES/χ²3 coverage, NIS residual ACF, noRF/outage and false-safe rate, elapsed time + motor energy. Physical scene/seed/anchor/mount clustered paired difference CI. Pilot seeds/confirmatory seeds separate and test sizes preregistered.

**C 종료 Gate:** 실제 위험 검출로 probe 동작하고 동일 full posterior를 이후 주행 EKF가 사용한다. SHAM 대비 RF 정보 이득과 best passive 대비 정확도·신뢰도·시간 tradeoff가 나타나야 한다. Native stationary three-packet demo 또는 mock test는 C full-route PASS가 아님.

## D — P3 일반화/최종 동결: V14–V15 (미착수)

### V14 | 독립 장면·하드웨어 가능 범위
기존 R2/R4/R5 모두 단일 corridor다. Holdout 장면: 폭/벽재질/코너/금속·유리 구조, 다른 anchor pose/height/mount 및 FFD incidence를 갖는 독립 현장 geometry를 별도 생성·측정한다. Receiver에서 실제 dual-LP P1/P2와 first-arrival amplitude CIR를 읽을 수 있는지, 시간동기/포트 gain/noise floor/온도 drift와 motor/slip/fps를 확인한다. HW 미검증은 SIMULATION_ONLY.

### V15 | Final model/claim
A/B/C의 실패 arm까지 보존하고, 바뀐 모델/LUT/FFD/source SHA, 관측기 정의, 물리 조건, calibration 기준을 고정한다. Range nuisance handling은 6state bias correction vs 7state GM bias vs Schmidt, probe posterior는 correlated batch vs fixed-lag smoothing을 independent heldout의 보정 확률/정보 기준과 실행 비용으로 비교하여 선택한다.
Acceptance: pose df3 NEES 기대값3, χ²3 95% threshold7.815와 95% coverage를 독립 seed/scene bootstrap 신뢰구간으로 검정하되 숫자에 맞춘 posthoc R inflation은 금지. RMSE 개선, no-harm, q calibration, memory/runtime+time cost와 일반화 통과까지 확인한다. 운영 hardware 미보유 시 최종 simulation scope를 명시한다.

## 요약 판정과 현재 업무 순위

| Stage | Status | Concrete next |
|--|--|--|
| A/V00 | PASS | Identity regression freeze |
| A/V01a | PASS | Observable/FP-window manifest freeze |
| A/V01b | BLOCKED | historical legacy45 H x5 exact recovery OR 12 source-consistent Native H regeneration |
| A/V02 | FAIL | isolate mismatch in prior/gyro/wheel/calibration and recover statistical consistency via prereg independent MC |
| A/V03 | PASS_IN_SCOPE | pole-safe regression in new H |
| B/V04–V10 | NOT_RUN_AFTER_A | 14-arm factorial & range/s/cross-time & calibrated passive baseline after A gate |
| C/V11–V13 | NOT_RUN | actual observed trigger physical stop fresh s0/pseudo 2–3 angle fullroute native after B |
| D/V14–V15 | NOT_RUN | independent geometry + final decision & artifact handoff |
| FINAL | scientific_PASS=false | no model confirmed |

**이 문서는 계획·상태 문서이다. 미수행 B/C/D 단계를 수행했다고 보고하지 않는다.** 최신 evidence register는 research/ABC_RESUME_20261011/STAGE_GATES.json 및 PROGRESS_AND_REEXECUTION_KO.md. 특정 stage PASS를 변경할 때는 대응 출력·sha·run ID·검증 표를 먼저 기록한다.
