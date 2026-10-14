# P4 동결 RF 단일 갱신 — 실험/코드 감사 사전등록

**질문:** 실제 동결 RF H/LoS·LUT의 원시 `[range,s]` 관측에서 **동일한 4-state DR prior와 동일한 원 R0 covariance**를 사용할 때 공동 1차 EKF/고정 linear 순차/Range-first 재선형 MAP가 어떻게 다른가? 또한 gyro bias covariance가 pose–bias 교차항을 유지하는가?

원 P0 39 assets, 7 case 및 frozen observer/LUT/source, R0 `Rs=.0081, Rr=.0068578637 m2, Rsr=0`, Range offset `-0.5315983906250129m`는 변경하지 않음. 태그 높이·mount·anchor는 frozen case. 원 truth legacy Euler 대비 SE2 predictor mismatch를 유지.

**이번 제한된 단계:** R2_aA_m0/seed0의 LoS·Full 각각 t>=30초 일정한 간격에서 대표 표본 12개, one-step. 4-state 원호 DR prior 생성 시 true bias/정답은 절대 필터에 주입하지 않음. R0 원 99% joint NIS gate를 모든 arm에 똑같이 적용하여 gate 효과를 분리. 원본 one-step EKF3 자료와 방법 변경을 과도하게 비교하지 않음. 상태 [x,y,psi,bg], bh prior mean0 SD0.1deg/s, q_b=0는 모델 가정이며 검증된 현실 캘리브레이션이 아님.

**감사:** GitHub cloud code execution 전에 source SHA/manifest/원본 observer/LUT 도구/충돌 가능한 truth 사용·이중 RF/각도/4state Jacobian/공분산을 검사. P3 자료 적격성 검사가 실패하면 P4 RF 실행을 허용하지 않는다. 본 자료 적격성 감사가 독립 scientific PASS는 아님.

**검증:** 동일 joint/affine sequential 결과는 같은 frozen Jacobian에서 부동소수점 수준으로 동등해야 함. Range-first nonlinearity는 개선 또는 악화 가능하고, Map solver 무수렴은 해당 one-step만 INVALID, 의도치 않은 정보 재사용은 HARD BLOCK. 모두 동일 가우시안 likelihood, gate accepted mask, 동일 truth-only scoring. 각 방법의 관측 한 번만 사용. 불확실도 coverage는 12 샘플에서 일반화하지 않음.

**후속:** P5에 다봉 위치 적분 G3 기준 미수렴 TV0.387>0.001이 저장돼 있으므로 'posterior reference validated'라고 주장하지 않는다. P4 local one-step 출력은 P5가 없어도 해석 가능하나 P6 전체 재귀 주장 근거로 자동 승격하지 않음. 과학적 가설 예상과 다르면 원인을 분해하고 다음 변경은 별도 감사한다.
