# T8 시간 바인딩 인증

| case | 재귀 입력 인증 | 정적 pose 쌍 |
|---|---|---|
| R4_aA_m0 | BLOCKED_INPUT | 0 |
| R4_aB_m0 | BLOCKED_INPUT | 0 |
| R5_aA_m0 | BLOCKED_INPUT | 0 |
| R5_aB_m0 | BLOCKED_INPUT | 0 |

재귀 EKF는 실행하지 않았다. 실패 행과 정적 pose의 시간·다중 후보 수를 보존했다. 정적 RF 관측 비교는 필터의 one-step 상태 갱신이나 Heading 평가가 아니다.

## 주장하지 않는 것

정적 비교로 시간 바인딩·Heading 개선, 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다.
