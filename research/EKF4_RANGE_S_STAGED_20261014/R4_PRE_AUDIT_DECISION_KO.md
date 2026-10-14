# R4 — 16개 P2 전체 실행의 수치 미수렴과 고정 검사

GitHub [run 38538726484](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38538726484)에서 P0/P1/R1/R2와 P2 대표 6셀 PASS, 원 P2 전체 600개×4모델 = 2400 모델 호출 중 2384 성공/16개 `LINE_SEARCH_FAILED`. 모델별 100회의 완료를 사후 선택하지 않는다. 동일 전체 커밋 `94a14b1a62dd360dff72c8852d0011bf11edaea2`의 artifact `11881761247` SHA256 `f80f9f749da08e3abd9c14e2e0241ba956cd4cae3f9935ec7815a966a39d60bd`를 고정한다.

원인 진단: 16개 실패는 이미 가깝게 수렴한 `||grad||∞ ~1e-8~1.5e-7`에서 매우 작은 감쇠 fraction 또는 직접 비용 비교의 부호 반전으로 종결하지 못함. D3 네 사례는 독립 80자리 GN full step 감소와 종결성을 확인. 새 16개가 같은 원인인지는 **회귀시험에서 각 원시 입력을 별도로 확인하기 전에는 확정하지 않는다**.

**수정 범위:** 같은 `J(y)=0.5(||y||²+||Lr^-1(z-h(mu+Lp y))||²)`, Q/R·seed·RF 전방모델, 80회/gradient 1e-8 유지. R3 terminal check의 `abs(new_cost-cost)≤256eps`라는 실제 비용 감소와 무관한 과도한 조건을 삭제하고 스텝 최대치만 1e-5→1e-4로 넓힘. 종결 승인에는 **원래 gradient 기준**, gradient 감소, d·grad 방향 감소, 3점 Simpson과 gradient trapezoid의 동의가 여전히 필요. 매우 작은 스텝 이외 direct Armijo에는 양수 roundoff 여유를 허용하지 않음.

**감사·실험 단계:** 정확 소스/계약/기록 SHA 감사 → P0/P1/R1/R2 → 아카이브 원본 16개에서 R4 고정 회귀(각 original prior/z/R만 사용) → 대표6 → full600. R4 고정 회귀에서 하나라도 실제 수치 상태/코드 결함이 남으면 전체 P2는 보류, 실패 사례 원인 진단. 이 테스트는 직접 관측의 independent signed RF 연구/실 FFD 검증이 아니며 R3 결과를 소급 고치지 않는다. 성공 후에도 `scientific_PASS=false` until independent RF scene/data model validation.

**주의:** 현재 수정은 일반 비선형 모델의 전역 수렴 증명이 아니다. 'terminal branch 통과' 자체가 과학적 정확성의 근거가 아니라, gradient와 원래 목적함수·공분산에 대한 추가 검사로 평가한다.
