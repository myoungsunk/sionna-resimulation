# Δs 보정 검증: X0a / X1 / X2

2026-10-26 실행 결과를 원본 바이트 그대로 보존한 패키지다. 복도 7 case × B0/L2, Full 채널, 기존 seed 0과 고정 보정값을 사용했다.

| 단계 | 상태 | 읽을 문서 |
| --- | --- | --- |
| X0a | 원본 비선형 결과 재현 14/14조건 PASS | [X1 결과 보고서](x1/RESULTS_KO.md) |
| X1 | 14조건 × 5 Arm 실행 및 수치 검사 완료 | [보고서와 그림](x1/RESULTS_KO.md), [비교표](x1/X1_PAIRED_COMPARISONS.csv) |
| X2 | **STOP_LINEAR_GATE** — 선형 근사 기준 미충족 | [실패 조건과 시계열](x2/RESULTS_KO.md), [판정표](x2/LINEAR_GATE.csv) |

X1: BASE mask를 유지한 Δs 기반 Range 평균 보정은 거리 오차를 14/14조건에서 줄였지만 Heading은 9/14조건에서 악화했다. 신규 수용 패킷에 Range만 적용하면 원래 Δs Arm보다 Heading이 12/14조건에서 개선됐다. 평균 보정과 수용 이력 모두 영향을 주며 gate 단독 원인으로 확정하지 않는다.

X2: t≥30초에서 BASE와 MU_R_EXDS 각각 7/14조건만 선형 근사 기준을 통과했다. 패킷별 기여와 Range–편파 교차항에 의한 상쇄 붕괴 판정은 실행하지 않았다. 정상 프로세스 종료를 과학적 PASS로 해석하지 않는다.

## 보존 범위

- `x1/`: 사전 정의, 소스·입력 해시, X0a/X1 상세 NPZ, 패킷 CSV, 비교표, 그림, 실행·종료 기록, 당시 실행 스크립트.
- `x2/`: 사전 정의, 입력 해시, 28개 선형 진단 NPZ, 정확도 gate, 구현 검사, 그림, 실행·종료 기록, 당시 실행 스크립트.
- 각 폴더의 `OUTPUT_SHA256.json`은 자신을 제외한 원본 산출물의 해시다. `PACKAGING_VERIFICATION.json`은 복사 및 해시 검증 결과다.
- `.npz`와 `.jsonl`은 저장소의 기존 Git LFS 규칙을 따른다. 원본 확보에는 Git LFS 객체가 필요하다.

## 재실행과 해석의 한계

스크립트·receipt의 절대 경로는 당시 Windows 실행 환경을 기록한 것이다. 이 폴더만 받아 실행 가능한 독립 배포 패키지는 아니다. 재실행에는 `INPUT_LOCK.json`의 원본 RF/pose·POWER 표·FFD bank와 원래 수치 환경을 복원하고, 스크립트의 입력/출력 경로를 별도 실행 위치에 맞추어야 한다. 원본 증거 파일을 직접 수정하거나 덮어쓰지 않는다.

패키지의 Git base는 `0686b23ceeefb696bc158b32b39f8077c564ef5d`이다. 실제 MR 재현 소스의 commit/blob은 `x1/source_blob_lock.json`과 `INPUT_LOCK.json`에 별도로 고정되어 있으므로 패키징 base와 실험 소스를 혼동하지 않는다.

Office 확장, 새 학습, R 재보정, Δs 대 d0 직접 비교, X3 이후 실험은 포함하지 않는다. 14조건을 독립된 14개 환경으로 해석하지 않는다.
