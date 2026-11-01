## 1. 준비한 문서

| 문서                                                                                                                                                                                                                                                 | 작성한 내용                                                    |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| [**01. 제안자 계약**](https://github.com/myoungsunk/sionna-resimulation/blob/proposal/dual-lp-physics-bridge-12case-20261101/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_BRIDGE_PROPOSER_20261101/01_PROPOSER_CONTRACT_KO.md)                           | 연구 질문, 유지할 모델·12조건, 변경 가능한 개입, 보존 대상, 역할과 실행 권한           |
| [**02. 과학·검증 명세**](https://github.com/myoungsunk/sionna-resimulation/blob/proposal/dual-lp-physics-bridge-12case-20261101/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_BRIDGE_PROPOSER_20261101/02_SCIENCE_SPEC_AND_VERIFICATION_KO.md)             | 물리 민감도–잔차 정렬, 동일 prior 갱신 분해, 상수 대 거리 lookup 비교, 보조 상관 분석 |
| [**03. 구현자 인계서**](https://github.com/myoungsunk/sionna-resimulation/blob/proposal/dual-lp-physics-bridge-12case-20261101/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_BRIDGE_PROPOSER_20261101/03_IMPLEMENTER_HANDOFF_KO.md)                        | 별도 객체가 구현할 모듈·입출력·테스트·허용오차·중단 기준·필수 결과물                   |
| [**04. 결과 활용·주장 규칙**](https://github.com/myoungsunk/sionna-resimulation/blob/proposal/dual-lp-physics-bridge-12case-20261101/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_BRIDGE_PROPOSER_20261101/04_RESULT_USE_AND_CLAIM_RULES_KO.md)             | 성공·혼합·불지지 결과마다 논문에 사용할 수 있는 표현과 제한                        |
| [**05. 원고 조정 계획**](https://github.com/myoungsunk/sionna-resimulation/blob/proposal/dual-lp-physics-bridge-12case-20261101/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_BRIDGE_PROPOSER_20261101/05_MANUSCRIPT_REVISION_PLAN_KO.md)                  | 현재 근거로 수정 가능한 문장, 새 검증 후에만 추가할 문장, 절별 수정·그림·표 배치          |
| [**06. 구현 전 검토·동결 준비표**](https://github.com/myoungsunk/sionna-resimulation/blob/proposal/dual-lp-physics-bridge-12case-20261101/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_BRIDGE_PROPOSER_20261101/06_PREIMPLEMENTATION_REVIEW_AND_FREEZE_KO.md) | 독립 감사 질문, 미확정 입력, source lock과 FROZEN 전환 절차               |

별도로 `CONFIG_PROPOSED.json`, `SOURCE_REFERENCE_LOCK.json`, `PACKAGE_MANIFEST.json`에 **수치 설정·소스 참조·업로드 무결성**을 기록했습니다.

---

## 2. 이번 설계에서 유지한 연구 목적

대상은 **R2-B·R4-B·R5-B × B0/L0/L1/L2의 12조건**입니다. 기존 4상태 Joint EKF와 `MB_VAR/self`를 유지합니다.

주장을 강화하는 방향은 다음과 같이 정했습니다.

> **실제 복소 FFD와 공통 first-path 관측 연산으로 정의한 Dual-LP의 위치·Heading 민감도에, 잔여 관측오차가 어떻게 투영되는지 확인한다. 이후 거리 평균 처리와 편파 신뢰도 조절이 그 갱신을 어떻게 바꾸어 현재 결과를 만드는지 검증한다.**

따라서 이번 검증을 위해 **5상태·SUB3·sub-tap·새 앵커·새로운 RT 환경으로 주모델을 변경하지 않습니다.** 물리 기반인 부분은 관측함수와 Jacobian이고, 현재 추가분산은 경험적 신뢰도 조절이라는 구분도 유지했습니다.

### 구현자가 먼저 수행할 세 검증

| 순서                      | 질문                                       | 설계한 비교                                                                                                 |
| ----------------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| **PB1. 물리 민감도–잔차 정렬**   | 어떤 편파 작동점에서 정보와 왜곡이 나타나는가?               | 같은 packet의 Full/Direct/SourceFFD, 두 포트 power, signed 잔차, \\(H\_{sx},H\_{sy},H\_{s\psi}\\), tap·port 전환 |
| **PB2. 동일 prior 갱신 분해** | 평균·분산 개입이 어떤 상태 갱신을 바꾸는가?                | 같은 prior뿐 아니라 **같은 직전 posterior lookup 상태**에서 평균×분산 2×2 shadow update                                  |
| **PB3. 거리 조건의 고유 기여**   | 단순한 일괄 down-weighting보다 거리 lookup이 필요한가? | 추가분산 **0 / train-only 상수 / 현재 lookup**, 동일 평균·운동모델·평가조건                                                |

PB2에서는 국소 shadow 갱신이 원래 재귀 상태를 덮어쓰지 않게 했습니다. 이어 **fixed-mask 재귀와 self-gate 재귀를 별도로** 비교하도록 했습니다.

PB3의 상수는 평가 결과에 맞춰 고르지 않습니다. 평가 route를 제외한 다른 두 B-route의 기준 궤적에서 **추가분산 \\(\sigma_b^2\\)의 평균**을 계산하고, 두 route를 동일 가중하도록 산식을 정했습니다.

현재 설계의 계산 범위는 **기존 factorial 96개 궤적 재사용·재현 + 신규 상수 대조 48개 궤적**입니다. 이는 후속 실행 범위이며, 이번에 실행했다는 뜻은 아닙니다. 새 RT 예산은 **0회**입니다.

---

## 3. 결과를 논문에 사용하는 규칙도 미리 작성했습니다

가장 중요한 것은 **좋은 결과가 나와야만 문서가 완성되는 구조로 만들지 않았다는 점**입니다.

| 향후 결과                          | 원고에서 사용할 해석                               |
| ------------------------------ | ----------------------------------------- |
| 물리 민감도·잔차·signed 갱신이 연결됨       | 해당 기하·경로 범위에서 관측구조와 개선 기전을 설명             |
| 동일 prior에서는 이득이 있으나 재귀에서는 악화   | 국소 갱신 효과와 이후 prior·gate 피드백을 분리           |
| 거리 lookup이 상수보다 우수             | 단순 일괄 가중치 감소를 넘어 거리 조건을 사용하는 추가 가치 제시     |
| 거리 lookup이 상수와 비슷하거나 열등        | 기존 Heading 개선은 유지하되, 거리 함수 자체의 우월성 주장은 제외 |
| R4-B에서 여전히 작은 Heading 이득·XY 손실 | 12조건 표에 그대로 유지하고 결합모델의 경계 사례로 설명          |
| 기하 평균을 제거하면 시간상관이 줄어듦          | 정적 공간 field를 주행하며 관측한 상관과 일관된 결과로 해석      |
| 시간·공간 분리가 불가능함                 | 식별되지 않았음을 명시하고 독립 시간 drift를 주장하지 않음       |

또한 \*\*“분산만 추가해도 Heading 12/12 개선”\*\*이라는 기존 사실을 반드시 함께 다루도록 했습니다. 결합모델의 가치는 성공 개수가 아니라, **R2-B·R5-B에서 각 단독 개입보다 우수한 이유와 R4-B에서 그 관계가 반대인 이유**로 설명하도록 구성했습니다.

---

## 4. 원고 조정 계획은 ‘지금 쓸 문장’과 ‘검증 후 쓸 문장’을 분리했습니다

원고의 사용자 지정 순서인 **관측 현상 → 모델 구성 → 같은 모델의 결과 → 관측에 연결된 한계**는 그대로 유지합니다.

| 원고 위치          | 조정 방향                                                    |
| -------------- | -------------------------------------------------------- |
| **§1.1 관측구조**  | FFD→좌표 변환→두 포트→CIR→공통 tap→편파비와 Jacobian을 전면에 배치          |
| **§1.2 잔차 분석** | RMS·평균·분산을 구분하고 Full–Direct와 Direct–모델 오차를 분리            |
| **§1.3 상관 분석** | 상관은 설계 동기와 관측 특성으로 사용하되, 정확한 시간 covariance 처리로 과장하지 않음   |
| **§2 모델**      | 물리 기반 \\(h/J\\)와 경험적 신뢰도 조절 \\(\sigma_b(\rho)\\)를 명확히 구분 |
| **§3 성능·구성요소** | 기존 12조건 표 유지, signed 갱신과 상수 대 lookup 대조 결과를 연결           |
| **§4 R4-B 한계** | 잔여 평균·prior 불일치를 후보 설명으로 두고, 실제 갱신 분석이 지지한 부분만 원인으로 서술   |

주요 그림도 **물리 작동점–잔차 지도, 갱신 분해, 분산 정책 대조**의 세 종류로 제한했습니다. 상세 case·실패·수치 검증은 부록으로 연결하도록 했습니다.

**현재 원고 v4는 직접 수정하지 않았습니다.** 후속 결과를 받은 뒤 어떤 문단과 그림을 바꿀지 계획한 상태입니다.

---

## 5. 업로드 범위와 인계 상태

기존 검토 패키지는 GitHub에서 읽을 수 있도록 **보고서·표·QA·역사적 재집계 스크립트 등 8개 구성파일을 원바이트로 게시**했습니다. 로컬 원본과 원격 Git blob이 일치함을 확인했습니다.

다만 **원본 ZIP 바이너리 자체와 전체 `RA4_336_ARMS.csv`를 새 폴더에 중복 업로드하지는 않았습니다.** 전체 CSV는 기존 GitHub artifact와 SHA로 연결했고, 원본 ZIP은 대화 첨부로 보존했습니다. 이 차이를 README와 manifest에도 명시했습니다.

[기존 검토자료의 GitHub 보존본](https://github.com/myoungsunk/sionna-resimulation/tree/proposal/dual-lp-physics-bridge-12case-20261101/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_BRIDGE_PROPOSER_20261101/reference_review) · DualLP_Manuscript_v4_Physics_Review_20261101.zip

현재 인계 상태는 다음과 같습니다.

**`PROPOSER_DOCUMENTS_READY / DRAFT_NOT_FROZEN / IMPLEMENTATION_NOT_RUN / INDEPENDENT_REVIEW_PENDING`**

별도 구현 객체는 **03 인계서로 source inventory부터 확인**하고, 실제 입력 해시와 설계 해석을 확정한 뒤 독립 pre-run 검토와 동결 절차를 거치도록 했습니다. 이번 제출은 그 객체가 목적·비교군·결과 사용 기준을 임의로 바꾸지 않고 구현할 수 있도록 준비한 **제안자 문서 패키지**입니다.

## 제안자 문서 패키지를 GitHub에 올렸습니다

**구현·실험은 진행하지 않았고, 원고 v4와 기존 모델·결과도 변경하지 않았습니다.** 새 브랜치에는 제안자 문서, 기존 검토 보고서와 핵심 표, 출처·배포 명세 등 **15개 파일만 추가**했습니다.

[**GitHub 패키지 안내문 열기**](https://github.com/myoungsunk/sionna-resimulation/blob/43818124f39ad5ae20eb372d682dd2a63d8786bc/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_LINK_PROPOSER_20261101/README_KO.md)\
DualLP_Physics_Proposer_Package_20261101.zip

브랜치: `research/dual-lp-physics-proposer-20261101`\
최종 커밋: `43818124f39ad5ae20eb372d682dd2a63d8786bc`

**업로드 범위는 구분해서 말씀드립니다.** GitHub에는 새 제안자 문서와 기존 평가서·핵심 표를 올렸지만, **기존 ZIP 이진파일 및 그 안의 전체 원자료를 GitHub에 그대로 복제하는 작업은 완료하지 못했습니다.** 위 다운로드 ZIP에는 기존 원본 ZIP과 구성원 9개를 모두 변경 없이 포함했고, 해시 일치도 확인했습니다. GitHub 안내문과 manifest에도 이 차이를 명시했습니다.

---

## 1. 준비한 문서

| 문서                                                                                                                                                                                                                            | 주요 내용                                                     |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| [**01. 제안자 검증 계약**](https://github.com/myoungsunk/sionna-resimulation/blob/research/dual-lp-physics-proposer-20261101/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_LINK_PROPOSER_20261101/01_PROPOSER_CONTRACT_KO.md)          | 연구 질문, 고정할 모델·데이터, 비교군, 수치 검증, 실행 상한, 중단·동결 조건            |
| [**02. 검증 명세**](https://github.com/myoungsunk/sionna-resimulation/blob/research/dual-lp-physics-proposer-20261101/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_LINK_PROPOSER_20261101/02_VERIFICATION_SPEC_KO.md)              | 물리 민감도, 동일-prior 평균×분산 분해, 상수분산 대조, 선택적 상관 분석의 구체적인 산출 방법 |
| [**03. 구현자 인계서**](https://github.com/myoungsunk/sionna-resimulation/blob/research/dual-lp-physics-proposer-20261101/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_LINK_PROPOSER_20261101/03_IMPLEMENTER_HANDOFF_KO.md)          | 다른 구현자가 읽을 순서, 구현 전 제출사항, 모듈 경계, 출력 스키마, 전달용 프롬프트         |
| [**04. 결과→주장 연결 규칙**](https://github.com/myoungsunk/sionna-resimulation/blob/research/dual-lp-physics-proposer-20261101/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_LINK_PROPOSER_20261101/04_RESULTS_TO_CLAIMS_KO.md)        | 지지·혼합·비지지·미확정 결과에 따라 어떤 주장을 유지·축소·보류할지 사전 정의              |
| [**05. 논문 초안 조정 계획**](https://github.com/myoungsunk/sionna-resimulation/blob/research/dual-lp-physics-proposer-20261101/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_LINK_PROPOSER_20261101/05_MANUSCRIPT_REVISION_PLAN_KO.md) | 원고 §1–4의 수정 위치, 현재 쓸 수 있는 문단, 결과 이후에만 쓸 문장, 그림·표 배치       |
| [**06. 역할 규정 적용·동결 준비**](https://github.com/myoungsunk/sionna-resimulation/blob/research/dual-lp-physics-proposer-20261101/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_LINK_PROPOSER_20261101/06_GOVERNANCE_AND_FREEZE_KO.md) | 기존 GitHub 거버넌스의 적용 범위, 제안자·구현자·감사자 책임, 아직 미확정인 입력·승인      |

별도로 **수치 설정 제안 JSON**, **출처·커밋·blob 목록**, **배포 manifest**, **원본 ZIP 구성원 해시 목록**도 포함했습니다.

---

## 2. 검증의 목적을 이렇게 고정했습니다

이번 제안의 목적은 새 필터를 개발하거나 모든 case의 성능을 높이는 것이 아닙니다.

> **기존 12조건의 결과를 유지하면서, 실제 Dual-LP 안테나의 물리적 응답과 잔여 관측오차가 EKF 갱신을 거쳐 성능 차이로 이어지는 과정을 설명한다.**

대상은 **R2-B·R4-B·R5-B × B0/L0/L1/L2**, 기존 정수 first-path 거리와 signed 편파비, 기존 4상태, 기존 평균 교체와 추가분산 설정입니다. `SUB3`, sub-tap, 5상태 GM, 다른 anchor, 신규 RT는 이번 범위에 포함하지 않았습니다.

### 우선 검증 세 가지

| 단계                        | 검증 질문                                                  | 핵심 통제                                            |
| ------------------------- | ------------------------------------------------------ | ------------------------------------------------ |
| **V1. 물리 민감도–잔차 연결**      | 선택한 경로에서 실제 FFD의 위치·Heading 민감도와 signed 잔차가 어떻게 정렬되는가? | 원본 관측기·좌표·포트·tap 정의 유지, 안정 구간과 전환 구간 분리          |
| **V2. 동일-prior 평균×분산 분해** | 평균 교체와 편파 가중치 조절이 어떤 signed 갱신·NIS·상태오차 변화를 만드는가?      | 같은 prior뿐 아니라 **같은 이전 posterior의 분산 조회 상태**까지 일치 |
| **V3. 상수분산 대 거리 lookup**  | 거리 조건별 조절에 실제 추가 가치가 있는가, 일반적인 down-weighting으로 설명되는가? | 상수는 다른 두 학습 route에서 사전 결정, 평가 결과에 맞춰 조정하지 않음     |

V0 출처·parity 검증이 선행합니다. 투영 상관과 누적 효과를 보는 V4는 설명을 더 강화할 때 수행하고, V5는 학습–예측–재생의 연결을 검증합니다.

**제안된 계산 상한은 기존 비교 재생 96개와 상수분산 추가 비교 48개, 합계 144개 전체 재귀 실행이며 RT는 0회입니다.** 이는 향후 동결할 실행 범위이지, 이번에 실행한 횟수가 아닙니다.

---

## 3. 실행 결과를 어떻게 사용할지도 미리 정했습니다

결과를 본 뒤 좋은 설명만 선택하지 않도록 **결과별 원고 처리 규칙**을 별도 문서로 만들었습니다.

| 향후 확인되는 결과                        | 원고에서의 처리                                              |
| --------------------------------- | ----------------------------------------------------- |
| 실제 FFD의 민감도·미분 검증 통과              | 물리적 관측함수와 Jacobian 구성의 근거로 사용. 전체 성능 개선의 증명으로 확대하지 않음 |
| 동일 prior에서 편파 gain 축소 확인          | 관측 가중치 조절의 직접 효과로 사용. 최종 RMSE 개선은 재귀 결과로 별도 확인        |
| R2/R5-B에서 결합모델의 추가 이득을 갱신 기록으로 설명 | 평균·분산의 상호작용을 구체적인 기전으로 제시                             |
| 거리 lookup이 상수보다 우수하지 않음           | 기존 Heading 개선은 유지하되, **거리 조건 자체의 특별한 우월성은 주장하지 않음**   |
| R4-B 원인이 명확하지 않음                  | 작은 Heading 이득·XY 악화·분산 단독 우위를 보존하고 원인 확정은 보류          |
| 상관 분석이 ACF 수준에 머묾                 | 관측 특성과 설계 동기로만 사용. 정확한 시공간 covariance를 처리했다고 쓰지 않음    |

**기술적 PASS와 과학적 지지는 별도 필드로 기록**하도록 했습니다. 정확하게 구현된 비지지·악화 결과도 유효한 실험 결과로 남깁니다.

---

## 4. 논문 초안은 구조를 유지하면서 중심을 조정하도록 계획했습니다

원고의 기존 네 단계는 그대로 유지합니다.

| 기존 순서               | 조정할 중심                                                          |
| ------------------- | --------------------------------------------------------------- |
| **① 관측 특성 분석**      | FFD→송수신 기하→CIR→공통 tap→편파비→Jacobian의 물리적 연결을 먼저 제시               |
| **② 분석에 근거한 모델 구성** | \*\*물리 기반 \\(h_s,J\\)\*\*와 **경험적 추가분산**을 명확히 구분하고, 실제 갱신 경로를 설명 |
| **③ 동일 모델의 성능 향상**  | 기존 12조건 표를 유지하면서 단독 모델 대비 결합 이득, 상수 대비 lookup의 역할을 분리           |
| **④ 관측 특성에 근거한 한계** | R4-B를 제외하지 않고, 확인된 signed 갱신·prior·gate 효과만 원인 설명으로 연결          |

주장 중심은 다음 문장으로 정리했습니다.

> **실제 안테나 응답으로 Heading에 민감한 Dual-LP 관측을 구성하고, 그 물리적 관측경로에 남은 구조적 오차가 상태 갱신으로 전달되는 방식을 분석하여 거리 평균 처리와 편파 신뢰도 조절의 역할을 설명한다.**

현재 증거로 바로 쓸 수 있는 문단과 **새 검증 결과가 나온 뒤에만 작성할 수 있는 문장**을 구분했습니다. 본문 그림도 물리 민감도, 동일-prior 갱신, 상수 대비 lookup의 **세 종류를 중심**으로 제한하고, 상세 trace·해시·음성시험은 보충자료로 배치하도록 했습니다.

---

## 5. 인계 상태

현재 상태는 \*\*\`PROPOSER_ONLY / DRAFT-v1 / NOT_FROZEN / VERIFICATION_NOT_RUN\`\*\*입니다.

기준 원고 `1aac4d38`와 비교하여 **기존 파일 변경 0개, 새 문서·참조 파일 추가 15개**임을 확인했습니다. 별도 구현자는 **03 인계서 → 01 계약 → 02 명세**를 읽고, 먼저 실제 입력 lock과 구현 전 검토서를 제출하도록 되어 있습니다. 그 후 제안자와 독립 감사자가 입력·수치 설정을 확인한 동결 명세에 따라 실행하게 됩니다.

전체 원자료까지 필요한 구현자에게는 **GitHub 안내문과 함께 DualLP_Physics_Proposer_Package_20261101.zip를 전달하는 구성이 현재 완전한 인계본**입니다.