# PALO-GAP-002

RF 오염 오라클, 온라인 특징, 잘못된 거부·수용, 공분산 및 개발용 판정기 대조.

- 사전 계약: CONTRACT.md
- 실행: `python -B campaign.py`
- 사후 검산·집계: `python -B analyze.py`
- 그림: `python -B plot_results.py`
- 결과 보고서: REPORT_KO.md (실행/분석 후 생성)

입력은 `D:/codex/PALO_EXACT_ORACLE_20261107_01`의 동결 LUT·controls·Full/LoS 측정·원본 결과를 참조한다. engine.py의 PRIOR에서 경로를 지정한다. 입력 계보는 이전 감사 커밋 eaf9a386ec8da9cb58aaeec2e3481563de0c0a7f이며, 입력 원본 커밋은 4c43020f04fbbf7d0510f792c4ab99a1d9f5ddb5이다. Python 3.13.15 / NumPy 2.2.4 / SciPy 1.15.2 사용. 결과 디렉터리가 있으면 덮어쓰지 않는다.

기존 원본을 수정하지 않는다. 저장된 636개 궤적의 X/P/prior/candidate/mask/benefit은 results/trajectories/에 있다. 전체 코드·결과 SHA256은 OUTPUT_MANIFEST.json에 기록한다.

이번 결과는 이미 공개된 단일 R2/seed0 자료의 개발용 진단이다. 오류 seed 반복은 RF 독립 반복이 아니다. 단순 온라인 특징 판정기를 시간 분할로 평가하더라도 미사용 환경의 최종 검증은 아니다. 추가 실험의 독립 감사와 GitHub 게시 여부는 보고서에 구분한다.
