# 판단값 진단 JSON 저장 결함 — 재실행 전 감사

## 사건과 영향
Run 38527288934 / code 0328b2a9d3f3e9a788dd77dae5e0c8a6fe7b60ac에서 수치 계산 및 조건별 CSV 생성 뒤, READOUT_RESULT.json 저장이 실패했다.
TypeError: Object of type int64 is not JSON serializable.
원인은 pandas groupby의 level key가 numpy.int64인 상태로 by_condition 보고서 목록에 들어간 것이다.

**DIAGNOSTIC_DEFECT_OR_WARNING**: 보고서 JSON/최종 리시트가 불완전한 결함. 이전 독립 모델 수식 검산, 동일한 원시 입력, 이미 생성된 CSV를 소급 무효화하지 않는다. 다만 누락된 JSON의 값을 검산 완료로 주장하지 않고, 이 진단 실행을 한 번 다시 수행하여 저장과 최종 확인을 마친다.

## 소스 변경 범위 감리
수정 소스 commit 05279183d21f316fe22248baabd29ceee4f7d5aa, readout_review.py Git blob 5cc1f4da71d50d540eedea5a6607bf1291d7c46c.
1. 조건 group key만 numpy scalar.item()으로 Python scalar 변환. 수치 값 자체는 동일.
2. 결과 보고서에 이전 실패 run과 export repair 범위 기록.
3. 최종 JSON writer에 allow_nan=False 추가. 비유한 값을 문자열/성공값으로 숨기지 않는다.

model.py, CONTRACT.json, PDF/CDF 수식, 직접 quadrature, Range 입력, posterior weights, prior 확률, 0.95 threshold, 선택 mask, 오차 평가를 변경하지 않는다. 새로운 과학 가설 실행이나 파라미터 튜닝이 아니다.

## 재사용/재검사
- 최초 38526264898의 모델/선형 G2G3 수식 검산: 불변 모델 hash 범위에서 REUSED_VERIFIED.
- 원본 artifact 11875206058 전체 SHA와 추출 파일 SHA 확인을 그대로 유지.
- READOUT_APPROVAL에서 수정된 diagnostic source hash를 갱신한 후에만 실행.
- CDF vs 독립 원분포 적분 검산 1e-8 허용치 그대로.
- 실패 run에서 이미 기록된 DIRECT_READOUT_BY_CONDITION.csv와 재실행 CSV가 바이트 일치하는지 후속 전달 감사에서 확인. 불일치하면 원인 확인 전 동일 결과라고 주장하지 않는다.
- 실패 artifact/run은 보존하며 이전 run을 success로 바꾸지 않는다.

## 결정
GO_WITH_CLAIM_LIMITATION: 동일한 진단을 수정된 보고서 형식 변환으로 한 번 재실행한다. 이 수정으로 인한 계산 결과 재해석/과학적 채택은 허용하지 않는다. 독립 reviewer 없음; 소스 변경 자체 확인 및 기존 독립 계산 경로를 사용하는 검산이다.
본 수정은 허용된 최대 2회 구현/진단 bug repair budget의 1회이다. 전체 비선형 G2/G3 및 재귀 실행은 여전히 NOT_RUN.
