# PALO heading oracle — 현 상태 분석 및 정확 폐루프 실행기

- `REPORT_INTERIM_KO.md`: GitHub `4c43020`을 기준으로 검산된 단일 갱신 오라클 결과 및 성능 악화 메커니즘.
- `palo_oracle_closedloop.py`: 정확한 frozen LUT를 호출하는 **폐루프 실험 코드**. 현 실행 환경에서 frozen LUT 전체 바이너리를 확보하지 못해 구문 검사만 수행했으며, 비선형 재귀 실험은 아직 실행되지 않았습니다.

사용법은 `REPORT_INTERIM_KO.md` 5절 참조. 실행기가 원본 S4 상태·공분산·NIS·게이트와 일치하지 않으면 fail-closed로 중지합니다. 결과는 새로운 경로에만 저장하고 기존 GitHub 데이터는 수정하지 않습니다.
