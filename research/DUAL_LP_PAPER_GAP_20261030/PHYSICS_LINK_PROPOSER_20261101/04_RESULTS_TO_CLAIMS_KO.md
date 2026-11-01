# 04. 구현·실행 후 결과를 어떻게 논문에 사용할 것인가

상태: **사전 사용 규칙, 결과 NOT_RUN**. 구현 PASS와 연구 가설 지지를 분리한다. 기존 원고 선택은 이미 결과를 본 회고적 선정이며 새 preregistered 외부 test로 재명명하지 않는다.

## 1. 현재 보존할 주장과 바꾸지 않을 사실
- 선택한 세 경로×네 gyro, seed0, self baseline에서 Heading 감소12/12, Heading·XY 동시 감소8/12. 독립 환경12개나 통계적 유의성의 증거가 아니다.
- 분산-only도 Heading12/12이며, 결합의 추가 이득은 R2/R5-B 8조건에서 두 단독 모델보다 Heading·XY 모두 낮다는 데 있다. R4-B 4조건에서는 분산-only가 결합보다 좋다.
- Range 잔차 RMS 감소와 global mean 편향 제거, final XY 개선은 다른 주장이다. R4-B의 RMS 감소를 원인 확정 근거로 쓰지 않는다.
- 물리 기반은 복소 FFD h_s/J다. sigma table은 경험적 reliability이고 exact space-time covariance 복원·새 정보 생성이 아니다.
출처는 원본 review archive와 고정 source register. 기존 사실의 재계산 차이가 나면 조용히 덮지 말고 baseline mismatch로 감사한다.

## 2. 결과→주장 결정표
| Claim ID / 연결 | 필요한 증거 | SUPPORTED일 때 사용 | MIXED/NOT_SUPPORTED/INCONCLUSIVE일 때 |
|---|---|---|---|
| C1 물리 FFD→state-dependent signed s | V0 source parity, V1 J/FD/port-scalar tests | 실제 antenna response와 같은 detector 정의로 방향·위치 민감도가 구성됨 | source/좌표/branch 오류이면 physics section 계산치 보류; stable subset만 통과했으면 분모 명시 |
| C2 관측 잔차→보수적 weighting 동기 | V1 geometry/error strata, 기존 D3 mean/std/R, V4 선택 | 구조적 잔차와 민감도 정렬을 고려해 effective weighting 검토 | residual이 R보다 작거나 단순 설명 안 되면 true-noise-calibration 주장 금지; empirical reliability로 한정 |
| C3 mean+variance의 결합 기여 | V2 same-prior corrections, full fixed/self 2×2, 원본12조건 | R2/R5-B의 부호·gain·위치–Heading 결합과 추가 이득을 조건부로 설명 | only end-to-end change만 있으면 ‘인과 기여율’ 없이 system effect; R4-B는 반례를 포함 |
| C4 거리 lookup의 독특한 가치 | V3 constant vs lookup, train-only lambda·모든12조건 | 비교한 상수 정의·조건에 대해 distance conditioning의 증분 이득 | 비슷/혼합/열등이면 generic down-weighting 결과로 남기고 거리 우월성 주장 삭제; 모델 tuning 금지 |
| C5 상관이 재귀 갱신으로 전달됨 | V4 projected mean/cov, linearised cumulative closure와 실제 trace | 고정 선형화·선택 trajectory에서의 지속성/누적 방향을 제시 | raw ACF밖에 없으면 동기·관측 특성으로만 사용; exact colored filter라 쓰지 않음 |
| C6 12조건 재현성 | V0/V5 inputs, frozen outputs, baseline state/P/mask | 같은 immutable data/model/seed의 재현 가능한 point estimate | 학습모형 없음이면 archived prediction replay만; fresh inference/generalisation 보류 |
| C7 R4-B 결과의 제한 원인 | V2 signed range/pol correction·prior decomposition + self policy | 확인된 경로만 설명; variance-only 우위·XY 악화와 연결 | mean 부호나 single NIS만으로 원인 확정 금지. ‘불일치가 관측됐으나 기전은 미확정’ |

음의 연구 결과도 정확히 구현되면 기술 PASS다. C4가 비지지여도 기존12조건의 Heading 감소가 사라지는 것은 아니다. 반대로 C1이 기술 통과했다고 C3/C4가 증명되지는 않는다.

## 3. 보고서와 원고에 넣을 정량 단위
모든 주요 결과는 route×gyro 12행을 유지한다. percentage=(test−baseline)/baseline, 음수 개선; Heading 단위 deg, XY cm, internal rad/m 유지. 기존 원고 Table3는 기존 self 결과이며 fixed 진단과 섞지 않는다. 합산 평균을 쓰면 route별/조건별 weighting을 사전 명시하며 paired direction counts와 개별값도 보존한다.

NIS/NEES/coverage는 uncertainty 진단이다. gain shrinkage에 따른 NIS 감소를 posterior calibration 개선으로 곧바로 표현하지 않는다. 수용된 packet만의 낮은 잔차분산으로 sensor R 정확성을 주장하지 않는다. 실제 분모와 버려진 원인, branch-stable 표본 비율을 같이 쓴다.

V3의 ‘상수와 동등’은 이 예산에서 통계적 equivalence test가 아니다. 점수 차이·방향·범위를 보여주고, 정의한 practical margin이 없으면 유의한 차이 또는 동등이라고 쓰지 않는다. 새로운 paired seed 효과·CI가 필요하면 별도 사전 계획을 추가한다. 현 표본으로 scene-level CI를 만들어 독립 환경효과처럼 표현하지 않는다.

## 4. 그림·표 패키지의 사용 순서
| 산출물 | 본문 역할 | 필수 caption |
|---|---|---|
| F1: 3 routes의 h_s/J_spsi·signed error·geometry | §1의 물리 관측 설명 | source SHA, stable/switch 분모, GT는 offline, physical H와 J 구분 |
| F2: same-prior mean×variance와 signed correction | §2와 §3 사이의 원인 연결 | lookup 전 시점, common prior, frozen mask, one-step vs recursive 구분 |
| F3: zero/constant/lookup 12조건 | §3의 거리 신뢰도 역할 | constant의 train-only 정의, fixed/self 분리, 기존 lookup in-sample 사실 |
| 현 Table3:12조건 main score | 핵심 Heading 관찰 보존 | BB_ORIG은 기존 보정 기준선, Conventional EKF와 구별, seed0 |
| 구성요소 표(기존 Table4+요약) | 결합과 단독의 차이 | variance-only도12/12, R4-B에서 variance-only 우위 |
| ACF/누적항·학습 계보·음성시험 | 부록/보충자료 | chronological vs spatial, dataset/seed 의존성, independent reviewer 여부 |

주제 확대 방지: main figures 최대3개, 상세 packet/trace/matrix와 provenance는 부록. 새tap/5state/Office 외부시험 결과를 이번 구조의 성과로 끌어오지 않는다.

## 5. 실행 후 반드시 제출할 주장 원장
`claim_id, question, technical_status, scientific_verdict, source_run_id, input_sha, code_sha, config_sha, numerator, denominator, comparison, effect_value, mask_policy, truth_role, limitations, auditor_verdict, manuscript_location`.
기존 claim은 EXISTING_RETROSPECTIVE, 새 결과는 NEW_EXPLANATORY_ANALYSIS로 구분한다. 자동 CI는 서식·해시·재현성만 검사하고 과학 SUPPORTED 판단은 별도 감사자에게 남긴다. 결과없는 항목은 NOT_RUN이며 예상 부호·좋은 문장을 결과처럼 채우지 않는다.

## 6. 허용·금지 표현
- 허용: ‘동일 prior에서 편파 관측의 gain column이 감소했다’; ‘선택한 R2/R5-B 조건에서 결합은 단독 개입보다 낮은 오차를 보였다’; ‘추가분산은 경험적 reliability 조절이다’.
- 조건부: ‘거리 조건이 상수 조절보다 유효했다’는 C4 지지 이후, 조건과 범위를 명시하여만 사용.
- 금지: ‘공분산 증가로 정보량 생성’; ‘12개 독립 환경의 유의한 개선’; ‘sigma table은 안테나 물리에서 유일하게 도출’; ‘한 시점 residual 크기만으로 최종 Heading 원인 확정’; ‘기존 ACF로 independent time drift/space kernel을 식별’; ‘R4-B 불리한 결과를 제외해 동시 성공’.
