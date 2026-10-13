# I2 실행 결과 — S1 개발 성능 곡선

I2 구현·검증·동결된 S1 개발 실행은 완료했다. 과학적 판정은 **INCONCLUSIVE**, 참조 posterior는 **REFERENCE_NOT_VALIDATED**이다. I3와 I7은 실행하지 않았다.

## 출발점과 범위

원격 기준은 `07dadb0ba165cc9d03c7ccb4c5fd3334bbe51b1f`, 브랜치는 `codex/dr-ekf-causal-followup-v2-20261013`이다. 로컬 HEAD는 `3032a58925ad4d1e3acec85865958e6580d79be7`로 오래되어, 출판된 작업 파일과 기준 커밋의 바이트 및 SHA256을 직접 대조했다. D6·V3/V4·I0/I1 파일은 변경하지 않았다.

결과 열람 전에 `out/I2_DESIGN.json`을 동결했다. R2/R4, drift d2, B0 bounded 세계와 A2_3_GAUSS_LEVEL 세계, 개발 seed 8000–8003, S1 prior, anchor A=(4,0,2.65), robot z=0.45를 사용했다. Range 표준편차 0.03/0.05/0.10/0.20 m, 관측률 1/5 Hz를 비교했다. R2는 I1에서 DR의 약한 Calibration 방향이 R4보다 약한 비교 대상이다. R5·다른 drift·anchor B는 이번 소규모 개발 행렬에서 제외했다.

사용자가 운용 요구를 미정으로 답했으므로 실용적 충분/부족 판정은 보류했다. S0 gauge·초기 위치 적분 범위도 추후 전달 예정이므로 S0 posterior는 NOT_RUN이다. I1의 국소 rank 2는 이 실험에서 충분한 실제 정밀도를 증명한 결과가 아니다. I1 profile 264 시작점 중 2개 반복 한도 기록, 구현 후 감사 미완료, F0 모델 미승인 및 RF provenance 한계는 그대로 유지한다.

## 실행·검증

- 기본 PF 144회: 16 episode × (DR + 8 Range 조건), 4096 입자.
- 선별 Gaussian R2/R4 seed8000 DR 및 0.05 m/5 Hz 셀: 16384 입자 × 독립 난수 2회, 총 8회.
- 같은 선별 4셀: 독립 비선형 MCMC, 4 chain, burn 1000, retained 1000/chain.
- 6시점 posterior 기록, 총 864 episode-arm-time 행. Calibration 원시 입자·가중치, MCMC 표본, noisy public 입력과 분리된 평가 truth를 보존했다.
- 기존 및 신규 테스트 **27개 통과**. 실행 전 독립 구현 감사 ACCEPT. 실제 실행 종료 코드 0, 관리 프로세스 자연 종료 및 자원 해제 확인.
- 공통 센서·prior의 arm 간 동일성, seed8000의 I0 입력 4 episode 바이트 배열 동일성, 코드·입출력 해시 검증 PASS.

실행 후 독립 산출물 감사는 모델 용량 제한으로 완료하지 못했다. 실행 전 구현 감사와 주 담당자의 결과·해시 검증을 완료했으며, 이를 실행 후 독립 감사 완료로 표시하지 않는다.

PF는 odometry 잔차와 공유된 입력 잡음을 조건부 Gaussian으로 처리하며, batch는 독립적인 Cholesky 인수와 latent pCN/MH로 같은 표적 분포를 계산한다. 참 거리·참 Calibration은 생성 및 사후 평가에만 사용한다. PF에는 likelihood gate, 공분산 보정, 정적 Calibration jitter가 없다. 측정 증분으로 계산한 Q의 조건부 likelihood는 물리적 생성모델 전체의 정확한 likelihood라는 뜻이 아니다. 특히 B0에는 slip·wheelbase mismatch가 남는다.

## 핵심 수치와 반례

아래는 **미검증 PF의 탐색 결과**이며 각 행은 4개 seed의 terminal Calibration 오차이다. 95% 포함률 역시 표본이 매우 작다.

| 세계/경로 | Gyro bias RMSE DR → 0.05m·5Hz (°/s) | Wheel asymmetry RMSE DR → Range | Range bg marginal 95% 포함률 |
|---|---:|---:|---:|
| Gaussian R2 | 0.187426 → 0.053843 | 0.004698 → 0.001391 | 0/4 |
| Gaussian R4 | 0.091059 → 0.051550 | 0.001936 → 0.001719 | 1/4 |
| B0 R2 | 0.136441 → 0.072389 | 0.003349 → 0.002213 | 0/4 |
| B0 R4 | 0.054790 → 0.023181 | 0.001067 → 0.000806 | 0/4 |

선별 조건에서는 RMSE 감소가 관찰되지만, 전체 조건에서 일관된 개선은 아니다. B0 R4의 0.03 m/5 Hz에서는 bg RMSE가 DR 0.054790에서 0.135575 °/s로 악화됐다. 이를 센서의 정보량 감소라고 해석할 수는 없다.

**PF 퇴화가 핵심 제한이다.** Range 128회 모두 terminal 초기 Calibration 계보 수가 100 미만이었다(1–48, 중앙값 3). 선별 R2 Range의 4096 입자는 1계보, 16384 입자 반복은 1/3계보만 남았다. R4 Range는 2계보 및 4/3계보였다. 입자 수 증가만으로 참조 신뢰성을 확보하지 못했다.

| MCMC 선별 셀 | 최대 classical split Rhat | 최소 within-chain ESS |
|---|---:|---:|
| Gaussian R2 DR | 3.7785 | 13.08 |
| Gaussian R2 Range | 6.6057 | 12.47 |
| Gaussian R4 DR | 2.2183 | 16.21 |
| Gaussian R4 Range | 4.9973 | 16.53 |

사전 기준 Rhat <1.05, ESS >400을 4셀 모두 통과하지 못했다. 이 ESS는 rank-normalized bulk ESS가 아니며, chain 간 불일치가 실제 다봉성인지 혼합 실패인지도 확정할 수 없다. 미방문 mode를 배제하지 못한다. PF–MCMC 평균/폭 일치 기준도 통과하지 못했다.

시간별 폭과 DR 대비 분산 비율은 `I2_WIDTH_TIMESERIES.csv`에 기록했다. 폭이 작아지거나 평탄해져도 입자 퇴화의 결과일 수 있어 정보 증가·포화로 판정하지 않는다. 공동 영역은 empirical 95% 질량 타원이며 HPD가 아니다. 퇴화한 공분산 또는 3 미만 계보는 파생 공동 포함률 집계에서 제외하고 유효/무효 개수를 표시한다. 원시 숫자 산출물은 보존했다. 0 분산 비율의 JSON 저장 실패 1회를 기록했으며, 계산 불가 값은 null로 남겼다. PSD repair나 원시 추정 결과 재실행은 하지 않았다.

## 판정과 다음 단계 경계

- 구현·범위 내 실행: PASS.
- 단일 Range의 실용적 충분/부족: INCONCLUSIVE — 요구 정밀도 미정 및 posterior 참조 미승인.
- 정보가 존재하지만 EKF가 실패하는가: 이번 I2로 판정하지 않음. EKF/CKF 비교는 실행하지 않았다.
- 구조적 가능성: I1의 조건부 국소 결과를 계승할 뿐, 새 구조적 확증 없음.
- S0·실제 RF·편파·I3·I7: NOT_RUN.

I3는 동일 public 입력을 사용할 준비가 되어 있으나, 과학적 추정기 비교 전에 **참조 posterior의 수렴 개선과 검증이 필요**하다. 임의 jitter를 넣거나 threshold를 완화해 승인하면 안 된다. 원시 likelihood를 보존하는 rejuvenation/더 효율적인 MCMC 등 변경은 별도 설계로 기록해야 한다.

## 산출물과 재현성

주 실행 폴더는 `out/i2_run_01/`이다. 필수 전달 파일은 `out/I2_DESIGN.json`, `out/I2_CALIBRATION_POSTERIOR.csv`, `out/I2_REFERENCE_VALIDATION.json`, `out/I2_GATE.json`이며 상세 원본은 실행 폴더에 있다. `I2_PERFORMANCE_CURVES.csv/png`, `I2_WIDTH_TIMESERIES.csv`와 각 episode의 `*_public.npz`, `*_config.json`, `*_pf.npz`, `*_posterior.json`, `*_batch.npz/json`을 함께 보존한다.

정확한 명령·환경·시각·종료 코드: `out/I2_EXECUTION_RECEIPT.json`, `out/I2_EXECUTION.log`. 코드/입력/출력 전체 SHA256: `out/i2_run_01/I2_RUN_MANIFEST.json`, 최종 배포 바이트 목록: `out/I2_PACKAGE_SHA256.json`. 테스트 및 무결성 검증: `out/I2_VERIFICATION.json`, `out/I2_TESTS.log`. 최종화 스크립트 해시 및 산출물: `I2_FINALIZATION_MANIFEST.json`. 업로드 영수증은 저장소 루트의 `I2_PUBLISH_RECEIPT.json`이다.

핵심 실행 SHA256:

- 설계: `e04832a919ee0ce028d277fc37c12bf965957963f28979fd405d882573faa0e7`
- PF/생성·평가 코드: `ec5ac51f33dbec5b6807cf2cbad62975c59a1eb39bc26be5c403b376366c6e07`
- 독립 batch 코드: `23de7f3a9e5b4685aa5bbc95cdd8b9485e76c3fb5ac0f2a875b3d6dff07d27c4`
