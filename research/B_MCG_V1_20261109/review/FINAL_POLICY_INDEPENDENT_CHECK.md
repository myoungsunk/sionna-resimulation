# 최종 정책 보정 재계산 감사

## 판정

**산술·분할·해시 검증 통과. B_FROZEN 및 B_BIAS_COV의 세 fold는 모두 OFF이며, 활성 정책의 유용성은 입증되지 않았다.** Primary-only 사전검증의 정책 기록과 입력 profile 기록은 최종 실행의 primary 부분과 완전히 같다.

이 검사는 별도 NumPy 배치식과 직접 pose-pair 행렬로 재계산했다. `calibrate_policy`나 `mcg`를 import하지 않았다. 같은 구현 협업팀의 별도 계산 경로 검증이며 외부 기관 인증 또는 별도 데이터 검증을 뜻하지 않는다.

## 확인한 항목

- 최종 lock SHA: `bf84d6ccf948d20556e2cd81dcbef2c10d3350c8806ea6de4956f6acfe164bcd`.
- 두 stratum × 세 fold × 12개 후보 × train/dev의 **144개 후보-partition 집계**를 다시 계산했다. 최대 정규화 수치 차이 **0**.
- 동일 prior의 full update를 별도 배치 Kalman 식으로 계산했다. 원본 상태 최대 차이 **0**.
- 시간 embargo와 전체 5초 history+10초 future support의 near-pose 제외를 직접 pairwise 계산했다. 저장된 **12개 train/dev mask 모두 정확히 일치**했다.
- 각 후보의 두 축 순이득, 좋은 갱신 손실비, actual accepted update activity를 재평가했다. 독립 판정에서도 적합 후보는 0개다.
- 선택된 OFF의 행별 `selected_beta`는 전부 `(1,1)`이며 저장한 lock SHA와 일치한다.
- raw online/evaluator NPZ 6개, 최종 profile NPZ 6개, archive trace 6개, profile config 및 runtime 코드 기록의 해시가 맞는다.
- 보정 코드/`mcg.py`의 실행 전후 SHA가 같고 현재 동결 소스와도 같다.

## 미통과 이유

| Heldout | 남은 train/dev | 최종 판정 근거 |
| --- | ---: | --- |
| R2 | 298 / 267 | 요청한 R4 training partition이 비었다. 한 route만 남았다고 요구를 완화하지 않았다. |
| R4 | 396 / 413 | 두 training route의 양 partition은 남았지만 모든 후보가 두 축·양 partition의 순이득 조건에 실패했다. |
| R5 | 0 / 311 | Training 전체가 purge되어 추정 불가다. |

사전에 정한 τ=2 ACTIVE_RS의 R4 fold 결과는 다음과 같다. 순감소율의 양수는 baseline loss보다 개선, 음수는 악화다.

| Stratum | Partition | 실제 damping | Heading loss 순감소율 | XY loss 순감소율 | 좋은 heading/XY 갱신 lost gain |
| --- | --- | ---: | ---: | ---: | ---: |
| B_FROZEN | Train | 4 / 396 | −0.001148% | −0.003015% | 0.03981% / 0.08231% |
| B_FROZEN | Dev | 1 / 413 | −0.00003670% | +0.001056% | 0.001549% / 0% |
| B_BIAS_COV | Train | 0 / 396 | 0% | 0% | 0% / 0% |
| B_BIAS_COV | Dev | 4 / 413 | +0.015155% | −0.001016% | 0% / 0.06597% |

대표 후보의 lost-gain budget은 5% 이내다. 실패 원인을 단순히 “좋은 갱신을 너무 많이 버렸다”라고 요약하면 부정확하다. 현재 split에서는 개입 자체가 적고, 개입 후 heading·XY 양쪽의 순이득이 함께 유지되지 않는다. S 단독의 τ=2는 두 stratum 모두 train/dev accepted update activity가 0이다.

## 데이터·분할의 한계

1. Heldout의 truth pose는 **offline geometric splitter**가 lock 전에 사용했다. 이것을 runtime 누출과 구분하되, “lock 전에는 heldout truth에 전혀 접근하지 않았다”고 쓰면 틀린다. 정책 ranking에는 training/dev loss만 사용했다.
2. 세 route의 `(gy−Δyaw_true)/sqrt(dt)` 공통 prefix를 재계산하면 최대 차이 `1.552×10⁻¹⁷`, 상관 약 1이다. 시간·공간 purge가 독립 noise seed를 만들어 주지는 않는다.
3. Secondary의 기존 B_BIAS_COV 보정은 guard-heldout route를 다른 training route의 과거 보정에 포함한다. 실제 `fit.train_routes`로 확인했다. 따라서 **nested 독립 검증이 아니며 민감도 비교**로 남겨야 한다.
4. OFF는 기준선을 유지하는 결정이다. 활성 guard가 성공한 증거가 아니다. Same-prior 판정과 실제 재귀·회복 평가는 별도다.

## GitHub 상태에 대한 별도 확인

[B-MCG 실행 #42600632209](https://github.com/myoungsunk/sionna-resimulation/actions/runs/42600632209)는 최종 재조회에서 **completed/success**로 확인했다(`updated_at=2026-11-09T10:37:27Z`). R2/R4/R5 세 job 모두 code/dependency·입력/FFD SHA 검사, source baseline과 diagnostic guard replay, artifact 보존 단계를 성공했다. 이는 실행·검증 절차의 성공이며, OFF로 결정된 활성 정책의 채택 근거를 바꾸지 않는다.

[별도 상속 workflow 실행 #42600630206](https://github.com/myoungsunk/sionna-resimulation/actions/runs/42600630206)은 job 0개로 실패했다. `.github/workflows/powerjoint-separate-rs-model-validation.yml`은 base `a8e76620…`와 현재 commit `e3ddc9fa…`에서 동일 Git blob `3379acf686d41371063b04d84e4336f75f86a054`이며, base64 bytes도 같다. 6,238 bytes, SHA256 `f29f0dbaa57428d5300a81f55f90deb10785f70c2adedfbf0edb694af46cd536`이다.

이 파일에는 top-level `env`에서 `runner.temp`를 사용하는 세 항목(`PJ_SOURCE_ROOT`, `PJ_OUT`, `PJ_BANK_DOWNLOAD`)이 있다. [GitHub 공식 context availability](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#context-availability)는 top-level env의 허용 context를 github/secrets/inputs/vars로 한정한다. 따라서 소스에 workflow validation 결함이 존재하는 것은 확인했다. 다만 현재 connector가 check-suite annotation endpoint를 지원하지 않고 run page를 열 수 없어 **GitHub가 반환한 정확한 annotation 문자열은 확보하지 못했다**. job 0개 실패와 위 소스 결함은 validation 실패와 일치하지만, 서버 오류 문구를 직접 확인했다고 쓰지는 않는다.

Workflow와 runtime은 변경하지 않았다. 근거는 `GITHUB_WORKFLOW_INDEPENDENT_CHECK.json`에 별도로 저장했다.

## 재현 자료

- 재계산 코드: `check_final_policy.py`.
- 수치·분할·해시 상세: `FINAL_POLICY_INDEPENDENT_CHECK.json`.
- 원본 보정 결과: `results/policy_calibration_final/POLICY_LOCK.json`, `REPORT.json`, `CANDIDATE_TRAIN_DEV.csv`, `SPLIT_MASKS.npz`.
