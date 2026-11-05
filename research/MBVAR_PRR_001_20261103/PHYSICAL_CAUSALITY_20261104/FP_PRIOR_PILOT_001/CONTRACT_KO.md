# FP-PRIOR-PILOT-001 — 사전 예측에 따른 CIR first-path 재선택 (탐색적 오프라인 시험)

상태: PROTOTYPE/EXPLORATORY. 원본 RF 재생성과 실시간 EKF 정책 승인 없음. 결과가 나오기 전에 조건·정책을 고정했으며, 사후 튜닝은 별도 실행/새 정책으로 표기한다.

## 핵심 가설

기존 검출기의 30% peak leading edge가 1~5 tap 늦게 선택하는 경우가 있다. 원래 Full MB_VAR 필터의 현재 시점 측정 이전 prior에서 산출한 **검출기 정의의 예측 거리**와 원래 Full CIR의 약한 leading edge를 함께 활용하면 잘못 선택한 tap을 일부 줄일 수 있을까? 그리고 그 결과가 signed Dual-LP 편파비와 ranging 오차를 동시에 줄일까?

- **중요한 차이:** range 자체가 평균적으로 정확한지와 first-path 선택의 드문 2/4tap 급변이 존재하는지는 별도 질문. 전체 오차 분포, 꼬리, false correction을 같이 보고한다.
- RX 속도 0.2m/s × 5Hz → 동작상 프레임당 약 0.04m. 이는 기하학적 거리의 가능한 변화 상한에 가까운 운동학 근거이며, **한 번의 CIR tap 간격이 0.14955m**라고 해서 반드시 매 tick tap이 바뀌면 안 되는 것은 아니다.
- 실제 full RF의 범위와 LoS는 별도 평가 참조이고, 이 LoS는 selector 안으로 들어가지 않는다. 원래 학습 mean/R를 갱신하거나, 사후 라벨로 threshold를 조정하지 않는다.

## 정확한 평가 모수

- R2, R4, R5 Anchor B, mount0, B0, **공개 seed10의 동결된 C1a premeasurement Full prior**. 각 979/742/1415 = 합계3136 pose.
- 원래 BLOCK_C Full/LoS 복소 H (노이즈가 첨가되지 않은 고정 RF), Hann(257)-IFFT(1028), strong RX peak의 30% leading edge를 기존 baseline으로 재구현.
- C1a cells의 h_r(x_minus), H_r(x_minus), Pprior 사용. 현재 packet z, GT, LoS tap, 미래 데이터는 selector에서 접근 불가.
- sigma_pred^2=H_r Pprior H_r^T+(0.20 m)^2. 20cm 바닥은 **사전 고정된 탐색 파라미터**, 검증된 교정 분산 추정이 아니다.
- 프레임마다 raw index, selected index, LoS oracle eval-only index, raw/selected distance and signed s errors, previous measurement age, hold status를 기록. 현재 구현은 이전 detector tap의 tracking 대신 모델 prior를 사용한다. 사용자의 4cm motion constraint는 추후 continuity-arm에서 직접 비교하는 연구 과제이다.

## 정책 (코드와 같이 동결)

1. 기존 30% strong-RX first tap에서 시작.
2. prior sigma가 0.75m 넘거나 값이 유효하지 않으면 그대로 사용/보류.
3. 기존 거리와 모델의 predicted detector-range 차이가 max(1tap,sigma) 이내면 기존 값 유지.
4. 그 외에는 기존 raw tap ±5 범위 및 predicted r ±2sigma의 교집합에서 strong RX amplitude ≥ 0.10×peak인 tap을 후보로 추출.
5. 각 후보 score = ((tap distance−predicted r)/sigma)^2 − 0.7 log(amplitude/peak). raw candidate보다 score가 최소0.8 좋아져야 교체. 지원되는 후보가 없으면 원래 tap을 유지하고 hold 기록.
6. 교체한 **동일 tap**에서 r과 s를 함께 계산. 그러나 단계 실험에서는 EKF 갱신을 다시 실행하지 않으며 mean/R를 원래 값 그대로 적용하여 성능 개선이라고 주장하지 않는다.

## 대조 및 중단

- 원래 raw tap vs 새 selected tap vs noise-free direct-only LoS reference tap. reference는 평가 전용 oracle.
- raw→correct, correct→wrong, closer/farther, path-specific detector range error and polarization signed ratio absolute error (mean, median, p90/95/99/max), changed subset.
- 두 관측은 같은 CIR에서 유래하므로 r/s 독립성, 이상적인 \(\chi^2\) calibration 또는 알고리즘 성능을 주장하지 않는다.
- 숫자가 좋은 경로만 골라 발표하지 않고 R2/R4/R5 전부 보고한다. score는 섞인 same-RF 공개 자료이고 독립 environmental test가 아니다.
- posterior 과신/장기 Heading/XY 및 5Hz 실시간 적용은 본 실험에서 **평가하지 않는다**.
- GH Actions native Sionna solver 실행이나 연구 DB 수정 없이 기존 Git LFS RF와 C1a frozen prior를 읽는다.
- test_pilot.py의 synthetic 음성 대조가 실패, baseline CIR 정의 불일치, 원본 pose_id 결측, H axes mismatch, 원시 원본 파일 미수신, nonfinite => FAIL-CLOSED, 산출물을 PASS로 게시하지 않는다.

이후 성능이 유의미하면: signed ratio selector selection-bias 및 r/s joint R 재적합, noisy CFR 시뮬레이션, 이전 raw detector+kinematic continuity arm, 데이터 내 PR-based prior overconfidence negative control, frozen-prior one-step EKF, 완전 t=0 closed-loop EKF, route-heldout/new RF independent science audit가 필요하다.

참고 원본: C3/G4_001/G4_PHYSICAL_FINDINGS_KO.md, NEW_RT_DATA/SM0/diagnostics.py, C1/C1A_001/RESULTS_001/cells, BLOCK_C/FULL_RF.
