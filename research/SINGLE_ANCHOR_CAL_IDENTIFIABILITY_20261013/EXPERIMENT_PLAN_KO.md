# 단일 앵커 Calibration 식별성 연구

목표는 gyro bias와 wheel asymmetry의 식별성과 실제 정밀도 한계를 조사하고, 정보 부족·추정기 근사·RF likelihood 오류를 분리하는 것이다. 현재 실행 범위는 I0뿐이다.

I0 입력·모델 계약 → I1 gauge/유효 FIM/비선형 모호성 → I2 Ideal Range posterior → I3 EKF/CKF/PF/batch 정합 → I4 실제 RF → I5 속도 개입 → I6 편파 s → I7 독립 확증 순서로 진행한다. 단계 종료 후 다음 단계는 별도 지시를 받는다.

S0 절대 pose prior 없음과 S1 외부 초기 pose prior 있음은 분리한다. I0 재현은 기존 S1만 다룬다. 기존 D6 UNRESOLVED와 V3/V4 개발 진단은 유지한다. 신규 L1–L7은 NOT_RUN이다.

I0 사전 고정 범위: I0_RUN_SPEC.json. 기존 개발 seed 8000, R2/R4/R5 × drift 0/1/2 × 기존 B0/GAUSS_LEVEL, 총 18 episode의 전체 시간축을 사용한다. 독립 통계 확증이 아닌 구현 재현 검사이다. 허용 오차는 실행 전에 고정하며 실패 후 완화하지 않는다.

향후 개발 12000–12031, 확증 13000–13299는 제안이다. 전역 seed 사용 이력과 namespace를 대조한 후 예약을 확정한다. I0에서는 두 집합 모두 생성하지 않는다. I7 셀·표본·효과 크기·coverage/정밀도/다중검정 기준은 개발 결과 이후 확증을 열기 전에 동결한다.

학습 scene/route에서만 RF 보정·R·시간상관 모델을 적합한다. 개발/확증 입력과 계수 산출 계보를 manifest로 분리한다. 같은 채널의 여러 thermal-noise seed를 독립 scene 표본으로 세지 않는다. 운용시간·거리·오차 예산이 미정이므로 실용 정밀도 수치는 UNRESOLVED_CONFIG이다.
