# B-MCG 입력·운동기준·P2 독립 감사

## 판정

**현재 입력의 단위·시간정렬·원본 코드 연결은 확인됐다. P2의 heading 적분도 맞다. 그러나 현재 B0 실험의 gyro에는 실제 상수 bias가 없으며, B 필터가 RF 갱신으로 만든 bias 추정치를 운동기준에 고정하면 상대 heading 예측이 더 나빠진다.** 또한 세 route는 같은 gyro 잡음 시퀀스의 앞부분을 공유한다. P2 결과를 독립 seed나 하드웨어의 신뢰구간으로 해석할 수 없다.

감사 범위는 `R2/R4/R5_B0_Full_10` 979/742/1,415행, 총 3,136행이다. 원본 입력 6개·FFD bank 2개 SHA/크기 검증, 3개 ROWS 파일까지 포함한 staging 11개 검증을 통과했다. 원본 코드의 `ORIGINAL_CODE` 5개 SHA도 일치한다. 이 문서의 새 수치는 `audit_controls.py`가 작성한 `CONTROL_PROVENANCE_AUDIT.json`과 P2 원본 산출물을 근거로 한다.

## 1. 실제 사용하는 운동 입력

| 항목 | 확인된 의미 | 구현상 함의 |
| --- | --- | --- |
| `ds[k]` | 구간 `(t[k−1], t[k]]`의 wheel odometry 전진거리, m | 속도가 아니므로 `dt`를 다시 곱하지 않는다. |
| `gy[k]` | 같은 구간의 gyro 적분각, rad | 각속도가 아니므로 `dt`를 다시 곱하지 않는다. |
| `dt[k]` | `t[k]−t[k−1]`, s | 현재 자료는 약 0.2초 간격. |
| `x[3]` | gyro bias 추정치, rad/s | 구간 회전은 `gy[k]−x[3]*dt[k]`. |
| `x0` | `t=0`의 RF 갱신 전 초기 상태 | 원본 replay는 `controls.x0[:3]`에 bias 0을 붙인다. 현재 archive `x0[3]`도 0이다. |
| `P0` | `t=0` RF 갱신 전 공분산 | 대각은 `[0.01, 0.01, radians(5)^2, radians(0.1)^2]`. |

모든 route에서 `ds[0]=gy[0]=dt[0]=0`. 원본 `online.predict`는 `k==0`에서 상태·공분산을 그대로 반환한다. `core.transition`은 `dt>0`만 허용하므로 `k=0`에 직접 호출하면 안 된다. P2는 anchor `a`에서 시작해 `a+1,…,k`만 적분하므로 이 규약을 지킨다. `dt`는 timestamp 차이와 배열 수준에서 일치한다.

**독립 wheel heading 입력은 현재 archive에 없다.** `sensor_v2.generate`는 `dtheta_odom`, encoder angle, 좌우 wheel increment를 생성할 수 있지만, 현재 online NPZ에는 `ds`, `gy`만 보존됐다. 현재 구현이 실제로 비교하는 것은 **wheel 거리+gyro 회전으로 만든 운동기준과 RF 관측**이다. 이것을 독립 wheel yaw와 gyro yaw의 교차검증으로 설명하면 틀린다. 평가 truth로 누락 wheel yaw를 재생하여 runtime에 공급해서는 안 된다.

## 2. B0의 실제 bias와 route 간 잡음 재사용

원본 `e0_baseline._controls`의 B0 recipe는 `SensorV2Config(level=1, condition='noise_pair', common_scale=0, bias_rw_rad_s_sqrt_s=0)`, seed 10이다. `noise_pair`는 wheel/gyro 잡음만 켠다. 이 recipe와 현재 평가 pose의 `legacy-euler` 증분으로 입력을 별도 재생했다.

| Route | 재생 `gy` 최대차, rad | 재생 `ds` 최대차, m | 생성된 실제 gyro bias |
| --- | ---: | ---: | ---: |
| R2 | 0 | 1.39×10⁻¹⁷ | 0 rad/s |
| R4 | 0 | 0 | 0 rad/s |
| R5 | 0 | 0 | 0 rad/s |

R2는 원본 `_controls`에서 별도 archived-controls 분기를 사용한다. 따라서 소스 recipe만 보고 R2까지 추정하지 않았다. 위 수치는 현재 R2 배열까지 수치 재생해 확인한 것이다. gyro scale factor도 이 recipe에서 0이다. `gy−Δyaw_true`는 seed 10 gyro RNG 잡음과 최대 `6.90×10⁻¹⁸ rad` 이내로 일치한다.

세 route에서 `(gy−Δyaw_true)/sqrt(dt)`의 공통 시퀀스 앞부분을 비교하면 다음과 같다.

| 쌍 | 공통 구간 수 | 최대 절대차 | 상관 |
| --- | ---: | ---: | ---: |
| R2–R4 | 741 | 1.552×10⁻¹⁷ | 1.000000 |
| R2–R5 | 978 | 1.552×10⁻¹⁷ | 1.000000 |
| R4–R5 | 741 | 1.552×10⁻¹⁷ | 1.000000 |

초기 pose 오차도 같은 RNG를 사용한다. 세 route의 초기 오차는 `(0.03098495 m, −0.04192450 m, −0.04116915 rad)`로 같다. **route-heldout은 경로 분할이며, 독립 센서 잡음 또는 독립 초기오차 분할이 아니다.** 이 사실은 route-based threshold의 계산상 누출 여부와 구분해야 한다. heldout truth를 학습 코드에 직접 넣지 않았더라도 공통 random realization 때문에 새로운 seed에 대한 일반화는 검증되지 않는다.

## 3. 잘못된 운동기준의 구체적 경로: RF가 수정한 bias 추정치

현재 원본 transition은 bias 상태를 그대로 유지하고 `Q_input[2,2]=0`을 사용한다. 실제 B trace를 검사하면:

\[
\hat b_k^- = \hat b_{k-1}^+,
\qquad
\hat b_k^+ - \hat b_k^- = K_{b,r,k}\nu_{r,k}+K_{b,s,k}\nu_{s,k}.
\]

첫 번째 식의 최대 오차는 0, 두 번째는 `1.97×10⁻¹⁹ rad/s` 이하이다. 따라서 현재 B0의 nonzero bias 추정치는 별도의 gyro bias 관측이 아니라 **RF innovation이 교차공분산을 통해 bias 상태를 갱신한 결과**이다.

| Route | B prior bias 최소–최대, deg/s | 5초 zero-bias 상대 heading 오차 p99 | 5초 B prior-bias 고정 오차 p99 |
| --- | ---: | ---: | ---: |
| R2 | −0.03463…0.09842 | 0.10440° | 0.49779° |
| R4 | −0.06929…0.13105 | 0.10839° | 0.62636° |
| R5 | −0.02017…0.04456 | 0.10077° | 0.26268° |

P2 두 실험은 시작 pose를 동일한 truth pose로 고정하고 bias만 다르게 준다. 모든 2/5/10초 창에서 아래 식이 최대 `8.89×10⁻¹⁵ rad` 오차로 성립한다.

\[
e_{\psi,\,\text{frozen B bias}}(W)
-e_{\psi,\,\text{zero bias}}(W)
=-\hat b_a^- W \quad\text{(각도 wrap 포함)}.
\]

즉 이 대조시험의 추가 heading 오차는 **anchor에서 물려받은 bias 추정치를 지속시간만큼 적분한 항**으로 끝까지 설명된다. 이 값을 독립적인 운동 truth처럼 강하게 강제하면 이전 RF 갱신의 영향을 다시 강화하게 된다. 설계의 bias nuisance 자유도와 잘못된 기준 stress test가 필요한 직접적 이유다.

다만 `RF innovation → bias estimate`라는 계산 경로는 확인했어도, 그 innovation의 모든 원인을 다중경로 하나로 귀속한 것은 아니다. RF 관측오차, 기존 평균 보정, 모델 불일치, 초기 상태오차, 잡음이 함께 작용할 수 있다. range/s별 누적 `K_bν`는 같은 실행의 대수적 기여도이며, 한 채널을 바꿨을 때의 폐루프 인과효과와 다르다.

## 4. P2 XY 오차에는 적분 규약 차이도 포함된다

현재 truth trajectory는 `motion_increments(..., convention='legacy-euler')`의 비홀로노믹 검사를 통과한다. 반면 같은 pose에 `convention='se2'`를 적용하면 세 route 모두 `path does not follow constant-curvature nonholonomic intervals`로 실패한다. 원본 `core.transition`은 SE(2) 구간 적분을 사용한다.

센서 잡음을 모두 제거한 truth 증분과 truth 시작 pose를 원본 SE(2) transition에 넣어도, 5초 창 XY 오차 p99는 R2/R4/R5 각각 약 **2.693 / 2.691 / 2.693 mm**이다. 이는 새로운 guard 구현 오류가 아니라 기존 trajectory 생성과 필터 적분 규약의 차이다. 기준선 재현을 위해 원본 transition을 유지하는 것은 타당하지만, P2 XY 오차를 순수 wheel 센서 오차로 설명해서는 안 된다. 이 차이는 위 heading의 `−bW` 항을 설명하지 않는다.

## 5. P2 코드 감사: 확인과 미검증을 구분

확인한 사항:

- `gy`를 각도로 사용하며 bias만 `dt`로 적분한다. `gy*dt` 이중 적분 오류가 없다.
- anchor `a`의 snapshot을 고정하고 `a+1,…,k`를 적분한다. 창 중간의 RF posterior로 bias를 교체하지 않는다.
- 현재 window 길이 2/5/10초는 모두 실제 0.2초 자료와 맞는다. 이 audit는 `max|dt−0.2|<1e−12`도 검사했다.
- P2가 읽은 B prior는 원본 R45 trace의 B prior와 최대 `1e−10` 미만으로 일치하고 원본 trace의 `t`, `pose_id`도 현재 입력과 같다. 보정 ZIP의 `SHA256.json`에 있는 B trace hash도 일치한다.
- `zero_bg`와 `frozen_anchor_bg`의 heading 차이를 독립 대수식으로 검증했다.

해석 또는 향후 검사에서 주의할 사항:

- true-anchor P2는 상대 운동오차를 분리하는 offline 검사다. 실제 오염된 위치·절대 heading anchor의 유효성을 입증하지 않는다.
- `window_abs_rotation_rad`는 `abs(wrap(yaw_end−yaw_start))`이다. 좌우 회전이 상쇄될 수 있으므로 **누적 회전량**이 아니다. motion strata에는 `sum(abs(Δyaw))` 등을 별도 저장해야 한다.
- 겹치는 window는 독립 표본이 아니다. 현재 quantile와 coverage는 기술 통계이며 보장된 확률 신뢰구간이 아니다.
- 현재 B0에는 실제 gyro bias·scale error·slip이 없다. 알려지지 않은 bias, 시간변동 bias, wheel slip, timing offset에 대한 보호성은 별도 stress test가 필요하다.
- P2 출력의 training-fold envelope는 구현 파라미터 후보일 뿐, heldout coverage만으로 활성 정책의 유용성이나 좋은 RF 보정 보존을 통과시킬 수 없다.

## 6. runtime 경계

online NPZ라는 이름에도 `clean_Hrf`, archived `prior/Pprior`, `trace_*`가 포함돼 있다. 모델의 런타임 입력은 필요한 키만 선택한 새 객체로 만들어야 한다. 허용 후보는 현재 noisy `Hrf` 또는 B에서 산출한 `[range,s]`, `t/pose_id`, `ds/gy/dt`, frozen `muMB/muBASE/R`, 시작 `x0/P0`이다. 이후 prior와 covariance는 해당 실행에서 직접 재귀 계산한다.

`clean_Hrf`, evaluator `clean_H/truth`, archived prior/posterior/trace는 평가 전용이다. packet 전체 전달 후 관례적으로 안 읽기를 기대하는 방식보다 key whitelist와 금지-key sentinel 검사가 필요하다. 원본 W0가 호출 인자상 요구하는 `D`는 그 arm에서 weight=1로 바로 반환하므로 새 guard의 feature로 사용할 근거가 없다.

## 근거 소스와 재현

- 원본 커밋: `c141839093d1a2e4a76f91eea632cb6467163e28`.
- [sensor_v2.py](https://github.com/myoungsunk/sionna-resimulation/blob/c141839093d1a2e4a76f91eea632cb6467163e28/research/FP_SC_RECOVERY_R0_R5_20261107/R45_sources/src/qclean_uwb/drivesim/sensor_v2.py): `CONDITIONS`, `motion_increments`, `generate`, gyro 및 wheel 출력.
- [e0_baseline.py](https://github.com/myoungsunk/sionna-resimulation/blob/c141839093d1a2e4a76f91eea632cb6467163e28/research/FP_SC_RECOVERY_R0_R5_20261107/R45_sources/src/qclean_uwb/fp_sc/e0_baseline.py): `_controls`와 원본 코드 해시.
- [online.py](https://github.com/myoungsunk/sionna-resimulation/blob/c141839093d1a2e4a76f91eea632cb6467163e28/research/FP_SC_RECOVERY_R0_R5_20261107/R45_sources/research/MBVAR_PRR_001_20261103/S1/online.py): `predict`, `replay`, `joseph`.
- [core.py](https://github.com/myoungsunk/sionna-resimulation/blob/c141839093d1a2e4a76f91eea632cb6467163e28/research/FP_SC_RECOVERY_R0_R5_20261107/R45_sources/research/EKF4_RANGE_S_STAGED_20261014/core.py): `transition`.
- 새 독립 감사 코드: `audit_controls.py`; 결과: `CONTROL_PROVENANCE_AUDIT.json`.
- 비교한 P2 코드: `precheck_motion.py`; 결과: `P2_MOTION.json`, `MOTION_WINDOWS.csv`.

감사 결과의 PASS는 **입력과 계산 경로를 확인했다는 뜻**이다. B-MCG 성능채택 통과를 뜻하지 않는다.
