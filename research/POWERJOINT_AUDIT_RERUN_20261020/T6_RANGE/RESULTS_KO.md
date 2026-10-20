## 2026-10-20 사후 적용성 정정

**INVALID_DESIGN_ZERO_RANGE_JACOBIAN — SRC_TAP에 한정.** Range 행 Jacobian = 0으로 직접 Range 감도 제거, C_rs·gate 영향만 남음. Range 교정 근거로 사용 불가
SRC_TAP은 양자화된 정수 검출 tap으로 range를 예측하므로 tap 내부에서 range의 위치 Jacobian이 0이다. 이를 연속 EKF의 range 관측으로 사용하면 range의 직접 위치 관측 정보가 제거되고 range–s joint gain·gate·교차공분산 경로가 달라진다. 따라서 잔차 0과 안정 tap FD 0은 range 관측식 교정의 유효성 증거가 아니며, SRC_TAP 재귀 arm 및 그 파생 표·개입·변화량은 INVALID_DESIGN_ZERO_RANGE_JACOBIAN이다. B_OLD와 B_REFIT_ONLY에는 적용하지 않는다.

과거 '요청 9,519점 중 2,268점 미확보이므로 BLOCKED_INPUT'이라는 현재 판정은 철회한다. 7,251점 실행 기록과 원문은 보존하며, 서로 다른 모집단의 대응은 별도 S0 모집단 감사에서 판정한다. 이 정정은 새 모집단 수치나 대응 인증을 주장하지 않는다.

아래는 보존된 당시 보고 내용이다. 현재 해석은 이 사후 정정을 우선한다. 원래 숫자 CSV·DECISION·사전 등록 파라미터는 변경하지 않았고 원문 bytes/SHA는 후속 S0_CORRECTIONS/ORIGINALS와 VALIDITY_INDEX.json에 보존했다.

---

# T6 검출 tap 기반 Range 교정

7조건 Full/Native LoS × 4 bias × 3 관측식 × 2 arm = 336행 재귀 계산 완료. TECHNICAL_PASS_SEVEN_CONDITIONS. 요청 9,519점 중 확보된 Native LoS는 7,251점이며 2,268점 부족으로 전체 과학 판정은 BLOCKED_INPUT이다. 확보점 잔차 RMSE=0 m, tap 내부 FD 43,506개 최대차=0이다. tap 경계는 미분 불가능하며 이를 매끄러운 거리 Jacobian으로 대체하지 않았다.

| case | channel | Heading old → SRC (°) | XY old → SRC (m) |
|---|---|---|---|
| R2_aA_m0 | full | 1.798910 → 6.312572 | 0.149970 → 0.851978 |
| R2_aA_m0 | los | 2.108206 → 0.233403 | 0.269707 → 0.082667 |
| R2_aB_m0 | full | 1.515858 → 3.611139 | 0.074295 → 0.432002 |
| R2_aB_m0 | los | 1.457319 → 2.249369 | 0.138643 → 0.302858 |
| R2_aA_m45 | full | 0.982634 → 2.094378 | 0.087113 → 0.331305 |
| R2_aA_m45 | los | 1.356951 → 0.326645 | 0.145885 → 0.088873 |
| R4_aA_m0 | full | 0.658932 → 0.718638 | 0.104755 → 0.122348 |
| R4_aA_m0 | los | 0.610679 → 0.521599 | 0.123566 → 0.075500 |
| R4_aB_m0 | full | 1.508341 → 1.406850 | 0.093826 → 0.140592 |
| R4_aB_m0 | los | 0.563874 → 1.121732 | 0.091491 → 0.226610 |
| R5_aA_m0 | full | 4.556146 → 17.904643 | 0.477497 → 1.904567 |
| R5_aA_m0 | los | 1.940648 → 0.367154 | 0.211062 → 0.140217 |
| R5_aB_m0 | full | 1.056234 → 0.933174 | 0.085002 → 0.147907 |
| R5_aB_m0 | los | 1.448022 → 0.667407 | 0.135283 → 0.095751 |

모든 지표는 RANGE_REPLAY.csv, 변화는 RANGE_COMPARISON.csv에 있다. B_REFIT_ONLY 대조를 보존했다. 독립 scorer 및 원 POWER 상태/gate 검사는 REPLAY_CHECKS.csv에 기록했다. T3·T4 SRC 후속 표는 별도 버전으로 보존한다. 실행 39359601219의 Range 단계는 성공했고 뒤따른 T3 단계의 입력 schema 오류가 job 전체 실패를 만들었다. 성공한 Range 계산을 재실행하지 않았다.

## 주장하지 않는 것

부족한 2,268점 검증, 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다.
