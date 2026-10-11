# P0 — 성능 비교 전제 복구: V00–V03 실제 실행 결과

기준일 2026-10-11. 기반 native source commit **5a50fa9f0813a3dd0f9ca53e26da3cd3fbcfada9**. 작업 브랜치 **codex/p0-foundation-recovery-20261011**. 원본 RF H, 원본 LUT 및 과거 결과를 덮어쓰지 않았다.

**종합 판정: P0 전체 PASS 보류.** RF 인덱스 오류는 복구했고, 같은 H에 대한 관측기 계산은 일치했다. 기본 matched-prior 이상적 센서 조건은 정합성을 보였지만 큰 초기불확실성·높은 drift 조건은 불일치가 남았다. Cartesian 극점 수정 후보는 값·미분 오류를 줄였으나 전체 주행 공분산 일관성은 회복되지 않았다. 전파 source-family 동등성과 신규 near-pole Native PathSolver 검증은 미완료다.

## 실행 근거

| 항목 | 실행 ID | 실행 source commit | 완료 범위 |
|---|---|---|---|
| V00/V01 | [38120812381](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38120812381) | a21f992fcd797bff8be3d07696ee3ad2881421ea | 원 입력 대응, 128seed 오류/수정 대조, 관측기 독립 재계산 |
| V02 | [38121351395](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38121351395) | d1a3d5caaf1034b0bd1bdd9cdc729473e22a7188 | 12조건×128seed, 4 MC checkpoints, deterministic/F/G/H 검산 |
| V03 V2 | [38121366509](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38121366509) | 4b29532718b13047ecadcf2a338ca7f4a392a414 | 9519 native-LoS 회귀,1120 직접 FFD point,672 filter replay |

Workflow success와 과학적 통과는 다르다. 아래 수치는 다운로드한 artifact 원 배열/CSV에서 독립 재계산했다. 동일 noise seed를 다른 arm에 재사용한 paired trial이며, 실행 수가 독립 환경 수를 뜻하지 않는다.

## V00 — 시간행이 아닌 pose_id로 RF bank 조회

기존 128seed script(cd8f3ef9)는 H[:last+1]을 timeline으로 사용했다. T10에서 k=68,88,90의 실제 pose는68,989,991이므로 이를 SAMPLES의 explicit pose_id→H_row 사전으로 고쳤다. 첫 프로브부터 전체 이력을 다시 실행했다.

- 7케이스의 Tnone/T10 합계 **19,038 시간행**에서 requested pose / H pose / XY / yaw 대응 PASS.
- XY 허용치5.1e-7m, yaw5.1e-7deg는 원본 SAMPLES의 6자리 반올림 정밀도 기준이다.
- 재사용 pose, 원위치 복귀, shuffle/noncontiguous bank, 누락 pose, 중복 bank ID, 시간 오류 및 잘못된 geometry 등 **9개 회귀 검사** 통과.
- R2A m0 원래 first91 시간행 중 **22행**이 잘못된 H를 사용하고 있었다.
- 같은 원본 filter/관측기/128 sensor 및 RF seed로 faulty reference와 fixed를 각각 수행. 두 source는 H 선택식 한 줄만 다르다는 독립 diff 검산 완료.

| 마지막18.0s 지표 | 기존 잘못된 인덱스 (격리) | 수정된 pose lookup |
|---|---:|---:|
| Heading RMSE(°) |4.21078|3.08393|
| Position RMSE(m)|.089568|.072439|
| Pose NEES mean(df3)|5.43083|4.74202|
| Pose95 coverage|79.69%|86.72%|
| Heading MSE / mean Pψ|2.158 부근|1.21178|
| Mean range model error(m)|−.489387|−.040731|

수정 후13.6/17.6/18.0s 세 관측의 mean range residual은 모두−.040731m이다. 따라서 기존의 "같은 위치에서 yaw에 따라−4/−34/−49cm" 해석과 2.16배 불일치 주장은 해당 잘못된 128seed 실행의 과학적 근거로 사용할 수 없다. 수정 결과의 마지막 heading MSE/P 3000회 seed-bootstrap95%구간은 [.9715,1.4666]이다. 이것이 전체 pose consistency PASS를 뜻하지는 않는다: 첫13.6s mean poseNEES10.6467, 마지막4.7420으로 잔여 불일치는 남았다.

원본 faulty 결과와 코드의 상태는 **QUARANTINED_REFERENCE_ONLY**이다. 조용히 삭제하거나 새 결과와 섞지 않는다. 새로운 corrected tensors와 원본을 둘 다 보존한다.

## V01 — 관측기 정의 잠금과 수치 parity

현재 native observation.py와 frozen Sensor-v2 observation.py를 **동일 H, 동일 random noise stream**으로 비교했다. 7cases×full/LoS×noiseoff/30/10dB=42조건, 조건당96 H rows를 사용했다. 직접 쓴 Hann/IFFT/common-tap 계산으로 다시 대조하여 FP tap/detection/s 일치를 검산했다. 이는 제한된 input sample parity이고 전체 전파모델 동등성 검사는 아니다.

동결한 연구용 관측 정의:
- 257 실제 frequency bins; Δf=**1,950,000Hz**; IFFT1028, multiplier257.
- symmetric Hann, stronger RX **amplitude** peak의30% leading edge, 같은 tap에서 양 RX power.
- s=(P1−P2)/(P1+P2), range=tap×c/(1028Δf).
- 실제 range tap step=.149552258804749m, quantization variance=.001863823176134m².
- 이전 filter 상수 Δf=1,953,125Hz가 주는 variance=.001857863713357m². 두 수치를 같은 것으로 쓰지 않는다. 이번 V00/각 correction-only replay에서는 원래 filter R을 유지하여 실험 변수를 섞지 않았다.
- primary research early gate는 [kFP,kFP+L), L=4/8/16. 기존5/9/17은 별도 legacy observation version. 하드웨어 amplitude-CIR 지원은 UNKNOWN.
- detector offset−.531598390625m와 native 독립 calibration−.5124272934/−.5327236346m는 provenance가 다른 값이며 서로 교환하지 않는다. 실제 device antenna delay는 이번에 측정하지 않았다.

**PASS:** 동일 입력의 FP/s/detection 관측기 계산.
**미완료:** 기존7 Method-B와 신규 native5 full H를 같은 설정/pose/주파수에서 대응한 12case 전파 source-family 동등성. 이는 후속 필수 P0 gate로 남긴다. 42 observer tests를 그 증거로 사용하지 않는다.

## V02 — UWB 오염을 넣기 전 센서/필터 sanity

12조건×128 independent seeds, 48s trajectory,0/12/24/48s checkpoints. 관측 생성 시 calibration truth는 simulator 내부에만 사용했다. matched 조건의 true initial error는 6상태 P0 Gaussian에 맞추고, 이상 range는 geometric d+independent σ.08m, 이상 s는 **명시적 합성 모델 −cos(2ψ)+σ.06**으로 만들었다. 이 s는 실제 FFD 성능이 아니라 EKF sanity용이다. 이상적 RF arm의 gate는 infinity로 두었고 odometry gate는 원 소스 규칙을 유지했다.

| 48s 조건 | mean Pose NEES | Pose95 coverage | 판정 |
|---|---:|---:|---|
| Matched small Gaussian / RF-off |3.31386|92.97%|기본 MC 정합 범위|
| 동일 조건 + ideal range |3.05531|96.09%|기본 MC 정합 범위|
| 동일 조건 + ideal range+s |3.27181|94.53%|기본 MC 정합 범위|
| 큰 Gaussian prior + ideal range |6.20012|81.25%|실패 조건|
| 기존 high-drift assumptions / RF-off |4.67433|85.94%|실패 조건|

4×12=48 체크포인트 중 nominal95% meanNEES gate 불합격4개, Bonferroni familywise gate 불합격3개다. 큰Gaussian48s와 기존high drift24/48s가 familywise 실패다. 따라서 **모든 조건에서 sensor-v2가 통계적으로 정합하다고 승인하지 않는다**.

- no-error/no-prior-uncertainty SE2 truth vs filter max error1.69e−14.
- independent finite-difference F/G/H 최대오차 약1.93e−9 이하.
- shared-input C 제거, 정확한 primitive Q, Euler truth, biasRW, encoder-slip arm도 수행했다. 이 특정48s trajectory에서 여러 대조의 차이가 작았다는 사실을 C/동역학이 일반적으로 중요하지 않다는 결론으로 사용하지 않는다.
- large-prior/legacy-high 결과는 RF multipath 없이도 발생한다. 큰 prior의 선형화·geometry interaction와 calibration prior 부정합을 후속 분해해야 한다.
- 기존 INITIAL_EMPIRICAL_MOMENTS.csv는 k0 관측까지 처리한 snapshot을 포함한다. 전달 패키지의 INITIAL_PRIOR_BEFORE_ANY_RF_CORRECTED.csv는 같은 초기 RNG로 RF 이전 prior를 별도로 재구성했다. 원 출력 이름의 의미를 정정했으며 실제 filter 결과는 바꾸지 않았다.
- raw MC JSON은 pandas 기본10 decimal precision이다. 이를 재해석한 NEES는 최대5.37e−5 차이로 원 float64 요약과 일치했다. 원 record의 solver error로 해석하지 않는다.

## V03 — Cartesian 기반 pole-safe 후보 구현과 실제 주행 회귀

원본 SHA 검증 LP±45 FFD를 Cartesian 전계로 먼저 변환하고, θ≤4°의 원래 필드로 local horizontal-direction degree4 complex polynomial을 fit했다. θ0 원점값은 FFD Cartesian mean으로 고정한다. 신호 s 정답 label을 fit에 넣지 않았다.

**최종 후보 버전:** CARTESIAN_FIELD_DEG4_CORE2_BLEND2_3_FP_V2.
- θ≤2°는 Cartesian field와 실제 body/antenna yaw로 h와 analytic Jacobian 계산.
- 2–3° smootherstep 접합; θ≥3° original LUT 유지.
- 첫 V1 후보의1–3° 접합은 이미 잘못된 θ0 cell을1–2° 구간에서 다시 섞는 문제가 확인되어, 전체 bad cell을 제외하도록 수정했다. V1 artifact는 superseded diagnostic으로 남겼다.
- field coefficient 파일명 V1은 field fit coefficients 버전이다. 그 계수는 같고 최종 적용/접합 정책은 V2다. 모델을 식별할 때 계수 SHA만이 아니라 V2 source/접합 정책도 함께 보존해야 한다.

| 검증 | 결과 |
|---|---:|
| 기존 native-LoS pose 회귀 |9519개|
| near-pole9개 original s RMS |.33909417|
| near-pole9개 corrected s RMS |**.00060822**|
| near9 corrected maximum abs |.00107044|
| 별도 direct original FFD point |1120개|
| 그 point에서 s 최대 차이 |.00133962|
| core analytic Jacobian vs finite-difference 최대 차이 |5.71e−10|
| 검사한2°/3° 접합의 값 차이 |6.00e−9|
| 같은 접합의 gradient 차이 |6.56e−8|
| ±180° yaw periodic value 차이 |9.02e−16|
| θ≥3° 원래9519 중9509개 |예측값 unchanged|

이는 검사한 좌표/경계의 검증이다. First-path tap selection의 비미분점 및 원래 LUT의 모든 grid boundary까지 전역 C1임을 주장하지 않는다. **새 near-pole Native PathSolver 채널 생성은 미실행**이고, 새점 기준은 원본 FFD 직접 계산이다.

모델 계수 SHA256: 87a38e9cc221244cb8b6ca08ba59afd2090bb64594d486b020c694d06dc76a5e.
원본 LUT SHA256: 711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079 (변경 안 함).

### 같은 기존 주행 672회 filter replay

7case×3drift×8seed×4arm. Tnone progress30s 이후 평가, 같은 원센서 stream·range 관측/offset/R·s noise model. 원본/estimated-rho guard/clamp/Cartesian h-H만 비교했다. 실제 Active Probe 운영이나 새로운 물리 slip 시뮬레이션이 아니다.

| h/H 처리 | Heading RMSE(°) | Position RMSE(m) | Mean poseNEES | Pose95 coverage |
|---|---:|---:|---:|---:|
| Original LUT |2.872955|.339649|170.68965|13.3527%|
| Estimated rho<.1m s guard |2.873371|.340189|126.38513|13.3240%|
| theta2 clamp 진단 |2.873250|.339983|126.84621|13.3391%|
| Cartesian candidate V2 |2.873357|.340233|**126.39620**|13.3259%|

RMSE는 거의 같거나 미세하게 악화하며, meanNEES만26% 감소한다. 대표 seed0/level0에 저장된 NEES>1000 발생행은158→87, 그 표본 maximum11993.6→1544.9. 이는 한 subset 진단이고 전체672의 failure count가 아니다. 특히 R2A m0 NEES 평균723.29→414.13에서 감소가 크며 대부분 다른 cases는 거의 같다. 따라서 **극점 오류로 인한 일부 tail은 줄었지만 전체 pose consistency는 여전히 나쁘다**.

## P0 남은 gate / 다음 작업 범위

1. **V01 propagation source-family parity:** 같은 pose/frequency/settings에서 full native와 legacy H를 직접 비교하여 12조건을 혼합할 수 있는지 판정. 관측기 equality와 구분.
2. **V02 stress failure 분해:** large-prior 및 high-drift의 초기6D prior·비선형 range geometry·과정/공유입력 정합을 추가 대조. 숫자를 맞추기 위한 Q/R 사후 확대는 하지 않는다.
3. **V03 independent Native near-pole gate:** 새Cartesian h/H를 fresh Native PathSolver near-pole 측정으로 독립 비교하고 실제 packet/tap 경계와 불확실성 범위를 확인.
4. **통합 사용 제한:** 기존 원본 code/H/LUT는 보존했고 main에 병합하지 않았다. 새 P0 branch·관측기 version·pole model SHA를 고정한 범위에서만 후속 비교. V00 old faulty128 결과는 계속격리.

따라서 현재 상태는 **P0_REPAIRS_EXECUTED_WITH_OPEN_GATES**이며 P0 전체 scientific_PASS=false다. 아직 P1의 최종 bias-state/Active-Probe 알고리즘 선택으로 넘어갈 근거가 완성된 것은 아니다.

## 재현 명령

```bash
python research/P0_RESTORE_20261011/run_v00_v01.py V01 --out p0_results/V01
python research/P0_RESTORE_20261011/run_v00_v01.py V00 --out p0_results/V00 --seeds 128
python research/P0_RESTORE_20261011/run_native_audit.py run_v02_ideal_consistency.py --out p0_results/V02 --seeds 128
git lfs pull --include='LP_plus45_bank.npz,LP_minus45_bank.npz' --exclude=''
python research/P0_RESTORE_20261011/run_native_audit.py run_v03_pole_recovery.py --out p0_results/V03 --seeds 8
```

Native 기본 FilterConfig는 legacy이며 문서화된 V2BodyFilterConfig 확장이 필요하다. `run_native_audit.py`는 이 import 및 V2 pole model만 명시적으로 연결하고 **정확한 executed source와 SHA를 artifact에 기록**한다. 최초V02/V03 실패는 이 실행기 config-class 연결오류였고 수정본 재실행이 완료됐다. 원래 필터 파라미터를 바꿔 실패를 숨긴 것이 아니다.
