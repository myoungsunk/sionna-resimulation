# G1-MODEL-003 S1 실행 정의

[사양 §3](../SPEC_B_NEW_RT_KO.md#s1-관측-체인-g-t1만)을 적용한다. S0 및 G0–G9 증거가 연결된 S1 진입 기록을 실행 입력으로 사용한다. RT 입력은 G-T1 A/B/C만 연결한다.

- 지연 원점은 G-T1 P-A TEACH/REPEAT의 고유 RF pose에서 noise-free RT LoS와 명목 좌표의 FFD 합성 LoS를 비교한다. TX +45°와 같은 주파수축, mount 0, 정수 30% leading edge를 적용한다. FFD는 절대 전파 지연과 동결 주파수축을 적용한다. RT LoS의 tap을 맞추기 위해 실측 index를 이용한 사후 오프셋은 적용하지 않는다. 전체 index 일치율 ≥ 99%를 요구하고 anchor별 결과도 기록한다.
- 후보는 사양에 열거한 여섯 가지다. −0.5/−1 tap은 30% 정수 교점에서 지정량을 빼고 tap 0에서 하한을 둔다. sub-tap은 30% 진폭 문턱을 끼는 두 tap 사이를 선형 보간한다. 분수 tap에서 s를 읽을 때는 두 RX의 복소 CIR을 먼저 보간한다.
- G-T1의 원래 경로 P-A·P-A′·P-B·P-C에 속한 고유 RF pose의 full H를 쓴다. 각 anchor·pose에 20개 열잡음 실현을 사용한다. 난수는 `SeedSequence([20261115, anchor_index, draw_index])`로 시작하고 고정 64 pose 배치 순으로 생성한다. 같은 CIR에 여섯 후보를 모두 적용하고 SNR 20/30 dB에 같은 정규 난수와 각 SNR의 분산을 쓴다. 기존 10 m 자유공간 기준 SNR과 검출 문턱을 재사용한다.
- 범위 오차는 검출된 packet의 원시 range에서 해당 RF pose의 참 경사거리를 뺀 값이다. 각 SNR에 전체 packet 대비 미검출 비율, 검출분 bias·RMSE를 낸다. 두 SNR 각각 미검출 ≤ 1%를 만족해야 한다. 두 RMSE의 평균이 가장 낮은 후보를 채택한다. O30이 적격이며 차이가 1 cm 미만이면 O30을 채택한다. 후보 결과와 OR을 기록한 뒤 LoS parity를 시작한다.
- OR과 고정 대조 O30의 offset은 기존 FFD 거리 평균법(2–16 m, 0.01 m, 고정 무작위 방향 150개)에서 검출기만 교체해 재산출한다. 관측 range의 보정은 검출 거리에서 이 평균을 뺀다.
- LoS parity는 G4와 같은 참 거리에서 선택 체인으로 FFD 직접 계산과 RT LoS를 비교한다. 전체 p90 |Δs| ≤ 0.005를 요구하고 anchor별 결과도 기록한다. M1-R의 인과적 계산은 별도 함수에서 위치 prior 거리와 분산에 5점 Gauss–Hermite를 적용한다. 거리에 따른 변화를 보존하기 위해 해당 함수가 선택 체인의 직접 FFD 계산을 재사용한다.
