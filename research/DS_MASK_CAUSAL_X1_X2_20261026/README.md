# Δs 보정 검증: X0a / X1 / X2

## 추가 결과: 비선형 개입 실험 E1–E4 (2026-10-27)

[결과 보고서와 그림](e1_e4/RESULTS_KO.md) · [196개 조건–Arm 전체 지표](e1_e4/ALL_METRICS.md) · [사전 실행 계획](e1_e4/PROTOCOL.md)

X2의 선형 근사 실패 후 승인된 비선형 개입을 순서대로 수행했다. E1–E4는 아래 원래 X1/X2와 별도의 후속 실험 번호다. 재현·수치 비교 1,483개와 단계별 검사를 통과했으며 60개 상세 trace를 보존했다.

- E1: 대상 6조건 모두 보정 강도에 따라 Heading 편향 크기가 단조 증가했다.
- E2: 상수 편파 편향 제거 후에도 signed bias 차이가 대부분 남았다. R4_aA에서 약 33–34% 감소했다. R2_aA_m45의 RMSE 차이 감소와 signed bias 차이 잔존을 구분한다.
- E3: 직접 Range→ψ/b_g 갱신 차단은 대상 6조건의 signed bias 차이를 충분히 해소하지 못했다.
- E4a: R5_aA 신규 편파-only 추가는 BM 악화량의 40–45%를 재현해 사전 70% 기준에 미달했다.
- E4b: R2_aB 네 패킷 복원 후 RMSE는 MB에 가까워졌지만 signed bias 차이 약 0.028°가 남아 사전 복귀 기준은 미통과다.

기술 검증 통과를 C8/C9의 단일 원인 확정으로 해석하지 않는다. 원본 90개 후속 산출물은 `e1_e4/`에 바이트 단위로 복사했으며, 이 추가 패키징 검증은 `E1_E4_PACKAGING_VERIFICATION.json`에 기록했다. 후속 실행 스크립트의 절대 경로도 당시 로컬 실행 환경을 기록한 것이므로 재실행에는 입력 복원이 필요하다.

## 기존 X0a / X1 / X2 결과

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


## 물리량 단위 기하 진단 A0″ / A / C 및 B 중단 (2026-10-27)

[결과와 시각화](geometry_physical/RESULTS_KO.md) · [고정 정의](geometry_physical/PROTOCOL.md) · [기하 차단 관측모델](geometry_physical/geometry_model.py) · [검증 기록](geometry_physical/REPORT_VALIDATION.json)

A0″·A·C 완료. 주 분석 6조건의 CUT_ALL Heading signed-bias gap 크기는 71.81~98.26% 감소했다. R4 두 경로는 방위각 단독 차단에서도 70% 기준을 넘었다. 이는 GT를 사용한 oracle 개입이며 이후 공분산/gain 변화도 포함한다. 기술적 위치 등가 오차와 인과 개입을 구분하며, B0/L2를 독립 표본으로 세지 않는다.

B는 B0/L2의 BASE 수용 집합 차이로 조건별 평균 c가 달라 사전 동일성 검산에서 중단했다. B sweep은 실행하지 않았고 기준을 변경하지 않았다. STOP_B_PAIRED_CONSTANT_GATE를 전체 실험 성공으로 해석하지 않는다.

원본 h_s: research/FFD_P0P3_20261016/source_model.py의 SourceFFD.spectrum / batch. 새 구현은 방향 u와 거리 r를 물리량 단위로 교체하며 태그/앵커 양쪽에 동일한 u를 적용한다. 코드와 입력의 로컬 절대 경로는 실행 당시 provenance를 위해 보존했다. 이 폴더 단독으로 실행 환경/외부 입력 전체를 제공하는 것은 아니다.

GEOMETRY_PACKAGING_VERIFICATION.json은 새 결과 파일의 byte-identical 복사를 확인한다. 기존 X1/X2/E1–E4 원본 결과는 보존했다.

## Component sweep and azimuth transplant (2026-10-27)

[Scoped final report](component_azimuth/RESULTS_KO.md) | [Protocol](component_azimuth/PROTOCOL.md) | [Validation](component_azimuth/REPORT_VALIDATION.json)

B resumed with each case/bias own BASE mask. Primary six conditions completed; both transplant directions exceed 0.7 under both denominators. Component effects differ by route; secondary conditions remain a separate track. Earlier B-stop artifacts are preserved.

Two previously committed Python cache files are removed. [Declared cache exclusions](CACHE_EXCLUSIONS.json) reconcile the preserved original geometry output manifest with the published package. Bytecode is ignored.

## Tangential ledger and CUT_ODO (2026-10-27)

- [Step 0/1 trace-only recalculation and exact increment ledger](tangent_ledger/RESULTS_KO.md): 78 checks passed; includes rotating tangent basis term.
- [CUT_ODO replay](cut_odo/RESULTS_KO.md): 364 checks passed, including E1 OFF parity. Position propagation uses previous GT starting heading; gyro-bias position path remains.

Azimuth gaps remain in all six primary conditions. Results are scoped to the recorded interventions; CUT_RT was not run. Original artifacts are preserved.
