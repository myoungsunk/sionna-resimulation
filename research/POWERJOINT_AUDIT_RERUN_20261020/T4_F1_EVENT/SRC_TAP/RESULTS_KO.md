# T4 F1 병합 결과

TECHNICAL: INCOMPLETE_OR_ERROR; 과학 판정: NOT_ESTABLISHED.

고정 5+5 이벤트를 대상으로 같은 개입의 전체 유익 이벤트 안전성을 요구했다. 세부 회수 비율·부호 변경은 DECISION.json, 모든 지표는 INTERVENTIONS.csv에 보존한다.

## 주장하지 않는 것

독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다. 모든 개입 비교는 ORACLE_DIAGNOSTIC이다.

T6 Source tap 재학습 버전. 10개 이벤트에서 모든 비D4 arm을 완료했고 D4 NONSPD 5건을 보존했다. B_OLD 판정과 섞지 않는다.

| 이벤트 | 역할 | 정본 skip 개선량 ° | 부호 변경 | 기준 충족 개입 |
|---|---|---|---|---|
| R5_A_M0_x10_16_V1 | harmful | 15.042645921591845 | False |  |
| C01_A_x16_21_V1 | harmful | 1.3862410590257153 | False |  |
| O03_y4_8_V1 | harmful | 1.2224214641011435 | False |  |
| C01_B_x16_21_V1 | harmful | 2.5897677561827326 | False |  |
| C02_A_x4_10_V1 | harmful | -0.19484800156560955 | True |  |
| R5_A_M0_x10_16_V2 | beneficial | 3.674158389069703 | True |  |
| C01_A_x10_16_V1 | beneficial | -5.308801935276251 | False |  |
| O03_y4_8_V2 | beneficial | 0.2865938078988064 | True |  |
| O02_y4_8_V1 | beneficial | -7.783617051282871 | False |  |
| R2_A_M45_x10_16_V1 | beneficial | -1.8088782799719985 | False |  |

SRC_TAP은 tap 내부 Range Jacobian이 0이므로 D2(s 제거)의 Range-only update가 상태를 바꾸지 않는다. D2=SKIP 회수율 1은 이 모델의 수학적 성질이며 관측 유형의 보편적 단일 원인 증거로 쓰지 않는다. 고정 역할 대비 부호가 바뀐 세 이벤트를 재분류하지 않았다.
