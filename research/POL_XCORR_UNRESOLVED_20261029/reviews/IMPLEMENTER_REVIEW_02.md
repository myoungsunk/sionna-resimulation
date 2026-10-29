# IMPLEMENTER_REVIEW_02 — P0V3 R-04/R-14 직접 검증 결과

**역할:** IMPLEMENTER (독립 과학 AUDITOR 아님)  
**계약:** POL-XCORR-001 v0.3 **DRAFT** / P0V3_DELTA_PREFLIGHT_ONLY  
**원본 base SHA:** 250d617ad89a4105fa1af546cc83ceed9de98f42  
**Governance SHA:** d5f84d9d04d28d465f3357e9299352eb184e6bfc  
**구현 기초:** research/pol-xcorr-p0-v03-decisions-20261029 HEAD cd6e7e43b0d61ebc786084a17089b57a2f762325  
**v0.3 DRAFT contract SHA256:** 39c396c72688d88efa84d0fcb7779ad2b5b693891ab87aaae803bd26793cb76e  
**v0.3 config SHA256:** c9ffef3ead75fba48c5f6172d8ff69215f336db88f84508d762e957763f56d9c  
**v0.3 science spec SHA256:** 5db75dcc0a332833de50d87ba2081bea5ca0cd74e7e093ae00ce987728368450  
**P0V3 script SHA256:** a5c2de6a143dea0fafeb3c22ccbf92c78043203f23eb7250ccab649191d8875f

## 1. 판정

- **P0V3 CORE TECHNICAL: PASS** (IMPLEMENTER 자체 실행·시험; 독립 감사 아님).
- GitHub Actions run [40884328487](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40884328487), execution HEAD d47dd70f63593182073412700d1102b5269f5c1a: SUCCESS.
- GitHub Actions run [40884686972](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40884686972), execution HEAD 82e45066f6acdadd8154d6abac3a567a59aca58d: SUCCESS.
- 두 실행은 동일 로직을 전체 checkout과 blob:none + sparse-checkout에서 재실행한 **기술적 일관성 검사**다. 독립 제3자 검증이나 scene 독립 반복으로 계산하지 않는다.
- 두 실행의 8개 공통 결과 파일 SHA256은 **8/8 완전 일치**. 각 MANIFEST에는 실행 HEAD 및 파일별 SHA256 기록.
- 어떤 label이나 Full-channel M1 판별 결과도 계산하지 않았으며, S0/P1/P2/P3/RT는 실행하지 않았다.

## 2. R-04 — Full/LoS 직접 observer index parity

대상: 7 case × 2 channel = **19,038행**, 14개 case/channel 그룹.

| 항목 | 불일치 |
|---|---:|
| independent first-path tap vs features.extract.tap | 0 |
| independent strongest branch vs features.extract.branch | 0 |
| FP 유효성 (peak>0, common-port FP power>tiny) | 0 |
| G5 유효성 (peak>0, tap+80<=1028) | 0 |
| 두 RX에 동일한 first-path tap을 적용한 power/s_fp | 0 |

**중요:** FP-valid와 G5-valid는 독립적으로 재계산하고 각각 비교했다. 두 개념이 항상 같다고 가정하지 않는다. late-tap 합성 fixture에서는 FP-valid=True, G5-valid=False가 재현된다.

근거: results_p0_v03/run_40884686972/P0V3_TAP_BRANCH_PARITY.csv 및 P0V3_R04_ADVERSARIAL_KEYS.json.

## 3. R-14 — LoS 7-tap Jones 에너지 및 WEAK_PORT 플래그

한 시점의 **LoS H만**으로 7-tap W에 대해 J를 직접 구성하고,
u=min(J11,J22)/(J11+J22), weak_port=(u<0.05),
q_W=4detJ/tr(J)^2, eps_rho=detJ/(J11J22),
coherence_sq=abs(J12)^2/(J11J22)를 계산했다.

| 층 | valid | weak | 비율 |
|---|---:|---:|---:|
| 전체 LoS | 9519 | 3492 | 36.68% |
| TIMELINE | 7251 | 3105 | 42.82% |
| STATIC_YAW_SWEEP | 2268 | 387 | 17.06% |

- 전체 9,519행 모두 VALID. 약한 포트는 **유효한 행의 boolean 진단 flag**이며 결측화하거나 삭제하지 않았다.
- q identity 최대 절대오차 3.469446951953614e-18.
- eps identity 최대 절대오차 1.1102230246251565e-16.
- u inverse 최대 절대오차 1.7208456881689926e-14, 검사 9,506행.
- u가 균형에 극도로 가까워 역함수가 수치적으로 ill-conditioned인 13행은 inverse-only 검사에서 건너뛰고 이유를 기록했다. 해당 13행도 identity 검사·통계 요약 및 행 데이터에서 보존했다.
- 사전 고정 수치 임계: q identity rel 1e-10, u inverse abs 1e-9, u>=0.499에서는 inverse-only conditioning skip. 이는 q_ref나 과학적 임계 변경이 아니다.

근거: P0V3_LOS_PORT_BALANCE.csv, P0V3_WEAK_PORT_SUMMARY.csv, P0V3_R14_MATH_QA.json.

## 4. 음성 시험 및 기존 참조

- 음성·경계 fixture **21/21 PASS**: tap/branch/valid 변조, RX swap, 공통 tap 전력 오염, late G5 validity, NaN/Inf, 결손/중복 key, zero/tiny/balanced port, rank1, negative determinant, invalid window.
- Locked core SHA PASS; trace 집합 SHA PASS. **Trace ray-to-Jones 재정렬/재합성 자체는 수행하지 않았으므로 R-01/T4_ONLY_BLOCKED 유지.**
- R-02 (9,519행) 최대 |Δ| 1.1102230246251565e-16 PASS.
- R-12 (9,519행) 최대 |Δ| 1.3322676295501878e-15 PASS.
- R-13a (9,519×17 G5) 최대 |Δ| 7.105427357601002e-15 PASS.
- R-13b는 이전 역사적 PASS의 출처만 기록했으며 이번 delta run에서 재실행하지 않았다. 원 artifact 만료일 2026-11-19; 별도 보존 필요.
- 원본 reference CSV는 허용된 key+feature 열만 읽었다. e_s/e_r/eta 등 label은 **미열람**.

## 5. 생성·변경·보존

**신규 구현:** scripts/p0v3_delta_preflight.py  
**신규 워크플로:** .github/workflows/pol-xcorr-p0v3-delta.yml  
**Append-only run evidence:**
- results_p0_v03/run_40884328487/
- results_p0_v03/run_40884686972/
각 폴더에 P0V3_STATUS, R04 parity, LoS energy rows, weak-port summary, R14 math QA, negative fixtures, strict reference audit, MANIFEST, 자체 IMPLEMENTER_REVIEW_02를 기록했다.

**원본 보존:** root AGENTS, 기존 v0.1/v0.2/v0.3 계약·config·SCIENCE_SPEC, 모든 H/trace, 과거 results_p0/run_*는 변경하지 않았다. 제안자 결정 브랜치에 force push하지 않았다.

**검증 방식:** GitHub Actions 원본 14개 H에서 재계산; 수치·coverage·hash·시퀀스 검증 및 실패 닫힘. 실행자는 IMPLEMENTER이며 independent_auditor=NOT_ASSIGNED.

## 6. 미해결 및 다음 gate

1. **R-10/F-14 — BLOCKING:** 제안자·구현자와 다른 실행 주체가 독립적으로 H→CIR→tap/branch→J→q/eps/u를 재계산하고 원본 SHA/누락·음성·로그를 감사해야 한다. AUDITOR 사전 서명 없이는 FROZEN 불가.
2. **F-11 — OPEN:** 업데이트된 primary E1(M0+q_W)에 대한 label-free 가정 기반 power simulation 및 사전 기록 필요. 실제 label 또는 AUC 결과로 설계를 보정하지 말 것.
3. **F-16 — OPEN:** R-13b historical artifact의 허용된 evidence copy와 checksum/만료 관리.
4. **R-01:** T4_ONLY_BLOCKED 지속; ray-level 분해 주장 불가.
5. **R-07/R-08:** DW1000 jitter 실측 및 VNA 파일 경로는 외부 자료 미확보. 후속 하드웨어 관련 주장 제한.
6. **R-11:** 신규 scene holdout RT 예산 DEFERRED. scene 독립 단위 1개, retrospective 판정 상한 유지.
7. **v0.3 FROZEN:** 제안자 승인, 최신 full governance/source/config SHA 확인 및 독립 감사 이후에만 가능. S0/P1/P2/P3 아직 금지.

**권고:** R-04/R-14 P0V3 기술적 이슈는 구현자 관점에서 CLOSED_TECHNICAL. 별도 감사·F-11 완료 후 proposer에 freeze 재검토 의뢰. 과학적 verdict는 발급하지 않음.
