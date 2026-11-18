# 감사 대응 (2026-10-08, 대상 커밋 df8b225)

감사 판정: REQUEST CHANGES. 아래는 차단 사항별 수정과 확인입니다. RF 솔버는 Sionna 환경에서 짧게만 돌렸고(아래 표 참고), 사무실 전체 실행은 하지 않았습니다.

| # | 지적 | 수정 | 확인 |
|---|---|---|---|
| 1 | P1 닫힌 상자에 전체 슬랩을 면마다 적용 | RF 형상과 시각화 형상을 분리했습니다. `OfficeSetup.rf_sheets()`/`objects()`는 물리 슬랩당 판 한 장(칸막이 세로 판, 책상 윗판, 바닥·천장·벽)이고, 상자(`boxes()`)는 시각화·통로 여유 계산에만 씁니다. 기하 LoS도 RF 판으로 계산합니다. | `scripts/office_slab_check.py` (Sionna): 한 장의 투과 계수가 해석식 T와 상대오차 3.4e-7–1.3e-5로 일치(8개 경우: 4재질 × 가로/세로), 닫힌 상자는 T²와 일치(2.6e-5 이하)하고 T와는 0.77–1.85 어긋남 → 감사 지적을 수치로 재현. 결과 `SLAB_CHECK.json`. 단위 테스트 `test_every_object_is_exactly_one_flat_sheet` 등 |
| 2 | P1 검증기가 불완전·다른 설정을 통과 | `src/qclean_uwb/runcheck.py` + `scripts/sweep_verify.py`로 재작성. 요청 계약(yaw·stride·bin 격자·솔버·어댑터/뱅크/러너/설정 해시·물체 목록)과 H·npz·receipt 일관성, 모든 호출의 LoS 유무, 위치 누락/중복/초과, 필수 파일(npz 포함)을 확인하고 하나라도 어긋나면 실패합니다. 이전 `office_verify_outputs.py`는 삭제했습니다. | 감사의 재현 A(경로 파일 없는 0 채널 + 불일치 receipt), 재현 B((1,1,2,2) 채널 + 최소 npz + 잘못된 러너 해시)를 `tests/test_runcheck.py`에 회귀 검사로 채택, 둘 다 실패로 판정 |
| 3 | P1 receipt만으로 재개·완료 판정 | `scripts/sweep_run.sh`: 요청 계약을 `RUN_REQUEST.json`에 기록하고 같은 OUT에 다른 요청이 오면 종료코드 2로 거절합니다(기존 결과 보존). 위치는 검증을 통과해야 건너뛰고, 실패한 폴더는 `_superseded/`로 옮겨 보존한 뒤 다시 계산합니다. 완료 표식은 전체 검증 통과 때만 만듭니다. | 감사의 재현(빈 `{}` receipt 6개) → 완료 표식 없음, 종료 1, 폴더 보존 (`test_run_script_receipt_only_*`). stride 128 결과를 stride 1 요청이 건너뛰지 못함(`test_stride_128_output_does_not_satisfy...`) |
| 4 | P2 작업 실패가 종료코드에 안 전달 | 위치별 실패와 xargs 종료 상태, 출력 검증 결과, 마감 중단을 종료코드로 구분합니다(0 완료, 1 실패, 2 요청 불일치, 3 미완료). `RUN_STATUS.json` 기록 | 감사의 재현(`PYTHON=false`) → 종료 1, FAILED 기록, 완료 표식 없음 (`test_run_script_failing_runner_*`) |

## 끝까지 돌려 본 것 (Sionna 환경, 이 세션)

- 사무실 `--geom-check`: Sionna LoS 경로와 기하 판정이 35곳 모두 일치(LoS 25, 막힘 10).
- 시험 6곳(bin stride 128, yaw 19개): `office_run.sh` 종료 0, 검증 통과, 다시 돌리면 0.8초에 전부 건너뜀, stride를 바꾸면 종료 2로 거절.
- 단위 테스트(`tests/test_runcheck.py`, `test_office_setup.py`, `test_ply.py`, `test_specular_model.py`) 통과.
- 이전 감사에서 못 본 것: 감사는 Snowball 접속과 RF 호출을 하지 않았고 제가 보고한 63경로/35곳 일치도 재현하지 않았습니다. 위 수치는 이 세션에서 다시 돌린 값이며 감사 쪽 재현은 아닙니다.

## 복도 조건에서도 같은 문제가 있었는지

1. **상자 이중 슬랩(1번):** 복도는 바닥·천장·벽 6장이 모두 판 한 장씩이라 해당 없습니다. 더 직접적으로, 복도 결과의 모든 경로(스윕 npz 전체)에서 상호작용 코드가 0(없음)과 1(정반사)뿐이고 투과(굴절) 경로가 하나도 없습니다(표본 4곳 확인: 첫 스윕·스캔 1·스캔 2·앵커 2, 모두 코드 집합 {0, 1}). 복도 결과는 투과 모델의 영향을 받지 않습니다. 해석식 모델(`specular_model`)은 처음부터 슬랩 하나 계수를 쓰고 Sionna 경로별 필드와 이미 1e-3 이내로 맞췄습니다.
2. **검증기가 못 잡는 불완전 출력(2번):** 복도 결과 전체를 새 검증기로 소급 점검했습니다(`scripts/corridor_audit.py`, `results/CORRIDOR_AUDIT_20261008.json`). 5개 디렉터리 102곳 모두 통과(요청 계약, 솔버·어댑터·뱅크 해시, H·npz·receipt 일치, 모든 호출에서 LoS 존재, 앵커 위치 일치, 중복 없음). 첫 스윕(`CORRIDOR_SWEEP_20261006`, 4곳)의 npz에는 물체 ID(`objects_cat`)가 없는 것이 유일한 차이이며 옛 러너 버전 때문입니다(그 분석은 지연 시간 매칭을 썼습니다).
3. **receipt만으로 재개(3번), 실패 미전파(4번):** 복도 실행 스크립트(`run_scan.sh`, `corridor_scan2_run.sh`, `corridor_anchor2_run.sh`, `corridor_anchor2b_run.sh`)는 같은 결함이 있었습니다. 이번에 복도 3개 스크립트를 `sweep_run.sh`의 얇은 래퍼로 바꿨고(기존 결과 보존을 위해 `ALLOW_RUNNER_CHANGE=1`), `run_scan.sh`에는 LEGACY 표시를 달았습니다. 실제 영향은 없었습니다: 위 소급 점검이 모든 복도 위치를 통과시켰고, 실행 중 실패 기록은 제가 직접 중단시킨 경우뿐이었습니다.
4. **러너 변경이 복도 결과를 바꾸는지:** 수정된 러너로 복도 4곳(앵커 (4,0) 두 곳, 앵커 (4,−0.4)에 태그 y = −0.4와 y = 0)을 yaw 2개 × bin 3개로 다시 계산해 저장된 H와 비교했습니다. 차이 0(비트 단위로 같음), 첫 스윕 위치 포함.

## 남은 위험

- 책상을 윗판 한 장으로 본 가정은 책상 아래·옆에 서랍이나 옆판이 있으면 LoS와 반사가 달라집니다(결정은 사용자).
- 사무실 전체 RF는 아직 돌리지 않았고 Snowball에서의 실행은 이 문서의 0–3번 순서로 게이트를 통과해야 합니다.
- 경로 파일(`*_sweep.npz`)은 저장소에 없고 H와 receipt만 올라갑니다. 검증은 npz가 있는 곳에서만 완전합니다.
