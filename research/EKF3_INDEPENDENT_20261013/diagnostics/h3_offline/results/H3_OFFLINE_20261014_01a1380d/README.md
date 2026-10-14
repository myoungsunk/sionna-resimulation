# H3 offline paired experiment — 2026-10-14

## 현재 판정

| 범위 | 실행·검증 결과 |
|---|---|
| 1단계 기하 Jacobian 분해 | 84조건·74,412시점 PASS |
| 2단계 역해·MAP 비교 | 168조건·148,824시점 PASS |
| 3단계 동일 posterior 표현 비교 | 168조건·148,824시점 PASS, 2단계 MAP 차이 0 |
| 4단계 동결 R0 사전 검사 | FAIL_CLOSED: 큰 bias·LoS·B_OLD의 G3 위치 적분 TV 0.387065 > 0.001 |
| 4단계 전체 비교 | 미실행 |
| 학습 RF 오차모델 | R2/R5의 기존 0.5 m 공간 buffer에서 학습 표본 없음 |
| 재귀 융합 | 미실행 — 4단계 gate 통과가 선행 조건 |
| scientific_PASS | false |

3단계는 불확실성 표현 비교다. MAP 점추정·분기 오류를 개선했다고 주장하지 않는다. 국소 Gaussian 유효 시점의 짝지은 비교에서 Full RF 다봉 HPD 포함률은 noise_pair에서 약 90.17%, 큰 gyro_bias에서 약 20.85%다. 전체 시점 지표와 무효 근사 비율은 보고서 CSV에서 별도로 확인한다. 시점 수는 독립 반복 실험 수가 아니다.

4단계 적분 실패를 G3 성능 악화로 해석하지 않는다. 허용치와 RF·센서·LUT·기존 결과를 유지했다. 감사 기록은 자체 검산이며 독립 감사 승인으로 표현하지 않는다.

## 결과 문서

- [1단계 보고서](STAGE1_01/REVIEW_02/SUMMARY_KO.md)
- [2단계 보고서](STAGE2_01/REVIEW_02/SUMMARY_KO.md)
- [3단계 보고서](STAGE3_01/REVIEW_01/SUMMARY_KO.md)
- [4단계 실패 보고서](STAGE4_SMOKE_01/SUMMARY_KO.md)
- [공간 홀드아웃 점검](SPATIAL_HOLDOUT_FEASIBILITY.csv)
- [동결 수치 계약](CONTRACT.json)
- [게시 파일 및 원본 해시](PUBLICATION_MANIFEST.json)

## 보존 및 실행 범위

초기 실패·수정 전 감사·부분 출력도 삭제하지 않고 보존했다. 루트 SUMMARY_KO.md와 FINAL_VALIDATION_RECEIPT.json은 초기 전체 runner가 학습 게이트에서 중단된 당시 기록이다. 현재 단계 판정은 위 표와 각 단계 receipt를 사용한다.

큰 CSV와 셀별 CSV만 gzip으로 포장했다. PUBLICATION_MANIFEST.json의 original_sha256은 압축 전 원본 해시이며, 각 기존 receipt의 CSV 해시와 비교할 때 먼저 압축을 풀어야 한다. 중간 원시 파일·실패 파일도 포함한다. RF 원자료는 이 게시에서 중복 추가하지 않는다.

코드는 실제 실행한 sidecar 원본 그대로다. Windows의 동결 체크아웃·캐시 경로를 참조하므로 GitHub 위치에서 바로 실행 가능하다는 주장은 하지 않는다. 재실행 전에 별도 작업 위치에서 참조 경로와 입력 manifest를 확인해야 한다. 이번 게시 작업에서 실험을 재실행하거나 gate를 수정하지 않았다.
