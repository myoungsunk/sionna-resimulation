# 논문 초안 조정 계획 — 물리적 Dual-LP 관측을 중심으로

대상 원고: `PAPER_MANUSCRIPT_WORKING_DRAFT_KO.md` @ `1aac4d38a6fa335116bcecbebc91ba53c876ecfd` (v4).

**이번에는 v4를 수정하지 않는다.** 아래는 즉시 문구 교정 가능 부분과 PB1–3 실행 이후에만 추가할 부분을 구분한 v5 편집 계획이다. R2-B/R4-B/R5-B 12조건, 기존 MB_VAR/self, 4-State를 유지한다.

## 1. 논문의 중심 주장

현재 표현인 “거리 평균 보정과 편파 분산 추가로 Heading이 개선되었다”를 다음 구조로 정밀화한다.

> 실제 복소 FFD와 공통 first-path 관측 연산으로 Dual-LP의 위치·Heading 민감도를 구성하고, 그 물리 관측경로에 남는 구조적 오차를 거리 평균 처리와 편파 신뢰도 조절로 구분하여 사용하는 4상태 Joint EKF를 검토한다. 선택한 단일 앵커12조건에서 Heading 점추정 이득을 관측했으며, 그 이득의 전달 기전과 경계 사례를 동일 입력의 통제 분석으로 설명한다.

이 문장은 목표다. 마지막 “전달 기전을 설명한다”는 부분은 PB1/PB2 결과가 지지하는 문장으로만 채운다. 물리 기반은 **h/J와 관측 chain**이며 σ(rho) 표는 **경험적 reliability**다.

## 2. 현재 근거만으로 가능한 수정과 결과 대기 수정

| 위치 | 지금 조정할 내용 | 실행 뒤 채울 내용 |
|---|---|---|
| 제목·초록 | physics-based h/J와 empirical uncertainty weighting을 분리; single-anchor, 선택12조건 명시 | PB1–3 결과에 맞춘 mechanism 문장 |
| §1.1 관측 | complex FFD→좌표 변환→두 포트→CIR→common tap→s, H의 위치/yaw 열 설명 | 세 경로의 sensitivity/residual map |
| §1.2 잔차 | RMS/mean/std 분리, Full–Direct와 Direct–model 차이 구분 | 같은 detector branch의 포트 차등 왜곡 정량 |
| §1.3 지속성 | ACF는 설계 동기; static field와 temporal drift 구분 | gain-projected residual 및 cross-fit/기하층 분석 |
| §2.1 구성 | μM은 전체 Range 오차 평균 교체, sigma는 유효 신뢰도 조절; 원 표 유지 | CONST 대 LOOKUP이 지지하는 역할만 명시 |
| §2.2 갱신 | 같은 prior gain 축소식, 기존 lookup 시점, Joseph/NIS 그대로 | signed range/polarization update와 first divergence |
| §3.1 성능 | 12조건 표와 BB_ORIG/self baseline 보존 | 재생 SHA/denominator 검증 결과 |
| §3.2 ablation | 분산-only도 Heading12/12라는 사실, 결합의 8조건 추가 이득 강조 | 같은-prior→fixed-recursion→self-recursion 연결 |
| 신설 §3.3 | 제목만 “거리 조건별 신뢰도 조절의 대조” | PB3 ZERO/CONST/LOOKUP 전체12조건 결과 |
| §4.1 R4-B | mean sign·prior mismatch는 후보 설명으로 유지 | mean 추가가 variance-only보다 불리한 구간/갱신 증거 |
| §4.2 신뢰성 | RMSE 개선과 uncertainty calibration 분리 | 여전히 불량하면 그대로 제한 |
| 방법/부록 | 학습–예측–μ–RF–EKF–score source map | 새 run/plot manifest와 독립 감사 범위 |

신규 숫자, claim, 완성된 figure를 미리 써넣지 않는다. 기존 표를 새로운 통계로 바꿀 때는 구표와 분모 차이를 보존한다.

## 3. §1.1 물리 관측구조 — 먼저 쓸 수 있는 문단

> 본 연구는 Dual-LP 수신 안테나의 두 직교 선형편파 포트가 입사 방향과 로봇 자세에 따라 보이는 차등 응답을 관측모형에 반영한다. 실제 복소 FFD를 송수신 기하에 따라 변환하고, 원 관측 생성과 동일한 CIR 및 공통 첫 경로 탭 연산으로 정규화 편파비를 계산한다. 이 관측의 Jacobian에는 평면 위치와 Heading에 대한 민감도가 함께 포함되므로, 거리 관측의 단일 시점 직접 yaw 민감도를 보완하면서 위치–방향 결합을 동일한 4상태 EKF 안에서 다룬다. 자이로 편향은 단일 편파 측정이 직접 알려주는 값이 아니라 운동모델과 상태 교차공분산을 통해 추정된다.

수식은 s와 ∂s/∂u, 2×4 H 구조를 짧게 제시한다. 상세 complex vector contraction과 좌표 convention은 기존 SourceFFD 근거로 방법/부록에 둔다. 이상적 안테나 단순각도식이 실제 모델이라고 오해되지 않게 한다.

## 4. §1.2–2.1 오차와 신뢰도 — 먼저 쓸 수 있는 문단

> 정규화 편파비는 두 포트에 공통인 주파수-독립 복소 스칼라 변화에는 불변이지만, 포트별 차등 응답과 경로 간 복소 중첩, 첫 경로 선택 및 수신 잡음의 영향까지 제거하지는 않는다. 따라서 방향 민감도가 존재한다는 사실만으로 편파 관측을 정확하고 독립적인 각도 제약으로 사용할 수는 없다. 본 연구는 Full 관측과 같은 기하의 직접경로 관측 간 차이, 직접경로 관측과 SourceFFD 예측 간 차이, 평균 보정 후 잔차를 구분하여 분석한다. 거리 오차의 조건부 평균 교체와 편파 추가분산은 이들 오차를 전부 제거하는 절차가 아니라, 서로 다른 관측오차 성분을 처리하고 상태 갱신의 신뢰도를 조절하는 절차이다.

**금지할 문장:** “자유공간 path loss가 커지므로 정규화 s가 반드시 변한다”, “ACF로부터 sigma 표를 유일하게 도출했다”, “추가분산이 참 receiver variance를 복원했다”.

## 5. §2.2–3.2 물리 민감도와 실제 개선의 연결

현재 대수적 사실은 같은 prior에서 편파 gain column이 λ 증가에 따라 줄어든다는 것이다. 이것은 Heading information을 새로 만드는 행위가 아니다. 실제 기전 문장은 PB2 결과에 따라 다음 중 하나를 선택한다.

- 연결이 지지됨: “선택된 기하 구간에서 잔여 편파 왜곡이 만드는 signed Heading 갱신을 줄였고, 고정 수용집합의 재귀 비교에서도 이득이 유지되었다. 실제 self-gate 결과는 별도로 제시한다.”
- local만 지지됨: “동일 prior의 갱신 강도 변화는 확인됐으나, 이후 prior·gate 변화 때문에 최종 오차에 대한 단일 기여율은 분리되지 않았다.”
- case별 mixed: “동일한 weighting 조절이 경로별 관측기하·잔여 평균·prior와 결합하여 다른 결과를 보였다.”

기존 self ablation에서 R2-B/R5-B 결합이 두 단독보다 우수한 사실과, R4-B에서는 variance-only가 우수한 사실을 같은 문단에서 연결한다. R4에서만 다른 알고리즘을 채택해 전체 성공표를 만들지 않는다.

## 6. 핵심 그림·표의 사전 배치

**Figure A — 물리 작동점과 잔차.** 세 경로 패널에 Hsψ와 signed εs, Full/Direct 분해, 거리/방위 또는 tap event를 같은 timestamp로 정렬한다. y축 단위/scale 통일. 과도한 3D 장식 대신 실제 observation/J 자료 사용.

**Figure B — 갱신 분해.** 각 case에서 사전 시간구간 또는 전구간 집계로 Kψrνr/Kψsνs, mean-only·variance-only·combined shadow를 제시한다. 예쁜 구간 사후 선택 금지. 고정 기준 “평가구간 전부”와 first divergence의 두 보기를 함께 제공한다.

**Figure C 또는 Table E — 거리 조건 대조.** 같은12조건의 ZERO/CONST/LOOKUP을 Heading·XY 각각 표시. 불확실성·수용율은 보조표. 상수가 우수하면 그 결과를 그대로 포함한다.

**기존 Table 3 — 주 성능 표.** 12조건과 값 유지. 개선이 0.74%인 R4-B를 통계적 유의성으로 포장하지 않는다. 12조건은3개 RF×4센서이며 독립 환경12개가 아니다.

**기존 Table 4 — 단독/결합.** B0 대표표에 추가해 네 bias의 우열 요약 또는 부록 전체표를 제공한다. 결합모델이 후보 중 항상 최선이라는 표현은 하지 않는다.

**부록:** source/pose hashes, inactive branch, FD 음성 시험, failed/no-data bins, archived prediction vs inference, 모든12조건 factor96조건 원장.

## 7. 논문 기여 문장의 세 수준

1. **현재 가능한 기여:** 실제 Dual-LP FFD를 반영한 관측구조와 기존4상태 추정기의 명확한 정의; 선택12조건의 Heading 감소 관찰.
2. **이번 검증 후 가능한 기여:** 선택한 물리 작동점에서 오차가 gain/상태로 전달되는 방식과 평균/신뢰도 개입의 조건부 설명; 상수 대 거리 조건 비교의 결과.
3. **별도 검증 없이는 불가능:** 모든 환경 우수, calibrated uncertainty, 새로운 temporal process의 식별, 최적 σ(rho), Dual-LP 또는 Δs feature 단독의 인과 우월성, 5상태/SUB3의 검증.

모든 기여를 하나의 논문에 넣으려 하지 않는다. 본문은 **관측 현상→모델 가정→같은 모델의 결과→근거에 연결된 한계**라는 사용자 순서를 유지한다.

## 8. 원고 적용 절차

PB5에서 결과/claim ledger를 받은 뒤 기존 v4를 read-only reference로 보존하고 별도 v5 commit에서 필요한 문단만 편집한다. 각 새 그림·문장의 source/run/hash를 manifest에 연결한다. 구현자가 쓴 해석은 제안자 검토를 거치고, 독립 auditor verdict와 동일시하지 않는다. 이번 패키지는 이 절차의 계획이며 원고 편집 완료로 보고하지 않는다.
