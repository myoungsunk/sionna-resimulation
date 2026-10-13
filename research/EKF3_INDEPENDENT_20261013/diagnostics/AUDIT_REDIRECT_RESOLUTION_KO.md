# D6–D9 REDIRECT 코드 감사 대응 기록

기준 감사 커밋: `4d5d726f8e9ce8c267db7f7dc981ac8de94b31e6`. 이 문서는 **코드 변경 사항과 재감사 필요 조건**을 기록한다. 실 RF 전체 실행 또는 과학적 성능 통과 증빙이 아니다.

| 지적 | 조치 | 회귀/증빙 | 남은 제한 |
|---|---|---|---|
| A1 `motion_increments` import | 공통·D6 bias·D9 모두 동결 `sensor_v2`로 수정 | 신규 entrypoint import 수집 테스트 | 실제 저장소 환경 pytest 필요 |
| A2 `WindowsPath` JSON 직렬화 | `json_safe` whitelist, 비정상 타입 실패, CSV/manifest 임시저장→원자적 게시 | `test_d6_d9_contracts.py`, 경로·NumPy 타입, 미완료 매니페스트 비생성 테스트 | CSV가 일부 생성되어도 manifest 미존재 시 INCOMPLETE |
| A3 E1/B_OLD residual 불일치 | D7 동결 LORO E1 잔차 별도 생성, D8 보정별 range label + mean/centered R, D9 엄격한 모델 계약 검사 | target mismatch 강제 실패 테스트 | R0 및 추정 분산의 독립 장면 calibration 미확정; Q3은 exploratory only |
| A4 prior/post 혼동 | D6 RF update 직전 `Pprior`, 업데이트 직후 `Ppost` 분리, D9도 prior/post 구분 | 단계별 trace/집계 스키마, F0 회귀 테스트 | 사용자 D6 실제 출력 확인 필요 |
| A5 계획 미구현 | 원본 D5 trace 해시/NEES 독립 감사, D6 2D타원/해석적 2차 모멘트/왜도, wheel yaw 대체대조, 기하 mismatch CSV, D8 phase evidence gating, D9 P95/NIS lag1, 가설별 verdict | 신규 D6 audit/verdict 모듈 및 테스트, 문서화 | SE2 truth 대체시 기존 RF H는 재생성하지 않음; 새로운 독립 scene 확증 아님 |
| A6 baseline·provenance 불충분 | 기존 EKF3 직접 비교, 원본 5파일 blob SHA 검증, 요청 F0 셀 누락/중복·RMSE·NEES·gate 건수 검사, 실행 Git commit과 코드 SHA 기록 | 독립 original EKF3/F0 단위 테스트와 D5 parity 부정 테스트 | 실제 D5 RF parity는 사용자 실행 필수; 임의 seed는 별도 NOT_RUN parity |

## 중요한 추가 계약

- `--use-trained-rsr`는 **차단**. D8에서 학습 route의 보정별 잔차 공분산은 기록하나 독립 Rsr calibration으로 인정하지 않는다.
- D8 기본 Q4는 **NOT_RUN**. 사용자는 독립 수신 위상 보정 및 noise floor의 원본 파일 + 해시를 제출해야만 실험적으로 평가 가능하다.
- Q3 개선은 LoRo 단일 복도 내 탐색 gate일 뿐, D9 F3–F6 품질 모델의 독립 scene 성능을 승인하지 않는다. heldout gate 실패 시 기본 D9은 fail-closed, 명시적 `--exploratory-unvalidated-quality`만 실험을 허용한다.
- 기존 D5 전체 trace가 없으면 D6-0은 `NOT_RUN`, 가설 verdict는 `INCONCLUSIVE`로 보고한다.
- 테스트 또는 소규모 synthetic 실행을 통과해도 `scientific_PASS=false`; 본 커밋에는 대규모 RF 실험 결과가 없다.

## 이 코드 변경의 검증 범위

- 파이썬 모든 진단/테스트 파일의 `py_compile` 및 AST 정적 검사는 수행 가능.
- 외부 원본 프로젝트 자산을 사용하지 않는 **격리 helper 검사**에서 JSON/path serialization, E1/R 학습 계약, covariance mismatch fail-close, D5 누락 비교 셀 오류 처리를 검증했다.
- 동결 original EKF3 기반 통합 pytest, D6–D9 전용 runner smoke, 기존 D5 Full RF parity, D6 D5 trace 원본 재계산은 **사용자 수행 전 `NOT_RUN`**.

## 재감사 판정 원칙

`code_audit=REDIRECT`, `execution_ready=false`, `D6_D9_full_experiment=NOT_RUN`, `scientific_PASS=false` 유지. 원본 의존 환경 테스트, Full route 결과/trace/manifest 수집과 독립 감사 후에만 REDIRECT 해소 여부를 판정한다.


## 추가 재감사 수정 (2026-10-13)

D9의 `.01` 초기 분산을 원본 `.1**2` 값인 P0_COV 복사로 교체했다. 원인 분리에서 이 변경만으로 실패 셀 네 arm의 NEES 차이가 모두 0이었다. 허용치 1e-8 유지.

E1은 동일 outer 경로 제외 계수로 모든 내부 학습/외부 평가 라벨을 계산하고 계수 해시·경로 계약을 검사한다. H3는 Q0와 Q1을 모두 비교한다. 동결 모델군 선정의 scene 의존 한계는 유지한다.

독립 소스 재감사 ACCEPT. 실제 실행 재검증과 GitHub 게시 증빙은 results/의 해당 실행 보고서 및 manifest에 기록한다. scientific_PASS=false 유지.
