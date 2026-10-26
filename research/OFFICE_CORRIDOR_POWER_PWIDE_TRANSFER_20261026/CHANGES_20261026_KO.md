# 환경 적응성 평가 코드 수정 기록

기준 커밋: `a744ad07dcf3365e1c1aeb16fc2b53a168ab62b0`.
수정 범위: 이 연구 패키지 안의 구현·시험·안내서. 기존 R2/R4/R5 소스와 결과 및 `lock.json`의 고정 값은 변경하지 않았다.

## 1단계 — 주요 결함

- Office 아카이브를 원본 T2의 `data/` 및 추출 영수증 계약으로 복원하고 재사용 시 파일 목록·크기·SHA-256을 검증한다.
- 검증한 체크아웃과 실제 PJ_SOURCE_ROOT/PJ_ART/PJ_OUT, 가져온 모듈 경로·Git blob을 연결한다.
- 고정 HEAD 외에 작업 파일·스테이징 변경과 추적되지 않은 실행 소스를 차단한다.

## 2단계 — 보완

- 준비 QA→CSV→학습 모델→평가 QA를 해시와 고정 소스 정보로 연결한다.
- 평가 입력은 사전 확정 manifest 해시로 검증하고 종료 직전에도 재검증한다.
- C_POWER는 원본 P2 기준선의 5개 지표와 `1e-7` 미만으로 일치해야 정상 결과를 저장한다.
- Direct-LoS B0 평가를 추가하고, 실제 prior 분포로 보정되지 않은 gate 암은 명시적인 탐색 옵션으로 분리한다.
- 시간·pose 정합성, 유한값, 출력 덮어쓰기 방지, 실행 버전·구현·입출력 해시 기록을 추가한다.

## 3단계 — C_PWIDE

- `fit-corridor --held R2|R4|R5`로 나머지 두 경로만 사용해 학습한다. 평가 경로 라벨은 학습하지 않으며 좌표는 공간 중복 제외에만 사용한다.
- Office와 같은 POWER/HGB 구현, 입력 특징, 중앙값 처리, 내부 경로 OOF 잔차 목표, ±20° 증강 3회 및 난수 시드를 사용한다. Corridor case의 anchor/mount/height는 고정 manifest에서 읽는다.
- 외부 평가 경로와 내부 teacher 검증 경로에 각각 `1e-4 m` 공간 제외를 적용한다. 데이터 부족 시 완화하지 않고 중단한다.
- `C_PWIDE`는 C_POWER 평균·분산을 유지하며 residual만 추가 보정한다.
- `O_POWER_C_PWIDE`는 Office POWER를 유지하므로 `O_PWIDE`와 비교해 PWIDE 학습 환경 변경을 별도로 살핀다. 전체 `C_PWIDE`↔`O_PWIDE` 차이는 POWER 변경도 포함한다.
- 평가 시 다른 held 경로로 학습한 대조군 파일, 해시가 달라진 모델·QA를 거부한다. 기본 6개 암, 탐색 gate 선택 시 10개 암이다.

## 검증

- 최종 `python -X utf8 -m pytest -q -p no:cacheprovider`: **61 passed**, exit 0 (18.91 s).
- `python -X utf8 verify_package.py`: **STATIC_PACKAGE_QA_PASS**.
- `git diff --check`: 통과.
- 신규 `fit-corridor` 명령 도움말: 정상.
- 합성 자료 시험: 원본 T2 pose/receipt 함수 연결, 원본 P2 갱신·채점 기준선 비교, 자료·모델 변조와 잘못된 경로 차단, inner/outer 공간 제외, held 라벨 제외, 실제 case geometry 전달, POWER 평균·분산 유지.

## 아직 확인하지 않은 것

실제 Office 또는 Corridor RF 학습·평가는 수행하지 않았다. 따라서 이 기록은 코드 및 오프라인 회귀시험 통과이며, 실제 기준선 재현이나 환경 전이 성능의 PASS가 아니다.

원본 경로 생성기의 motion 복원 분기는 합성 통합시험 범위 밖이다. 재실행 시 기존 reconstructed_motion이 있는 추출 디렉터리 대신 새 추출 경로를 사용한다. 기존 자료는 보존한다.

gate의 source-only 재귀 prior 보정은 미완료다. Office 3개 경로와 Corridor 경로들은 각각 하나의 장면에 속한다. 표본 수·mount 분포 차이는 남아 있으므로 순수 환경 인과 효과나 독립 장면 반복 결과라고 주장하지 않는다. 실제 실행 전 각 held 경로의 동결 입력 목록과 자료 충분성을 확인해야 한다.

## 4단계 코드 검토 보완
- `freeze_input_contract.py`: target/control SHA manifest를 별도 단계에서 생성. 유일 artifact 파일, 고정 P2 checkout/경로/조건 확인, RF 연산 없음.
- `replay`: Corridor 모델 QA에 저장된 control input manifest SHA와 현재 실제 학습 파일을 재검증하고 종료 전 다시 확인. 불일치 시 중단.
- `O_POWER_C_PWIDE`: 추론 POWER 고정은 맞지만 teacher 대상(`μ_C,inner` 대 `μ_O,inner`)이 달라 순수 학습 환경 효과로 해석 불가함을 명시.
- 추가 합성 contract 테스트 3개는 별도 격리 환경에서 통과. 실제 RF 학습/성능 평가는 미실행.
