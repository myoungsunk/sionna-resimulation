# Stage 2·3·5 재진단 v2.1 — 실제 데이터 실행 결과

2026-10-28 · 기준 커밋 `450a21fd38cf6be510d55352ae3741c8e808bc0a`

최종 상태: **TECHNICAL_QA_PASS_NOT_SCIENTIFIC_ADOPTION**. 실행 종료 코드 0.
이는 기술 검증 완료이며 Heading 개선 방법 채택이나 인과 가설 확정을 뜻하지 않는다.

| 단계 | 검증 |
|---|---|
| Stage 2 | 잔차 통계 336행, 28개 검사 PASS. 거리별 native packet lag 및 8/16/32초 bootstrap |
| Stage 3 | 308개 검사 PASS. 기존 ALL 결과 168개 비교의 최대 차이 2.092548356813495e-12, 기준 1e-10 이내 |
| Stage 5 | 독립 Fisher 672개 시나리오, 1,428개 검사 PASS. 안정 수치미분 1,675건, 비매끄러운 전환 5건 별도 분류 |

## 확인 순서

1. [최종 판정](results/PATCH_V2_FINAL.json)
2. [실행 상태·명령·로그 경로](execution/EXECUTION_STATUS.json), [실제 실행 로그](logs/)
3. [Stage 2 통계](results/02_residuals/RESIDUAL_STATS.csv)
4. [Stage 3 모집단 비교](results/03_RF_R_H/R_SAMPLE_CONTRASTS.csv), [기존 ALL parity](results/03_RF_R_H/LEGACY_ALL_PARITY.json)
5. [Stage 5 독립 검산](results/05_full_observability/FISHER_INDEPENDENT_AUDIT.csv), [rank 민감도](results/05_full_observability/FISHER_RANK_SENSITIVITY.csv)
6. [패치 수정·합성 검증 보고서](package/REVIEW_FIXES_V21_KO.md)

## 구성과 보존

- `code/`: 실제 실행한 v2.1 코드와 코드 해시, 적용·합성시험 기록.
- `results/`: 세 단계 전체 출력. NPZ를 포함한 실제 파일이며 LFS 포인터가 아니다.
- `package/`: 전달 패치·실행 도구·설명서·검증 자료. 별도 ZIP도 포함.
- `logs/`, `execution/`: 실제 실행 및 원본 보존 근거. 실행 전후 비교한 기존 코드·결과 파일 70개는 변경 없음.
- 기존 `DS_REASSESS_1_TO_6_20261027` 및 원본 로컬 결과는 변경하지 않았다.
- **실제 데이터 Stage 1·4·6은 재실행하지 않았다.** 적용 과정의 합성 회귀시험 28개는 기존 합성 smoke test를 포함한다.
- 원본 Full RF 캐시를 사용한 Stage 2 통계 재산출이며 CIR FFT를 새로 실행하지 않았다.

## 재현 주의

v2.1 패치의 실제 적용 기준은 정확한 `450a21f` checkout이다. 이 업로드 커밋을 그대로 RepoRoot로 사용하면 exact-HEAD 게이트가 거절하는 것이 정상이다. 별도의 기준 checkout과 새 CodeOut/OutputRoot에서 package 설명서의 절차를 따른다. 절대 경로는 실행 당시 Windows 경로를 보존한 provenance이며 새 환경의 경로와 동일하다고 가정하지 않는다.

[업로드 파일 해시](UPLOAD_SHA256.json)로 파일 무결성을 확인할 수 있다. 통계적 표본 부족 NA와 비매끄러운 전환 별도 분류는 실행 실패와 구분한다.
