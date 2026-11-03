VERDICT: ACCEPT

`4c99971a60dfee3404c5539d0e3c2f8e50b8f907`의 동결 명세에 대해 `SPEC_APPROVED`를 발급한다. 범위는 S1 구현 전 설계·입력 준비다. 단계별 코드감사와 실행 GO는 후속 gate로 유지한다.

| # | 판정 | 확인한 근거 |
|---|---|---|
| 1 | PASS | Full control 여섯 개의 MB μr·BASE μs/R, Rrs=0 확인. Native-LoS POWER_DIAG 기반 μs/R와 재현된 MB μr convention 명시 |
| 2 | PASS | CONTRACT/INPUT/ENV receipt, component 및 decision 문서 해시 일치. F64 reference 8개 bytes hash·ID·dtype·finite 검사 통과 |
| 3 | PASS_WITH_BOUNDARIES | seed0–9 lineage, 추가 seed10–29의 동일 RF 센서 실현 정의 확인. 미사용 RF/환경·holdout 주장 배제 |
| 4 | PASS | R1 수치규칙과 v0.3 후보·label·window·bootstrap·선정·중단 규칙 동결 |
| 5 | PASS | P와 CP factorial 분리, C_CP의 역사 재가중, D−B/D−C·interaction 정의 일관 |
| 6 | PASS | 동일 prior·손상 snapshot·causal replay·retrospective 점수 구분 |
| 7 | PASS_A0_SCOPE | 8개 F64 기준선 증거 확보. 기존 독립 motion/F/G/Joseph baseline 검산 통과. 단계 구현의 전시점 parity는 코드감사 대상 |
| 8 | PASS_DESIGN_ONLY | 위험도 상쇄·정상관측 손실·P/Q 구분·history 부족·singular nuisance 처리 규칙 명시 |
| 9 | PASS | 기술·과학·운용 판정과 NULL·보호조건 실패 처리 분리 |
| 10 | PASS_A0_SCOPE | 별도 auditor 세션에서 독립 특징행렬·모델 inference·baseline 계산 수행. 단계마다 독립 코드·runner 증거 요구 유지 |

EVIDENCE:

- 독립적으로 직접 작성한 tap 추출·행렬 조립 결과가 TRAINING_LOCK의 ordered keys/X/y 해시와 정확히 일치했다. R4 제외 학습 7,675행, R5 제외 학습 5,753행이다.
- 학습 입력·manifest 22개의 SHA256과 original commit `902ddcaf0f8e59734bb8026d3bcdc36eab506a27`의 Git blob identity를 모두 검증했다.
- frozen model의 원래 HGB 설정을 확인했다.
- Full R4-B B0/L2 각 742개 pose, R5-B B0/L2 각 1,415개 pose를 archived residual 유도 μr 및 original CONTROL μr와 각각 비교했다. 실패 0개, 최대 차이는 각각 `1.3877787807814457e-16 m`, `1.1102230246251565e-16 m`다.
- frozen model을 R2_SEARCH의 별도 Native-LoS 특징행렬에 적용했다. R4 742개, R5 1,415개 pose의 저장 μr와 차이가 정확히 0이다.
- `NATIVE_LOCK.json` 네 artifact 해시가 모두 일치했다.
- R1 독립 τD는 `0.07138038868537433`이다. 원본 979개 고유 pose에서 published fp 불일치 0개였다.
- 독립 baseline 수식과 canonical Full R4-B/B0/seed0 비교의 최대 state 차이는 `3.552713678800501e-15`, P 차이는 `7.37257477290143e-18`이었다.

동결 계약 SHA256은 `6c24e19de5ddb9d22f8e6b7724a7955680a2108295f02aac7793a13a4d33bf96`, INPUT_LOCK은 `2d1e9b8968c4c1e699a0f8593655cb85166d6bea1e73df3922beb5ea94632e9d`, ENV_LOCK은 `a9274b2f61b8c0c411354de671da5a9881d46c94a3b66b2ee5d1a23e39d4e91b`다.

FINDINGS:

원래 Native-LoS 입력 부재 blocker는 승인된 역사 모델 재현·Full 전 pose gate·동결 모델 inference 검증으로 해소됐다. 추가 A0 blocker는 발견하지 못했다.

MISSING_EVIDENCE:

- 현재 감사자의 exact stdin checker와 출력은 대화 tool 기록에 있다. 저장소의 독립 감사 artifact로 보존하는 작업은 Mother가 수행해야 한다.
- S1/S2/S3 구현·코드감사·성능 실행·결과감사 증거는 해당 단계에서 생성한다.

REQUIRED_CORRECTION:

설계나 입력에 대한 필수 수정은 없다. 독립 checker/출력과 이 판정을 append-only로 보존한다. 과학적 성능 개선·과거 원본 model binary 동일성·미확보 역사 LoS 출력 동일성·로봇 실시간 적용성은 이 승인에서 주장할 수 없다.

독립 검사는 WSL Ubuntu-24.04의 CPython 3.11.17, scikit-learn 1.7.2, BLAS/OMP 한 thread에서 수행했다. SourceFFD와 원래 센서 생성기는 공유했고, 특징행렬 조립·모델 inference 비교·motion/F/G/Joseph 검산은 별도로 작성했다. 파일 수정·추가 fit·S1 과학 실행은 수행하지 않았다.