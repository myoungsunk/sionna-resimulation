# DLP-EKF-GAPS-001 / P2 — 4상태 Range-only vs Joint SourceFFD 전체 재귀 검증

**정리일:** 2026-11-02 KST  
**단계:** P2 FROZEN → 원본 C0 재귀 계산 완료 → scorer `PASS` → GitHub 대용량 결과 영구 보존 완료.  
**검증 성격:** 하나의 기존 C0 Corridor, 원본 RF 반복, 센서 seed=0의 후향적 실험. **미지 환경 일반화와 확률적 교정 성능을 증명하지 않는다.**

## 1. 정확한 실행 / 저장 이력

- P2 제안자 계약 SHA-256: `568ef6b794457f682ae9fd96e30d8a6f072d0283fcfd17aed4dcc2adfb76a48b`.
- 독립 계산 preflight: [run 41314437944](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41314437944), `ACCEPT_WITH_BOUNDARIES` (12/12, 0 FAIL). 같은 ChatGPT 대화 내의 별도 실행 코드/runner이며 **독립 사람의 GitHub 승인 아님**.
- P2 전체 원본 4상태 재귀 실험: [run 41315429738](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41315429738), R2/R4/R5 모든 route 계산 step 성공, 후속 scorer **PASS**, 84개 metric/84개 contrast/12개 pooled metric, 실패·비정상 frame 0.
- 단, 이 원 실행의 GitHub Actions *전체 conclusion은 failure*: 결과를 28개 `.npz` 그대로 Git에 push하는 마지막 단계에서 기존 `*.npz` Git LFS 업로드 서버가 `Not Implemented`로 거부. **계산 실패나 과학 PASS와 혼동하지 않는다.**
- 이를 **원 재귀 계산 없이** 복구한 [run 41388940715](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41388940715) **SUCCESS**. 기존 artifact 35개 원시 출력 SHA와 28개 trace NPZ 개별 해시, scorer 결과를 검증한 후 text 보고서 및 하나의 non-LFS ZIP을 append-only로 Git에 저장.
- [P2 복구 영수증](../runs/P2_FROZEN_RANGE_ONLY_41315429738/P2_RECOVERY_RECEIPT.json): 28개 NPZ 압축 ZIP `P2_ALL_28_TRACES_IMMUTABLE.zip`, 크기 27,290,828 bytes, SHA-256 `063d5c25892365f8d307fc424470b5066db36fa5f825fbf17b5bcb2bcc5531c3`.
- [QA 원본](../runs/P2_FROZEN_RANGE_ONLY_41315429738/P2_POSTRUN_QA.json) 및 [행렬 전체](../runs/P2_FROZEN_RANGE_ONLY_41315429738/P2_POOLED_METRICS.csv). P2 preflight와 run scorer가 검사한 각 항목은 원 receipt의 실제 PASS로만 표현하고, `U00–U15 16/16 all independently audited`라는 과잉 주장은 하지 않는다.

## 2. 실험 고정

- 상태 `[x,y,psi,b_g]^T`, 원본 EKF4 `f/F/Q`, Sensor-v2 원본 seed0, 공통 초기 `x/P`, 각 arm 자체 posterior를 이어가는 **full self-gated recursion**.
- 비교군: `DR4` (RF 없음), `R4` (1-anchor scalar range only, chi2(1) 99% gate), `J4_SRC` (같은 packet [r,s] SourceFFD, chi2(2) 99% gate).
- (R_r=0.0068578637\mathrm{m}^2), (R_s=0.0081), (R_{rs}=0)은 convention이며 독립성 입증은 아니다. Range 모델 `d-0.5315983906250129m` 유지.
- 7 case × Full/NativeLoS × B0/L2 = **28개 trace**, 각 3 arm의 raw x/P/status/NIS 포함. 평가 t≥30s는 모드·bias·arm 조합당 원본 6,201 step, 7 case. B0 true gyro-bias 0, L2 true +0.20deg/s gyro-bias-only perturbation. L2는 Sensor-v2 전체 스트레스가 아니라 다른 결정론적 오류를 비활성화한 분리 시험.
- 3 anchor나 P3, M2, 새로운 RF, 새 실험 환경은 이 P2에서 실행하지 않았다.

## 3. 7 case pooled 결과 (Heading ° / XY m)

각 channel×bias의 6,201개 평가시점을 case별 제곱오차로 가중 합산. 시간·case를 7개 독립 실험처럼 추론하지 않는다.

| RF | Bias | DR4 Heading / XY | R4 Heading / XY | J4 Source Heading / XY |
|---|---|---:|---:|---:|
| NativeLoS | B0 | 0.496 / 0.159 | 3.653 / 0.364 | **0.438 / 0.050** |
| NativeLoS | L2 | 28.692 / 2.906 | 4.892 / 0.538 | **0.488 / 0.051** |
| Full | B0 | **0.496 / 0.159** | 9.628 / 1.392 | 3.888 / 0.457 |
| Full | L2 | 28.692 / 2.906 | 12.867 / 1.738 | **3.999 / 0.432** |

**중요:** R4는 LoS에서도 DR4보다 Heading error가 큰 B0 조건이 존재하며, Full에서는 특히 악화한다. Joint J4는 L2 gyro bias 유입 시 개선하지만 **Full B0에서는 DR4보다 나쁘다**. 따라서 "RF를 추가할수록 정확해진다"는 보편적 결론은 기각한다. 이 비교는 1개 측정성분과 2개 측정성분의 비교이지 동등 정보/비용 비교가 아니다.

## 4. Gate/일관성/리소스

- B0 Full 전체 time-case 7251에서 **R4 accepted 7011, rejected 240** / **J4 accepted 6659, rejected 592**. L2 Full R4 accepted 7001/rejected 250, J4 accepted 6653/rejected 598. Gate policy는 차원이 다르며 동일 mask가 아니다.
- LoS B0/L2에서 R4와 J4는 전체 7251 time-case에서 각각 7251 accepted, rejected 0.
- Full B0 `pose95_coverage` 가중 평균: R4 **18.82%**, J4 **12.24%**. Full L2: R4 **10.69%**, J4 **11.77%**. 낮은 coverage는 posterior uncertainty 과신을 시사하며, 단일 seed의 시간적 비독립 샘플을 모집단 calibration 검증처럼 취급하지 않는다.
- LoS J4 `pose95_coverage`: B0 **89.63%**, L2 **90.53%**. 반면 원시 `R0`는 여전히 경험적 고정값이며 이 실험은 새 소음모델을 학습하지 않았다.
- 동일 RF packet 1개당 R4는 scalar range 1개, J4는 range+s **2개**를 사용한다. 7251 time-case를 제공할 때 R4 7251, J4 14502개의 scalar-component attempts이다. 에너지·시스템자원 동등성을 주장할 수 없다.
- scorer는 전체 **84개 필터 trace**의 own-prior 재귀 일치 max `0`, 별도 Joseph 공분산 재계산 최대 `4.44e-16`, NIS 최대 `2.84e-14` 수준, 0개 누락/비정상. 저장된 posterior/수치 검산 범위의 통과이지 독립 물리 환경 검증은 아니다.

## 5. 학술적 해석 및 다음 P3 경계

이번 기존 C0에서는 one-anchor Range-only가 heading/gyro-bias 추정을 안정적으로 보장하지 않으며, Joint SourceFFD도 Full multipath와 잘못된 관측분산 하에서 overconfidence를 보인다. Range H의 순간 상태 관측 Jacobian은 yaw/bias에 직접 민감하지 않아, 오로지 운동모델이 만든 cross-covariance를 통해 영향을 미친다.

다음 P3의 질문은 "새로운 **비공선 제3 앵커 위치**를 물리적으로 배치할 수 있고 동일 FFD source/observer를 적용할 수 있는가"이다. P3 **기하/Source-only LoS canary**는 P2의 Full 7-case 성능 향상이나 실제 다중앵커 packet synchronization 증명으로 소급되지 않는다. P4에서 native C H and clocks, resource budget이 없으면 다중앵커 필터 효과를 실험할 수 없다.

### Inspectable source and data

- [전체 84개 case metric](../runs/P2_FROZEN_RANGE_ONLY_41315429738/P2_CASE_METRICS.csv)
- [84개 paired contrast](../runs/P2_FROZEN_RANGE_ONLY_41315429738/P2_PAIRWISE_CONTRASTS.csv)
- [12개 pooled metric](../runs/P2_FROZEN_RANGE_ONLY_41315429738/P2_POOLED_METRICS.csv)
- [P2 source and checks](../p2_runtime/p2_recursive_range_joint.py) · [truth-only scorer](../p2_runtime/p2_score_aggregate.py)
- [28개 원래 posteriors 및 evidence ZIP](../runs/P2_FROZEN_RANGE_ONLY_41315429738/P2_ALL_28_TRACES_IMMUTABLE.zip)
- [원 검증 영수증](../runs/P2_FROZEN_RANGE_ONLY_41315429738/P2_POSTRUN_QA.json) · [원 결과 SHA 매니페스트](../runs/P2_FROZEN_RANGE_ONLY_41315429738/P2_MANIFEST.json)

**끝:** `P2_NUMERICAL_SCIENCE=PASS`, `P2_EVIDENCE_PUBLISHED=SUCCESS`, `P2_GENERALIZATION=NOT_TESTED`. 원본 P1 및 C0, 기존 P2 이외의 프로젝트 실험, main은 변경하지 않았다.
