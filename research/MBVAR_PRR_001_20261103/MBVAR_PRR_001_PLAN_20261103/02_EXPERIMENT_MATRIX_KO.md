# MBVAR-PRR-001 — 실험 구성 및 주장 판정 요약

상위 계약: [01_EXECUTION_PLAN_KO.md](01_EXECUTION_PLAN_KO.md). 모든 항목은 미실행이다.

## 1. 단계별 실행표

| ID | 단계 | 실험 | 변경 | 고정 | 판정 목적 |
|---|---|---|---|---|---|
| G0-01 | 공통 | 원본/무처치 parity | 없음 | RF·μ/R·controls·x0/P0·gate | 정확한 MB_VAR 기준점 |
| S1-01 | 1 | 기존 prior의 threshold 검사 | threshold만 | 원래 prior·H·관측 | 놓친 오염/오검출 |
| S1-02 | 1 | 동일-prior Rss 할인 | w와 일관된 K/P | prior·mask·μ·Q·range | 한 갱신의 직접 효과 |
| S1-03 | 1 | W0/H-d0/W-d0/W-d0-DS 자연 재귀 | 위험도·w | 기존 모델과 A_B | 예방이 전체 이득인지 |
| S1-04 | 1 | LoS·초기큰오차 음성대조 | 같은 운용 규칙 | 물리입력/동일seed | 정상 정보를 버리는 위험 |
| S2-01 | 2 | P만 확대, 측정 사용 OFF | ΔP | 평균·관측 적용 없음 | 평균이 바뀌면 구현 오류 |
| S2-02 | 2 | 동일 손상 snapshot A/B/C_P/D_P | 예방·P recovery | 시작 x/P·미래controls | 이미 틀어진 상태의 회복 |
| S2-03 | 2 | 전체 주행 A/B/C_P/D_P | 실제 상태기계 | 전체 입력/정책/seed | 예방+복구 온라인 효과 |
| S2-04 | 2 | trigger/F·O 및 축 ablation | 등록된 한 요소 | 나머지 계약 | 발동 vs 처리 방향 효과 |
| S3-01 | 3 | IDENTITY_REPLAY | 재처리만 | 모든 설정·관측·가중치 | 재실행 자체는 변화 없어야 함 |
| S3-02 | 3 | reweighted replay vs cold replay | 과거 가중치 | checkpoint·관측·정책 | 재처리 정확성·중복 방지 |
| S3-03 | 3 | A/B/C_CP/D_CP | 예방·과거재가중 복구 | P injection OFF | checkpoint 추가 가치 |
| S3-04 | 3 | missing/short/late/corrupt history | 입력오류 주입 | 오류정책 | 잘못된 복구 차단 |
| S3-05 | 3 | 10/30/60초 buffer·실행비용 | 등록된 buffer 길이 | 나머지 정책 | 유효이력·계산비용 경계 |

## 2. 공통 네 실험

| Arm | 현재 관측 가중치 예방 | 복구 처리 | 비교 |
|---|---|---|---|
| A | OFF | OFF | 기존 MB_VAR |
| B | ON | OFF | B−A=예방 |
| C_R | OFF | ON | C−A=복구 |
| D_R | ON | ON | D−B=예방 위 복구 추가 효과, D−C=복구 위 예방 추가 효과 |

- R=P: C_P/D_P, checkpoint OFF.
- R=CP: C_CP/D_CP, P injection OFF.
- D_P+CP는 별도 승인된 보조 실험. 주 네 실험에 몰래 통합하지 않음.
- C_CP가 역사 가중치도 바꾸지 않는다면 identity control일 뿐이다.

## 3. 같은 시작점 시험과 전체 주행 시험

| 시험 | 시작점 | trigger | 점수 | 무엇을 말할 수 있나 |
|---|---|---|---|---|
| 동일-prior | 한 시점의 동일 x/P | 고정 처치 | 한 번의 dx, P 변화 | 국소 영향 |
| 동일 손상 snapshot | 원본 MB_VAR에서 동일한 잘못된 x/P | 공통 인과 schedule | 이후 10/20초 오류·회복시간 | 복구 능력 |
| 전체 causal replay | t=0 동일 초기조건 | arm별 운용 규칙 | 전체 emitted RMSE/coverage/실패 | 방법 성능 |
| retrospectively smoothed | replay 뒤 과거 수정곡선 | 현재까지 정보 | 보조 그래프 | 과거 추정 재해석, 온라인 성능 아님 |

## 4. Claim별 필수 근거

| Claim | 최소 검증 | 주요 반증 |
|---|---|---|
| 더 잘 검출 | recall↑ + false-positive 손해 | 기각 수만 증가 |
| 나쁜 갱신 감소 | 동일 prior에서 진짜 오류 변화 비교 | K가 작아졌다는 사실뿐 |
| 예방 개선 | 전체 재귀·시드·LoS 보호 | 수용표본 선별, hotspot만 보고 |
| 상태 복구 | 같은 손상 시작점에서 평균오차↓ | σ만 커져 coverage↑ |
| replay 개선 | identity parity + online emitted 이득 | 과거곡선만 수정, 중복 정보 |
| 결합의 필요성 | D−B/D−C 및 비용 | D−A만 양호 |

## 5. 조건과 규모

- R4-B / R5-B, B0 / L2, Full / 기존 Native LoS.
- 개발 seeds0–9, 추가 센서 실현 seeds10–29.
- 4 arms×2 routes×2 biases×2 channels×30 seeds = 960 arm 실행/복구 방식.
- P와 CP 모두 수행 시 최대 1,920개. A/B hash-identical 결과 재사용 가능.
- per-packet, 동일snapshot, 합성·ablation 수는 별도 cap 등록.
- 모든 seed는 같은 RF를 재사용하므로 독립 환경 표본이 아님.

## 6. 실패 시 분기

- 코드·입력·인과성 FAIL → 즉시 STOP, 새 SHA와 재감사 전 재실행 금지.
- S1 국소만 지지 → 전체예방 주장은 보류; S2 진행은 원인 질문이 남는 경우 별도 승인.
- S2 coverage만 개선 → 상태복구 지지 아님; S3 필요성 검토.
- S3 현재 출력 이득 없음 → replay 추가가치 미확인; 더 단순한 방법 유지.
- 보호조건 악화 → 전체개선 주장 NO-GO, 실패 조건 공개. 사후 route별 다른 계수로 구제 금지.
