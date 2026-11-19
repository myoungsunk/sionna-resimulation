# 기준선 불일치 상태의 사용자 승인 탐색 실행

- 질문: IPALO-FAR-KRIGING-AB-20261119 / AUTHORIZED-EXPLORATION-01.
- 역할: IMPLEMENTER 및 자기 검사. 독립 감사·과학적 채택 아님.
- 선행 커밋: `d19d4853460de49e87850dc9b919ab469531cfc7`.
- 사용자 지시(2026-11-19): **“우선 그냥 진행하도록 해”**. 기준선 미통과 보고 이후의 명시적인 계속 실행 지시로 적용한다.
- 기존 계약의 기준선 실패 시 중단을 이번 탐색 실행에 한해 변경한다. 원래 `1e-8` 허용치, 실패 판정, 과거 증거는 유지한다. 일반 `smoke/explore` 실행의 기본 중단 동작은 유지한다.
- 적용 지침: 기존 실험이 고정한 `gm_theta_m6/inputs/COMMON_CONTRACT.md`, `ROLE_IMPLEMENTER.md`를 따른다. 이번 사용자 지시가 본 실행 진입 게이트만 재정의한다. 파일 해시는 실행 영수증에 기록한다.

## 실행 정의

원래 `krige_online.py`를 양쪽에 사용한다. 결정적 동률 처리 수정안은 적용하지 않는다. 기준 F2SKRWV의 `<6 m`와 시험 F2SKRWV_FAR_K의 `<10 m` Kriging 선택 외의 평균·분산·필터·평가 정의를 유지한다. 같은 복원 입력, B0/L2_GYRO_ARW, seed 30–49, R2/R4/R5를 사용한다. 40조건별 H2/H2S/F2SKRWV/FAR 12개 trace를 보존한다. 추가 seed 또는 독립 환경을 만들지 않는다.

`run_far_kriging_ab.report_one`의 명시적 keyword 옵션만으로 기준선 불일치 기록 후 진행한다. 원래 호출은 기본값 False라 중단한다. 별도 `run_authorized_exploration.py`에서 승인 확인 옵션과 별도 출력 경로를 요구한다. 입력 누락, 비유한 값, 조건/시각 불일치 등은 계속 실패 처리한다. 원본 데이터는 읽기 전용 mount로 보존한다.

40개 결과·2400개 기준선 scalar·480개 trace의 완전성/고유성/유한성, 입력·출력·코드 hash, 실행 환경/명령/종료 상태를 확인한다. 원래 집계의 `condition_pass`는 이번 출력에서 `descriptive_thresholds_met`로 이름을 바꾸고 `scientific_adoption_pass=False`를 명시한다. 결과를 보고 허용치나 성능 규칙을 조정하지 않는다.

허용 주장: 복원 환경과 동일 입력의 탐색적 paired 성능 차이. 금지 주장: 원래 기준선 재현 성공, 수정안 채택, 독립 확인/독립 감사, 일반화된 성능 개선. 기준선 불일치와 사후 게이트 변경은 최종 보고서의 첫 부분에 남긴다.
