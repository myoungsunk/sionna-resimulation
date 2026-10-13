# D15 FFD 확보 후 LoS gate 및 재귀 EKF 실험

## 판정

- FFD 입력 무결성: PASS. 사용자 전달 bank 2개의 SHA-256 및 manifest 내용이 동결 입력과 일치.
- LoS smoke → 7조건 전체 gate → EKF smoke → 전체 융합 순서로 실제 실행 완료. 네 실행 모두 exit 0.
- 단위 테스트 28 PASS. 독립 연결 코드 감사 ACCEPT.
- 기존 P2 parity: 24,804개 state/covariance/status 비교 PASS, 허용치 1e-8 유지.
- 기존 D5 parity: 요청한 원본 56/56 셀 일치, 최대 절대 차이 8.402167850363185e-11 (허용치 1e-8).
- D0 및 Range-only B: 원본/dense의 28개 짝 전체 결과 정확히 일치.
- 재귀 융합 채택: **보류 / 현재 고정 R0 설정에서 Full RF 개선안으로 채택하지 않음**.
- `scientific_PASS=false`. 독립 RF scene 및 확증 seed 검증 아님.

## LoS 관측모델 및 전체 gate

| 항목 | 결과 | 기존 기준 |
|---|---:|---:|
| Full–LoS s RMS 비율 | 0.863512518 (13.65% 감소) | ≤0.95 |
| 경로별 비율 R2/R4/R5 | 0.878941 / 0.882974 / 0.828510 | 2경로 이상 개선, 최악 ≤1.05 |
| LoS 모델 잔차 RMS 비율 | 0.0000514794 | ≤1.25 |
| 평균 Heading 민감도 비율 | 1.001562731 | ≥0.80 |
| Jacobian 안정 비율 | 99.9194% | ≥95% |
| Full Joint one-step Heading RMSE 비율 | 0.957935179 | ≤1.05 |

전체 gate는 EXPLORATORY_GATE_PASS이다. LoS 오차가 작은 것은 동일한 동결 FFD를 사용한 수신기·관측모델 정합 결과이며, 독립 실제 환경 정확도 증거로 확대하지 않는다.

## 재귀 융합

7조건 × LoS/Full × D0/A/B/C × 원본/dense = 112셀. seed 0, noise_pair level 1, gyro bias 추가 없음, 초기 Heading 표준편차 5도, 기존 B_OLD·R0·Rsr=0 유지. 평가는 t≥30초, 조건별 기존 timeline을 유지했다. 아래는 샘플 수 가중 집계이며 독립 반복 실험의 통계적 유의성 검정이 아니다.

| 채널·모델 | Heading RMSE 원본→dense (°) | 위치 RMSE (m) | 평균 pose NEES | Pose 95% 포함률 |
|---|---:|---:|---:|---:|
| LoS A | 0.2575 → 0.1397 | 0.05479 → 0.04828 | 11.099 → 8.414 | 87.24% → 52.22% |
| LoS C | 0.2519 → 0.1934 | 0.05307 → 0.04824 | 25.646 → 3.912 | 70.20% → 84.91% |
| Full A | 1.1870 → 1.2331 | 0.25196 → 0.24138 | 18.423 → 144.636 | 39.14% → 13.14% |
| Full C | 1.3167 → 1.5032 | 0.23241 → 0.26184 | 50.914 → 164.150 | 15.21% → 14.13% |

Full C Heading RMSE는 약 14.17%, 위치 RMSE는 약 12.66% 악화했다. LoS C는 개선됐지만, LoS A의 포함률 악화도 있으므로 전체 통계적 일관성이 개선됐다고 할 수 없다. Full–LoS 특징 차이 감소와 one-step 개선이 재귀 융합 개선으로 이어지지 않았다. 이번 실행만으로 원인을 단정하지 않는다. 별도 진단이 필요하며 사후 R 또는 임계값 조정은 수행하지 않았다.

## 구현·재현·보존

새 d15_dense_fusion.py만 추가하여 DENSE_SINGLE 수신 특징과 동일한 direct LoS 모델을 연결했다. 관측·소스·bank 해시 및 전체 gate PASS를 강제하고 실패 gate 우회 옵션을 제거했다. 원본 d14/d13 runner, ekf3, P0/P2, D0–D5, RF 입력과 이전 산출물은 수정하지 않았다. D14 접두사 파일명은 재귀 결과 스키마 재사용을 의미한다.

FUSION_POOLED_METRICS.csv는 집계값, D14_RECURSIVE_ABLATION.csv는 개별 셀, D14_DELTA_VS_F0.csv는 짝별 변화다. EVIDENCE.zip에 전체 one-step 및 재귀 trace, 원시 로그, 실행 명령·exit code·시간, manifest 및 실행 소스 사본이 있다. BANK_RECEIPT.json은 사용자 전달 파일의 동결 입력 대응을 기록한다. VERIFICATION.json과 AUDIT.md에 검증·독립 감사 기록을 보존했다. 모든 관리 대상 프로세스는 종료 후 ownership을 해제했다.
