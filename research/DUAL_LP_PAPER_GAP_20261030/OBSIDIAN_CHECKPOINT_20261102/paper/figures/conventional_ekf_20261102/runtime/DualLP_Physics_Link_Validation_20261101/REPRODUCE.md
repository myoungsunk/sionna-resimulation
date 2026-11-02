# 실행·재검사 안내

## 1. 결과 열람

`REPORT.md`, `QA.json`, `results/tables/`와 `results/figures/`는 메인 ZIP만으로 읽을 수 있습니다. `results/traces/`에는 실제 실행 132개, `results/shadow/`에는 12조건 × 4후보 상세 배열이 있습니다. `FIXED_SELF_TRACE_INDEX.json`은 144개 논리 비교와 실제 파일의 대응표입니다. 기존 BASE fixed 12개는 같은 BASE self 파일을 가리킵니다.

검증 파일은 제안문서가 아니라 새로 실행된 결과입니다. 기존의 사라진 ZIP 자체와 바이트 일치 복원은 아닙니다.

## 2. 전체 재실행용 FFD 입력

메인 ZIP에서 유일하게 외부로 분리한 실행 입력은 아래 두 파일입니다. 함께 전달한 companion ZIP을 압축 해제하여 다음 위치에 넣으세요.

```text
DualLP_Physics_Link_Validation_20261101/
  recovered/inputs/banks/
    LP_plus45_bank.npz
    LP_minus45_bank.npz
```

|Companion ZIP|내부 파일|원 NPZ SHA-256|
|---|---|---|
|DualLP_Recovered_FFD_Plus45.zip|LP_plus45_bank.npz|b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b|
|DualLP_Recovered_FFD_Minus45.zip|LP_minus45_bank.npz|39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9|

인터넷이 되는 환경에서는 `python code/fetch_missing_inputs.py`가 고정 commit URL에서 누락 입력만 받고 SHA-256을 검증합니다. 이미 존재하는 파일이 hash와 다르면 덮어쓰지 않고 중단합니다. URL·원본 commit·hash는 `recovered/RECOVERY_MANIFEST.json`에 있습니다. GitHub Actions artifact의 보존기간이 지나도 원 Git/LFS 입력 URL을 우선 사용하도록 구성했습니다.

## 3. 실행 환경

이번 실제 실행 환경은 Linux, Python 3.13.5, NumPy 2.3.5, pandas 2.2.3입니다. 나머지 설치 버전은 `requirements.txt` 및 `MANIFEST.json`에 기록했습니다. `replay_validation.py`는 fork worker를 사용하므로 Windows에서는 WSL에서 실행하세요. FFD가 크기 때문에 worker를 과도하게 늘리지 마세요. 3 workers로 실행했고 두 bank는 fork에서 공유합니다.

```bash
cd DualLP_Physics_Link_Validation_20261101
python -m pip install -r requirements.txt
python code/verify_package.py              # 메인 ZIP 안의 파일만 검사
python code/fetch_missing_inputs.py --verify-only
python code/verify_package.py --with-external
python code/reproduce.py --dest ../DualLP_Reproduction_New_Run --workers 3 --figures
```

`reproduce.py`는 **새 경로만 허용**합니다. 전달된 원 결과는 덮어쓰지 않습니다. 읽기 전용 recovered 입력을 가능하면 hard link로 공유하고, 코드·설정·evidence는 복사합니다. 원 결과 파일은 새 실행 폴더로 복사하지 않고 아래 순서로 실제 계산합니다.

1. 원 `diag_mbvar.run`을 사용한 전체 재생 및 원 CSV/CONTROL 대조.
2. 원 Full/LoS/Source 관측·Jacobian·scalar/port 검사.
3. 동일 prior 평균×분산 shadow 갱신과 signed 분해.
4. 별도 2×2 역행렬·covariance contraction을 이용한 자체검토, 대화 수치 대조, 음성 fixture.
5. 보존 HG/MR prediction → 원 CONTROL 평균 계보 대조.
6. previous-posterior lookup, R, innovation, NIS, rejected state 계약 확인.
7. 결과 보고서 생성. `--figures`가 있으면 그림도 새로 계산한 CSV로 생성.

필터를 다시 실행하지 않고 저장 trace만 재검사하려면 `quality_and_comparison.py`, `mean_lineage_validation.py`, `trace_contract_checks.py`를 새 복사본에서 실행할 수 있습니다. 이 세 검사는 bank의 수치 field를 로드하지 않습니다. NumPy/pandas 및 보존 source 파일은 필요합니다.

## 4. 형식과 단위

내부 Heading은 rad, 표의 Heading RMSE는 degree, 내부 XY는 m, 표의 XY RMSE는 cm입니다. 최종 score는 `t>=30-1e-9`의 모든 시간점이며 same-prior 주 비교는 같은 시간조건 AND BASE accepted입니다. 둘을 혼동하지 마세요.

이 실행 환경에는 parquet engine이 없어 ledger는 정밀도 17자리 CSV.gz와 NPZ로 보존했습니다. source PKG 구조는 변경하지 않았습니다. `__pycache__`, `.pyc`, 임시 PID 파일은 배포에서 제외했습니다. 원 무선·CONTROL 입력은 보존하고, 신규 RT나 학습은 수행하지 않습니다.

## 5. 감사·동결의 한계

`contracts/CONFIG_LOCK.json`은 실행 전 설정 snapshot이며 제안에서 상속한 NOT_RUN/문서 작업 필드가 남아 있습니다. 최종 상태는 루트 `QA.json`입니다. 해석 기록은 `contracts/RECONSTRUCTION_METADATA_CLARIFICATION.md`에 있습니다. 이 재현은 과거 결과를 이미 본 상태에서 사용자 요청으로 수행한 회고적 재구현이며, 독립 FROZEN pre-run 서명이나 독립 사후 감사로 표시하지 않습니다.

V4는 선택 항목으로 미실행입니다. V5 저장된 예측의 계보는 검사했으나 fresh inference는 모델/scaler/fold 미회수로 BLOCKED입니다.
