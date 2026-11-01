# 기존 원고 v4 검토 패키지 — 읽기 가능한 보존본

이 폴더는 사용자가 전달한 `DualLP_Manuscript_v4_Physics_Review_20261101.zip`의 검토 보고서·원장·표·재집계 스크립트를 GitHub에서 읽을 수 있게 옮긴 것이다. **이번 제안자 작업에서 재집계 스크립트나 새 실험을 실행한 것이 아니다.**

## 포함된 원본 파일

원본 ZIP의 9개 파일 중 아래8개를 byte-identical하게 복사했다. Git blob 값은 로컬 원본과 원격 업로드 후 비교했다.

| 파일 | 원본 Git blob |
|---|---|
| [검토 보고서](MANUSCRIPT_V4_PHYSICS_CLAIM_REVIEW_KO.md) | c007302cf7a9a3e7b1cc168d02d31ccdbacc9215 |
| [기존 검토 QA](RECHECK_QA.json) | c5e2169e2f98060ac3d8bd2e7ea0aca9357d77ee |
| [원본 manifest](MANIFEST.json) | e8cdbe144f24f8ec0f585a68d604d67be4c56d85 |
| [D2 선택값 전사](evidence/D2_SELECTED_SELF_TRANSCRIPTION.json) | b100f2addffa35839d4a8ec6ea6ce0b0f00a58df |
| [역사적 재집계 스크립트](recompute_review.py) | d8c868b6e4574ae44121f0fdf466addcb3849da6 |
| [12조건 전체 비교](tables/SELECTED_12_CONDITIONS_RECHECK.csv) | 32267b40e5fd4bcd3476410f233a2ec839ae9c7c |
| [평균·분산 fixed/self 대비](tables/MEAN_VARIANCE_FIXED_SELF_CONTRASTS.csv) | 8562ec9a08e34361ee4a6665df0f08af00553a36 |
| [D3 선택 잔차표](tables/D3_SELECTED_B0_RECOMPUTED.csv) | 0db9c074fc80be1b4cfa302cd3e07e951eb97569 |

## 외부에 유지한 원자료

`evidence/RA4_336_ARMS.csv` 전체 원자료는 이번 폴더에 복사하지 않았다. 원래 [RA4 실행 artifact](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40859507594/artifacts/12890904334) 또는 사용자가 전달한 원본 검토 ZIP에서 얻는다.

- 파일 크기: 79,647 bytes
- SHA256: `bb19a4f49260a45d94a98832f64110c66056487f6555b44e482064ef3221b7c0`
- Git blob: `482deda8a7f574e3522e2352354a5d690cbdc34d`

후속 재현 시 이 파일을 정확한 `evidence/RA4_336_ARMS.csv`로 복원하고 SHA를 확인해야 한다. artifact는 서비스 보존기간/권한에 영향을 받으므로, 기존 raw 입력 archive를 별도 보존한다. 원본 `recompute_review.py`는 `/mnt/data/RA4_336_factorial.zip`가 있으면 그것을 우선 읽으므로, 재현자가 어느 입력을 사용했는지 확인해야 한다. 이 스크립트는 참고용 원바이트 보존이며 새 검증 구현물/실행 승인이 아니다.

## 원본 ZIP의 보존 범위

- 원본 ZIP 이름: `DualLP_Manuscript_v4_Physics_Review_20261101.zip`
- 원본 크기: 47,466 bytes
- SHA256: `0d261f54a586cb0c11f24f32586ae693b83092bb24168dce0d2209b924156980`
- ZIP CRC 검사: 이 문서 작성 시 정상
- **ZIP 바이너리 자체는 이 Git tree에 업로드하지 않았다.** 대화의 원본 첨부로 보존하고, GitHub에는 위 읽기 가능한 파일과 원자료 연결을 게시했다. 이 폴더는 원자료 다운로드 없이 완전히 자급적인 재실행 ZIP이라고 주장하지 않는다.

원본 QA의 `repo_writes=0`와 manifest의 `github_writes=0`는 **그 이전 검토 작업의 기록**이다. 이번 GitHub 문서 업로드 횟수를 뜻하지 않는다. historical `48/48`, `12/12` 등은 새로운 독립 감사 결과가 아니다.

이번 새 제안자 설계와 결과 사용 규칙은 [상위 패키지 안내](../README_KO.md)를 읽는다.
