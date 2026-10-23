# BASE 보존형 RF 식별성 검증 코드 v2

**구현 및 합성 단위시험 패키지입니다. 이 커밋에서 실제 RF 재귀, 실제 데이터 학습, S0–S7 수치 실험은 실행하지 않았습니다.**

원 계획: `BASE_RF_IDENTIFIABILITY_PLAN_V2_KO.md` (SHA256는 `manifest.json`).
원본 기준: `0686b23ceeefb696bc158b32b39f8077c564ef5d`.
원본 연구 브랜치와 자료는 변경하지 않습니다. 기존 `src` 계열을 대체하지 않는 별도 연구 모듈입니다.

## 구현과 검증의 구분

| 단계 | 실행 진입점 | 구현 내용 |
|---|---|---|
| S0 | `stages.run_s0` | 원본 해시·관측 재추출·중간 상태/gate·MC 요약 parity, process 잡음 분리 |
| S1 | `stages.run_s1` | 현재 NOES 잔차와 과보정, c1/c2/c_model, 모집단·부호 지속성 |
| S2 | `stages.run_s2` | 동일 RF의 prior perturbation, profile projection·유효 rank·mask |
| S3 | `stages.run_s3` | 여섯 후보, POWER 조건/teacher 정합성, nested group OOF·누수 계보 |
| S4 | `stages.run_s4` | 같은 prior·공분산·gate의 한 번 갱신과 손실 항등식 |
| S5 | `stages.run_s5` | 실제 packet/block 분기, 이후 BASE 재귀, 긴 horizon·검열·4-state 예산 |
| S6 | `stages.run_s6` | 자연 궤적에서 bias 모형·nuisance 식별성·비선형 다중해 진단 |
| S7 | `stages.run_s7` | 완전 paired 평가, LoS, eta2, 정확도·꼬리·포함률·일관성·실패 표 |

S6은 조건부 탐색입니다. 시간 필터를 자동 설치하거나 좋은 rank만으로 운용을 승인하지 않습니다.
`PASS` 실행 영수증은 계산/구현 무결성 판정이지 연구 가설의 성공 판정이 아닙니다.
연구 결과는 SUPPORT / CONTRARY / INCONCLUSIVE / BLOCKED로 별도 기록합니다.

## 파일 구조

- `common.py`: observable-only Packet, 불변 입력, exact join, 체크섬과 단계 영수증.
- `native.py`: 원본 SourceFFD·센서·POWER·observer를 읽는 지연 로딩 어댑터.
- `runtime_features.py`, `replay.py`: GT에 접근하지 않는 특징과 실제 재귀.
- `training.py`: train-only POWER teacher·잔차 학습·imputer·Omega 및 계보.
- `diagnostics.py`, `temporal.py`, `oracle_scoring.py`: 진단·반사실·truth 전용 채점.
- `scorecard.py`: case별 paired 통계. 실패/누락을 삭제하지 않음.
- `stages.py`, `cli.py`: 단계 실행과 실패 시 중단.
- `audit.py`, `tests/test_protocol.py`: 구현 감사와 합성 계약시험.
- `AUDIT_KO.md`, `manifest.json`: 감사 수정 내용과 요구사항–시험 대응표.

## 안전한 코드 감사

저장소 루트에서 구성 예시를 복사하고 `work_dir`을 새 출력 폴더로 바꿉니다.
코드 감사에는 원 RF 파일이나 원본 SourceFFD를 불러오지 않습니다.

```bash
cp research/PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023/config.example.json /path/to/config.json
python scripts/base_rf_identifiability_v2.py audit-code --config /path/to/config.json
python scripts/base_rf_identifiability_v2.py plan --config /path/to/config.json
```

코드 감사만 할 때는 `{"work_dir":"/absolute/path/to/new-audit-output"}`만 있는 구성 파일도 가능합니다.
`AUDIT/IMPLEMENTATION_AUDIT.json`, 단위시험 로그, `AUDIT_STATUS.json`이 생성됩니다.
코드·manifest·설정이 바뀌면 이전 감사 영수증을 재사용할 수 없습니다.
원본과 출력 폴더가 겹치면 중단합니다.

## 실제 데이터 실행에 필요한 준비 — 이 커밋에서는 수행하지 않음

1. 원본 기준 SHA의 별도 **clean detached worktree**를 `reference_root`로 준비합니다.
2. 기존 원본 source/RF snapshot, 검증된 FFD banks, final trace, L4 모델, P1R GRID를 각각 지정합니다.
   기존 출처: run 39256621315 / 38875080492 / 39376076166 / 39893308814 및 원 P1R GRID artifact.
3. Python 3.11과 `requirements.txt`의 고정 과학 패키지 버전을 사용합니다.
4. 모든 입력은 기존 공급 파일을 사용합니다. 이 코드에는 다운로드·ray tracing·Actions dispatch가 없습니다.
5. integrity lock을 생성하고, 원 artifact의 출처·SHA를 별도로 확인합니다.

```bash
python scripts/base_rf_identifiability_v2.py inventory --config /path/to/config.json --lock-out /path/outside-inputs/input-lock.json
```

lock은 공급 파일의 무결성 목록이지 출처의 진위를 새로 증명하는 것이 아닙니다.
원 RF는 historical input manifest의 SHA와도 비교합니다. `asset_lock` 설정 후 감사를 다시 실행합니다.

명시적인 RF 실행 승인이 있을 때만 다음 형태를 사용합니다.

```bash
python scripts/base_rf_identifiability_v2.py stage --stage S0 --execute-rf --config /path/to/config.json
```

`--execute-rf`를 생략하면 원본 import 전에 중단합니다. S0 이후 S1/S2 → S3 → S4 → S5 → S7이 primary이며 S6은 별도 조건부 진단입니다. 각 단계는 선행 영수증·출력 체크섬을 확인합니다.
과학 패키지 버전이 다르거나 원본 파일이 빠지면 BLOCKED입니다. 원본 CSV 평균으로 빠진 trajectory/P를 추정하지 않습니다.

## 비교 조건

- 고정 RF/control/초기값. 분기 뒤의 d0/H/K/P/gate는 각 상태에서 재계산합니다.
- 후보 보정은 POWER 이후의 추가 보정입니다. WIDE total correction은 incremental로 명시적으로 변환합니다.
- BASE_eta2는 **갱신 R만 두 배**, gate R은 원본 그대로입니다.
- heading·위치 단위가 다른 값을 임의 합산하지 않습니다.
- GT/LoS/fp_shift는 라벨·진단·ORACLE에만 사용합니다. u_perp는 보정기 입력이며 독립 관측으로 중복 동화하지 않습니다.
- 4배 IFFT padding 탭은 상관된 특징입니다. 단순 탭 수를 정보 수로 쓰지 않습니다.
- 내부 그룹 검증이 표본 부족이면 BLOCKED를 남기며 outer 결과로 후보를 선택하지 않습니다.
- 7×2×12 중 일부만 설정한 경우 partial scope를 명시합니다. 원 계획 전체가 완료됐다고 표시하지 않습니다.
- 95% CI가 0을 가로지르면 INCONCLUSIVE입니다. 승인된 허용 악화폭이 없으므로 margin은 0입니다.

## 남아 있는 확인

실제 RF 입력의 모든 parity, 실제 SourceFFD의 극점/FP switching, 파일 staging 완전성 및 후보 성능은 실행하지 않았습니다. 구현 감사와 합성 시험 통과를 이를 대신하는 증거로 쓰지 않습니다. `AUDIT_KO.md`의 수정과 제한을 함께 읽어야 합니다.
