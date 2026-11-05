# C3-CODE-01 수정 기록

독립 G1 CODE 감사는 저장 진단 배열 native_cfr32를 NaN으로 변조해도 QA가 통과하는 결함을 재현하여 REDIRECT했다. 최초 감사 기록은 audit/C3_CODE_AUDIT_RESULT.json에 보존한다. 이때 신규 RT/모델 초기화는 0이었다.

수정은 `qa.native_cfr_check`로 native complex64/shape/finite를 강제하고, producer가 bin 원본을 저장한 직후 다음 solver 호출 전에 검증하도록 한 것이다. 최종 RAW QA는 native_cfr32 존재와 (257,2) schema를 검사한다. 기존 결과를 숨기거나 tolerance를 완화하지 않았다. native API CFR와 legacy 합의 새로운 일치 기준을 추가하지 않았다.

회귀검사는 missing/NaN/Inf/dtype/shape와 단일 bin 저장 직후 검사 경로를 포함한다. pinned WSL 자체 검사 결과는 logs/G1_OFFLINE_TESTS_002.log에 보존한다. 수정 완료와 독립 재감사 승인, GO 발급은 별도이며 재감사 전 RT 실행 금지이다.
