# G3 재검사 및 이전 통과 주장 정정 — 2026-10-08

**이전 G3 6개 통과 주장은 무효입니다.** 원래 소스 0d4588f의 검사기는 이번 경로의 `drive` phase를 선택하지 않아 6개 보고서 모두 `stations: 0`이었습니다. 이전 strict/relaxed PASS와 ROUTE_DECISION/FINAL_VALIDATION에 기록된 G3 PASS는 판정 근거로 사용할 수 없습니다. 사용자가 문제를 지적한 뒤 실제 위치 수를 확인하는 최신 검사기로 재검사했습니다.

## 실제 재검사

수정 c92da48을 포함하는 요청 시점 최신 브랜치 commit `8b693825f46a8a2de64a87de09d48bc50a6e5704`를 별도 디렉터리에 받아 원본 `routes-continuity`만 실행했습니다. G3 검사기 이외 관련 paths/corridor/rf_store와 실행 shell의 hash는 기존 소스와 동일했습니다. 트레이스와 원본 S1을 읽기 전용으로 연결했습니다.

| 블록 | 실제 검사 위치 | strict 미매칭 | relaxed 미매칭 | 5e-14 s | 2e-13 s |
|---|---:|---:|---:|---|---|
| R2_aA | 925 | 1 | 0 | FAIL | PASS |
| R2_aB | 925 | 1 | 0 | FAIL | PASS |
| R4_aA | 547 | 3 | 0 | FAIL | PASS |
| R4_aB | 547 | 3 | 0 | FAIL | PASS |
| R5_aA | 1343 | 9 | 0 | FAIL | PASS |
| R5_aB | 1343 | 9 | 0 | FAIL | PASS |

6블록 합계 5,630위치를 검사했고 timeline에서 계산한 기대 위치 수와 모두 일치했습니다. 누락 트레이스 0개, status 비정상 0개, 검사 exit 0입니다. **엄밀 기준은 6개 모두 FAIL**, 사용자가 이전에 승인한 **2e-13 s 기준은 6개 모두 PASS**입니다. 총 strict 미매칭 26개, relaxed 미매칭 0개입니다. 최대 잔차는 약 1.00642e-13 s입니다.

현재 B안 G3 적격성은 승인된 완화 기준에서만 인정됩니다. 엄밀 G3 통과, 경로 물리적 유일성/등가성은 주장하지 않습니다. 경로 집합 변화와 최소 delay 간격 등 상세값은 원본 JSON에 보존했습니다.

## 기존 H·S6와 시간 순서

원본 H 12개 hash는 기존 H_STORE_VALIDATION과 같고 S6 CSV/manifest/분석 37개 파일 hash는 최종 묶음의 manifest와 동일합니다. RF trace/apply/S6는 다시 실행하지 않았습니다. G3 재검사는 저장된 H/S6를 변경하지 않았습니다. 이는 기존 S6 수치가 유지됐다는 파일 무결성 확인이며 물리 모델의 정확성이나 scientific PASS를 입증하지 않습니다.

S6는 **무효한 사전 G3 검사 후 실행됐고**, 이번의 유효한 G3 검사는 **S6 종료 후**에 이뤄졌습니다. 사전 gate 검증 순서가 적절했다는 주장은 하지 않습니다. L1·L2 FAIL은 그대로 유지되고 S6는 진단용 시뮬레이션입니다.

## 증거 보존

이전 JSON/로그/결과 묶음은 `old_invalid` 및 기존 스냅샷에 그대로 보존했습니다. 현재 판정은 이 디렉터리의 새 G3 JSON과 G3_RECHECK_RECEIPT를 사용하십시오. 원본 소스/트레이스/H/S6는 덮어쓰지 않았습니다.

재검사 묶음 SHA-256: `7f7f7766324665d986908688f357e954d793386e13ae64639e71e7cf29c65ee7`. 전송 해시 및 포함된 20개 파일 hash를 검증했습니다. SOURCE_PROVENANCE, START_RECEIPT, 재실행 로그, 새 JSON 6개, coverage 감사 및 H/S6 불변 검증을 제공합니다.
