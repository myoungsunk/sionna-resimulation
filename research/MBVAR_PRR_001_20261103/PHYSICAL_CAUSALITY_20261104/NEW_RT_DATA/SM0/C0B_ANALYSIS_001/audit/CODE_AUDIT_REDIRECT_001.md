VERDICT: REDIRECT

FINDINGS:

- 반사실 영 채널 처리가 분석 계약과 다릅니다. `diagnostics.evaluate()`의 chain/surface 제거 후 `detect()`가 영 채널을 만나면 전체 분석을 중단합니다. 계약은 반사실 signed ratio를 undefined로 기록하도록 정했습니다.
- `analyze.py` 실행 영수증에 계약에서 요구한 governance 해시 및 실제 Python/NumPy 환경 기록이 없습니다.
- 원본 호환 loader, F64 분석 우회 차단, 15개 입력·코드·데이터 해시와 수용 문서 검사 구조는 적절합니다.

EVIDENCE:

- 합성 사례 `DIRECT=D`, `wall=-D`, `floor=D`는 Full=LoS=D로 유효합니다. floor 제거 시 영 채널이 되며 현재 코드는 `undetectable all-zero composite`로 실패합니다.
- 합성 Hann257/IFFT1028 결과와 독립 직접 DFT 최대 차이 `4.6404e-13`.
- strongest-RX의 30% 경계 선택, 3개 반사 그룹의 permutation 기반 독립 Shapley 검산, 반복 surface를 포함한 chain의 중복 제거 검사 통과.
- 실제 RF FFT 호출 0회, 파일 변경 0개.
- 검증기·결과는 도구 출력 `SM0_C0B_SYNTHETIC_PREAUDIT_RESULT`.

MISSING_EVIDENCE:

- 수정본의 영 반사실 처리 및 환경 영수증 재감사.
- 전체 데이터 독립감사와 실제 C0-B 결과. 아직 실행 승인하지 않았습니다.

REQUIRED_CORRECTION:

- 동결된 기존 diagnostics를 보존하면서 개정 분석 경로에서 영 반사실의 재검출 tap/s를 undefined로 기록하고 건수를 보고하십시오. 원래 Full/LoS 영 채널 STOP은 유지하십시오.
- 실행 영수증에 적용 governance 해시와 실제 Python·NumPy 환경을 기록하십시오.
- 수정 후 합성 대조와 코드 해시를 재감사하겠습니다.
