# SM0 위상 정밀도 수정본

기존 producer.py, postprocess.py, INPUT_LOCK 및 GO, STOP 원시 데이터와 감사는 그대로 보존한다. 새 구현은 이 디렉터리에만 추가한다.

- AMENDMENT_KO.md — 사후 정밀도 계약 개정. 실제 분석 채널은 원본 complex64 per-ray 위상, 그룹 합산은 complex128. 별도 F64 경로 합산 검산.
- qa.py — 원시 계수 재계산, 원본 reduction, 실제 분석 그룹, 포트별 archive 재현, F64 검산 및 실패 게이트.
- producer.py — 원래 producer의 수정본. 새 코드·계약 해시를 GO에 묶으므로 기존 GO로 실행할 수 없다. 실패 원시 데이터도 저장한다. 새 RT 실행 전 별도 독립 GO가 필요하다.
- revalidate.py — 보존 데이터만 읽어 별도 결과를 생성한다. PathSolver/FFT를 호출하지 않는다.
- test_precision.py — 실제 보존 canary와 오염·부적합 입력·구 GO 거부 및 구 postprocess 차단 13개 검사.
- REVALIDATION_001/ — 초기 코드의 수치 재검증 결과. 이후 독립 코드감사에서 구 postprocess가 F64 분석으로 우회할 수 있는 상태값 문제를 지적했다. 결과는 보존한다.
- REVALIDATION_002/ — 감사 지적 수정 후 최종 코드 해시에 묶은 재검증. 새 성공 상태 AMENDED_NUMERICAL_PASS를 사용해 구 postprocess가 거부하도록 한다. 원래 STOP은 변경하지 않는다.

초기 수정본 시험에서 original32 reduction의 불일치를 탐지했다. per-ray field 값은 같아도 배열 stride에 따라 NumPy reduction의 반올림 순서가 달라질 수 있어, 원본의 C-contiguous [RX,TX,path] 메모리 배치도 복원했다. 이 실패는 수정 중의 오프라인 검사이며 새 RF 실행은 없었다.

이 수정은 신규 14개 pose, 후처리 또는 C1–C3를 실행한 결과가 아니다. 과거 ray 계수 부재에 따른 완전한 경로 동일성의 한계도 유지한다. 새 postprocess 연결과 신규 생산 GO는 후속 실행 전 검토 대상이다.
