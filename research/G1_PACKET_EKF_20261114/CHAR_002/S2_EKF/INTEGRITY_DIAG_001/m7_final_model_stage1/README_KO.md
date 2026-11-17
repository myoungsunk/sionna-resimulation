# M7 Stage 1 — 실제 검증 결과

2026-11-16 사용자의 “검증 ㄱㄱ” 지시에 따라 수정 계획 `ff7955d3`을 실행했다. 현재 실행의 계약·입력·trace·점수는 **`attempt_02/`**에 있다. 아래의 이전 구현 단계 HOLD 기록은 현재 실행 상태를 뜻하지 않는다.

주 재생 1,440회와 동일 DR trace 참조 30개, 논리 cell 1,470개 및 점수 그룹 70개의 집계를 완료했다. mount 0°, 앵커 B, Full RF, R2/R4/R5, seed 10–29 범위다. B0와 Q가 일치하는 L2가 주 판정이며, 고정 gate와 Q 불일치 stress는 보고 전용이다.

**수치 판정: 모든 arm의 M7_PASS가 false다.** H3(GM-θ+KI)의 무결성·정확도 동시 통과는 B0 **12/20**, Q 일치 L2 **11/20**이며, 거울해 passage는 각각 **11건·10건**이다. 동시 통과 18/20 및 전 실행 거울해 0 기준을 충족하지 못했다. 기준을 완화하거나 추가 모수를 탐색하지 않았다. 20개 seed는 같은 RF 실현을 공유하므로 독립 환경 반복의 결과가 아니다.

- [검증 요약·궤적별 중앙값 표](attempt_02/brief/REPORT_KO.md)
- [궤적·arm·seed별 점수와 10 s 하한](attempt_02/assessment/BY_TRAJECTORY_SEED.csv)
- [I/A/J 통과 수와 seed 10–14 / 15–29 별도 표](attempt_02/assessment/COUNTS_SUBSETS.csv)
- [실패 항목](attempt_02/brief/FAILURE_REASONS.csv), [R2·R5 진단 창](attempt_02/brief/R2_R5_WINDOWS.csv), [창별 seed 분포](attempt_02/brief/R2_R5_WINDOW_DISTRIBUTIONS.csv)
- [조건·gate 짝 차이와 구간](attempt_02/paired_assessment/PAIRED_COMPARISONS.csv), [수용 mask·q 지원률·bias](attempt_02/paired_assessment/PAIRED_GATES_SUPPORT_BG.csv)
- [R5 통과별 진입 상태·명목 y 정보](attempt_02/passages_assessment/R5_PASSAGE_INFORMATION.csv)
- [입력 계약](attempt_02/input_generation/RUN_CONTRACT.json), [H5′ 적합 계약](attempt_02/h5prime/RUN_CONTRACT.json), [사전 검사 계약](attempt_02/precheck/RUN_CONTRACT.json)
- [본 재생 계약](attempt_02/replay/RUN_CONTRACT.json), [점수·짝비교 계약](attempt_02/scoring/RUN_CONTRACT.json)
- trace: `attempt_02/replay/cells/<condition>/<mode>/seedN/<route>/<arm>/trace.npz`. 고정 gate H0 30개는 receipt로 own trace를 참조한다.

실제 SourceFFD 사전 검사 9개와 별도 점수 재검산을 통과했다. 조건·gate 짝비교 20 seed(비교 50개), R5 통과 진단 70개 그룹도 완료했다. 주 실행·stress·주 점수 평가의 독립 검토는 ACCEPT이며, 보충 짝비교·통과 진단의 내용은 해당 독립 검토 범위에서 제외됐다. 재생 완료·수치 기준 판정·독립 검토·모델 채택은 구분한다. H5 실패만으로 b_θ의 필요성을 주장하지 않으며, H5′와 함께 해석한다.

최신 실행 증거 목록과 SHA-256은 `attempt_02/completion/`에 둔다. 이전 루트 SHA 목록과 `implementation_checks/`는 당시 구현 검사 증거이며 현재 실제 실행 전체의 목록으로 사용하지 않는다.

## 이전 구현 단계 기록

이하 내용은 실제 실행 전 구현·합성 검사 기록이다. 당시의 HOLD와 “미실행” 표기는 보존된 과거 상태다. 현재 실행 결과는 위 링크와 `attempt_02/`를 사용한다.

질문 ID는 `G1-INT-001/M7-STAGE1`이다. 계획 커밋 `ff7955d3212065649057a335720e11fb92fff234`와 SHA-256 `9bafa3640fe34d1185481a97b1898a38d8490f59f261904d0cd93f94e69e4053`을 기준으로 코드를 수정했다. 범위는 mount 0°, 앵커 B, Full RF, R2/R4/R5다.

**현재 상태: 구현 및 합성 검사. 실제 입력 생성·donor 적합·원본 trace parity·M7 실험 재생은 보류다.** 이 묶음에는 M7 성능 결과나 동결한 실행 계약이 없다. `IMPLEMENTATION_POLICY_DRAFT.json`의 세 실행 권한은 모두 `HOLD`다. 게시된 계획서와 기존 M5·M6·Stage 0 증거는 수정하지 않는다.

## 계획 변경과 코드 연결

| 계획의 요구 | 반영 위치와 동작 |
|---|---|
| 주 L2의 Q 일치 | `m7_replay.py`: 주입과 필터 N을 B0=0.015, L2=0.060°/√s로 연결. 기존 G를 통한 Q 전파를 유지하고 gyro 입력 분산 항만 변경한다. |
| Q 불일치 stress 분리 | 같은 L2 online 입력을 재사용하되 필터 N=0.015로 실행하는 별도 조건 ID. `m7_assess.py`에서 최종 M7 판정에서 제외한다. |
| 센서 짝과 seed 초기화 | `m7_inputs.py`: B0/L2 모두 level=1·noise_pair, gyro 백색 계수만 4배. 같은 seed의 wheel·RF·x0/P0 짝 동일성, gyro 잔차 4배, 참 bias 0 및 seed 10 parity 검사 코드를 둔다. |
| H5′ 대조 | `m7_h5prime.py`: 기존 M6 쌍→블록→donor 집계에서 σθ만 0으로 둔다. donor 비율의 평균으로 바꾸지 않으며 근거리 q를 강제로 0으로 만들지 않는다. 실제 적합에는 별도 GO·입력/코드 해시가 필요하다. |
| 자기 상태 R_ref | `m7_replay.py`: 직전 posterior 거리에서 D5 σ_b²를 조회한다. KI는 예측 prior 거리에서 q를 조회한다. `m7_score.py`는 parity용 scheduled R_ref trace의 본 판정 유입을 거부한다. |
| 무결성·정확도 분리 | `m7_assess.py`: I_seed/A_seed/J_seed와 각각의 수·Clopper–Pearson 구간, 네 조합의 seed 목록을 제공한다. 같은 조건·운용·seed의 H2를 정확도 기준으로 쓴다. |
| 기존 통과 기준 | 궤적 RMSE +25%, pooled +10%, 주 조건별 N_joint≥18/20 및 전 실행 거울해 0을 유지한다. B0와 Q 일치 L2를 모두 통과해야 같은 arm의 M7_PASS다. |
| 미사용 seed 별도 보고 | `m7_report.py`가 seed 10–14와 15–29의 점수·H2 대비 비용·DR/거리 대비 개선율·거울해·b_g 통계를 따로 집계한다. 비율의 기준이 0이면 미정 수를 표시하고 seed 분모는 유지한다. 새 부분집합 통과 문턱은 없다. |
| b_g 오차 필수화 | `m7_replay.py`가 b_g·P_bgbg·prior·Q를 남긴다. `m7_assess.bias_metrics`가 참 bias 0 기준 °/s 오차와 정규화 오차를 계산하고, 직접 gyro 주입오차와 추정 bias 누적 보정을 구별한다. 새 통과 문턱은 없다. |
| 집계 연결 | `m7_score.py`: 기존 from_trace·block bootstrap·branch scorer를 연결한다. arm마다 다른 자체 gate mask를 허용하고 5/10/20 s 짝 구간을 계산하며 10 s 구간으로 판정한다. |
| 완전성 | `m7_spec.py`: 1,470개 논리 cell, 고정 대조 H0 재사용 30개, 실제 재생 1,440회, B0/L2 online 입력 120개를 정의한다. 누락·중복·조건 재표기를 거부한다. 이 수는 예정 수이며 실행 횟수가 아니다. |

H5는 GM 몫을 차감한 잔여 q_s를 사용한다. **H5 실패는 b_θ가 필요하다는 증거가 아니다.** H5′도 모든 가능한 KI 대안에 대한 b_θ의 필수성을 입증하는 시험은 아니다.

## 구현 파일

- `m7_inputs.py`: offline 센서 입력 생성·읽기 검증. 실제 생성 함수는 동결 계약과 `input_generation=GO`를 요구한다.
- `m7_replay.py`: H0/H1/H2/H3/H4/H5/H5P의 online 재귀. evaluator를 받지 않고 online packet의 추가 필드도 거부한다.
- `m7_h5prime.py`: σθ=0 donor 적합. 실제 파일 적합 함수는 `donor_fit=GO`를 요구한다.
- `m7_assess.py`: 궤적·pooled·seed·조건별 판정, 구간과 b_g 진단.
- `m7_score.py`: 기존 점수 및 bootstrap 함수와 위 판정의 연결.
- `m7_report.py`: 5개 조건·운용 campaign의 완전성, 전체 및 두 seed 부분집합별 기술 통계와 최종 판정 연결. seed 간 분포는 bootstrap 구간으로 부르지 않는다.
- `m7_spec.py`: 동결 계획의 범위·조건·예상 cell과 HOLD 기본값.
- `check_m7_replay.py`, `test_m7_*.py`, `verify_m7_implementation.py`: 독립 산술 재계산을 포함한 구현 자기 검사. 실제 원본 trace를 비교하는 함수는 정의만 돼 있고 이번에는 실행하지 않았다.

재생 함수는 합성 검사에도 쓰이는 계산 함수다. 함수의 존재나 기본 인자는 실험 실행 승인을 뜻하지 않는다. 실제 실행 때는 계획 §4 순서대로 출처·모수·입력을 동결하고 검사한 뒤 별도 `RUN_CONTRACT.json`으로 연결해야 한다. 파일·코드·환경을 해시로 확인하는 호출 측 절차를 생략해서는 안 된다.

## 이번 검사와 한계

`implementation_checks/`에는 실제 실행한 합성 검사 기록을 보존한다. `CHECKS.json`의 소스 SHA-256과 현재 파일을 대조하고, 최신 코드와 일치하는 기록을 사용한다. 개발 중 수정 전 기록도 덮어쓰지 않는다.

최종 소스의 `attempt_02` 검사에서는 단위검사 **34개가 모두 통과**했고, 별도의 B0·Q 일치 L2·Q 불일치 stress 합성 재귀 검사도 통과했다. 이는 실제 M7 실험의 실행 수나 성능 결과가 아니다.

검사는 작은 해석적 관측 모형·가짜 센서 설정·합성 donor 배열·가짜 점수 표를 사용한다. 세 Q 조건의 GQGᵀ 전달, 1차원 거리 갱신, 부호 있는 GM·Joseph 갱신, zero-parameter parity, KI 인과성·10 s/100개 이력, 관측 정보 차단, LORO holdout 제외, seed 수와 판정·집계 연결을 확인한다. 기존 M6 적합 **코드 정의**는 불러오지만 실제 donor·RF·평가 궤적 배열은 읽지 않는다.

수치 검사와 별도로 재생·입력·적합·판정 및 점수 연결 코드를 읽기 전용으로 검토했다. 정적 검토 ACCEPT의 범위는 `CODE_REVIEW.json`에 남긴다. 이는 실험 감사 완료나 모델 채택 판정이 아니다.

검사를 다시 실행할 때는 이 폴더에서 다음처럼 **새 출력 폴더**를 지정한다.

```powershell
python -B -X utf8 verify_m7_implementation.py --plan ../PLAN_M7_FINAL_MODEL_STAGE1_KO.md --output-dir implementation_checks/new_attempt
```

실제 데이터에 대한 seed 10 입력 parity, 과거 M6 재귀 parity, 실제 H5′ 적합과 입력 생성, 주·stress 재생·성능 집계는 모두 남아 있다. 합성 검사 통과를 이 단계들의 통과로 보고하지 않는다.
