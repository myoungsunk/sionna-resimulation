# G1-MODEL-003 S0

S0a PASS. G1-DIAG-003의 원본 입력과 기준은 `G1_DIAG003_S0_20261114/S0_INPUT_MANIFEST.json`에 기록했다. [R2 hosted 재생](https://github.com/myoungsunk/sionna-resimulation/actions/runs/43606841242)의 판정은 REPORT_LEVEL_PASS다. 두 재생의 수치 파일 34개가 바이트 단위로 일치했고, RF ZIP의 B0 DR-only 원본 배열과의 상태·공분산 최대 차이는 두 재생, 네 조건에서 모두 0이었다. 과거 R2 결과 ZIP은 만료되어 그 ZIP과의 프레임 비교는 미검증이다. 이전 로컬 실행에서 관측한 공분산 차이는 별도 실패 기록으로 보존한다.

[Anchor B hosted 재생 및 게이트 검증](https://github.com/myoungsunk/sionna-resimulation/actions/runs/43608230392)에서 R4‑B는 1.323°와 40.0%, R5‑B는 2.541°와 22.1%로 원본 보고 자릿수에 일치했다. 두 경우 모두 원본 trace NPZ와 재생 trace NPZ의 SHA‑256도 일치했다.

S0b PASS. 생산 메타데이터의 pose ID로 0.2 s packet timeline을 만들고 `TIMELINE_CHECK.json`과 `TIMELINE_READBACK.json`에 검사 결과를 남겼다. TEACH 전체 뒤에 정렬된 REPEAT를 놓고, P‑E의 세 재배치 표본은 각각 같은 TEACH의 대안 REPEAT로 연결한다. station 사이 이동은 동결 P‑A′를 따르며 REPEAT 정렬과 P‑E 어긋남은 station 안에서 적용한다. TEACH 측정에서 개별 정지 시작·종료 시각이 확인되지 않아 지정한 기본값 2 s를 각 TB3 정지점에 적용했다. P‑B와 P‑C의 네 경로는 독립 시간축이다. 동일한 RF pose를 쓰는 packet도 별도의 열잡음 seed를 갖는다.

첫 구현은 정렬된 REPEAT station을 직선으로 잇는 방식에서 pose 허용 오차를 넘겼다. 첫 검사와 코드는 로컬 `attempt_01_direct_aligned_transit/`에 보존했다. 이후 사양의 P‑A′를 station 사이 기준으로 적용하고 모든 packet을 다시 검사했다. 이번 단계는 생산 pose 메타데이터만 사용했다.
