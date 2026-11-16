# 최종 모델 판단 전 Stage 0 — 기존 trace 진단 게시 묶음

mount 0°, 앵커 B, B0, R2/R4/R5, seed 10–14의 기존 M6 trace를 분석한 결과다. **추가 EKF 재생은 0회**다. seed들은 하나의 RF 실현을 공유한다. G1+KI를 해결된 주 arm으로 승격할 근거는 없으며 근거리 q_s=0의 충분성도 미확인이다.

## 결과와 자료

| 자료 | 위치 |
|---|---|
| 종합 결과·M7 반영 판단 | [REPORT_KO.md](REPORT_KO.md) |
| 전체 집계 결과 | [RESULTS.json](RESULTS.json) |
| 루트 동결 계약 | [RUN_CONTRACT.json](RUN_CONTRACT.json) |
| 원본 산출물·입력 해시 영수증 | [MANIFEST.json](MANIFEST.json) |
| 제한된 독립 검토 | [CLAIM_REVIEW.md](CLAIM_REVIEW.md) |
| R2 seed 10·11 heading·gyro·bθ 분해 | [r2_seed_decomposition/REPORT_KO.md](r2_seed_decomposition/REPORT_KO.md) |
| R2 packet·구간별 표 | [PACKET_TIMELINE.csv](r2_seed_decomposition/PACKET_TIMELINE.csv), [WINDOW_SUMMARY.csv](r2_seed_decomposition/WINDOW_SUMMARY.csv) |
| R2 시간축 그림 | [R2_SEED_DECOMPOSITION.png](r2_seed_decomposition/R2_SEED_DECOMPOSITION.png) |
| R5 통과 1–3·진입 상태·AR 기억 | [r5_passage_bias/REPORT_KO.md](r5_passage_bias/REPORT_KO.md) |
| R5 통과별 비교·진입 상태 | [R5_PAIRED_PASSAGES.csv](r5_passage_bias/R5_PAIRED_PASSAGES.csv), [R5_NEAR_ENTRIES.csv](r5_passage_bias/R5_NEAR_ENTRIES.csv) |
| R5 AR 기억·근거리 정보 손실 | [R5_AR_MEMORY_AND_INFORMATION.csv](r5_passage_bias/R5_AR_MEMORY_AND_INFORMATION.csv) |
| R5 시간축·공분산 검산 데이터 | [R5_TIMELINE.csv](r5_passage_bias/R5_TIMELINE.csv), [R5_POSTERIOR_COVARIANCE.csv](r5_passage_bias/R5_POSTERIOR_COVARIANCE.csv) |
| R_ref 여유·감도 노출 | [rref_exposure/REPORT_KO.md](rref_exposure/REPORT_KO.md), [DISTANCE_EXPOSURE.csv](rref_exposure/DISTANCE_EXPOSURE.csv) |
| 원래 입력 → 저장소 경로 | [INPUT_LOCATIONS.json](INPUT_LOCATIONS.json) |
| 게시 출처·범위 | [PUBLICATION.json](PUBLICATION.json) |
| 전체 게시 파일 해시 | [SHA256SUMS](SHA256SUMS) |

루트 계약 SHA256은 `3e6413fa4294ab8e5568b9811477504f02711eb8f8585846da989edff713eb59`다. 원본 48개 파일을 byte 단위로 보존했다. 최초 R2 구현 중단과 수정 후 attempt02 계약도 포함한다. 기존 입력·M6 trace·보고서·계약은 수정하지 않았다.

기존 게시 경로로 연결되는 입력은 중복 저장하지 않았다. 그 외 D3 분해 3개, seed 10 online NPZ 3개와 출처 코드 3개는 `inputs/`에 원본 해시 그대로 포함했다. 루트 계약 입력 64개와 추가 출처 코드 2개의 위치·해시를 `INPUT_LOCATIONS.json`에서 확인할 수 있다.

## 코드와 확인 방법

분석 코드는 [analyze_r2.py](r2_seed_decomposition/analyze_r2.py), [analyze_r5.py](r5_passage_bias/analyze_r5.py), [supplement_memory.py](r5_passage_bias/supplement_memory.py), [analyze_rref.py](rref_exposure/analyze_rref.py)다. 각 폴더에 당시의 검증 코드·동결 계약·실행 및 검증 영수증이 있다.

원본 분석 코드는 당시의 절대 경로와 출력 보호 규칙을 보존한다. 새 checkout에서 아래 명령은 원본 경로 없이 Python 표준 라이브러리로 게시 파일·기존 입력 해시, R2 heading 회계·RMS, R5 bθ 회계·통과별 y RMS·근거리 q_s를 확인한다. 입력 NPZ는 [기존 M6 묶음](../gm_theta_m6/README.md) 등을 사용하며 Git LFS 원본을 먼저 받아야 한다.

```powershell
python verify_archive.py
```

이 검증은 게시 후 확인이며 새 EKF 실험·원인 개입 시험이 아니다. 원본 분석을 다시 실행하려면 계약과 `INPUT_LOCATIONS.json`의 입력을 복원하고 새 출력·계약을 사용해야 한다. Stage 0의 허용 주장은 기존 trace에 대한 진단이며 KI의 반사실 인과, 독립 RF 일반화, M7 채택은 포함하지 않는다.
