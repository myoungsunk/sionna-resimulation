# R3 실행 전 소스 감사 및 결정 (2026-10-14)

기준: 2781ee299f6908399acbb6bec91efb6e81cdc366. 범위는 기존 동결 synthetic P2와 사전 R1/R2/P0/P1 gate, 해당 cloud workflow. **이 문서는 실행 결과가 아니며 PASS 주장이 아니다.**

## 무효화 가능 결함 및 조치
1. HARD_NUMERICAL_CASE: `core.map_update`의 `new_cost <= cost + armijo + roundoff`는 비용 증가·감소 불명 스텝을 정상 수용할 수 있음. `integrated_descent`를 건너뛰고 작게 감쇠된 스텝을 반복하는 문제를 확인. R3는 direct acceptance에서 양수 roundoff 허용을 삭제하고, 32eps를 넘어서는 음의 double ΔJ + 원 Armijo 조건 모두 만족해야 직접 수용. 아니면 적분 검사로 전환.
2. CASE_RESULT_INVALID: 실패 네 건에서 수렴 기준 1e-8 미충족; 원 결과를 수정/보정하지 않고 그대로 보존. R3의 국소 진단 실패는 `NUMERICALLY_STALLED`을 명시적으로 반환; 더 낮은 gradient tolerance나 성공 대체 없음.
3. 잠재 수치 이슈: 정확 Hessian≠GN. 기존 GN 방향이 검증 가능한 감속을 못 만드는 경우에만 중앙차분 true-gradient Hessian을 조건수/양정정부호 검사 후 fallback으로 사용; 모델·비용·Q/R 및 사전등록 값 불변.
4. 검증 결함 방지: 각 스텝의 optional telemetry 키를 무조건 인덱싱하지 않음; 회귀에서 signed direct/integrated decrease·독립 gradient·원 covariance를 확인. 과거 실패 네 건을 전수 성공한 것으로 해석하지 않음.
5. 실행 무결성: 원 입력(spec/generator)/truth 분리와 paired seed 동결; 독립 모델별 실패 격리·원시 trace/manifest 기록 유지. 기존 GitHub workflow의 대표실행 전 preaudit 및 P0/P1/R1/R2 순서 유지, **새 R3 회귀 이후 대표 6조건 → full P2**, full 직전 추가 감사 의무화.
6. P3–P6: 현재 브랜치에는 해당 실행기와 RF freeze adapter가 없음. P2 과학 결과와 별개로 P3 원본 입력 감사가 필요. 실측 RF/독립 scene/polymodal reference PASS를 합성 P2로 대체하는 행위 금지.

## 차단·판정
- 사전감사/회귀/대표 6조건의 코드 결함·solver 실패: 해당 영향 범위 재감사 후 수정. 미해결 상태에서 full 실행 금지.
- full P2: 600 paired trial(3경로×2bias×100), 4모델; 누락 모델은 가짜 출력 대신 무효 사례, 유효 paired denominator를 보고.
- bias 효과: 기존 경로별 bootstrap 95% CI 기준을 변경하지 않음. ALL_THREE_SUPPORT 실패 시 과학 주장 HOLD, P3 input identity audit 자체는 별도.
- R3 numerical acceptance는 국소 진단이며 formal floating-point error certificate가 아님.
- independent peer audit는 아직 미수행, `scientific_PASS=false`.

변경 코드: `core.py`, `solver_r3.py`, `test_solver_r3.py`, `pre_run_audit.py`, `record_r2.py`, `.github/workflows/ekf4-range-s-staged.yml`. 원 `P2_SPEC.json`, `synthetic.py`, `stable_descent.py`, `test_core.py`, `test_solver_r2.py` 등은 건드리지 않음.
