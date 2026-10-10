# 고정-truth noisy 회전 제한 대조군 전달본

주 보고서: [REPORT_COMPLETED7_KO.md](REPORT_COMPLETED7_KO.md). 최종 비교표는 SUMMARY_CURRENT의 SPEC_ALIGNED 파일이다.

- PRE_CORRECTION_ARCHIVE: 수정 전 6,120회와 station P6/RF 원자료. 이 안의 C는 LoS range+s 조건으로 사양서 C와 다르다.
- C_CORRECTION_ARCHIVE: full RF range+LoS s로 C만 1,020회 재실행한 원자료. 원자료를 덮어쓰지 않았다.
- SUMMARY_CURRENT: 수정된 C를 합친 6,120회 표, seed별 worst/NIS, third-RF와 복귀 후 진단. 집계 숫자는 full-route 성능이 아니다.
- HARNESS: 별도 실행/계측/검산 소스. 원 sensor/filter core는 변경하지 않았다.
- EXECUTION_RECEIPTS.json / LOGS: 실행 명령·exit·자원·로그. 실패 pilot도 보존한다.
- DOWNLOAD_INTEGRITY.json / PUBLICATION_MANIFEST.json: shard 및 게시 파일 내용 해시.

archive는 32MiB 이하 실제 byte shard다. 별도 새 작업 디렉터리에서 part-000,001,... 순서로 이어 tar.gz를 만들고 PACKAGE_MANIFEST의 archive_sha256을 확인한 뒤 해제한다. 해제된 OUTPUT_MANIFEST의 file SHA도 확인한다. 두 archive는 별도 디렉터리로 해제하고 원 C 파일을 조용히 교체하지 않는다. FFD bank와 원 전체 주행 7.2GiB RAW archive는 외부 원보관본이며 이번 station subset과 구분한다.

공분산 파일의 validated는 추정 가능 flag이고 independent_site_count는 distinct XY 개수다. 통계적 calibration/독립성 PASS가 아니다. q_site/q_point·F/H joint mixture·실제 구동/slip 이동·새 geometry는 미검증이다. F01/F02 OPEN, scientific_PASS=false.
