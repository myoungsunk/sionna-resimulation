# FP–EKF 접근 A/B 실패 원인 재감사 — 2026-11-05

**판정:** `ARCHIVED_RECURSION_ARITHMETIC_PASS / HISTORY_BOUNDARY_BUG_CONFIRMED / C1_COVARIANCE_BUG_CONFIRMED / INFORMATION_LABEL_SWAP_CONFIRMED / PATCHED_NONLINEAR_PERFORMANCE_NOT_RUN`.

대상 원본 SHA: `d70360a4cac98de47c3365244a08112bf6414e28`.
분류: `NONINDEPENDENT_REAUDIT`. 기존 분석에 참여한 동일 도구의 재감사이며 별도 독립 연구자 승인으로 부르지 않는다.

## 1. 정정해야 할 이전 설명

접근 A/B는 이전부터 구현·평가됐다. S1의 현재 관측 가중치 조절, S2의 공분산 복구, S3의 체크포인트 재귀 재계산을 구분해야 한다. 앞선 설명에서 기존 S3까지 새로 해야 할 미실행 C2처럼 취급한 것은 부정확했다.

사용자가 말한 접근 A/B와 코드의 실험 arm A/B는 다르다.

| 기존 단계/arm | 실제 동작 | 하지 않는 것 |
|---|---|---|
| C1 현재 관측 대조 | 기존 prior·gain에서 Full/LoS 관측 교체 | 과거부터 자연 재귀 재실행 |
| S1 / S3 arm B | 현재 편파 관측의 가중치를 낮춤 | 정확한 LoS 관측 복원 |
| S2 C_P / D_P | 접선·Heading 공분산 바닥값 주입 후 순방향 갱신 | 과거 체크포인트 되감기, 주입 순간 상태 평균 교체 |
| S3 C_CP | 과거 체크포인트부터 4상태·공분산 재계산 | 오염 관측의 정확한 값 교체 |
| S3 D_CP | 현재 관측 예방 + 체크포인트 재계산 | 자기 궤적만으로 게이트를 재결정하는 전면 self-gated 개입 |
| S3 arm A | W0 기준선 | 사용자 개념상의 접근 A와 동일하지 않음 |

원본 구현: `evidence/inputs/research/MBVAR_PRR_001_20261103/{S1,S2,S3}`.

## 2. 이번에 실제 실행한 범위

### 원시 배열 검산

R4/R5 × B0/Full × seed 10,14,20 × S2/S3 각각 4개 arm = **48개 전체 trace, 51,768개 저장 시점**.

각 시점에서 다음을 별도 행렬식으로 계산했다.

- 직전 자기 posterior에서 다음 자기 prior로 이동하는 x/P 전파, F/G/Q.
- S=H P Hᵀ+R, K, 상태 갱신, Joseph 공분산, NIS.
- 원본 관측 z와 평균보정 μ의 arm 간 일치.
- 채택된 재계산 끝점과 실제 출력 x/P의 일치, 다음 prior 반영.
- 원본 공개 SHA가 있는 trace/retrospective 파일 33개의 바이트 해시.
- sensor-v2의 원본 seed namespace와 독립 난수 식으로 만든 B0 운동 입력 대조.
- 기록된 성능지표와 재계산한 성능지표 대조.

**48개 모두 산술 검산 통과.** 최대 상태 전파 잔차 3.56e-15, 공분산 전파 2.78e-17. 독립 센서 입력 대조 최대 1.82e-15. 48개 성능점수 대조 최대 6.22e-15.

이것은 원시 배열 기반 재감사다. SourceFFD의 비선형 h/H를 안테나 bank에서 새로 평가한 전체 필터 재실행은 아니다. 저장 h/H를 사용한 산술 검산과 실제 안테나 모델의 정확성 검증을 혼동하지 않는다. 원본 event의 cold replay 일치 수치는 기존 실행 영수증이며 이번에 새로 cold 필터를 돌린 수치가 아니다.

근거: [QA](evidence/QA.json), [확장 QA](evidence/EXTENDED_QA.json), [48개 검산](evidence/RECURSION_ARITHMETIC_CHECKS.csv), [모든 저장 시점](evidence/EVERY_SAVED_STEP.csv).

### 전체 기존 평가 재집계

S2/S3 각각 640개 primary 조건 행, 각 20개 평가 시드(10–29)를 다시 집계했다. L2/Native_LoS도 집계에는 포함하지만 48개 원시 배열 전수 검산 범위와 구분한다. 시드는 같은 RF 환경의 센서 실현이며 독립 환경 반복이 아니다.

## 3. F1: 접근 B가 아예 적용되지 않은 버퍼 경계 결함

원본 `S3/history.py`는 패킷과 체크포인트를 모두 `timestamp < now-60`이면 삭제한다. 초기 prior 체크포인트는 index=-1, timestamp=-1로 저장되며, 0번 관측을 다시 처리하려면 반드시 index<0인 체크포인트가 필요하다.

0초부터 이상 구간이 시작됐고 60초에 복구 조건이 충족된 경우, 패킷 0…300은 아직 모두 남아 있다. 그러나 초기 체크포인트는 이미 제거됐다. 재계산 입력을 만들지 못해 `HISTORY_INSUFFICIENT`를 기록하고 기존 foreground 상태를 유지한다. 따라서 이 경우 결과가 같다는 것은 재계산의 무효과가 아니라 **재계산 미적용**이다.

S3 전체 평가의 259개 시도: ACCEPT 230, HISTORY_INSUFFICIENT 28, CANDIDATE_OUT_OF_BOUNDS 1.

**28개 history 실패 전부를 원본 버퍼 코드로 재현했다.**

| 조건 | 영향 시드/arm | 건수 |
|---|---|---:|
| R4 Full, B0 및 L2 | seed 14,15,16,17,19,21 × C_CP,D_CP | 24 |
| R4 Native_LoS, B0 및 L2 | seed 14 × C_CP,D_CP | 4 |

Full 각 조건/arm에서 20개 중 6개, 즉 30%가 복구를 적용하지 못했다. 예를 들어 R4 B0 Full seed14에서 C_CP는 A와, D_CP는 B와 전체 x/P가 동일하다.

### 경계 수정 및 회귀시험

[격리 패치](patches/history_retention.diff)는 60초 경계 바로 앞의 체크포인트 하나를 남긴다. 패킷 보존범위를 늘리거나 빠진 데이터를 만들지는 않는다.

```python
# original
while self.checkpoints and self.checkpoints[0].timestamp < cutoff:
    self.checkpoints.popleft()
# proposed
while len(self.checkpoints) > 1 and self.checkpoints[1].timestamp < cutoff:
    self.checkpoints.popleft()
```

60.0초에는 초기 checkpoint와 301개 패킷으로 재생 입력 생성 성공. 60.2초에는 0번 패킷이 실제로 사라져 여전히 거부. 패킷 누락·설정 해시 불일치·pose ID 변조도 계속 거부한다. 실제 28개 실패 시점 모두 수정 후 history eligibility가 회복됐다.

**28개 후보의 전체 비선형 재계산·채택·성능 개선은 아직 실행하지 않았다.** 버퍼 이용 가능성과 필터 성능 개선은 다른 판정이다.

근거: [28건 명세](evidence/ALL_28_HISTORY_FAILURES_REPRODUCED.csv), [경계 회귀시험](evidence/HISTORY_BOUNDARY_REGRESSION.csv), [전체 시도 판정](evidence/ALL_S3_EVENT_DISPOSITIONS.csv).

## 4. 적용된 접근 B의 재귀 전파는 실제로 반영됐는가?

검사한 48개 trace 중 S3 관련 18개 복구 시도에서 15개가 채택됐다. 15개 모두 retrospective 경로 끝 x/P가 실제 출력과 정확히 같고, 다음 시점의 prior도 수정된 자기 x/P에서 계산됐다.

R4 seed10/20 C_CP는 기준선과 상태가 달라진 시점이 각각 442개이며, 그 이후 441개 시점에서 기준선 prior가 아니라 변경된 자기 prior를 사용함을 확인했다. R5 seed10/20도 수정 상태의 실제 후속 전파가 확인됐다.

따라서 **“접근 B 전체가 이전 prior를 계속 가져다 쓰는 가짜 재귀였다”는 가설은 검사 범위에서 기각**한다. 다만 F1의 미적용 사례, 채택 거절 사례, 새 SourceFFD 평가를 하지 않은 감사 한계는 별개다.

R5 seed14 C_CP는 37.0초에 후보가 생성됐지만 `CANDIDATE_OUT_OF_BOUNDS`로 거절됐다. 원래 기록에는 거절 후보의 x/P와 어떤 항목이 경계를 넘었는지 없으므로, 위치·Heading·gyro-bias 중 어느 제한이 원인이었는지 이번 기록만으로 확정하지 않는다. 이 사례의 checkpoint는 6.0초, Heading 오차 -10.8495도였으므로 되감은 시작 상태가 이미 틀려 있었다는 점은 확인된다.

근거: [채택·체크포인트 원장](evidence/S3_ADOPTION_HISTORY.csv), [전파 검산](evidence/RECURSION_ARITHMETIC_CHECKS.csv).

## 5. F2: C1의 거절→수용 전환 공분산 오류

이전 `verify_c1_selfgate.py`는 counterfactual이 수용되면 원래 저장된 Ppost를 사용했다. 그러나 원래 관측이 거절됐으면 그 Ppost는 Pprior이다. 바뀐 관측이 수용될 때는 `Pprior-K S Kᵀ`를 사용해야 한다.

```python
# incorrect when original observation was rejected
var = Ppost if yes else Pprior
# corrected fixed-prior/fixed-gain yaw projection
var = Pprior - float(kp @ S @ kp) if yes else Pprior
```

총 1,079개 시점의 C1 재검산에서 **19개 시점, 62개 관측 개입 비교**가 영향받았다. Heading 추정은 바뀌지 않고 공분산 및 NEES가 바뀐다. 최대 분산 과대평가 약 17.7%. 이 표본에서 95% 포함/이탈 판정이 뒤집힌 건은 0이다.

R4 2.8초, 편파만 LoS로 교체: Heading 오차 -0.928970도는 동일하고, sigma 1.352957→1.247016도, NEES 0.471449→0.554957로 정정된다.

이 오류는 실제 결함이지만 **이전의 큰 Heading 오류나 S3 실패 전체를 설명하지는 못한다.** 6개 시점의 S 복원 다중근은 버리지 않고 모두 결과에 남겼다. 이 재계산 역시 1D Heading 투영이며 전체 비선형 재귀 개입이 아니다.

근거: [영향 비교](evidence/C1_REJECT_TO_ACCEPT_COVARIANCE_BUG.csv), [전체 근 후보](evidence/C1_CORRECTED_ALL_ROOTS.csv), [정정 요약](evidence/C1_COVARIANCE_CORRECTION_SUMMARY.csv). 정정 구현은 `audit.py:audit_c1`이다.

## 6. F3: 정보량 진단 열 이름이 반대로 저장됨

기존 계약의 conditional은 gyro-bias를 제거한 Schur-complement 지표, marginal은 그 전 3×3 블록 지표를 뜻한다. `Geometry.information()`의 반환 순서와 호출자의 unpack 순서가 달라 두 열이 반대로 저장됐다.

실제 S2 25,884행에서 교환 관계 확인, 최대 산술 차이 4.89e-15. 독립 예제의 진짜 conditional=1, marginal=2가 각각 2,1로 기록되는 것을 원본 코드로 재현했다. 수정 후 1,2가 된다.

반환되는 boolean은 원래부터 Schur 지표로 계산했으므로 **이름 수정 자체는 복구 발동을 바꾸지 않는다.** 이 열을 이용한 기존 기하학 해석은 정정해야 한다.

근거: [정보량 원장](evidence/INFORMATION_LABEL_AUDIT.csv), [격리 패치](patches/information_labels.diff), [QA](evidence/EXTENDED_QA.json).

## 7. 버그 외에 왜 성능 목표를 충족하지 못했는가?

### 7.1 기존 실험은 RF 오염을 정확히 제거한 실험이 아니었다

S1은 관측 가중치를 낮추며, S3는 suspect 시작부터 복구 시점까지 historical weight를 0.25로 설정한다. 이때 Rss는 Rvar의 4배다. 원래 z는 그대로 사용한다. 이번 trace 비교의 z 차이는 최대 4.45e-16, μ 차이는 0이었다.

따라서 S3 실패를 “깨끗한 과거 관측으로 되돌려도 복구 불가능”의 증거로 사용할 수 없다. 정확한 편파 오염 제거와 편파 신뢰도 1/4 처리는 서로 다른 개입이다. 정상 정보를 함께 낮추는 것이 R5 악화의 후보 기전이지만, 그 독점적 기여율은 이번 감사로 확정하지 않는다.

### 7.2 게이트는 수정된 대상 궤적이 아니라 shadow BASE에서 온다

S3는 별도 shadow BASE 필터의 수용 mask를 공통 사용한다. 자기 x/P/h/H/K는 달라져도 수용/거절은 이 mask를 따른다. 이것은 기존 공통-mask 계약에 따른 설계이며 오래된 K를 재사용하는 버그와 다르다.

R4 B0 Full seed10 D_CP에는 자기 NIS는 통과하지만 shadow는 거절하는 패킷 13개가 있었다. R5 seed10 D_CP에서는 26개다. 이 설계의 결과를 모든 게이트까지 수정된 자연 재귀 결과로 해석하면 안 된다.

### 7.3 평균 개선과 개별 시드 보호가 달랐다

아래는 기존 S3 Full/B0, t>=30초의 **시드별 RMSE를 평균한 값**이다.

| 경로 | 기준선 A | 현재 가중치 B | 과거 재계산 C_CP | 결합 D_CP |
|---|---:|---:|---:|---:|
| R4 Heading RMSE, deg | 1.38465 | 1.27763 | 1.29469 | 1.17413 |
| R5 Heading RMSE, deg | 1.79484 | 1.68366 | 1.80647 | 1.66550 |

그러나 paired 비교는 다음과 같다.

| 조건/비교 | Heading 개선 | 악화 | 동일 | 중요 반례 |
|---|---:|---:|---:|---|
| R4 Full B0, B−A | 20 | 0 | 0 | XY는 20/20 악화 |
| R4 Full B0, C_CP−A | 14 | 0 | 6 | 동일 6개는 history 미적용 |
| R4 Full B0, D_CP−B | 14 | 0 | 6 | 동일 6개는 history 미적용 |
| R5 Full B0, B−A | 3 | 17 | 0 | 평균 -0.11118도이나 중앙값 +0.06354도 |
| R5 Full B0, C_CP−A | 1 | 18 | 1 | 한 건은 후보 채택 거절 |
| R5 Full B0, D_CP−B | 2 | 18 | 0 | 평균 -0.01816도이나 중앙값 +0.00787도, XY 20/20 악화 |
| R5 Full L2, C_CP−A | 1 | 19 | 0 | 평균도 악화 |
| R5 Native_LoS B0, B−A | 0 | 20 | 0 | 깨끗한 관측 보호 실패 |

시드가 다른 센서 실현을 공유 RF에서 비교하므로 이를 독립 환경 20회 검정이라고 부르지 않는다. 악화 수는 1e-9도 초과 기준의 방향성이고, 크기와 함께 해석해야 한다.

**결론:** R4는 일부 미적용과 Heading/XY trade-off, R5는 적용 후에도 나타나는 정책상의 악화가 섞여 있다. 버퍼 결함 하나를 고쳤다고 R5 문제가 해결됐다고 말할 근거는 없다.

근거: [전체 그룹](evidence/ALL_EVAL_PRIMARY_GROUPS.csv), [전체 paired 시드 결과](evidence/ALL_EVAL_PAIRED_OUTCOMES.csv), [자기 NIS와 shadow 차이](evidence/OWN_NIS_VS_SHADOW_GATE.csv), [실제 점수 재현](evidence/PUBLISHED_SCORE_PARITY.csv).

## 8. 유효성 판정과 수정 적용 범위

| 주장 | 재판정 |
|---|---|
| 기존 S3는 재귀 재계산을 구현하지 않았다 | 틀림. 구현·실행·채택 후 후속 전파 증거 있음 |
| B가 결과에 전혀 적용되지 않은 사례가 있다 | 맞음. history 실패 28건 및 별도 채택 거절 1건 |
| 전체 기존 평가를 무효로 해야 한다 | 아님. 원래 정책의 운영 결과는 보존하되 미적용과 적용 후 효과를 분리해야 함 |
| current RF 교체 후 오차가 남는 국소 결론 | Heading 값은 유지. C1 분산/NEES 일부 정정 필요 |
| R4에서 recovery가 전혀 도움되지 않았다 | 틀림. B0/L2 Full의 14/20 시드는 Heading 개선 |
| R5 보호 실패는 모두 재귀 코드 버그 때문이다 | 지지되지 않음. 실제 전파가 반영된 조건에서도 악화 |
| 28개 history 수정 후 성능이 개선됐다 | 아직 계산하지 않았으므로 주장 불가 |
| 전체 비선형 h/H와 모든 입력·게이트를 새로 재실행했다 | 이번 작업 범위 아님 |

패치는 `patches/`에 격리했고 원래 S1/S2/S3 구현과 과거 결과를 덮어쓰지 않았다. 차기 수정본의 최소 검증은 28개 history 미적용 사례에 대해 후보 생성·채택·실제 출력·후속 전파를 각각 기록하는 것이다. 동시에 R5 기존 악화 사례를 회귀집합에 남기고, 후보 거절 시 x/P 및 개별 경계 위반값도 저장해야 한다. 새 정책 탐색보다 이 누락 조건과 기존 목적별 판정을 먼저 복구해야 한다.

## 9. 재현 및 보존

[첫 실행](https://github.com/myoungsunk/sionna-resimulation/actions/runs/42015790753) 및 [확장 재감사](https://github.com/myoungsunk/sionna-resimulation/actions/runs/42017208193)가 성공했다. 원본 RT는 새로 실행하지 않았다.

```bash
python -m pip install -r research/FP_EKF_AB_REAUDIT_20261105/requirements.txt
python research/FP_EKF_AB_REAUDIT_20261105/audit.py --offline --out research/FP_EKF_AB_REAUDIT_20261105/evidence
python research/FP_EKF_AB_REAUDIT_20261105/extended_audit.py --root research/FP_EKF_AB_REAUDIT_20261105
python research/FP_EKF_AB_REAUDIT_20261105/finalize_evidence.py --root research/FP_EKF_AB_REAUDIT_20261105
```

`evidence/inputs/`에는 이번 재감사에 사용한 원본 trace, 이벤트, 전체 단계 점수, 소스, Actions ZIP 실물을 보존했다. `audit.py`, `extended_audit.py`, 격리 패치와 모든 계산 CSV/QA/로그도 함께 커밋된다. 대형 원본 RF 전체를 이번 감사에 사용한 것은 아니며, 이 패키지가 연구 저장소 전체 원본의 사본이라는 뜻은 아니다.

`OUTPUT_SHA256.json`은 실행 로그가 닫힌 뒤 최종 생성한다. 최종 manifest 자체를 제외한 보존 파일을 대상으로 한다. 이전 중간 artifact의 실행 중 로그 해시 문제는 최종 패키징에서 별도로 정정하며, 과학 결과를 바꾸지 않는다.
