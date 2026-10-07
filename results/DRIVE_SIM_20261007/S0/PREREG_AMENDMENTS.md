# PREREG 수정 기록 (S0)

원본 `PREREG.json`(커밋 `02009ca`)은 수정하지 않는다. 변경은 이 파일에만 추가한다.

## A1 — G1은 production 설정(`--threads 1`)에서 판정한다 (명확화, 완화 아님)

- 원 문구: G1 "H 상대 오차 ≤ 1e-6". thread 수는 명시하지 않았다.
- 관측(`REFERENCE_CHECK.json`, 같은 position x7.0_y0.0, yaw 0/50°):
  - `--threads 1`: 저장 H와 **오차 0.0**(비트 동일, 65 bin × 2 yaw).
  - `--threads 4`: pose별 상대 오차 3.2e-6, bin별 최대 1.2e-5 → **원 임계값 1e-6 미달(FAIL)**. 원인 추정: 병렬 reduction 순서(float32 비결합성).
- 조치: production A안은 기존 scan 방식대로 단일 thread 프로세스 4개 병렬(`corridor_scan2_run.sh`)이므로 G1은 `--threads 1`에서 판정한다. 임계값 1e-6은 그대로 두고, `--threads 4`는 production에서 쓰지 않으며 FAIL 결과를 그대로 기록한다.

## A2 — S1 설계 결정 (RF/필터 결과를 보기 전에 확정)

원 PREREG에서 모호했던 부분을 구현 전에 고정한다. 모두 `assumption`.

1. **Probe 주기 T는 "주행 시간(drive time)" 기준.** probe 시간(7.2 s)은 주행 시간에 포함하지 않는다. 따라서 위치·주행 heading은 T와 무관하고, T∈{10,20,60}의 probe 위치는 T=10의 부분집합이다 → RF 계산 집합은 T=10 기준 상위집합 하나로 충분하다.
2. **Truth는 kinematic으로 일관.** 위치는 heading을 따라 적분한 unicycle 경로다(`p_{g+1}=p_g+0.04·(cosψ_g, sinψ_g)`). heading 흔들림 때문에 y가 y₀에서 ±수 cm 벗어난다. (직선 경로 + heading 흔들림은 odom 모델과 모순이므로 쓰지 않는다.)
3. **Heading 흔들림은 주행 시간의 함수**: `w(τ)=A·sin(2πτ/T_w+φ)`, A=4°, T_w=12 s, φ는 고정 seed(20261007)에서 한 번 뽑는다(truth는 Monte Carlo seed와 무관). 제자리 회전(probe, 끝 지점 180° 회전) 동안은 흔들림을 고정(hold)한다.
4. **경로 길이**: x₀=1.2 m, 편도 440 step(17.6 m), step 0.04 m. 흔들림에 의한 x 이동 감소와 허용영역 [1,19] 경계 여유(약 0.2 m)를 확보하기 위해 18 m 대신 17.6 m로 한다.
5. **끝 지점 180° 회전**: 25°/s(probe와 동일), 5 Hz 표본당 5° → 36 표본, `turn_phase` flag.
6. **Probe 표본열(36 표본 = 7.2 s)**: 현재 heading 기준 상대 yaw `[−5…−45](9) + [−40…+45](18) + [+40…0](9)`. 한 probe에서 서로 다른 yaw는 19개(−45…+45, 5° 간격).
7. **y₀∈{0, 0.35}**: y₀는 적분의 초기값. 안테나 world yaw = 몸체 yaw + 장착 offset. Lever arm 0이므로 안테나 위치 = 몸체 위치.
