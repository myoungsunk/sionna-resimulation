# G3 26-ray 포렌식 → H 영향 → RA3 순차 감사 (2026-10-29)

**원본 보존:** 기존 RF/H/S6, BB/MB_VAR 및 RA0–RA2 결과를 덮어쓰지 않음. 감사 코드와 24위치 CSV만 별도 브랜치에 추가.

## 검산 완료 (IMPLEMENTER)
- 원 최종 trace receipt 묶음 SHA256 `2d2321599ae08e7b98a8652133e22173eaed7731d11e5cb89863b5c91b4bde06`, **5630 위치, 354410개 개별 ray**, 엄밀 `5e-14 s` 초과 **26 ray / 24 위치**. 6그룹 G3 원 재검사와 완전히 일치. 전체 path 엄밀 초과 비율 **0.007336%**.
- 현재 [24위치 동결 CSV](g3/G3_FROZEN_24_OFFENDING_LOCATIONS.csv)에는 route/anchor/pose_id/미일치 ray 수/동률 병합 가능성/좌표차를 수록. source `rf_poses` 기준 **12개 H 파일, 48개 H 행**이 최대 영향 후보(이 H들이 잘못됐다는 주장은 아님).
- [실제 실행 #40852794655](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40852794655) — 원 receipt 5630개, 원 H와 별개인 G3 이력, pose-index 검사.
- 좌표 반올림의 대응 delay 상한은 `1.997e-15 s`이므로 이것만으로 엄밀 초과를 설명 불가.
- `TIE_S=1e-13 s`로 24위치 중 23곳은 원 image delay 병합 시 `5e-14 s` 이상 이동하는 후보가 존재. **실제 mismatch가 병합 때문이라고 판정하지 않음**.
- 2026-10-07 보관 원 NPZ trace는 `STORED_PATH_TRACES_R2_aA`에서만 별도 확보됨. [R2-A 925 ray 위치 재검산 #40850815112](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40850815112): 실패 `pose_id=915, ray_index=62`; 병합 전/후 원 image residual 모두 `5.109035715995e-14 s` = **UNMERGED_STRICT_FAIL**. 원 tau가 float32 격자에 놓이는 것은 확인됐으나 **내부 PathSolver 어느 연산에서 잔차가 발생했는지는 미확정**.
- [R2-A 단일 ray 대조 #40851669162](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40851669162): 원 H 재생 오차 `<2.4e-17`; 해당 지연만 image delay로 *가상 변경* 시 복소 H 상대 `2.6–3.1e-7`, 편파 `|Δs|≤2.18e-14`, 거리 `Δr=0`, first-path switch 없음. 25개 타 ray에 대한 보증 아님.

## H 영향의 결정적 조건 (PROPOSER)
- `path_continuity`의 0행 검사 결함 또는 class 통과/판정만 수정하면 실제 H/RF packet **변경 없음**, BB/MB_VAR 재실행 **불필요**.
- 원 Sionna trace 자체를 물리적으로 재생성·수정해야 한다면 먼저 **나머지 5그룹의 23위치/25 ray**에 대한 원 tau 확보 또는 해당 위치만 targeted RT를 실시. 원 RT 5630개 재시뮬레이션을 먼저 하지 말 것.
- H 실제 차이가 확인될 때만 12 H 파일의 최대 48행을 별도 버전으로 생성하고 257-bin/양 port/first-path r,s/tap의 차이를 확인.
- packet이 실제 바뀌면 [7 case ×4 gyro = 28조건](https://github.com/myoungsunk/sionna-resimulation/blob/audit/g3-26ray-ra3-20261029/research/RA0_RA1_RA2_AUDIT_20261029/g3/G3_FROZEN_24_OFFENDING_LOCATIONS.csv), 우선 BB_ORIG+MB_VAR **56개 recursive replay**, 필요시 기존 14 arm×28 = 392 score rows, S6 최대 12블록×4500=54000 row를 재평가. 영향은 각 case 최초 변경 pose_id 이후 누적될 수 있음.
- 원 `rf_store.assemble`은 `unmatched_paths`가 아니라 `status=='OK'`만 확인하므로 G3 strict FAIL과 H 자격 조건은 분리되어 있음. 수정 대상이 확정되기 전에 H를 무효로 단정하지 말 것.

## RA3 필터 정의 (IMPLEMENTER → AUDITOR)
- `exp_pb.run`/원 `ctl_core`: `sigma_b`를 **이전 posterior/현재 predict 이전**에 조회. 일부 후속 코드 `run_four_priorities.py`는 **현재 predicted prior**에서 조회. `MB_VAR` 동일 명칭 아래 의미를 섞지 말고 `MB_VAR_LEGACY`, `MB_VAR_PRIOR`로 분리.
- [RA3 8개 canary #40851671917](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40851671917) — 원 state/P 재구현 최대 절대차 **0**, 바뀐 것은 분산 조회 시점뿐; 8개 Arm Heading RMSE 차이 최대 **0.00549°**, XY 차이 최대 **0.09075 cm**.
- [원 7 case×4 gyro 전체 28조건 재검산 #40852149539](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40852149539) — **completed/success**, 원 source state/P 절대차 0, 56 arm(7 case×4 gyro×BB/MB)의 원래 BB_ORIG 대비 MB_VAR Heading **23/28→23/28**, XY **20/28→20/28**, 동시 **19/28→19/28**. 개선/미개선 판정이 바뀐 조건은 **0/28**. 연속 점수는 변함: 주요 MB_VAR Heading RMSE 변화 최대 **0.006278°**, XY RMSE 변화 최대 **0.060967 cm**. 모든 BB/MB arm 포함한 최대치는 각각 **0.010476°**, **0.237204 cm**.
- [RA3 전체 상세 실행 정의·검산 보고서](ra3/RA3_FULL_SEMANTICS_AUDIT_20261029.md) — 같은 명칭 아래 posterior-before-predict와 predicted-prior 구현 혼용 금지, 원 MB_VAR 이름/기준 성능은 LEGACY로 유지. 기존 RF 물리 유효성에 대한 승인은 별개.

## AUDITOR 경계
실제 원 source/아카이브 근거 산술은 별도 방식으로 검산했지만 모든 업무가 동일 모델 세션의 작업이므로 **SELF_REVIEW_ONLY**. 5개 경로군 원 tau 미확보, RT 물리 solver 내부 오차 귀속과 25 ray의 물리적 H 영향은 **BLOCKED_EVIDENCE**. GitHub Actions 성공은 연구 독립 승인이나 새로운 물리적 주장 PASS가 아니다.
