# trace `signature` 필드는 슬롯 식별에 쓸 수 없다 (G3_v2 감사 항목 1)

감사 항목 “반사 순서 또는 경로 signature의 일치”를 확인하려 했다 (`signature_audit.py`, `signature_audit.json`).

**발견:** 전달된 trace npz의 `signature`(문자열 배열)는 `tau`/`ang`/`jones`/`present`의 슬롯과 정렬되어 있지 않다. 슬롯은 지연 오름차순이고 signature는 이름 사전순(`LOS, ceiling, ceiling>end_x_max, …`)이다. 두 순서가 우연히 맞는 것은 슬롯 0(LOS)과 1(ceiling)뿐이다. 예: 한 위치에서 슬롯 2의 지연 1.4028e-8 s는 같은 이름 `ceiling>end_x_max`의 기하 지연 1.1645e-7 s와 전혀 다르다. 추가로 일부 위치(R4_aB 3, R4_aA 3, R2_aA 1, R2_aB 1, R5_aA 9, R5_aB 7)는 `signature` 길이가 `tau` 길이와 다르다.

**귀결:** 
1. “signature 일치” 검증은 **수행 불가(NOT_RUN)** 이다. 이름 기반 식별로 PASS를 주장하지 않는다.
2. G3_v2의 경로 식별은 **지연 + 출발각 + 도착각** 3중 기하 일치와 1:1 배정에 의존한다. 서로 다른 시퀀스의 최소 각 간격은 지연이 가까운 경우에도 ≥ 9.8e-2 rad이고 매칭된 쌍의 각 잔차는 ≤ 6.6e-4 rad이므로, 이 식별은 기하적으로는 충분히 분리되어 있다(완전 모호 0건).
3. 단, 이는 “trace 슬롯이 어떤 반사 시퀀스로 만들어졌는지”를 trace 쪽 라벨로 확인한 것이 아니라 기하와의 일치를 본 것이다. 데이터 제공자에게 슬롯 정렬된 signature를 요청하는 것이 정확한 해결책이다 (`NEXT_BLOCKERS_KO.md`에 등재).
