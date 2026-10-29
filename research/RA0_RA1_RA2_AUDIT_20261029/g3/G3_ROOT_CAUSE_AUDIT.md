# G3 엄밀 5e-14 s 6/6 FAIL의 원인 감사 — 원인 확정과 미확정을 분리

## 판정
- **과거 'G3 PASS'의 근본 원인: 확정.** 최초 `path_continuity.py`는 새 경로의 `phase='drive'`를 검사 위치로 선택하지 않아 `stations=0`에서도 PASS를 허용. 2026-10-08 개선판에서 `drive`를 선택하고 `NO_STATIONS_FOUND`를 차단하여 정정됐다. 원본 source commit `0d4588f79116e221d874307f233d69ff0b13d99c`, G3 재검사 source `8b693825f46a8a2de64a87de09d48bc50a6e5704`.
- **수정된 G3의 엄밀 FAIL: 26개의 실제 보고된 delay 잔차가 5e-14 s를 초과했기 때문인 것은 확정.** 완화 2e-13 s에서는 그 26건도 모두 적합. 누락 trace 0, status 비정상 0.
- **26건 각각의 물리적/수치적 근본 원인: 현재 증거로 미확정 `BLOCKED_RAW_TRACE`.** 재검사 `S2/G3_continuity_*.json`은 집계값을 보존하지만 offending raw `tau`별 `path_id/pose` 및 unmerged sequence 잔차를 보존하지 않는다. **추측을 근본 원인으로 등록하지 않음.**

## 원본 자료 직접 점검
[재검사 README](https://github.com/myoungsunk/sionna-resimulation/blob/f100a983cc389fcdef073592a254add61e7115da/results/DRIVE_SIM_20261007/SNOWBALL_ROUTE_RUNS/01a11669/g3_recheck_20261008/README.md)

| case | 위치 수 | strict(5e-14) 초과 경로 | 2e-13 초과 | max |Δτ|, s | 대응 경로 길이, mm |
|---|---:|---:|---:|---:|---:|
| R2_aA | 925 | 1 | 0 | 5.10904e-14 | 0.01532 |
| R2_aB | 925 | 1 | 0 | 5.83157e-14 | 0.01748 |
| R4_aA | 547 | 3 | 0 | 9.38368e-14 | 0.02813 |
| R4_aB | 547 | 3 | 0 | 8.18799e-14 | 0.02455 |
| R5_aA | 1,343 | 9 | 0 | 1.00642e-13 | 0.03017 |
| R5_aB | 1,343 | 9 | 0 | 9.67821e-14 | 0.02901 |

**정의:** residual은 실측 거리 오차가 아니라 path solver `tau`와 image-method 기준 delay의 절대차이다. `cΔτ`는 등가 경로 길이 차로만 해석. 5e-14s=0.01499mm, 2e-13s=0.05996mm. 6개 실패는 그룹마다 1개 이상 초과해서 각 그룹 Boolean이 FAIL인 것이고 모든 경로가 실패한 것이 아니다. 전체 경로 개수의 엄밀한 분모는 raw trace 경로 길이 합계가 필요하다.

## 잠재적인 근본 원인 4개의 독립 분리
1. **경로 동률 병합 단위와 검증 허용오차 불일치 — 구조적 검사기 취약점 확인.** `src/qclean_uwb/drivesim/paths.py`의 `TIE_S=1e-13`이 원 image delay 여러 개를 하나의 class 최소 delay로 뭉친다. 반면 G3 strict는 `5e-14`이다. 동일 class의 두 진짜 delay가 8e-14 떨어진 합성 반례에서는 raw-nearest=0이더라도 class-representative-nearest=8e-14로 **물리적으로 일치하는 경로가 FAIL**한다. 검증하는 fixture `g3_forensic_checks.py`를 추가했다. **그러나 이것이 실제 26개 전부의 원인인지는 raw trace가 없어 미확인**이다.
2. **RT 지연값의 유한정밀도/좌표 정밀도.** `rf_b_trace.py::_solve`가 Sionna `p.tau`를 `np.asarray(...).astype(float64)`로 저장한다. float64 변환은 선행 solver의 유한정밀도 오차를 없애지 않는다. raw `p.tau`와 exact image delay를 같은 pose 기준으로 다시 계산해야 오차 배분 가능하다. `float32` 영향 단정 금지.
3. **pose·앵커·벽면·경로 순서 좌표계 차이.** `path_continuity.py`는 timeline에서 소수점 6자리로 반올림한 x,y를 tag화한 후 trace `rx_xy`로 실제 재계산한다. 보존 trace 좌표와 생성 source/config 차이를 path별 점검해야 한다.
4. **solver의 실제 경로와 3차 반사 image 모델 차이.** 가장 가까운 image sequence와의 매칭이 무조건 참인 것은 아니다. raw unmatched 값이 동률 이전의 전체 image 후보와도 strict 초과하며, 좌표·정밀도 검증을 거친 경우에만 물리적 경로 오차로 분류할 수 있다.

## 원인 확정에 필요한 결정적 26행 감사
각 mismatch에 대해 `route,anchor,pose/tag,x/y exact,ray_index,tau_dtype,tau_raw,nearest_unmerged_sequence,tau_image_unmerged,nearest_merged_class,tau_class_rep,delta_unmerged,delta_merged,delta_ulp,reflex_order,path_presence/freq_status`를 원본 trace로 출력한다.

- `delta_unmerged<=5e-14<delta_merged`: **TIE_CLASS_ARTIFACT**.
- 정확한 full-image와도 실패하지만 양자화/좌표 반올림으로 설명: **NUMERIC_OR_POSE** (설명 수치 필수).
- 완전 원소스 좌표/주파수·유한정밀도 검사 후에도 실패: **PHYSICAL_TRACE_OR_MODEL**, 원 Sionna 송수신 경로 카나리 재실행 대상.
- 원 trace 파일 미확보 또는 설명할 수 없는 잔차: **BLOCKED_EVIDENCE**. 다른 원인으로 옮기거나 값을 완화하지 않는다.

**추가 승인 없이 전체 RT 재생성 금지.** 보존된 offending 26개 원 trace 확보→분류→필요한 경우에만 카나리 RT 비교→영향 받은 H/관측 변경량 계산→BB/MB_VAR score 영향 경계 순서가 원칙이다.

## 임시 수정/재실행 결정
- `TIE_S` 또는 `strict` 기준을 정답에 맞춰 완화하지 말 것. raw unmerged 및 merged 두 잔차를 **별도 동결된 감사 지표**로 보고, 어떤 기준이 물리 주장에 합당한지 독립 결정.
- 이미 존재하는 H/S6는 해시 일치하므로 RA2 raw H→packet parity는 별도로 유효. **엄밀 G3 통과로 소급 포장 불가.**
- 수치적 정밀도나 path tie만으로 H/r,s가 실제 달라졌다는 것이 확인되기 전에는 모든 H 및 MB_VAR를 일괄 재실행하지 말 것.
- 현재 최종 판정: `REVISION_REQUIRED / STRICT_G3_FAIL_CONFIRMED / PHYSICAL_ROOT_CAUSE_BLOCKED_RAW_TRACE / SELF_REVIEW_ONLY`.
