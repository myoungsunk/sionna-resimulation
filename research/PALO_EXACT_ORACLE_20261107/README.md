# PALO exact closed-loop oracle diagnostic

질문: 선택적 편파 사용의 가능성을 탐색하는 진단 대조.

독립 감사: [ACCEPT 및 검산 근거](audit/INDEPENDENT_AUDIT_KO.md).
원본 실행 결과: [REPORT_KO.md](REPORT_KO.md).
전체 상태·공분산·prior·candidate·수용 mask: `results_v2/*.npz`.
지표: [SUMMARY.json](results_v2/SUMMARY.json).

`REPORT_KO.md`의 "독립 감사/푸시 미실행"은 최초 실행 당시 상태를 보존한 기록이다. 최신 감사 판정은 위 후속 보고서가 대체한다. 기존 입력·원본 실행 보고서·실패 기록은 수정하지 않았다.

실행기: `run_exact.py`; 자체검사: `check_results.py`. 동결 런타임 NumPy 2.2.4 / SciPy 1.15.2. 재실행은 결과가 없는 별도 사본에서 수행해야 한다. 기존 results_v2가 있으면 덮어쓰기를 거부한다. 원본 입력과 Git blob 식별자는 INPUT_MANIFEST.json, 기존 산출물 해시는 OUTPUT_SHA256.json에 보존했다. 최종 게시 파일 전수 해시는 DELIVERY_MANIFEST.json에 추가된다.

참값을 쓰는 현재 시점 greedy oracle이며 온라인 알고리즘, 전역 최적 성능 상한, 공분산 보정 또는 연구 채택의 증거가 아니다. 독립 RF/경로/seed 일반화는 검증하지 않았다.
