# 20 — 기존 Frozen LoS LUT 수직 입사 극점·Jacobian 수치검증

일자 2026-10-11 | 실행: [Actions 38114389117](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38114389117) SUCCESS. 코드 run_lut_pole_jacobian_audit.py. 입력 Frozen hs_lut_2deg.npy(2° sampling)와 7개 cases의 native matched LoS 계산결과 9,519개. 신규 Sionna RF raytracing 없음, 원 자료/필터 수정 없음.

## 1. 실제 원 RF에 대응시킨 이상 사례

앵커 수평 rho<.1m의 원 저장 9 pose 중 4개에 |s_nativeLoS-h_LUT|>.1:
- R5-B pose706 rho=.038388m, theta=.999649°, s_nativeLoS=-.946821, s_LUT=-.069205, eLUT=-.877616, multipath eMP=-.000078.
- R5-B pose707 rho=.045873m, native=-.949229, predicted=-.458738, eLUT=-.490490.
- R5-A pose856 rho=.072430m, eLUT=-.108520, eMP=+.000277.
- R5-B pose705 rho=.063688m, eLUT=-.108033, eMP=-.000123.
이를 제외한 rho>=.1m 원 pose 9510개 LUT error RMS=.009621, max abs=.04665.

이는 **native LoS만 있어도 발생하는 LUT 모델 오류**이며 전체 7케이스의 평균 eLUT가 작다는 통계와 모순되지 않는다.

## 2. 실제 LUT 원본에 수평 근접방향 8종을 대입한 근사 극점 검증

R5-A anchor에서 동일 body yaw 0°로 접근 방향 az=0,45,...,315°를 비교, 서로 거의 같은 수직 incidence로 접근해도 LUT 반환값 범위가:

| rho (m) | s predicted max-min (0..2 bound) | max XY Jacobian magnitude (/m) |
|---|---:|---:|
| 0 (코드의 exact pole) | 0 (atan2(0,0) 하나의 값) | 0 |
| .00001 | **1.95291** | **195,983** |
| .0001 | 1.95063 | 19,575 |
| .001 | 1.92781 | 1,935 |
| .01 | 1.69958 | 171.0 |
| .03 | 1.19246 | 41.82 |
| .05 | .68546 | 25.49 |
| .1 | .01357 | .0903 |
| .2 | .02732 | .0980 |

따라서 LUT는 theta≈0 보간 경계에서 경로 접근 방향에 대해 심각한 불연속/비물리적인 방위 의존성 또는 polar basis 취급 문제가 있다. 수직 입사 앵커의 중앙 좌표와 근접 양쪽을 단순히 theta/phi equirectangular LUT로 보간하면 값과 6상태 EKF Jacobian이 불안정할 수 있다. 일부 original pose의 analytic XY derivative는 finite difference와 잘 맞더라도 **잘못 보간된 값의 미분이 수학적으로 맞을 뿐 물리 모델이 맞음을 보장하지 않는다**.

중요한 근거 제한: 링 sweep은 Frozen LUT 출력만 검사한 것이므로 임의 8방향의 fresh native LoS channel이 아니다. 실제 9개 original native LoS는 대조됐지만 FFD 극점 보간이 왜 이렇게 되는지 물리적인 최종 원인 확정은 아직이다.

## 3. EKF 보호와 수정 순서

- 임시 instrument-safe gate 후보: anchor horizontal radius rho_est<.10m에서는 편파 s update 보류; 그 위치에서 measured range와 odom은 별도 품질 판단 후 계속 유지. 위치 prior가 불확실하다면 radial uncertainty sigma_rho를 포함해 rho_est-k*sigma_rho<.10m일 때 보수적으로 보류하는 arm도 비교한다. **이 수치는 기존 원자료에서 발견한 위험 영역 기준의 exploratory guard이지 운영 threshold 검증이 아님**.
- θ→0에서 원 RX/TX FFD의 **카르테시안 Jones field 및 실제 회전**을 사용해 polar basis 일관성과 yaw 주기성을 먼저 검증. theta=0의 물리 방위 정의를 잘 정하고, near-axis clean LoS value/jacobian parity를 확인한 뒤 pole-safe LUT/gradient를 다시 생성해야 한다.
- LUT 변경 후 기존 F01/L1 및 극점 이외 >.1m 전 구간의 수치회귀, 0/45 mount, 7/12case 동일 geometry consistency를 재검증. LUT 바뀌었으면 원래 7case FFD calibration SHA와 다른 모델이므로 새 버전으로 명시하고 blind test 필요.
- 반드시 비교: C_LOS all points vs pole-rho guard vs pole-safe field model, 동일 seed/route/mount/time, heading/posRMSE + NEES and coverage. **이 문서의 실행은 LUT/Jacobian 검증이며 guarded EKF 전체 재실행 결과는 포함하지 않는다.**

실행 artifact frozen-lut-polar-singularity-actual-data-20261011: actual near-LOS/J, ring sweep, radius summaries, status, report. Scientific_PASS=false 유지.
