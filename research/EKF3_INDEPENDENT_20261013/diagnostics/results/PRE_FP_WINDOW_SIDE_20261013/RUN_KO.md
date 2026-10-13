# FP 이전 window 재현

저장소 루트에서:
```
python research/EKF3_INDEPENDENT_20261013/diagnostics/d16_pre_fp_window_audit.py --out artifacts/PRE_FP_REPLAY_NEW
```
P0의 실제 RF 자산과 동결 의존성이 필요하다. 기존 결과를 덮어쓰지 않도록 새 출력 경로를 사용한다. PRE3/4에는 FP tap을 포함한다. 기준점은 원본FP 및 기준포트FP, 양포트 window는 동일하다. 임계값/가중치 탐색 없음.

RAW_EVIDENCE.zip의 analyze.py는 실제 실행한 절대경로 소스이며, 새 d16 runner는 repo/out만 인자로 변경한 재현용 소스다. 이식된 runner는 구문 검사를 완료했으며 추가 RF 재실행은 하지 않았다. RECEIPT는 원본 실행 기준이다. 첫 실행은 출력 schema 오류로 종료했고 공통열명으로 수정한 뒤 exit0로 재계산했다.

이 게시 내용은 side 대화의 FP 이전 window 분석만 포함한다. 메인 작업의 D15 코드/FFD 확보/LoS 검증을 수정하거나 완료한 것이 아니다. scientific_PASS=false.
