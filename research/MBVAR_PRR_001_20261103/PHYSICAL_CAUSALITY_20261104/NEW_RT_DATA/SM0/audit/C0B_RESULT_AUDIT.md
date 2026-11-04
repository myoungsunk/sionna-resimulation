VERDICT: STOP

FINDINGS:
- 첫 R4 pose194 canary의 **F64 LoS 오차 `2.4708055×10⁻⁵`가 동결 기준 `1×10⁻⁵`를 초과**했습니다. `C0B_DATA_ACCEPTED=NO_GO`.
- 같은 원시 계수의 legacy32 LoS 오차는 `1.5256916×10⁻⁷`. 차이는 주로 위상 정밀도에서 발생하지만, 사후 기준 변경으로 PASS 처리할 수 없습니다.

EVIDENCE:
- 257 bins, 16,080 paths, 63 groups 및 1,055개 검사 PASS.
- 독립 F64 재합산 잔차 `3.3469×10⁻¹⁶`; Full archive 오차 `4.2320×10⁻⁵` PASS.
- native CFR 산술 재생이 저장된 Full과 비트 단위 일치. 해당 직접파의 LoS 오차도 `3.3314×10⁻⁵`.
- 입력·pose·geometry·PLY·material·solver·포트·원시 해시 일치. 게시 SHA `fc224bb5af7a014c62b089a8cca71234a1b98e96`.
- 검증기와 결과: `SM0_STOP_RESULT_VERIFIERS`; 전체 257행 표: `SM0_STOP_PER_BIN_METRICS`.

MISSING_EVIDENCE:
- 과거 원본 ray 계수가 없어 물리 경로의 완전한 동일성은 입증되지 않았습니다. 물리 원인·heading 인과성·일반화는 미검증입니다.

REQUIRED_CORRECTION:
- STOP과 실패 원시 증거를 보존하십시오. 나머지 14개 pose 및 추가 시뮬레이션은 진행하지 않습니다.