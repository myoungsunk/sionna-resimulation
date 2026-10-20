# S1 N1 이벤트 검증 결과

**TECHNICAL_PASS_CORE / NOT_ESTABLISHED**. B0가 주 판정이며 L2는 보조다. 모든 이벤트 개입은 `ORACLE_DIAGNOSTIC`이다.

개정 격자로 후보110개를 열거해79개(기존35/신규44)를 고정했다. 종료 후30초가 부족한31개는 원래 후보와 제외 사유를 보존했다. 신규 물리61개는 RF 행 범위·개수·시각61/61 일치했다. 원래30+47개 source의 상태는 BLOCKED_SOURCE_UNAVAILABLE이며 이79개가 원래77개라고 주장하지 않는다.

| 범위 | 유해 D2 회수≥50% | 유익 D2 악화≤skip의50% | 중립 | 과학 판정 |
|---|---:|---:|---:|---|
| overall | 12/18 | 9/48 | 13 | NOT_ESTABLISHED |
| corridor | 10/15 | 7/42 | 12 | NOT_ESTABLISHED |
| office | 2/3 | 2/6 | 1 | NOT_ESTABLISHED |

전체 유해 이벤트의 D2 회수 비율12/18은2/3 기준을 충족하지만, 유익 이벤트의 안전성9/48은2/3 기준에 못 미쳤다. 따라서 N1 지지 조건을 충족하지 못한다. 이전 skip 수치는 알려진12개에만 참고열로 보존했으며 현 POST30 label이나 분모를 정하는 데 사용하지 않았다.

각 비율은 조건 수를 독립 표본 수로 해석하지 않는다. corridor는 R2/R4/R5/C01–C03의 같은 장면이며 office는 O02/O03의 한 장면이다. O01은 포함 가능한30초 horizon 이벤트가0개다. p-value는 계산·보고하지 않는다.

## 검증과 오류 보존

정본30개 case×bias에서 과거 POWER1 gate 불일치0, Heading 차이 최대1.3311574065255629e-13°. 현 실행 모든 유효 개입의11개 지표를 독립 scalar/Cholesky scorer로 재계산한 최대차는7.1054273576010019e-13이다. no-change joint adapter의 state/cov 최대차는0/0이다. pinned engine과 T4 helper는 원본 bytes를 유지했다.

첫 run39370673576의 R2/R5에서 CSV 기본 float parser 때문에 원본 시각과 약1e-14s 차이가 발생했다. 오류10건과 첫 실행 CSV·JSON은 FAILED_EXECUTION_R01/에 보존했고, NPZ를 포함한 원본 전체는 각 release archive에 보존했다. V2 lock3062701은 round_trip parser만 적용하며 입력/이벤트 행/과학 임계값을 바꾸지 않았다. 재실행39370942876의 R2/R5와 첫 실행의 나머지6개 성공 결과를 정본으로 묶었다.

## D7 적용 범위

D7 평가 불가80개 event×bias 행을 삭제하지 않았다. 기존 주로 실제los_exists 미인증은 NOT_EVALUABLE_LOS_STATUS_UNCERTIFIED, 실제 차단이 포함된 신규 이벤트는 NOT_EVALUABLE_LOS_BLOCKED로 남겼다. 신규 평가 가능한 행만 same-pose 실제 Native LoS s와mu_s=0을 적용하고 rawFull range·mu_r·C와 원래 joint gate를 유지했다.

| 범위 | D7 평가 가능한 유해 이벤트 | D7·D2 모두 회수≥50% | D7<20%, D2≥50% 패턴 |
|---|---:|---:|---:|
| overall | 9 | 7 | 0 |
| corridor | 8 | 6 | 0 |
| office | 1 | 1 | 0 |

마지막 열은 이 D7/D2 비교에서만 나타난 제한된 패턴이며 필터 구조 변경의 인과적 필요성이나 모든 관측 교정의 불가능성을 뜻하지 않는다.

## Full-only 특징

기존 T7A SPEC12 중 개정 포함 명단과 RF 행·시각이 정확히 맞는 이벤트는12/12이다. ONLINE_FEATURE_MAPPING.csv에서 누락/불일치를 표시했다. 온라인 특징 정의를 확대하지 않았다. r_D2와의 Spearman은 그중 B0 유해 이벤트에 한정되며 특징별 분모를 ONLINE_FEATURE_SPEARMAN.csv에 기록했다.

## 산출물·정본

EVENT_TABLE.csv와 EVENT_TABLE_L2.csv는 각각79개 고정 행이다. INTERVENTIONS.csv는790개 event×bias×arm의 POST30 지표·평가 불가 상태를 포함한다. 실행별 PACKET_LOG, FIRST_HARMFUL_UPDATE, DIVERGENCE, GROWTH와 원본 manifest는 execution/에 보존한다. MANIFEST.json에 run·artifact·archive SHA256·expiry와 엔진/센서 hash를 기록했다. 대용량NPZ는 원래 Actions artifact와 audit-traces-20261020-r01 release mirror에 보존했다. 각 원본 전체 SHA/CRC와 release 전체 readback을 확인했다. Windows 직접 전송 취소와 부분 파일 보존은 LOCAL_RECOVERY_TRANSPORT.json에 기록했다.

엔진 `034e57a7209a3bd1bb8857b24fd85c64942e1258`, SHA256 `e725f92bd74e6a845b07418d6f3b7a2974a518b2cd03b16969518bf879ee11b8`. 센서 lock SHA256 `b05e7ead6cf658d20a4830094cec56332ffcc839e7dccf04fd4ce3a1f86ccef0`. B_OLD=−0.5315983906250129m이며 SRC_TAP은 사용하지 않았다.

## 주장하지 않는 것

독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증, 온라인 정책의 성능, D7 패턴의 인과적 필요성, 원래77개 명단 복원을 주장하지 않는다. S0의 OPEN/NOT_ESTABLISHED 잔차 판정은 유지한다. S2/S3, 새 gate·기억 모델, RF 시뮬레이션, T6 tap EKF 및 D4 대체는 실행하지 않았다. S1 결과에서 멈춘다.
