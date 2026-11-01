# DLP-PHYS-LINK-001 — R4 QA V3 독립 재감사

## 최종 판정: ACCEPT_WITH_BOUNDARIES

**R4-OPEN-01/02/03 종료.** `R4_QA_V3`은 독립적으로 원본 CONTROL·trace를 대조하고 직접 오염시킨 시험에서 유효하다. 이는 QA 수정에 한정한 승인이지 전체 새로운 RT/물리적 인과 모델의 인증이 아니다.

- 검증한 구현자 커밋: [`8c11b017783705b9c4884c11d67a68b5710578ae`](https://github.com/myoungsunk/sionna-resimulation/commit/8c11b017783705b9c4884c11d67a68b5710578ae)
- 이전 독립 감사의 미완결 항목: `R4 stale got`, `strict timestamp`, `independent scoring denominator`
- 원격 비교 기준: `25e16bfb71786835dbd7260467e243016c0bca6b` → 신규 **23파일** / 기존 파일 변경 0 / 삭제 0
- 보완 ZIP: 68,709 bytes, SHA-256 `ed324559ba7575d553fd68b84293bf770ea21e1c90dd65f2e96137d7e8f803e2`; 21개 manifest 파일의 sha256·Git blob·size 일치
- V3 source SHA-256 `6d375c8dd8f0805786ea6081c9a3437dbcda4ec477a687dc2ed81a0acee98669`; Git blob `06da34867269f791093deff9d069dd90498a2ec5`
- 봉인된 원 입력 108개 SHA-256, 이전 감사에서 확인된 132개의 raw trace SHA-256 유지

## 별도 실행으로 확인한 결과

| 검증 | 제3자 계산·실행 결과 |
|---|---|
| 정상 Python + `PYTHONOPTIMIZE=1`에서 V3 전체 QA 독립 재실행 | PASS / PASS |
| 선언된 필수 검사 / 선택 검사 | 5,729 / 5,729 PASS · 2 / 2 PASS |
| 입력·검출기 오염 및 메타시험 | 76 / 76 기대결과 일치 |
| Pytest (일반 인터프리터) | 8 / 8 PASS |
| 이전 V2 원장 5,290행 전체 8개 필드 | 0개 변경 |
| 새로운 검사 | 441개, 검사 ID 중복 0개 |
| 공개 CSV/판정 JSON/음성시험 JSON 재생산 | **일반·최적화 출력이 게시본과 바이트 일치** |
| 별도 NumPy 수학식·원본 해시 검사 | 122 / 122 PASS |
| 12 case×gyro 조합에서 실제 V3 검출기를 호출한 교차검증 | 96 / 96 PASS |
| 144 logical trace × 5 timestamp / denominator guard | 720 / 720 원본 CONTROL에 대한 독립 기대값과 일치 |

## 결함별 독립 반례

1. `pose_id`와 `t` 손상시험이 **각 현재 호출의 반환값**을 사용한다. V3 대상 코드의 검출기를 전부 0으로 무력화하면 오염이 미검출되고 해당 음성시험은 FAIL한다. 이 실패를 확인하는 메타시험만 PASS가 된다. 단독 및 역순 실행도 동일하다.
2. 동일/역순 timestamp 및 비유한 time을 검출한다. 원본 CONTROL의 `t_s`와 saved `dt[1:]`를 독립 비교한다.
3. 독립 원 CONTROL의 `t>=30` 분모와 mask를 비교한다. R2-B/B0 +1초 이동은 평가 표본 **829→834**, `score_count=5`, `score_mask=5`로 정확히 검출했다. R4/R5의 원본에서도 동일한 수학식으로 검증했다.

## 역할 분리와 과학적 해석

- 실제 별도 실행은 새로운 scratch Python 파일과 NumPy 비교식을 사용했다. archived `bootstrap`는 **입력/CONTROL/trace 로더**로만 재사용했고, V3 검증기는 **시험대상**으로만 호출했다. 저장된 PASS 필드만 재포장한 것이 아니다.
- 이전 R1/R2/R3/R5 감사의 원자료 재산출 증거는 그대로 승계한다. 이번 재감사는 **R4 QA 변경만**을 다룬다. 132회 EKF 재귀, 새로운 RT/FFD 물리장, fresh inference는 새로 실행하지 않았다.
- 과학적 결과 `MIXED`, R4 XY 악화, 지정 상수 대비 R4의 lookup 열세는 그대로 남는다. `15503350…` 원본 실행은 여전히 미복구. 독립 scene 일반화·하드웨어 calibration·전체 누적인과는 인증 불가.
- 이 서명은 **AI 별도 계산/실행 감사**다. 동일 사람이 구현자와 독립 서명했다거나 **별도 사람 감사 서명이 있었다고 주장하지 않는다**. `python -O -m pytest`는 assert 비활성화 위험이 있으므로 승인 근거로 삼지 않고, 최적화된 전체 QA 자체를 별도로 실행했다.

**결론:** 기존 `REVISION_REQUIRED`의 R4 QA 3개 원인은 새 커밋에서 해소. `ACCEPT_WITH_BOUNDARIES`로 **R4 관련 판정만 상향**한다. 역사적 증거와 주장 범위는 변경하지 않는다.

감사자 원 실행 상세 파일: `AUDIT_INPUT_LOCK.json` 및 `FINAL_AUDIT_VERDICT.json`. 별도 재현 Python 스크립트/122개 검사/96개 반례 원장은 독립 감사 다운로드 ZIP에 포함한다.
