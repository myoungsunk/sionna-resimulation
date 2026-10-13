# I2 S0 추가 실험 결과

**구현·검증·동결된 실행은 완료했고, 과학적 판정은 INCONCLUSIVE이다.** 초기 반경 posterior의 수치 검증은 PASS지만, PF·Batch 참조 8조건은 모두 REFERENCE_NOT_VALIDATED이다. I3/I7은 실행하지 않았다.

## 적용 계약과 보존 범위

사용자 확정 S0 계약을 적용했다. DR의 초기 pose는 상대좌표 gauge (0,0,0)이고 Range 조건은 anchor 수평 원점과 초기 방사방향 +x를 선택한다. 초기 반경은 첫 noisy range posterior에서 샘플링하고 상대 Heading은 Uniform(-pi,pi]이다. 참 rho·Heading·pose를 추정기에 제공하지 않았다. 초기 Range는 초기화에만 사용하고 후속 갱신은 k=1부터 수행한다. Calibration prior는 각 기존 config의 동결된 Gaussian 표준편차를 유지한다.

원격 출발 커밋은 `ed1dc86221c54553e50b1204aab3129d95e1cbef`, 브랜치는 `codex/dr-ekf-causal-followup-v2-20261013`이다. 로컬 HEAD `3032a58925ad4d1e3acec85865958e6580d79be7`와 출판된 작업 파일이 다르므로 파일 바이트 해시를 확인했다. 기존 I2 배포 파일 660개는 실행 전후 모두 해시가 일치한다. D6/V3/V4/I0/I1/S1 원본, 기존 보고서와 인계 문서를 덮어쓰지 않았으며 이동·삭제한 파일은 없다.

## 실행 설계와 완료 수량

결과 전에 `I2_S0_DESIGN.json`을 동결했다. 기존 S1 noisy 센서·Range 입력을 재사용하고 `x0`를 제거했다. S0 public 파일은 허용 관측 7개 필드만 포함한다.

- 기본 조건: R2/R4, d2, B0 및 A2_3_GAUSS_LEVEL, 기존 개발 seed 8000–8003, DR 또는 sigma 0.05/0.20 m × 1/5 Hz Range. 80회 PF, 각 8192입자.
- 반경 prior 민감도: Gaussian R2/R4, seed8000/8001, 두 sigma·5Hz에서 radius, half-normal scale 10m/100m. 기본 area와 비교하는 추가 24회 PF.
- 계산 영역 민감도: Gaussian R2/R4 seed8000, sigma0.20m·5Hz에서 slant-distance 상한 max(|dz|,z0)+6sigma 및 +10sigma. 추가 4회 PF.
- 수렴 선별: Gaussian R2/R4 seed8000의 DR와 sigma0.05m·5Hz Range. 20k/80k 입자 × 독립 반복 2회, 추가 16회 PF.
- Batch: 같은 두 경로에서 DR 한 조건, Range area/radius/half-normal100 세 조건씩 총 8조건. 4chain, burn2000, retained2000/chain.

총 **PF 124회(기본·민감도108 + 고입자16), Batch 8조건·32chain**, 기본·민감도 posterior 6시점 ×108 = 648행을 보존했다. 실행은 2026-10-13 18:13–18:19 KST, 종료 코드 0이다. 40개 테스트와 실행 전 독립 구현 감사 ACCEPT, 사후 입력 동일성·최초 Range 단일 사용·코드/입출력 SHA 검증 PASS를 확인했다.

실행 후 독립 감사도 코드·산출물·보고서를 검토해 **ACCEPT**했다. 이는 미수렴 및 INCONCLUSIVE를 포함한 기록의 타당성 승인으로, 참조 posterior가 수렴했다는 승인이 아니다. 감사 기록은 `out/I2_S0_AUDIT.json`에 있다.

## 초기 반경 prior·계산 영역 검사

기본 prior는 면적 균일 참조측도로, rho Jacobian을 포함한다. 반경 균일 및 half-normal은 의도적인 대안 prior이며 유일한 무정보 분포나 기본 S0 조건으로 주장하지 않는다. 기본 무한 영역 정의는 수치적으로 12sigma slant 상한까지 적분하고 누락 질량 상한을 검증했다.

| 수치 검사 | 관측 최대값 | 사전 기준 |
|---|---:|---:|
| 기본 적분 영역 밖 posterior 질량 상한 | 3.0181e-33 | ≤1e-12 |
| 적분 격자와 독립 quadrature 정규화 상대 차이 | 3.2103e-14 | ≤1e-9 |
| 역 CDF 격자 세분화 quantile 차이 | 8.6121e-8 m | ≤1e-5 m |

6sigma/10sigma 축소 영역은 민감도 시험이며 기본 영역의 허용 기준과 혼동하지 않는다. 이 시험에서 제외된 초기 posterior 질량의 최대값은 **1.3299e-9**였다. 수치 검사 PASS는 이러한 영역이 물리적 위치 prior라는 뜻이 아니다.

대안 prior에 따른 초기 반경 중앙값의 최대 변화는 **0.025664 m**였다. 동일 seed의 terminal PF Calibration 평균 차이는 bg 최대 **0.190578 °/s**, eps 최대 **0.00561775**였다. 영역 상한 변경에 따른 terminal 평균 차이도 bg 최대 **0.002524 °/s**, eps 최대 **7.5027e-5**로 관찰됐다.

이 terminal 차이를 곧바로 실제 posterior의 prior 민감도로 확증하지 않는다. 초기 분포의 작은 변화도 퇴화한 PF의 재표집·입자 선택 경로를 바꿀 수 있다. 수렴한 반복 추정이 없으므로 Monte Carlo 오차와 prior 효과가 분리되지 않았다. **초기 반경 수치 계산은 통과, Calibration posterior의 prior·영역 강건성은 INCONCLUSIVE**이다.

## PF·Batch 수렴 결과

기본·민감도 Range PF 92회에서 terminal 초기 계보는 **1–12개, 중앙값 1개**였다. 선별 Range 고입자 반복도 충분한 다양성을 유지하지 못했다.

| 선별 area 셀 | PF 계보: 8192 / 20k 반복 / 80k 반복 | Batch 최대 Rhat | 최소 ESS |
|---|---|---:|---:|
| R2 DR | 170 / 236,367 / 1495,1476 | 2.0563 | 21.38 |
| R2 Range | 1 / 1,1 / 1,1 | 14.5940 | 18.08 |
| R4 DR | 93 / 198,167 / 821,691 | 1.1073 | 42.46 |
| R4 Range | 1 / 2,1 / 3,2 | 1.3219 | 30.68 |

Rhat는 Calibration 및 Range 조건의 rho/sin(delta)/cos(delta)에 대한 classical split Rhat, ESS는 within-chain initial-positive-pair 추정이다. rank-normalized bulk ESS가 아니며 미방문 mode를 배제하지 못한다. 사전 기준 Rhat<1.05, ESS>400과 PF 계보·posterior 평균/폭 일치 조건을 모두 충족한 경우는 **0/8**이다. 대안 prior의 Batch 역시 미승인이다.

Heading 원형 histogram·chain 원형 평균/집중도와 원시 표본을 보존했다. 서로 다른 chain 상태가 실제 다봉성인지 혼합 실패인지 확정하지 않았다. 단순한 큰 입자 수, 좁은 폭 또는 낮은 RMSE를 참조 승인 근거로 사용하지 않았다.

## Calibration 성능 — 미검증 알고리즘의 탐색 결과

각 행은 기본 area prior, 개발 seed4개의 terminal 오차다. Range는 sigma0.05m·5Hz이다.

| 세계/경로 | bg RMSE DR → Range (°/s) | eps RMSE DR → Range | Range bg/eps 95% 포함률 |
|---|---:|---:|---:|
| Gaussian R2 | 0.178769 → 0.172640 | 0.004482 → 0.003893 | 0/4, 0/4 |
| Gaussian R4 | 0.066532 → 0.130853 | 0.001543 → 0.004204 | 0/4, 0/4 |
| B0 R2 | 0.137494 → 0.110164 | 0.003385 → 0.003088 | 0/4, 0/4 |
| B0 R4 | 0.054371 → 0.116409 | 0.001099 → 0.003432 | 0/4, 0/4 |

Range 추가가 항상 오차를 줄이지 않는 반례를 확인했다. 그러나 이 결과는 정답 posterior가 정보 부족을 보였다는 증거가 아니다. 특히 비교한 0.05m·5Hz 기본 PF는 각 episode에서 단일 초기 Calibration 계보로 붕괴했다. 퇴화한 공동 영역은 INVALID로 남기며 공분산을 수리하지 않았다. 시간별 폭이 작아지는 현상도 정보 증가·포화로 확증하지 않는다.

기존 S1과 입자 수·실행 설계가 다르므로 이 표와 S1 표의 차이를 초기 pose 정보의 인과 효과로 직접 해석하지 않는다. Calibration 오차만 평가했으며 절대 XY RMSE는 계산하지 않았다.

## 판정과 제한

구현·검증·범위 내 실행은 PASS, 반경 수치 초기화는 PASS다. PF/Batch 참조는 REFERENCE_NOT_VALIDATED, prior 강건성과 실용적 충분/부족은 INCONCLUSIVE다. 사용자의 운용 오차 요구는 아직 미정이다. 조건부 measured-input Q 모델은 물리적 생성 likelihood 전체와 같지 않으며 B0의 slip·wheelbase mismatch도 유지된다.

I1의 국소 rank 결과, 최적화 2개 시작점 반복 한도 및 당시 구현 후 독립 감사 미완료 기록은 변경하지 않는다. F0 미승인 및 RF provenance 미해결 사항도 이번 Ideal Range 실험으로 해소되지 않는다. R5·다른 drift·anchor·RF·새 환경으로 일반화하지 않는다. 개발 seed를 독립 확증으로 사용하지 않는다.

다음 I3에는 입력 파일을 전달할 수 있지만, 주요 원인 판정에 앞서 **표적 분포를 보존하는 참조 수렴 개선과 재검증이 필요**하다. I3를 자동 실행하지 않는다. `I3_S0_HANDOFF_ADDENDUM_KO.md`에 인계 내용을 남겼다.

## 파일·재현성

- 구현: `i2_s0.py`, `i2_s0_batch.py`, `run_i2_s0.py`, `finalize_i2_s0.py`, `i2_s0_verify.py`, `tests/test_i2_s0_*.py`.
- 실행 원본: `out/i2_s0_run_01/`. 각 episode의 public/config, PF 초기 반경·Heading/Calibration 입자와 가중치, posterior JSON, Batch 표본·chain 진단을 포함한다.
- 주요 집계: `I2_S0_CALIBRATION_POSTERIOR.csv`, `I2_S0_PERFORMANCE_CURVES.csv`, `I2_S0_PRIOR_SENSITIVITY.csv`, `I2_S0_INITIAL_RADIUS_SENSITIVITY.csv`, `I2_S0_BATCH_PRIOR_SENSITIVITY.csv`, `I2_S0_REFERENCE_VALIDATION.json`, `I2_S0_GATE.json`.
- 정확한 명령·시각·환경·종료 코드: `out/I2_S0_EXECUTION_RECEIPT.json`, `I2_S0_EXECUTION.log`, `I2_S0_TESTS.log`, `I2_S0_PROCESS_RECEIPT.json`.
- SHA256: 실행 폴더의 `I2_S0_RUN_MANIFEST.json`, `I2_S0_ANALYSIS_MANIFEST.json` 및 배포 전체 목록 `out/I2_S0_PACKAGE_SHA256.json`. 검증 `out/I2_S0_VERIFICATION.json`, 업로드 영수증 저장소 루트 `I2_S0_PUBLISH_RECEIPT.json`.

핵심 SHA256: 설계 `573044529f2f7ffedb8fd8c1d5694323bb7510a8fbe781719339416582a519e9`, PF/실행 코드 `70d673bd5ea6c26b6791172c217ac65a0b61b63560432e3db785bd357ac6ce46`, Batch/반경 코드 `9b88e545b9eca8ae1c0a8807ef37d3a4955c3875a23f444b3ff39feef8137de7`.

재검증 명령은 `python research/SINGLE_ANCHOR_CAL_IDENTIFIABILITY_20261013/i2_s0_verify.py`이다. 새 실험을 자동 시작하는 명령이 아니다.
