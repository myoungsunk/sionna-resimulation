# SM0 개정 계약의 나머지 14 pose 실행

역할 IMPLEMENTER, 질문 SM0-PRECISION-001 및 C0-B-Q0. 기준 Git b4f8752f2008eda352795d92712f2e41cdd0db76, PR #28. 사용자 2026-11-04 승인 「개정 계약 기준으로 나머지 14개 pose도 실행하고 독립감사해. 통과하면 C0-B 분석을 진행하고 단계별 결과를 GitHub에 푸시해」.

SM0-PRECISION-001의 분석 정밀도와 수치 기준을 변경하지 않는다. 기존 194 canary의 사후 재검증 ACCEPT를 재사용하고 재시뮬레이션하지 않는다. 나머지 목록은 원래 요청의 순서를 유지한다. R4 168,172,173,234,500,525,729, R5 401,465,979,980,982,983, R2 525. 모든 pose는 원래 Tnone 좌표/방향이다.

수정된 producer.py, qa.py, 입력/환경/해시를 독립감사자가 검증한 뒤 이 목록에 한정한 GO를 발행한다. 한 번에 한 pose를 실행하고 처음 비정상 종료 또는 수치 불일치가 나오면 남은 목록을 중단한다. 실패 데이터 및 로그를 보존하고 임계값 변경·실패 pose 대체·자동 재실행을 하지 않는다.

실행 launcher는 Windows managed-processes가 소유하는 Windows Python이다. WSL Python은 Windows job의 Linux containment라고 주장하지 않으며, 각 foreground WSL 명령의 종료를 launcher가 기다린다. 종료 요청 파일을 pose 사이에 검사한다. 완료 후 manager finish 및 해당 실행의 실제 종료를 확인한다.

원시 데이터를 GitHub에 동결하고 15 pose 전체 독립 수치감사를 받는다. 전체 통과한 경우에만 C0-B 원래 diagnostics의 Hann257/IFFT1028, 30% detector, same-tap 분해, semantic-chain/면별 leave-out 및 coherent port-power 기여를 원본 호환 field로 계산한다. 분석 loader 및 추가 면별 제거 구현도 실행 전 독립 코드감사를 받는다. 구 F64 postprocess는 재사용 실행하지 않는다.

단계별 푸시 대상은 (1) 실행 전 계약/GO, (2) 14 pose 원시/결과 및 독립감사, (3) C0-B 분석 및 결과감사다. C1–C3, SM1/SM2, 학습, 새 guard는 범위 밖이다. 사후 hotspot 15개에만 설명을 한정하고 독립 일반화/발생 빈도/Heading 과신 인과성을 주장하지 않는다. 기존 STOP과 NO_GO 기록을 보존하고 개정 계약 결과와 구분한다.
