# 실행 전 독립 코드 감사

판정: ACCEPT. 감사자: ablation_audit (read-only).

- M0와 RF_HUBER_ONLY는 기존 보정 함수를 재사용하며 3-state, R0, Huber 1.345, 보정 전 NIS gate, 원본 FP/Range를 유지한다.
- gyro_bias의 백색 Wheel/Gyro 잡음 비활성화, bias 크기 0.01/0.05/0.20 deg/s 및 seed 부호가 정확히 명시되었다.
- 기존 결과 SHA, 양 모델 noise_pair parity 및 수용/거부 횟수, 독립 D5 smoke 12셀과 D0 매 시점 상태/공분산 일치를 검사한다.
- 단일 scene, E1, 작은 seed 수의 주장 경계를 유지한다.
- 필수 수정 없음. 실제 실행 증거는 이 사전 감사 범위 밖이며 smoke와 noise_pair 전체 재현 후 gyro 전체 실행하는 순서를 요구한다.

근거: huber_gyro.py, test_huber_gyro.py, 동결 sensor_v2.py 및 sensors.py. 최종 결과 감사는 별도 기록한다.
