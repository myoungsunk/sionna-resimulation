# T0/T1 두 RX 초기 에지 전수 진단

고정 원본 e4930310987ca89c4ce7d71f33f1a7e3d799fddf

**자기검산 결과. FP 교체·EKF·S3·원래 E1-02/E2를 실행하지 않음.**

Full 3136개: 오류 1003 / 정상 2133; 미교체 오류 998. Native-LoS 3136개.

| 진단 | 오류 경보/1003 | 정상 오경보/2133 | 미교체998 경보 | 오류에서 참조와 일치할 가상 tap |
|---|---:|---:|---:|---:|
| RAW | 0 | 0 | 0 | 0 |
| VAB_MIN_SUPPORTED | 997 | 2133 | 992 | 367 |
| TWO_PORT_GLOBAL30 | 343 | 229 | 341 | 233 |
| TWO_PORT_LOCAL_EDGE | 406 | 431 | 404 | 240 |

경보는 원래 raw와 새 에지가 다르다는 진단이다. 잘못됐다는 확정이나 정정 성공과 구별한다. 기존 normal을 훼손할 위험도 동시에 보고한다.

VAB_MIN_SUPPORTED는 e-1을 포함할 수 있다. TWO_PORT_GLOBAL30는 각 포트 자체 peak30% crossing, TWO_PORT_LOCAL_EDGE는 VAB로 채택된 lobe의 실제 edge이다. 두 방법 모두 P/M/정답 없이 current CIR만 사용했다.

원래 오류 방향과 크기: {"Full": 3136, "errors": 1003, "normal": 2133, "unchanged_errors": 998, "Native_LoS": 3136, "error_by_route": {"R2": 286, "R4": 284, "R5": 433}, "error_by_sign": {"LATE": 748, "EARLY": 255}, "error_by_magnitude": {"ONE": 916, "GE2": 87}, "old_final_reasons": {"HOLD_HISTORY": 3, "INSUFFICIENT_WRONGNESS_OR_GAIN": 501, "ORIGINAL_BEST": 464, "ABSTAIN_AMBIGUOUS": 26, "NULL_PATH_PRIOR_CONFLICT": 4, "SUPPORTED": 5}}

기존 참조/원래 detector를 전수 재현했으며 원시 payload는 INPUT_HASHES.json에 기록. 새로운 진단의 통계적 일반화/독립감사는 수행하지 않았다.
