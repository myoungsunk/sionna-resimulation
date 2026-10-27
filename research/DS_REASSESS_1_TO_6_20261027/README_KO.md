# Δs–Range–Heading 재진단 1~6단계 전달 자료

**원본 동결 RF/E1 자료를 사용한 1~6단계 실행 완료. 모든 단계의 기술 검증 PASS.** 결과는 [전체 결과 보고서](results/RESULTS_KO.md)에 있다. 이 완료 판정은 가설 입증이나 특정 보정 방법의 채택을 뜻하지 않는다. 새 앵커의 RF 시뮬레이션이나 실측은 수행하지 않았다.

## 실행과 검증 범위

| 단계 | 내용 | 완료 근거 |
|---|---|---|
| 1 | BASE / EX / EXDS / range oracle | [상태·입력·코드 해시](results/01_range/RUN_STATUS.json), [검사](results/01_range/CHECKS.json) |
| 2 | Full CIR FP 재계산·잔차 통계 | [상태](results/02_residuals/RUN_STATUS.json), [검사](results/02_residuals/CHECKS.json) |
| 3 | route-heldout R·FFD 유한차분 | [상태](results/03_RF_R_H/RUN_STATUS.json), [검사](results/03_RF_R_H/CHECKS.json) |
| 4 | PRIOR/GT × PASS/ALL CUT_RT | [상태](results/04_CUT_RT_factorial/RUN_STATUS.json), [검사](results/04_CUT_RT_factorial/CHECKS.json) |
| 5 | 4/5상태 누적 Fisher 관측성 | [상태](results/05_full_observability/RUN_STATUS.json) |
| 6 | 앵커 기하·5상태 bias·접선 Q | [상태](results/06_layout_bias_Q/RUN_STATUS.json), [검사](results/06_layout_bias_Q/CHECKS.json) |

7개 사례(R2_aA_m45, R2_aA_m0, R2_aB_m0, R4_aA_m0, R4_aB_m0, R5_aA_m0, R5_aB_m0)의 B0/L2 조건을 사용했다. Mount 0° 사례도 포함된다. B0/L2는 동일 RF를 이용한 쌍이며 독립 RF 표본 두 개로 세지 않는다.

기존 완료 기록과 업로드 전 검증에서 415개 산출물의 SHA-256을 확인했다. 이번 패키징에서는 단계별 모든 검사 PASS, 실행 코드 해시, 중복을 제외한 입력 파일 30개의 해시, 압축 자료를 다시 읽은 415개 산출물 해시를 재확인했다. E1 재현 최대 절대오차는 약 3.88×10⁻¹⁴이며 고정 허용오차 10⁻¹⁰ 이내다. 단계 5는 recursive OFF parity 검사를 수행하는 단계가 아니므로 CHECKS 수가 0이다. 관측성 결과의 범위를 별도로 읽어야 한다.

## 코드 수정과 재시험

[code/dsreassess/io.py](code/dsreassess/io.py)에 누락된 `from .numerics import wrap` 한 줄을 추가했다. 원본 ZIP의 Python 코드와 비교했을 때 변경은 이 한 곳뿐이다. 임계값·학습·원래 mask·기본 Q/R은 변경하지 않았으며 명시된 진단 Arm만 개입했다. 실제 실행 당시 코드 SHA와 전달 코드가 일치한다.

전달된 `code` 폴더에서 시험 8개를 다시 실행해 통과했다([시험 로그](UPLOAD_TESTS_CODE_ROOT.log)). 최초 업로드 검사에서는 다른 작업 폴더에서 호출해 패키지를 찾지 못했고, 코드 폴더에서 정상 재검증했다. 최초 실패 로그 [UPLOAD_TESTS.log](UPLOAD_TESTS.log)도 남겼다. 실험을 다시 실행하지는 않았다.

[원본 ZIP](DS_REASSESS_1_TO_6_CODE_20261027.zip)과 원래 checksum 파일도 보존했다. `code/SHA256SUMS.txt`는 수정된 전달 코드의 해시다. `code/README_KO.md`, `code/TEST_REPORT_KO.md`의 미실행 표기는 ZIP 작성 시점의 기록이며, 실제 완료 근거는 `results`와 이 문서다.

## 파일 구성과 복원

- `code/`: 수정 코드, 원래 CLI·설명·합성 시험.
- `results/`: GitHub에서 읽을 수 있는 CSV/CSV.gz, 단계별 QA·해시, 전체 보고서, 실행 로그·수정·재개 기록. 대용량 NPZ는 완전 보존 압축본에 있다.
- `EXECUTION_COMPLETE.tar.gz.part000`~`part003`: 최종 FIX2 결과 폴더 전체를 담은 압축본의 순서 있는 분할 파일. NPZ를 포함한 모든 결과를 원래 상대경로로 복원한다.
- [UPLOAD_VALIDATION.json](UPLOAD_VALIDATION.json): 원본 ZIP, 단계별 검증, 입력 및 전달 파일 해시, 완전 압축본 SHA.
- [verify_delivery.py](verify_delivery.py): 파일 검증 및 선택적 복원. 실험 실행 기능은 없다.

이 폴더에서 Python 3.13으로 해시를 확인한다.

```powershell
python verify_delivery.py
# 선택: 기존에 없는 새 폴더에 NPZ까지 복원하고 415개 산출물을 검증
python verify_delivery.py --extract D:/SLAM_bot/DS_REASSESS_DELIVERY_RESTORED
# 코드 시험만 실행
cd code
python -m pytest -q tests
```

실험 자체를 재현하려면 별도로 원래 frozen SourceFFD, bank, E1, RF, p2_artifacts가 필요하다. 그 원본 입력 바이너리를 이번 전달에 중복 포함하지 않았으며 위치·출처·해시는 PREFLIGHT/RUN_STATUS에 남겼다. 입력 없이 시험 통과만으로 실제 RF 재현을 주장하지 않는다.

## 원본 보존과 한계

최종 결과 원본은 `D:/SLAM_bot/DS_REASSESS_RUN_20261027_FIX2`, 코드 원본은 `D:/SLAM_bot/DS_REASSESS_V1_20261027`에 그대로 보존했다. FIX1에서 완료된 1~5단계를 보존·복사한 뒤 FIX2에서 6단계를 완료한 경위는 [RESUME_PROVENANCE.json](results/RESUME_PROVENANCE.json)에 있다. 이번 업로드 작업에서 원본 파일의 이동·삭제·실험 재실행은 하지 않았다.

`results/EXECUTION_SUMMARY.json`의 `commit_push=NOT_PERFORMED`는 업로드 전 기록이므로 수정하지 않았다. 현재 전달 여부는 이 자료를 포함한 Git 커밋과 원격 브랜치로 확인한다.

EXDS−EX는 서로 다른 학습 모델의 비교다. CUT_RT는 축·적용 구간·평가창을 구분하고 gap 감소와 절대 RMSE를 함께 읽어야 한다. Stage 6 가상 앵커는 기하 Fisher 진단이며 가상 앵커 RMSE나 RF 개선의 증거가 아니다. 결과에 맞춘 임계값 변경은 하지 않았다.
