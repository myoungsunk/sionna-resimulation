from pathlib import Path
import json,datetime
import pandas as pd
J=Path('/job');m=pd.read_csv(J/'ANALYSIS/ARM_MEAN_SEED_METRICS.csv');cv=pd.read_csv(J/'RELIABILITY/METRICS.csv');p=json.loads((J/'PROBES/STATUS.json').read_text());a=json.loads((J/'OUTPUT/00_INPUT_AUDIT.json').read_text());verify=json.loads((J/'VERIFICATION.json').read_text())
def table(df,columns):
 x=df[columns].copy();lines=['| '+' | '.join(columns)+' |','| '+' | '.join(['---']*len(columns))+' |']
 for _,r in x.iterrows():lines.append('| '+' | '.join(f'{v:.6g}' if isinstance(v,(float,int)) else str(v) for v in r)+' |')
 return '\n'.join(lines)
text=f'''# Sensor-v2 CIR·RF heading 연구 실행 보고서

작성: {datetime.datetime.now(datetime.timezone.utc).isoformat()}

## 결론과 실행 상태

저장된 7개 full/LoS RF 케이스와 동결한 sensor-v2로 A–E 본 비교 **5,250회**를 실제 실행했다. 본 비교의 실패는 0건이며, 센서-only 초기화/wheelbase 대조 360회, 원 필터 대비 계측 parity 80회, E 저장 경로 smoke 7회도 완료했다. 총 필터 실행은 **5,697회**다. 실행 성공은 모델 정합·공분산 정합 또는 과학적 PASS를 의미하지 않는다.

관측 특징과 heading 정답률 사이에 route별 연관이 있었지만, 확률 보정은 충분하지 않았으며 E 정책은 D보다 평균 heading/위치 RMSE를 악화시켰다. E는 일부 공분산 과신을 줄였어도 충분한 coverage를 얻지 못했다. 이번 정책을 production에 채택하지 않는다. **F01/F02 OPEN, scientific_PASS=false, GENERALIZATION_NOT_PROVEN=true**를 유지한다.

프로브는 저장된 각도에 대한 오프라인 진단만 수행했다. Sigma_probe의 시간·각도 간 공분산, 센서 잡음을 포함한 실제 회전 제어, 회전 시간 계약이 없어 확률 보정·F 필터 갱신·실제 운용 효과는 BLOCKED다. 신규 RF·새 환경·하드웨어 실험을 실행하지 않았다.

## 1. 질문 → 기준 → 입력 확인

질문은 실제 저장 RF와 IMU/wheel 입력에서 CIR 특징이 RF-heading 정확도를 설명하며, 독립 route 평가와 신뢰도 적용에서도 유효한지다. 사양서는 연구 브랜치 `codex/cir-heading-reliability-prereg-20261010`, 게시 커밋 `c2d829e`의 `research/HEADING_RELIABILITY_20261010/00_PREREG_CIR_AND_RF_HEADING_KO.md`, `01_SENSOR_V2_SIM_SPEC_KO.md`를 보존했다. 필터/생성기는 통합 감사 `16d22fc3121963743cf7f1bf56233e00083c5518`의 `audits/DRIVE_SIM_20261010/02_sensor_v2_review/source`를 git archive로 분리했다. 원본 파일 내용의 재검사 결과 변경 없음이다.

입력은 `/home/KMS/DRIVE_SIM_POST_A23_SUPPLEMENT_20261010_01a12449/BLOCK_C/`의 CASES.json, SAMPLES.json, FULL_RF/H_*.npy, H_LoS_*.npy, freqs_hz.npy다. R2-A 0/45°, R2-B 0°, R4-A/B 0°, R5-A/B 0° 총 7케이스이다. full/LoS 배열은 각각 N×257×2RX×2TX, TX0(+45°)를 사용했다. 물리적으로 별개의 환경 7개가 아니라 한 corridor의 경로·anchor·mount 조건 7개다.

원 LUT는 읽기 전용 선택 원본에서 복사했고 재생성하지 않았다. 두 사양서의 LUT SHA 문자열은 65자리였으며, 실제 원본 두 곳과 일치한 64자리 SHA는 `711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079`다. 입력 결과를 보기 전에 `PREEXEC_HASH_CORRECTION.json`으로 중복 d 한 글자를 정정했다. 사양서 원본은 고치지 않았다. bank·LUT hash는 하드웨어 타당성을 입증하지 않는다.

주파수축 SHA256: `fe0bcfeb1426847ea090668845fe124482086d0510e38ebdb463609e2a1169f8`. LUT metadata SHA256: `8773e79fbb39d07fd80605339a0752e6e4e5eb0658572f091e67395ab0fd5856`. 전체 H·pose·timeline·source SHA, shape와 observer 비교 수치는 `OUTPUT/00_INPUT_AUDIT.json`, `SOURCE_MANIFEST.json`에 있다. full/LoS 총 **19,038개 광대역 관측**을 Hann→4N IFFT→30% leading-edge→공통 tap ratio의 독립 NumPy 계산과 동결 observer로 대조했고 s·power·range 최대 차이는 0, tap도 동일했다. 이것은 기존 H 처리 parity이며 Sionna 물리·LUT 정합 게이트의 새 PASS가 아니다.

## 2. 질문 → 동결한 실행 방법 → 모델 적용 한계

실행 전 `PLAN.json`에 seed, 표본 수, 초기화, Q/R, sensor 설정, classifier, E 정책, 평가 mask와 CPU 한도를 고정했다. source는 6상태 EKF/direct-s이고 공유 gyro/wheel 상관 규약 C=-GQBᵀ를 그대로 사용했다. sensor 실제 입력·true parameter(평가 전용), Q/F/G/C, 전체 P6, pre-RF/post-range/post-RF 상태, innovation/S/R/H/NIS, gate 및 mask를 모든 run의 NPZ/JSON으로 저장했다.

- 본 비교: 7케이스×3 drift×50 seed(0–49)×A–E =5,250회. RF는 저장된 noise-free H이며 추가 30dB 잡음 arm은 실행하지 않았다.
- A RF-off, B 실제 range, C 실제 range+저장 Sionna LoS-only s, D 실제 range+full RF s, E D에 held-out-route 신뢰도 abstention/inflation을 적용한다.
- **C는 LUT와 완전히 일치하는 합성 관측 대조군이 아니다.** 저장 LoS-only 채널에서 관측을 계산했다. 사양서의 “matched direct LoS” 표현을 완전 모델 정합 증거로 사용하지 않는다.
- 기본 wheelbase는 unknown. pose prior와 초기 pose 오차는 0.1m/5° Gaussian으로 대응하지만 calibration 상태 prior까지 완전 정합한 초기화는 아니다. calibration 추정치는 0, 실제 drift는 기존 생성기의 signed scenario 값이다. common scale/bias RW 추가는 0, 기본 slip과 measured-increment Q 근사는 보존했다.
- 별도 360회는 R2/R4/R5-A, 3 drift, seed0–19에서 pose 정확 초기화/unknown wheelbase, 확률 pose 초기화/외부 정확 보정 wheelbase를 비교했다. known 값은 통제 실험의 외부 보정 가정이며 하드웨어 측정 보정이 아니다. calibration truth를 online 추정 상태로 초기화하지 않았다.
- 원 Tnone timeline의 dt=0.2s, t≥30s 평가를 사용했다. R2/R4/R5 길이는 979/742/1,415 sample이다. 기존 truth는 legacy-Euler 생성 규약과 일치하고 exact-SE2 lateral residual 검사는 실패했다(최대 약0.000146m). truth를 변경하지 않았으므로 v2 exact-arc filter와의 근사가 남는다. 완전 정합 센서 대조군으로 부르지 않는다.
- R/Q/gate/prior는 A–D에서 동일하며 E의 R_s 배수만 사전에 정한 정책으로 바꿨다. q<0.5 또는 inverse ambiguity/no-match면 s를 abstain, 그 외 배수는 min(100,max(1,1/max(q,0.1)²))다. 모델 출력 확인 후 튜닝하지 않았다.

## 3. heading 후보와 누출 방지

RF-off A의 pre-RF 추정 위치·heading·P를 사용해 [-180°,180°) 0.25° 격자에서 LUT 역문제 후보를 계산했다. 모든 대안과 prior score를 저장하고 최소 wrapped heading prior score의 branch를 선택했다. truth는 후보 선택에 사용하지 않고 정답 라벨에만 사용했다. 격자 구간의 선형 root 보간이므로 연속 역문제의 엄밀한 해법은 아니다. no-match residual≤0.01, 5° 초과 분리 후보의 score gap<2 ambiguity 규칙은 실행 전 동결했다.

1050개의 A trajectory에서 평가 sample **930,150개**를 라벨링했다. 이용 가능 heading sample은 R2 281,894/373,050(75.56%), R4 172,529/177,600(97.14%), R5 204,216/379,500(53.81%)이다. 이 행들은 같은 RF를 반복하는 seed/time 조건이며 독립 RF 표본 93만 개가 아니다. Tnone에 없는 RF pose 또는 평가 mask 밖 pose에는 운용 prior가 없다고 표시했다. `missing_prior_pose_ids`는 t<30s 제외도 포함하므로 모두 “trace 없는 pose”로 해석하면 안 된다.

특징은 amplitude-CIR D1–D4, normalized two-port P1–P5, 실제 수신 range·LUT slope·추정 P·gyro-wheel 차이·예측 S로 표준화한 innovation K만 사용했다. phase·truth·ray/path label은 inference에 사용하지 않았다. model whitelist와 train/calibration/test station 분리를 별도 검증했다. E는 자신의 실제 pre-RF 상태에서 K와 inverse availability를 다시 계산한다. A prior에서 학습하고 E prior에서 적용하므로 정책 적용으로 입력 분포가 바뀔 수 있다.

P1/P4 구현의 epsilon을 절대 CIR power 대신 합1 정규화 이후에 적용하도록 학습 전에 수정했다. 이 수정 전 코드와 재계산 산출물은 `FEATURES_INITIAL_PRESERVED/`, 변경 기록은 `FEATURE_IMPLEMENTATION_CORRECTION.json`에 있다. 최초 feature CSV는 같은 신규 OUTPUT 경로에 재기록됐고, 이후 수정 전 계산을 별도 경로에 재생성하여 보존했다. 원 RF·LUT·기존 감사 결과는 덮어쓰지 않았다. gain 1e-8/1/1e8 검산에서 normalized P1/P4 최대 변화 4.44e-16으로 1e-12 검산 한계 이내다.

## 4. 독립 route 신뢰도 결과

각 route를 통째로 held-out하고 같은 route의 anchor/mount/seed를 모두 같은 fold에 두었다. training station 20%를 sigmoid calibration용으로 분리했다. median+missing indicator, StandardScaler와 L2 LogisticRegression(C=1,max_iter=2000)는 training만 사용했다. 모든 threshold는 고정했다. 불확실 구간은 available subset에서 제외하고 availability를 별도로 보고했다.

{table(cv[cv.model.isin(['distance','D','DP','DPK'])],['route','model','brier','auroc','ece10','calibration_slope'])}

낮은 Brier가 좋은 지표다. DP-D Brier 차이는 R2 -0.00580, R4 -0.02101, R5 -0.00655이고 1,000회 station bootstrap 구간은 각각 [-0.01002,-0.00166], [-0.02815,-0.01403], [-0.01187,-0.00089]다. 이는 이 corridor의 held-out route 안에서 P 추가가 D보다 조건부 예측을 개선한 증거다. “실제 편파 매칭” 또는 다른 환경의 일반화 증거로 확대하지 않는다.

DPK도 distance-only보다 Brier가 작았지만 ECE는 R2 0.0931/R4 0.1382/R5 0.0786으로 남았다. R5 calibration slope 0.4168은 과도한 score spread를 시사한다. 높은 분류 지표와 올바른 확률 보정은 별도이다. constant prevalence 모델의 slope는 식별할 수 없으므로 METRICS.csv의 해당 회귀 계수는 해석에서 제외한다.

Pearson/Spearman, station bootstrap CI, distance/slope를 제거한 탐색적 partial association, held-out 선형 MAE/RMSE/R², 10분위 bin은 `ASSOCIATION/`과 `RELIABILITY/FEATURE_BINS.csv`에 있다. time sample을 독립 유의성 반복으로 사용하지 않았다. spatial station의 상호 독립성까지 입증한 것은 아니며 CI는 이 환경·그룹 정의에 조건부다. unresolved 경로 분류는 H만으로 만들 수 없어 미검증이다. 실제 장치에서 전체 magnitude CIR 접근 가능 여부도 UNKNOWN이다.

## 5. 정확도와 공분산을 함께 본 실제 결과

아래는 각 케이스×drift×seed metric을 같은 가중치로 평균한 기술 통계다. route/drift별 결과와 대응 seed bootstrap은 별도 파일에 보존했다. 다른 실행의 NEES≈321 또는 A23/S6와 설정이 다르므로 같은 실험의 재현으로 취급하지 않는다.

{table(m,['arm','heading_rmse_deg','pos_rmse_m','nees_mean','pose_coverage','heading_coverage'])}

NEES는 [x,y,heading] 3차원 subspace, radian wrapping, 원 P3로 계산했다. 양측 tail은 chi-square(df3)의 2.5/97.5% 경계, pose coverage는 95% 경계이며 heading coverage는 ±1.95996σ다. model/prior가 정합하지 않아 이를 승인된 PASS 기준으로 사용하지 않는다. singular covariance를 jitter로 숨기지 않았다. seed별 covariance singular 수·실패 status·마지막 sample이 raw에 있다.

C는 작은 RMSE를 보이지만 NEES≈69.36, pose coverage≈0.268로 공분산 정합을 보이지 않았다. D는 C보다 정확도와 일관성이 모두 악화됐다. E는 D의 평균 NEES를 약268→175로 줄였지만 heading RMSE 2.942→3.382°, 위치 RMSE 0.344→0.417m로 악화시켰으며 pose coverage≈0.191에 그쳤다. **E의 production 채택 근거가 부족하다.** 고정 정책의 negative/mixed 결과를 그대로 남긴다.

`ALL_RUN_METRICS.csv`에는 heading P95/worst, lateral RMSE, 양측 NEES tail, pre-gate/accepted NIS, rejection, accepted s 이후 circular heading error 증가 비율, E abstention/outage 길이를 저장했다. harmful 정의는 같은 sample의 post-range 대비 post-s heading 절대 오차 증가이며 인과 기여율이 아니다. NIS accepted-only와 pre-gate는 별도다. false-accept는 held-out heading label에서 q≥0.5/0.9를 구분한 `ASSOCIATION/FALSE_ACCEPT.csv`에 있다. 실제 probe recovery/time 기반 운용 결과는 시간 계약 부족으로 미검증이다.

## 6. 프로브 진단과 차단한 해석

같은 XY의 연속 yaw block에서 [0], [0,2], [0,2,4]를 고정 선택했다. 실제 recorded yaw offset을 오프라인 실험의 schedule로 사용했다. prior가 있는 동일 subset과 같은 seed에서 비교했고 truth로 branch를 선택하지 않았다. 저장 관측을 사용하므로 신규 Sionna는 실행하지 않았다.

{p['rows']:,}개의 상태/비교 행 중 계산 가능 진단 행은 {p['usable_rows']:,}, prior 없는 station/run 행은 {p['missing_prior']:,}이다. 그 행은 제거해 성공으로 바꾸지 않고 NO_EVALUATION_PRIOR로 보존했다. `07_PROBE_STATIONS.csv.gz`, `08_PROBE_COMPARISONS.csv`, `PAIRED_DIAGNOSTIC.csv.gz`에 residual vector, common correction, slope span, leave-one-out point influence와 평가 heading 오차를 저장했다.

Sigma_probe=.09²I는 **진단 점수 계산용 가정**으로만 사용했다. 실제 off-diagonal covariance를 검증하지 않았으므로 여러 관측의 정보량·chi-square probability·Brier uplift·F 필터 효과를 주장하지 않는다. 대각 가정 결과가 좋아져도 독립 관측 증거가 아니다. body 회전에 따른 gyro/wheel noisy control과 elapsed time 모델이 없으므로 비용은 NA, 운영 가능한 free probe로 해석하지 않는다. 향후 validated Sigma, timestamp/회전속도, 동일 noisy sensor replay 계약을 확보해야 F를 실행할 수 있다.

## 7. 실행 비용·검증·수정 이력

Snowball에는 KMS로 접속했다. 컨테이너 이미지 `rt-dual-engine:s2-deps-r2-20260928`, Python `/opt/rt-env/bin/python`, CPU32/memory96GiB 한도를 사용했고 BLAS/OpenMP thread는1로 제한했다. 기존 다른 job을 중지·수정하지 않았다. 대표 실행 명령은 Docker read-only `/input`, `/routes`, `/lut` mount에서 `/opt/rt-env/bin/python /job/simulate.py main`, `controls`, `labels_v3.py`, `reliability.py`, `probes.py`, `e_driver.py`, `analysis.py`, `association.py`, `verify.py`다. 전체 mount·image ID·시각·exit code·실제 Cmd는 `EXECUTION_CONTAINERS.json`, 상세 로그는 LOGS/에 보존한다.

본 A–D4200회는 약106.3초, controls360회 약7.0초, E1050회 약73.9초, heading labels 약18초, route classifier 약75.4초였다. 준비·실패 진단·전송 시간과 총 CPU time은 이 wall-clock 숫자에 포함하지 않는다.

계측된 pilot80회는 원 `run_filter_v2`와 state/cov 차이≤1e-12를 확인했다. A–E1050쌍은 센서 입력·초기 prior·mask가 byte-value 수준에서 같았고, E R 배수 및 abstention 조건도 검산했다. 모델21개 inference whitelist와 training/calibration/test route 분리 검사는 통과했다. source 해시105개 재검사에서 원본 변경 없음이다. 이 CHECK PASS는 구현/보존 검사이며 scientific_PASS가 아니다.

중간 실패를 숨기지 않았다. 초기 audit의 Windows 상대경로 처리와 사양서 65자리 hash 때문에 중단된 시도, labels의 CSV 위치와 Parquet 미설치 때문에 중단된 시도를 LOGS/에 남겼다. 환경 패키지를 추가 설치하지 않고 CSV.gz로 바꿨다. 첫 분석은 빈 error 문자열을 실패로 세어 5,250실패라고 잘못 기록했으며 필터 실패가 아니었다. `ANALYSIS_ATTEMPT1/`에 보존하고 비어 있지 않은 error만 세도록 수정했다. 최종 실패 수0은 모든 main/E run status와 키 검증에 근거한다. 기준을 완화하거나 covariance guard를 우회하지 않았다.

## 8. 산출물과 다음 판정

실행 source·사양서·PLAN과 correction records, 입력 audit, raw sensor/상태/P6/innovation/mask NPZ, 후보 전부, 모델·held-out 예측, station/seed bootstrap, 그림·Korean report를 독립 output root에 보존한다. 각 파일 SHA256과 크기는 `OUTPUT_MANIFEST.json`에 기록한다. 로컬 전달 폴더와 원격 root의 대응은 DELIVERY_RECEIPT.json에 기록한다. 압축/전송 자체는 과학적 PASS가 아니다.

이번 실행은 “특징과 heading 오류의 조건부 연관”에 제한적 지지를 주지만, “보정된 신뢰도 확률”과 “정책을 적용하면 정확도와 일관성이 동시에 개선된다”는 결론은 지지하지 못한다. 다음 필요한 것은 새 R tuning이 아니라 probability calibration 실패의 조건 분석, 실제 CIR 접근 계약, probe Sigma와 body-rotation 시간/센서 계약, 독립 환경 평가이다. 사용자 추가 요청 없이 RF 재생성·필터 모델 수정·새 geometry·production 채택·commit/push를 진행하지 않는다.
'''
(J/'FINAL_REPORT_KO.md').write_text(text,encoding='utf-8');print('report written',len(text),flush=True)
