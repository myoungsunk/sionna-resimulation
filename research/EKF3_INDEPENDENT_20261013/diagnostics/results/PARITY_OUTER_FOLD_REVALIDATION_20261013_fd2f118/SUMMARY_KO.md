# D9 parity·E1 outer-fold·H3 Q1 수정 및 재검증

코드 커밋: `fd2f1180232dd56eed261a59d1e994955222f45c`. 실행일 2026-10-13. 원본 코드·RF·LUT·보정계수 불변. 로컬 Python 3.10, NumPy 2.2.4에서 실행했으며 GitHub Actions나 독립 RF scene 실험이 아니다.

## 판정

- 요청한 세 코드 수정의 독립 소스 감사: **ACCEPT**.
- 원본/수정 진단 관련 테스트: **59 PASS**, 실패 0.
- D9 기준선 재현: **PASS**, 모든 검증 셀 최대 차이 **0**. 절대 허용치 **1e-8 유지**.
- 품질 모델 채택 및 과학적 판정: **scientific_PASS=false**. Full RF 학습 품질 모델은 D8 gate FAIL로 D9 적용하지 않았다.

## 1. Parity 실패 원인과 수정

D5의 초기 위치분산 `.1**2`는 `0x1.47ae147ae147cp-7`, 기존 D9의 `.01`은 `0x1.47ae147ae147bp-7`이다. 1 ULP 차이가 재귀 필터에서 누적되어 R5_aB_m0/full/noise_pair/level1/seed0/B_OLD/A 평균 pose NEES 차이 3.5364204720167436e-7을 만들었다.

동일 입력으로 원본 D5를 다시 계산하면 게시 D5 지표와 정확히 일치했다. 관측값만 교체하거나 NEES 계산기를 원본으로 바꾸어도 기존 D9 차이는 남았다. **초기 P만 원본 P0_COV로 바꾸면 네 arm 모두 차이 0**이었다. 이를 그대로 코드와 bitwise 회귀 테스트에 반영했다. 원본 D5·EKF3 및 판정 허용치는 변경하지 않았다.

## 2. E1 홀드아웃 수정

D7에 동결 detector의 설계 벡터 8개를 추가했다. D8에서 outer 평가 경로가 R2이면 학습 R4/R5와 평가 R2 모두 동일한 E1_R2 계수로 잔차를 계산한다. 이전처럼 각 행의 자체 경로 LORO 계수를 사용하지 않는다. E1 보정 학습 경로와 XY가 겹치는 평가 위치를 제외하고 개수를 기록한다.

D9은 outer 경로, 원본 모델 SHA-256, 선택된 E1 계수 SHA-256을 검사한다. 잘못된 이전 fold는 탐색 override 여부와 관계없이 거부한다. 회귀 테스트는 다른 경로의 계수 변경에 outer fold 레이블이 영향받지 않음을 확인한다.

한계: 기존 E1 **모델군 선정**은 동결 scene 전체에 의존했다. 따라서 완전 nested 모델선정 또는 독립 환경 일반화가 아니다. D9 기준선은 전체 요청 경로이며 D8의 공간 중복 제외 scoring 집합과 동일하지 않다.

## 3. H3 Q1 비교 수정

Q3는 Q0 고정모델과 Q1 s_fp-only 모델 **모두**보다 개선되고 기존 calibration 범위를 만족해야 한다. Q1 누락은 INCONCLUSIVE이며 channel/correction/target별 결과를 기록한다. 임계값을 완화하지 않았다.

재평가: 18개 route/channel/correction/target 비교 셀에 Q1이 모두 존재한다. 현재 모델의 H3_CIR_QUALITY_PREDICTION 판정은 **NOT_SUPPORTED**다. 이는 이번 모델·개발 scene 범위의 결과이며 CIR 정보의 일반적 무용성을 의미하지 않는다.

## 4. 실제 재실행 범위

| 실험 | 조건 | 결과 |
|---|---|---|
| D7 | smoke + 7조건 LoS/Full | receiver parity 및 추출 완료 |
| D8 | R2/R4/R5, B_OLD + Full E1, Q0–Q3 | outer-fold/Q1 수정 적용 완료 |
| D9 R5 실패 회귀 | Full, seed0, level1, noise_pair, F0 | 4/4 셀 차이0 |
| D9 B_OLD | 7조건×LoS/Full, seed0, level1, noise_pair, F0/F1/F2 | F0 **56/56** 셀 차이0 |
| D9 E1 | 7조건×Full, 같은 motion 조건, F0 | **28/28** 셀 차이0 |
| D9 품질 모델 | R2_aA_m0/LoS, 같은 motion 조건, F0–F6 | 4/4 F0 셀 차이0, 탐색 실행 완료 |

D8 gate는 R2/LoS/B_OLD만 PASS, 나머지 8개 FAIL. Full RF learned-quality 실험을 강행하지 않았다. LoS Joint C의 F0→F3: Heading RMSE 0.232503→0.080178도, 위치RMSE 0.026632→0.023402m, pose NEES 2.94115→15.05266, 95% pose 포함률 96.02%→26.90%. RMSE 감소에도 일관성 악화가 재현돼 최종 개선으로 채택하지 않는다.

## 5. 게시 증빙

- `PARITY_ROOT_CAUSE.json`, `ROOT_CAUSE_ABLATION.json`: 원인 분리. ablation의 probe.py는 수정 전 6e40ec9 checkout에 대한 진단용이다.
- `VALIDATION_RECEIPT.json`, `TEST_RECEIPT.json`, `TEST_RESULTS.xml`: 실제 코드 revision/명령/결과/해시 검증.
- `POST_FIX_EVIDENCE.zip`: 수정 후 모든 CSV/로그/manifest/runner/가설 결과. 각 stage manifest로 출력 해시를 검증할 수 있다.
- `PRE_FIX_6e40ec9_EVIDENCE.zip`: 이전 실패 로그, D6 MC/Bias·전체 D5 trace 감사 및 D7–D9 결과 보존. 원본 NPZ는 기존 로컬 증빙에 남아 있고 zip에는 해당 감사 index가 있다.
- 열람용 summary 폴더에는 D8 점수·D9 지표·parity·가설 결과를 별도로 제공한다.

현재 verdict는 변경이 없는 MC/기존 D5 trace 및 이전 **6e40ec9 Bias smoke** 결과를 입력 증빙으로 재사용한다. 이를 수정 후 Bias 전체 재실행으로 표시하지 않는다. 전체 multi-seed D6/D9 격자와 독립 RF scene은 실행하지 않았다. 7조건 smoke의 회귀 해결과 과학적 확증은 별개의 판정이다. 모든 관리 프로세스는 종료 확인했다.
