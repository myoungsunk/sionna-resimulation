# 독립 DATA 감사 — ACCEPT

신규 Native RT R4_aB_m0 pose194 원본 pose의 새 capture를 검증했다. 이전 STOP 데이터를 신규 실행 대신 제출하지 않았다. 기존 STOP 판정은 보존했다.

- 257bin, 16,080ray, 63group, 265artifact 검증.
- source24·bank2·과학 코드7개, 실제 runtime·GO·좌표·시각·해시 일치.
- 최대 RX별 Full 상대L2 6.226666194524051e-5 < 1e-3, LoS 1.6265880494270924e-7 < 1e-5.
- 독립 F64 closure 상대L2 3.2511637721193044e-16.
- SciPy Hann257/IFFT1028 독립 검산: Native/archive Full/LoS tap 모두26. eMP 차3.1232623511345814e-6은 보고용 진단이며 새 합격 임계값을 추가하지 않았다.
- retained194와 공통30array exact 일치. 압축 NPZ 바이트 일치는 요구하지 않았다.

자기검사를 독립감사로 표시하지 않았다. 별도 감사자 precision_audit의 원본 도구 출력은 SM0_FRESH_DATA_AUDIT_RESULT.json, 실행 기록은 INDEPENDENT_EXECUTION_CALLS.json에 보존한다. JSON의 재사용 검산기 내부 문구 `prospectively amended new pose`는 새로운 좌표를 뜻하지 않으며 동일 원본 pose의 신규 capture를 뜻한다.

추가 RT0회, 완료된14개/C0-B 재실행0회. 이번 감사는 Heading 인과효과나 C1/C2 실행 승인이 아니다.
