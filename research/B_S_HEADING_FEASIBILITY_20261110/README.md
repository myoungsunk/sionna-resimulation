# B: 선형·비선형 S–Heading 범위 비교

- [선형 분석 보고서](LINEAR_REPORT_KO.md): 분산 구성, 위치 고정/위치 범위 포함 스윕, 3,136행 데이터.
- [비선형 비교 보고서](nonlinear_20261110/REPORT_KO.md): 원본 SourceFFD와 동일 조건 선형 검사 비교.
- [비선형 전수 비교 CSV](nonlinear_20261110/COMPARISON.csv)
- [실제 Heading 범위 그림](nonlinear_20261110/NONLINEAR_RANGES.png)
- [계약과 주장 한계](nonlinear_20261110/CONTRACT.md)
- [검증 결과](nonlinear_20261110/CHECKS.json), [원본 실행 출처](nonlinear_20261110/PROVENANCE.json), [업로드 파일 SHA](UPLOAD_MANIFEST.json).

현재 허용폭에서 비선형화해도 해로운 S 검출은 0/1,390이다. 폭 10%에서는 선형 대비 유익한 관측 31건 추가 보호·해로운 관측 7건 추가 검출이지만 유익한 524건도 배제한다. 가능성 검토 결과이며 새 가드 적용·폐루프 성능 개선·채택을 주장하지 않는다.

## 입력 및 재현 범위

원본 코드: `e3ddc9fa4371d899a08a2a873d2ee5cf32074a01`. 원본 실행: [Actions 42600632209](https://github.com/myoungsunk/sionna-resimulation/actions/runs/42600632209).
대형 원본 NPZ와 편파 bank는 [기존 검증된 Release](https://github.com/myoungsunk/sionna-resimulation/releases/tag/fp-sc-original-npz-20261108)를 참조한다. 이 폴더에는 중복 업로드하지 않았다. 파일별 SHA는 PROVENANCE와 BANK_RECEIPT에 보존했다.

보고서·CSV·그림·저장된 비선형 SCAN NPZ는 즉시 열람 가능하다. 분석 코드는 실행 당시 파일을 보존한 것으로 원본 입력이 자동 포함된 독립 실행 패키지는 아니다. 전체 재계산에는 이 폴더에 R2.zip/R4.zip/R5.zip와 각각의 `R*_B0_Full_10__online.npz`, `__evaluator.npz`가 필요하며 nonlinear_20261110에는 SHA 일치 bank 두 개가 필요하다. Python 3.13.15, NumPy 2.2.4를 사용했고 SciPy/Matplotlib이 필요하다. 원본 재현 스크립트의 Windows Malgun Gothic 폰트 및 finalize.py의 로컬 governance 경로는 다른 환경에서 별도 준비해야 한다.

원본 실행 파일과 체크섬은 수정하지 않았다. 업로드 시 추가한 문서는 README, LINEAR_REPORT_KO, UPLOAD_MANIFEST이다. 새 시뮬레이션·재귀 EKF·Actions 실행 없이 기존 결과를 게시했다.
