# PREC-V2 — R1·Anchor B 원래 8개 canary 지연 불일치 수정 검증 보고

- UTC 수행: 2026-11-03, **GitHub Actions 성공**: https://github.com/myoungsunk/sionna-resimulation/actions/runs/41600953304
- 실제 소스 실행 commit: `cd33dd0e3e0858ac277c73e24e5afcfe45ba0059`
- 검증 코드: `precision_v2/solver_matched_delay.py`
- 계산 입력: 과거 고정 8개 Native LoS/Full NPZ (원본 SHA 고정), source-only geometry.
- 기반: 원래 V2 `HOLD_RF_PARITY` (수정 또는 삭제하지 않음).

## 버그의 위치와 원인

V2 SourceFFD `physical_h_col`은 원본 double 좌표의 거리 `d/c`를 사용했다. Native Sionna-RT 2.0.1은 아래 코드처럼 Mitsuba `mi.Vector3f`와 `dr.norm`, `dr.rcp(speed_of_light)` 경유로 지연을 계산한다.

- https://github.com/NVlabs/sionna-rt/blob/v2.0.1/src/sionna/rt/path_solvers/field_calculator.py
- `ki_world = mi.Vector3f(vertex - prev_vertex)`
- `path_length = dr.norm(ki_world)`
- `tau = path_length*dr.rcp(speed_of_light)`

기존 turn pose(440,458,476)에서 float64 기하 지연과 저장된 Native 지연의 차이 `3.900169068688608e-15 s`가 약 `1.59e-4`의 복소 응답 차이를 만들었다. 입력 좌표 및 지연의 숫자 표현 차이가 주원인이지, 새로운 다중경로가 등장했다는 뜻이 아니다.

## 수정/동결 범위

Source 원본 `H_source`와 Source 좌표만 받아 동일한 DrJit 연산으로 `tau_render`를 계산하고,
`H_render(f)=H_source(f) exp(-j2πf(tau_render-d64/c))`를 **정합 검사용 출력에만** 적용한다.

- Native `H`/Native `tau`를 **수정 계산 입력으로 사용하지 않음** (Native tau는 계산 이후 독립 확인).
- phase/gain fitting, GT lookup, 허용치 변경, 나쁜 pose 삭제 및 가중치 변경 없음.
- `SourceFFD.batch()`, `h,H`, `R0`, EKF, 원본 C0 장면·FFD bank, 포트·FP 검출기에는 변경 없음.

## 원래 8개 canary 전 bin 수치 검증

| 검증 지표 | 기존 원본 V2 | DrJit 연산 일치 수정 | 사전 기준 |
|---|---:|---:|---:|
| 복소 채널 상대 RMS | 1.0051515145524099e-4 | **4.911678562479378e-7** | ≤1e-4 |
| 복소 채널 상대 최대 | 1.5950092587162026e-4 | **7.1294878847295e-7** | ≤5e-4 |
| signed 편파차 RMS | - | **1.06774551949669e-7** | ≤2e-6 |
| signed 편파차 최대 | - | **2.387675771542419e-7** | ≤2e-5 |
| FP tap/strong port mismatch | 0/0 | **0/0** | 0/0 |
| 저장 Native tau와 source-only DrJit tau 정확히 같은 pose | - | **8/8 (각 257 bin 전부)** | 별도 진단 |

**수치 정합 재실행: PASS.** 이 결론은 기존 8개 원본 데이터에 대한 source-only 재현을 뜻한다. 원래 V2 `HOLD_RF_PARITY`는 불변이다.

향후 independent held-out Native 4개 및 별도 감사 완료 전에는 `SCIENTIFIC_SUPPORTED`라고 기술하지 않는다. P1 전체 917개 RF, P2 관측오차 전체 경로 통계, P3 실제 4상태 재귀는 이 보고서가 완료 증거가 아니다.
