# A23 분석 입력 원본

이 디렉터리는 실제 A23 실행 입력을 추가로 보존한다. 원본 파일은 바꾸지 않았고 새로운 RF·필터 실험을 실행하지 않았다. F01/F02와 scientific_PASS=false는 유지한다.

H, LUT, metadata, 주파수축은 전체 파일이다. 정렬 확인에 필요한 P0 timeline과 rf_poses도 포함했다. 실제 FFD bank는 각각 약 248 MB로 GitHub 단일 파일 제한을 넘으므로 **전체 바이트를 40 MiB 조각 6개씩, 총 12개로 무손실 분할**했다. LFS pointer나 해시 목록만 게시한 것이 아니다. 모든 조각이 이 브랜치에 들어 있다.

원본 NPZ를 복원하려면 Python 3.9 이상에서 다음을 실행한다. NumPy 설치는 복원 자체에 필요하지 않다. 출력 디렉터리를 지정하며 기존 파일을 덮어쓰지 않는다.

```text
python restore_ffd_banks.py --out YOUR_OUTPUT_DIRECTORY
```

도구는 각 조각의 크기·SHA256과 최종 원본의 크기·SHA256을 모두 확인한다. 복원 실패 시 partial 파일을 보존한다. 복원된 파일 이름은 `LP_plus45_bank.npz`, `LP_minus45_bank.npz`다. 분석 프로그램에는 이 실제 복원 파일을 공급한다.

| 자료 | 위치 |
| --- | --- |
| 실제 full RF H | H_R2_aA_m0.npy |
| 기존 LoS-only LUT | hs_lut_2deg.npy, hs_lut_meta.json |
| 주파수축 | freqs_hz.npy |
| 실제 LP±45 FFD bank 전체 내용 | FFD_CHUNKS/ 및 FFD_RESTORE_MANIFEST.json |
| 원 production bank provenance | BANK_MANIFEST.json |
| H와 pose 대응 | timeline_R2_Tnone.csv, rf_poses_R2.json |
| 입력과 조각 해시 | INPUT_MANIFEST.json |

결과·trace·잔차 자료는 상위 디렉터리의 `retrieved/OUTPUT/`에 있다. source·input hash 일치는 입력 동일성 증거이며 실제 안테나/하드웨어 정확성을 입증하지 않는다. 이번 입력 추가로 잔차 분해나 편향 상태 증강 시험을 수행했다고 주장하지 않는다.
