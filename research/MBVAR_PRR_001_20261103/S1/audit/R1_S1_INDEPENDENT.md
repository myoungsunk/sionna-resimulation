VERDICT: ACCEPT — **S1 결과의 기술적 유효성에 한정**. `S1_RESULT_ACCEPTED_WITH_SCOPE`; 전체 개선·채택은 **NO-GO**, **S2는 HOLD**입니다.

FINDINGS:

| 잠금 평가 Full 조건 | Heading RMSE 쌍대 비율 중앙값 | 기준 | 판정 |
|---|---:|---:|---|
| R4 B0 | 0.921514 | ≤0.90 | FAIL |
| R4 L2 | 0.905549 | ≤0.90 | FAIL |
| R5 B0 | 1.062248 | ≤1.05 | FAIL |
| R5 L2 | **1.050435** | ≤1.05 | FAIL |

R5 L2를 반올림하여 PASS로 처리하면 안 됩니다.

- **S1-C1: PARTIAL.** Full의 큰 오염 정의에서 recall 100%이나 precision은 약 13–16%, clean-loss는 R4 약 5.19%, R5 약 2.05–2.08%입니다. Native-LoS의 recall은 오염 표본이 없어 NA이며, R5 clean-loss는 B0 0.652%, L2 0.466%입니다.
- **S1-C2: PARTIAL.** 동일 prior에서 실제 할인된 R4 Full 26개 갱신 모두 covariance trace 감소량이 작아졌습니다. 그러나 Heading 오류는 개선 13개·악화 13개, XY는 개선 4개·악화 22개입니다. R5와 Native-LoS의 등록된 첫 20개 표본에서는 처치가 발생하지 않았습니다. 따라서 ‘잘못된 갱신이 전반적으로 감소했다’는 주장은 지지되지 않습니다.
- **S1-C3: NOT_SUPPORTED.** R4 Heading은 개선됐지만 목표에 미달하고 XY가 악화됐습니다. R5 Full 보호 기준도 실패했습니다.
- Native-LoS의 RMSE 중앙값·p90 보호 기준은 통과했습니다. 다만 R5 Native-LoS 오류와 최악 seed NEES가 악화되어 무해성을 주장할 수 없습니다.
- R4 Heading coverage는 목표 방향으로 이동했지만 약 40% 수준입니다. 95% calibration 복원 주장은 허용되지 않습니다.

EVIDENCE:

- 코드 `c4f7394842a808b59f3e14f3c5eb985250c0c5cd`, 실행 `EVAL_001`.
- 독립 runner에서 production update/score helper 없이 **320 traces / 345,120 packets / 1,600 점수행 / 320 paired-summary행**을 검산했습니다.
- **71,400개 검사**, 불일치 없음; 최대 절대 차이 `2.28e-13`. 모든 trace finite·정규화 PSD·공통 mask 통과, 실패 로그 없음.
- 입력·epsilon·계약·GO·개발 manifest 연결 및 변경 없는 코드 확인. seed 단위 bootstrap 재계산 통과.
- 게시 커밋 `5b82a7d15cb515285ad3e37a4db7976ce43286e2`의 **325개 artifact**가 일치합니다.
- RUN_MANIFEST SHA256: `57d50e641795b25d976c5b16d5aa089c7913431ffbc7565f30b4e2f3e1ac469b`.
- 정확한 독립 검산 소스와 실행 결과는 이번 stdin 도구 transcript에 있습니다. 파일 수정·과학 재실행 없음.

MISSING_EVIDENCE:

새 RF·경로 일반화는 검증하지 않았습니다. 원격 LFS payload 재다운로드 없이 게시 pointer의 SHA256·크기를 로컬 원본과 대조했습니다.

REQUIRED_CORRECTION:

계수·결과 수정은 필요하지 않습니다. 실패를 보존하고 전체 개선·채택 주장을 보류하십시오. 계약의 실패 분기에 따라 **S2는 남은 원인 질문에 대한 별도 책임자 승인 후에만** 진행할 수 있으며, 현재 감사는 S2 GO를 발급하지 않습니다.