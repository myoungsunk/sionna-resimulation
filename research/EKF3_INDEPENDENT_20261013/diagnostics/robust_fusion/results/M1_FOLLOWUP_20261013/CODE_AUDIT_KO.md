# 실행 전 독립 코드 감사

판정: ACCEPT. 감사자 `/root/ablation_audit`, read-only. 이번 감사 자체는 실험 실행이 아니며 실행 결과는 별도 receipt에 기록한다.

- 합성 초기 truth는 N(x0,P0), 운동은 동결 입력잡음 공분산과 SE(2). M0/M1-A는 동일 데이터 공유.
- 고정 true bias의 포함률을 unconditional calibration으로 주장하지 않고 D0의 Bias 수렴을 요구하지 않는다.
- RF 여섯 비교군은 평균·분산·Huber·gate를 독립 변경. Huber-only의 NIS는 동일 prior/R0로 먼저 계산하고 통과 관측만 공동 block-Huber로 처리.
- 기존 학습 모델, 참조 SHA 및 절대 허용치 1e-8 parity, E1 해석 제한 유지.
- 수치 미분 F/G/H, Gain/Joseph, 거부 시 상태 불변, 무잡음 Bias0 불변성, D0 비수렴 테스트 확인.

필수 수정 없음. 실제 83개 테스트 및 smoke/full 성공 여부는 실행 로그·TEST_RECEIPT·실험 manifest로 별도 확인한다.
