# DR-only EKF 통계적 불일치 원인 규명 — 진단 계획 (실행 전 동결)

대상: 단일 앵커 UWB 연구의 RF-off Sensor-v2 6-state EKF (`x=[x,y,ψ,b_g,SF_g,ε_w]`), 기준 커밋 `50583681`.
이 문서는 2026-10-13 사용자 제공 통합 진단 계획을 실행 전에 요약·동결한 것이다. D0~D5의 어떤 결과도 보기 전에 커밋한다.
D6(독립 확증)의 arm·판정 기준은 D1~D5 이후 별도 사전등록 문서(`D6_PREREG_KO.md`)로 **D6 실행 전에** 커밋한다.

## 원칙
- 동결 코드(`results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src`)는 수정하지 않는다. 기준 arm은 동결 `SensorV2Filter.step`을 그대로 호출하는 wrapper로만 실행한다.
- 목표는 NEES를 낮추는 것이 아니라 "필터가 계산한 불확실성 = 실제 오차"가 되도록 하는 데 무엇이 필요한지 근거로 결정하는 것이다. Q 확대·prior 축소로 수치만 통과시키는 것은 원인 해결로 인정하지 않는다.
- 진단 전용 개입(C 제거, 참값 Q, oracle calibration)은 최종 모델 후보가 아니며 그렇게 표기한다.
- 각 단계 상태: `NOT_RUN / PASS / FAIL / INCONCLUSIVE`, 입력·코드 SHA256을 manifest로 남긴다. R2-2 판정(`DR_MODEL_MISMATCH_UNRESOLVED`)과 사전등록 기준은 변경하지 않는다.

## 두 트랙
- Track A (가설 검증): A1 EKF 선형화, A2 calibration prior 분포 불일치, A3 IMU–wheel 측정 상관(C) 처리, A4 F/G/Q 근사(측정값 기반 Q, Jacobian), A5 calibration 상태 식별성, A6 gate·평가 규약·수치.
- Track B (데이터 기반 현상): B0 시점별 상태·공분산·혁신 복원, B1 시점별 ANEES·최초 지속 이탈, B2 실제 MSE 행렬 `M_k` vs EKF 평균 공분산 `P̄_k`(편향/분산 분리, 예측 직후 vs 갱신 직후), B3 heading 기여 `e_ψ²/P_ψψ` + heading 조건부 XY 기여(기대값 1, 2), longitudinal/lateral 분리, B4 오차분포 형상(산점도·타원, 왜도·첨도·다봉성, 부호별 분포).

## 실행 순서와 게이트
| 단계 | 내용 | 종료 조건 |
|---|---|---|
| D0 | 동결 B0 9셀(R2/R4/R5 × drift 0/1/2), seed 6000–6299 재현 | R2-2 집계 일치, 입력 해시 |
| D1 | 시점별 ANEES·coverage·최초 지속 이탈·주행 phase | 발생 구간·성장 패턴 |
| D2 | `M_k` vs `P̄_k`, heading/조건부 XY NEES, 백색화 고유방향 | 과신 상태·방향 |
| D3 | F/G/H finite difference, Q/R/C 경험적 검증, 1-step/구간 MC vs EKF 공분산 | 수식·코드 불일치 확인/배제 |
| D4 | prior 일치(A2-1/2/3), oracle calibration, odometry ON/OFF, C 제거(진단) | 초기분포·관측 갱신 영향 분리 |
| D5 | 동일 센서·생성 모델에서 EKF vs sigma-point(CKF) vs PF / 비선형 MC | 선형화 원인 직접 검증 |
| D6 | 새 seed 8100–8399, 사전 동결 arm | 원인 판정 재현 또는 미해결 기록 |

## Seed
| 구분 | Seed | 용도 |
|---|---|---|
| R2-2 기존 | 6000–6299 | D0 재현, D1/D2 현상 분석(가설 형성용 개발 데이터) |
| 개발·QA | 8000–8031 (32) | 9조건 × D4/D5 개입 스크리닝 (필요 시 6000–6299로 정밀화, 개발용으로 표기) |
| 독립 확증 | 8100–8399 (300) | D6 전용. D6 사전등록 커밋 전 사용 금지 |

같은 seed를 서로 다른 arm에 적용해 paired 비교한다. 경로가 달라도 같은 seed를 쓰므로 셀 간 독립 실현으로 세지 않는다.

## 일관성 판정 (R2-2와 동일, 변경 금지)
셀 일관 = t ≥ 30 s 시간평균 앙상블 ANEES ∈ [2.4, 3.6] 그리고 pose95 coverage ∈ [0.92, 0.98] 그리고 마지막 25 % 구간 ANEES ∈ [2.4, 3.6]. arm 일관 = 9셀 모두 일관.
보조 지표: 시점별 ANEES 밴드 χ²(3N)/N, heading 기여(기대 1)·조건부 XY 기여(기대 2), 예측 전후 공분산 정합, odometry innovation 통계, 오차 꼬리분포.

## 원인 판정 규칙
| 발견 | 해석 | 후속 |
|---|---|---|
| 단일 스텝부터 경험적 Q/C와 코드 불일치 | 잡음·관측 공분산 구현 문제 | F/G/Q/C 수정 후 전체 회귀 |
| 생성분포와 prior를 맞추면 일관성 회복 | 초기 불확실성 모델 문제 | prior·생성 가정 정정 |
| 단일 스텝 정상, 긴 주행에서 EKF만 악화 | 비선형 선형화 문제 유력 | UKF/CKF/PF 또는 EKF 유효 영역 제한 |
| odometry 갱신에서만 과신 급증 | 측정 상관·calibration update 문제 | C/K/gate·관측 모델 재검토 |
| 약한 calibration 방향과 과신 일치 | 식별성·사전 의존 문제 | 상태 축소·고정·재매개변수화 |
| 모든 추정기에서 불일치 유지 | 생성기·평가 규약·공통 모델 문제 | 범위 확대, 미해결 유지 |

D5에서 RMSE 개선만으로 선형화 해결로 판정하지 않는다. 경험적 공분산·ANEES·95 % coverage가 함께 개선돼야 한다.
종료 시 셋 중 하나를 명시한다: 원인 확인·수정 / EKF 사용 조건의 정량적 제한 / 원인 미해결. 그전에는 E1 range·편파 `s`의 NEES 변화에 전체 필터 일관성 개선의 의미를 부여하지 않는다.
