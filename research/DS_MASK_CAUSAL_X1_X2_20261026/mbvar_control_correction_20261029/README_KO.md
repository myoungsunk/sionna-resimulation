# MB_VAR 대조조건 정정 실행 (2026-10-29)

- 설계: `PROTOCOL_CONTROLS_KO.md`(본문 + 실행 전 수정 A1–A9)
- 코드:
  - `ctl_core.py`: filter와 처치 hook. `exp_pb.run`과 산술이 동일하며 seed 0 parity를 검사한다.
  - `run_stage.py`: stage별 shard 실행
  - `aggregate_ctl.py`: 사전 판정 규칙을 기계적으로 적용
- 실행: `.github/workflows/mbvar-control-correction.yml`. 이 폴더의 `RUN_REQUEST.json`이 변경되면 실행된다.
- 결과: `results/run_<GitHub run id>/`에 저장된다. 요약은 `RESULTS_SUMMARY.md`, 판정은 `DECISIONS.json`, 세부는 `JUDGE_*.csv`이다.
- 사전 감사: `E7_P0_AUDIT.json` (nested LORO는 이번 실행에 포함되지 않는다)
- semi-synthetic replay(E4)는 truth를 쓴 진단용 구성이다. 실제 RF 환경 생성이 아니다.
