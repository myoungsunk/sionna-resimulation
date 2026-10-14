# RF Heading 직접 역변환 H1–H4 (2026-10-14)

[실험 보고서](SUMMARY_KO.md) · [집계 검증](ANALYSIS/AGGREGATION_RECEIPT.json) · [전체 실행 증빙](OPT/FULL/RECEIPT.json)

H1–H2 12,402개, H3 74,412개 신규 역변환 분석 및 H4 기존 trace 1,337,904개 업데이트 재계산을 보존한다. H4 1,512개 그룹의 NIS/gate/공분산 parity는 기존 허용치 1e-8 이내 PASS. 새로운 재귀 EKF 실행 결과로 표현하지 않는다. scientific_PASS=false.

## 원시 H4 복원

대용량 원시 gzip은 OPT/FULL/H4_EKF.parts 아래 40MiB 조각으로 저장했다. 이 폴더에서 `python restore_h4.py`를 실행하면 OPT/FULL/H4_EKF.csv.gz가 복원된다. 각 조각과 최종 gzip의 SHA-256을 검증하며 기존 파일을 덮어쓰지 않는다. 분할·복원 왕복 검증을 완료했다. H1–H3 gzip과 smoke trace는 원본 그대로 포함했다.

## 코드와 증빙의 의미

OPT/run_heading.py와 OPT/inverse_core.py는 실제 전체 실행한 코드다. 상위 run_heading.py는 압축 및 반복 표 변환 최적화 전 smoke 코드로, 양쪽 smoke 출력의 압축 해제 바이트가 동일하다. aggregate.py/render.py/report.py 및 검사 receipts를 포함했다.

실행 코드는 당시 Windows 입력/cache/trace 경로를 그대로 보존한 source snapshot이다. 다른 환경에서 실행하려면 경로를 매핑해야 하며, 이 게시 자체가 이식성 검증을 의미하지 않는다. frozen 데이터는 새 RF 생성 없이 기존 입력을 사용했다. 각 receipt의 절대 경로 해시는 원래 실행 환경의 provenance다. 게시 파일 자체의 상대 경로 해시는 PUBLICATION_MANIFEST.json에 있다.

SUMMARY_KO.md는 GitHub에서 열리는 상대 링크로 변환했다. EXECUTED_SUMMARY_KO.md는 당시 최종 보고서 원본 바이트다. 실험 gate·수치·모델 파라미터는 바꾸지 않았다. 기존 연구 파일은 수정하지 않고 이 폴더만 추가했다.
