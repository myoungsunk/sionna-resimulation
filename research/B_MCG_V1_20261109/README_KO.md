# B-MCG v1 — 구현 전 검증, 원인 감사, 연구용 구현

**기본 정책: OFF / 운영 채택 보류.** 구현과 재현 검사의 통과는 성능 채택과 다릅니다.
사용자 지시에 따라 B만 사용하며 K1/K2 및 새로운 FP 재선택은 사용하지 않습니다.

## 현재 의사결정

최종 소스의 B_FROZEN 사전검증에서 R2/R4/R5 모두 active 정책을 선택하지
못했습니다. R2·R5는 엄격한 support/near-pose 제외 후 필요한 학습 분할이
비었고, R4는 선언한 12개 후보 중 train/dev 양쪽의 heading·XY 순이득,
활동량, 좋은 보정 보존 예산을 함께 통과한 후보가 없었습니다.
`POLICY_LOCK.json`은 이 primary 선택을 동결합니다. `ACTIVE_POLICY.json`은
기본 OFF를 명시합니다. 보정된 B_BIAS_COV는 기존 보정값을 고정한 별도
민감도 조건이며, nested 독립 route holdout으로 해석하지 않습니다.

`ACTIVE_R`, `ACTIVE_S`, `ACTIVE_RS`는 사전 선언된 τ=2 연구용 대조군입니다.
이 대조군의 실행은 선택 정책의 운영 활성화가 아닙니다. `NAIVE_YAW_CLIP`
이라는 기존 CLI 식별자는 실제로 출력 heading을 자르지 않으며, prior에서
계산한 trial 보정각 문턱으로 양 관측을 감쇠하는 부정 대조입니다.

## 구현

- `mcg.py`: immutable pre-RF anchor, raw ds/gyro 적분, 4개 공통 nuisance,
  history-only profile, exact SourceFFD 검사, 채널별 비정합성 점수,
  UNKNOWN, PSD 대각 추가 및 채널 제거 Joseph adapter.
- `experiment.py`: runtime 입력 whitelist, 기존 raw B shadow 보존,
  same-prior trial/actual 분리, 자체 상태의 실제 재귀와 hash-locked traces.
- `calibrate_policy.py`: route/시간/near-pose support 분할, 사전 후보,
  좋은 보정 손실 예산, 두 손실 축 독립 판정, 선택 후 heldout 평가.
- `run_arm_grid.py`: 사전 검증 이후 OFF/OBSERVE_ONLY/ACTIVE_R/S/RS,
  DR_ONLY, naive 부정 대조의 독립 재귀 실행.
- `ci_route.py`: 각 route에서 두 보정 조건의 기준선/OFF/고정 ACTIVE_RS를
  GitHub Actions로 재현. Green CI는 실행·수치·재현 통과만 의미합니다.

## 검증 및 발견한 원인

`INPUT_AUDIT.md`, `P3_PROJECTION_AUDIT.md`, `INDEPENDENT_CODE_AUDIT.md`,
`SOURCE_STRESS_AUDIT.md`, `AMENDMENT_001_PROFILE_VALIDITY.md`에 증거와 한계를
분리했습니다. 검증 코드는 `precheck_*`, `audit_*`, `stress_source.py`,
`synthetic_adversarial.py`, `test_mcg.py`, `test_calibration.py`입니다.

현재 B0 데이터의 실제 gyro bias는 0인데, RF 혁신이 bias 추정치를 바꾸어
운동 기준에도 오차가 전달되는 경로를 전수 항등식과 원본 SourceFFD 재귀로
확인했습니다. 같은 noise seed와 초기오차를 공유하므로 세 route를 독립
noise/scene 반복 실험으로 세지 않습니다. 독립 wheel heading은 archive에
없습니다. `ds`와 gyro 적분각 `gy`를 사용합니다.

잘못된 과거 RF 정렬이 정상 복귀를 억제하는 반례도 검사했습니다. 초기의
일부 실패는 finite nuisance 후보 누락 때문이었고 수치 검사를 보강했습니다.
그 뒤에도 다른 회복 사건에서 허용 후보 누락을 발견했습니다. 따라서
유한 탐색이 모든 허용 정렬을 포함한다는 보증은 없고, 작은 후보 spread나
작은 innovation을 실제 위치·heading의 정확성으로 해석할 수 없습니다.

## 재현

Python 3.12, NumPy 2.3.5, SciPy 1.17.0을 사용합니다. 원본은
`c141839093d1a2e4a76f91eea632cb6467163e28`, 인과 감사 수리는
`beb845665661ad8c68d07c88f6d268da4832e493`, 기존 B 보정은
`a8e76620b9f805b8e16d4525312c7a69b247306e`입니다.

```bash
python research/B_MCG_V1_20261109/test_mcg.py
python research/B_MCG_V1_20261109/test_calibration.py
python research/FP_NATIVE_B_CAUSAL_ABLATION_20261108/acquire_inputs.py --out /tmp/fp-release-assets
python research/FP_NATIVE_B_CAUSAL_ABLATION_20261108/stage_inputs.py --repo . --assets /tmp/fp-release-assets --out /tmp/b-mcg-stage
python research/B_MCG_V1_20261109/acquire_archive.py --out /tmp/b-mcg-reference
python research/B_MCG_V1_20261109/ci_route.py --route R2 --archives /tmp/b-mcg-reference/extracted/tmp/fp-b-calibration --out /tmp/b-mcg-R2 --policy-lock research/B_MCG_V1_20261109/POLICY_LOCK.json
```

Historical Actions artifact가 만료되면 `acquire_archive.py --archive`에
동일 SHA의 사용자 보관 ZIP을 지정합니다. 큰 원본 NPZ/FFD는 Release 경로,
크기와 SHA를 고정했고 Git에 새로 복제하지 않습니다.

각 실행은 현재 소스 및 config 해시, input/archive 계보, 실제 trace, 오류를
기록합니다. Truth/clean CIR는 evaluator·진단 코드에만 있고 runtime monitor
인터페이스에는 없습니다. 결과 누락·빈 분모·baseline 회복 censoring은
0이나 PASS 대신 NOT_ESTIMABLE/NOT_VERIFIED로 표시합니다.
