# C1/C2 입력 및 실행 계획

상태 PREPARATION_ONLY. 추가 RT 0회. SM2a는 동일 XY의 합성 yaw 반증 자료이며 원래 궤적의 EKF 시간열에 삽입하지 않는다. C1/C2의 실제 RT 입력은 원래 R2/R4/R5 Full/LoS와 SM0-B/SM1a의 pose·time 조인이다.

입력 잠금은 INPUT_SHA.json에 기록했다. Git 소스 SHA는 실제 blob 바이트 SHA256이다. RF archive SHA는 기존 영구 원본의 SHA다. 다음 실행에서 REFLECT_ROOT의 E1 CONTROL B0 trace, 전체 Full/LoS 패킷, 실제 모델 파일 및 noise realization을 확보해 파일 SHA와 배열 키를 추가해야 한다. 현재 해당 실행 입력들의 실물 SHA, prior replay parity, noise seed별 일치 검증은 미완료다. 계획 상태는 BLOCKED_INPUT_FREEZE이며 구현 실행 PASS를 뜻하지 않는다.

필수 조인 키는 source run SHA, route, anchor B, pose_id, 원본 Tnone index와 t, GT x/y/yaw, RF Full/LoS SHA, mask, noise seed이다. raw 거리에서 보정 거리로 가는 offset과 noise 가산 위치도 확인한다. GT는 평가와 명시한 oracle 관측 교체에만 사용한다. 28개 부분 구간만으로 recurrent filter를 초기화하지 않는다.

C1은 기존 ctl_core의 load/run 및 원래 predict와 Joseph 갱신을 재사용한다. 지정 시각의 같은 prior x/P, h/H, K, R, mu와 mask를 복제해 (rF,sF), (rL,sF), (rF,sL), (rL,sL) 네 arm을 한 번 갱신한다. delta x=K delta z와 Joseph P 동일성을 검사하고 r/s 기여와 결합효과를 보존한다. yaw 상태 차이는 wrap 규칙을 적용한다. gate 재계산은 별도 정책으로 표시한다.

C2는 네 arm을 전체 원래 궤적의 동일 초기 상태·P·controls/odom·Q·noise seed로 재귀 실행한다. 첫 lane은 고정된 BASE gate mask, 두 번째 lane은 각 arm의 self gate다. 각 arm은 자신의 prior/H/K를 사용한다. mu_B/MB와 상태 의존 R의 배경은 원래 실험 계약에서 하나를 지정하여 잠그고, 비교 중 바꾸지 않는다. 기존 ctl_core SEEDS=0..9는 후보이며 이를 실행 범위로 자동 채택하지 않는다.

실행 전 수치 검증 제안은 float64 prior/posterior·KΔz·Joseph P 비교 atol=1e−10, rtol=1e−8, mask/index exact, 유한성 전수 검사다. 음의 공분산 고유값은 −1e−10 미만이면 STOP, 대칭오차는 max abs 1e−10 초과면 STOP이다. 입력 SHA 불일치, 중복/누락 조인, baseline trace mismatch는 즉시 중단한다. 이 기준은 아직 실제 baseline 검증을 통과하지 않은 제안이며 실행 전에 고정해야 한다.

과신 평가는 각 step의 innovation, S, NIS, heading Hψ(rad⁻¹), K, prior/posterior x와 4×4 P, wrapped GT 오차, NEES4, XY95, Heading95를 저장한다. χ² 95% 기준은 4차원 9.487729, XY 5.991465, heading 3.841459이며 원래 joint gate는 ctl_core/PB의 기존 값을 그대로 쓴다. coverage는 전체·고정 mask·실제 accepted mask에서 분모를 따로 기록한다. 시간 표본을 독립 시행으로 간주한 신뢰구간은 만들지 않는다. 첫 accepted 오염과 회복은 원래 임계값 정의를 확보한 후 집계한다. 임계값이 없으면 연속 오차·coverage·공분산 궤적만 보고한다.

실행 순서는 입력·모델·trace·noise SHA 완결 → baseline x/P/mask replay → C1 한 step 대수 검사 → C1 전체 고정 표본 → C2 fixed gate → C2 self gate → paired error/coverage 보고다. RF gate, EKF 재현, 오염의 갱신 영향, 재귀 성능과 과신 판정은 각 근거를 기록한다. RT 비용은 0이며 EKF wall-time 예산은 baseline 오프라인 시간 측정 후 고정한다. 산출물은 JOIN_LEDGER, INPUT_SHA, BASELINE_PARITY, C1_UPDATES, C2_STEP_TRACE, COVERAGE, FAILED_KEYS와 보고서다.
