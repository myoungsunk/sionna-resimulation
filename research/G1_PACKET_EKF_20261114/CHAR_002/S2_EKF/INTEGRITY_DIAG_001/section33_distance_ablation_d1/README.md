# §3.3 원본 재생 코드와 trace 게시

`FABLE_PROMPT_FINAL_MODEL_KO.md` §6의 D1에 해당한다. mount 0°, 앵커 B, B0, R5, seed 10의 거리별 팽창 제외와 방향별 대조를 포함한다.

원래 Windows 인라인 실행에서 코드를 복구했다. 당시 trace는 메모리에만 있었으며, 원본 코드에 저장 래퍼를 적용해 18개 NPZ를 생성했다. 세 단계 결과가 원래 출력 JSON과 정확히 일치했고 baseline/full 재생 parity 차이는 0이다.

| 자료 | 위치 |
|---|---|
| 전체 표와 범위 | [REPORT_KO.md](REPORT_KO.md) |
| 원본 거리 제외·방향 복원 코드 | [original_main.py](original_main.py) |
| 원본 방향 약화 코드 | [original_directional_weaken.py](original_directional_weaken.py) |
| trace 저장 실행 코드 | [run_replay.py](run_replay.py) |
| 코드 출처 | [SOURCE_PROVENANCE.json](SOURCE_PROVENANCE.json) |
| 원래 실행 결과 | [original_results/](original_results/) |
| 동결 계약 | [RUN_CONTRACT.json](RUN_CONTRACT.json) |
| 실행 영수증 | [runs/EXECUTION.json](runs/EXECUTION.json) |
| 독립 수치 검산 | [VERIFICATION.json](VERIFICATION.json) |
| 파일·trace 검증 코드 | [verify_archive.py](verify_archive.py) |
| 입력과 원래 M5 계약 | [inputs/](inputs/) |
| M1-I trace 4개와 점수 | [runs/A1/](runs/A1/) |
| HF-KI 4° trace 8개와 점수 | [runs/A2_4/](runs/A2_4/) |
| 방향 약화 trace 6개와 점수 | [runs/A2_4_weak/](runs/A2_4_weak/) |

trace 필드는 x, P, prior, Pprior, h, H, Reff, K, nu, S, mask, t, pose_id, near, rho다. 세 단계에서 공통 대조가 반복되어 18개 파일에 13개 서로 다른 조건이 들어 있다.

새 checkout에서 Git LFS 파일을 받은 뒤 Python과 NumPy로 `python verify_archive.py`를 실행하면 파일 해시, 실행 영수증, 입력·gate·분할, baseline/full parity와 점수를 확인한다.

전체 물리 모델 재생에는 동결 계약에 기록한 M5·S2·SourceFFD 의존 경로가 필요하다. 원래 실행 경로와 소스·입력 SHA-256을 보존했다. 같은 실행 환경에서 새 출력 폴더를 지정한다.

```powershell
python run_replay.py --output D:/SLAM_bot/artifacts/G1_SECTION33_D1_RERUN_01
```

`SHA256SUMS`가 게시된 모든 파일을 묶는다. 3 m는 사후 진단 경계이며, 이번 게시 범위는 기존 R5·seed 10 재현이다.
