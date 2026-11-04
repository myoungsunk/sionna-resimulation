# SM0 개정 계약 및 C0-B 실행 완료

2026-11-04 사용자 승인 범위를 완료했다. 신규 14개 pose는 모두 정상 종료했고, 보존 R4 pose194를 포함한 총15개 데이터를 독립감사에서 수용했다. C0-B 분석과 별도 결과감사도 수용됐다. 기존 STOP 원시 자료와 원래 NO_GO는 그대로 보존한다.

## 단계별 게시

| 단계 | Git 커밋 | 결과 |
|---|---|---|
| 나머지 14 pose 실행 전 독립 GO | 2b10911d50cf371a5eae7d48e9fbe920614f1d92 | 원래 좌표·환경·개정 정밀도 고정 |
| C0-B 분석 코드 독립 사전감사 | e7e67b1bd60e6fb684c5871ea9b00bca867a2ccf | 합성 대조 및 실패 차단 통과 |
| 신규 원시 데이터 | 90267fab16bde224652ec886f234e1f5e57d0619 | 14/14 수치 통과, 3,612 LFS 객체 게시 |
| 전체 데이터 독립감사 | 181c36d8167b232c1a04cf1b353330aa4a71a595 | ALL_15_AMENDED_SM0_DATA ACCEPT |
| C0-B 분석·독립 결과감사 | a4850b7ab31a1f259764c90ad94464bd06c93d14 | 선택된 시뮬레이션15 pose 범위 ACCEPT |

## 핵심 검증

- 15 pose, 3,855 frequency bins, 241,200 raw paths 및 원시 artifact3,975개 해시 검증.
- 실제 분석 Full 최대 상대오차 1.2103707894821433e-4, RX별 최대1.2950749541768317e-4로 1e-3 이하.
- LoS RX별 최대 상대오차 6.91387858594439e-7로 1e-5 이하.
- 독립 F64 합산 최대 상대오차 3.441366669238409e-16로 1e-8 이하.
- C0-B 검출 tap60개, chain 제거1,860행, surface 제거180행, window복소값2,160개, scalar비교18,915개 독립 검증.
- C0-B scalar 최대 차이1.7208456881689926e-15, coherent power closure 최대 절대 잔차1.6059744679941534e-18.

## 결과의 의미

| 선택 사례 | eMP | Full/LoS tap | 확인 범위 |
|---|---:|---|---|
| R4 pose168 | +0.3422 | 33/31 | 같은 tap 차이와 검출 tap 선택 차이가 함께 존재 |
| R5 pose465 | −1.2980 | 73/57 | tap16칸 이동, tap선택 차이−1.4821과 같은 tap차이+0.1841 |
| R2 pose525 | +0.7824 | 57/57 | tap이동 없이 큰 같은 tap 편파비 차이, 음의 y벽 체인 제거 효과+0.6774 |
| R4 pose234 | +0.0014 | 22/22 | 작은 순편파오차와 개별 반사 제거 효과의 크기는 다름 |

면 제거 효과는 저장된 ray 성분을 제거하는 오프라인 반사실이다. 면별 효과를 더하거나 signed ratio 제거 차이를 합산 기여율로 해석하지 않는다. 실제 벽 제거 재시뮬레이션, 새로운 RF 일반화 및 Heading/공분산 과신 인과성은 검증하지 않았다. C1–C3와 SM1/SM2는 실행하지 않았다.

## 원본·감사·재현 자료

- [신규14개 데이터 색인](BATCH_AMENDED_001/INDEX.csv)
- [전체15개 데이터 독립감사](BATCH_AMENDED_001/audit/DATA_RESULT_AUDIT.md)
- [C0-B 결과 해설](C0B_ANALYSIS_001/RESULTS_KO.md)
- [15개 전체 결과표](C0B_ANALYSIS_001/RESULTS_001/SUMMARY.csv)
- [C0-B 독립 결과감사](C0B_ANALYSIS_001/audit/RESULT_AUDIT.md)
- [C0-B 독립 검산기](C0B_ANALYSIS_001/audit/INDEPENDENT_RESULT_VERIFIER.py)
- [보존된 최초 STOP 감사](audit/C0B_RESULT_AUDIT.md)

첫 canary의 개정 재검증은 사후 계약 변경이다. 나머지14개는 개정 계약을 실행 전에 고정했다. 15개 모두 이미 관찰한 hotspot/대조 표본이므로 비노출 확인 표본이나 발생 빈도 추정에 사용하지 않는다.

계산 및 LFS 보조 프로세스는 정상 종료하고 manager 소유권을 해제했다. 해당 WSL producer의 종료도 확인했다. 실행 성공, 개정 데이터 수용, C0-B 결과 수용은 각각 별도 판정이며 알고리즘 채택을 뜻하지 않는다.
