# Stage 2·3·5 패치 v2.1 수정 및 검증 결과

2026-10-28 · 기준 커밋 450a21fd38cf6be510d55352ae3741c8e808bc0a

## 수정한 세 문제

1. Stage 2 거리별 ACF: whole 복사본 대신 원래 near/mid/far 열을 보존한 all 모집단으로 native lag 쌍을 정렬한다. 전체·수용 표본 모두 양 끝의 조건을 검사한다. 누락 packet을 이웃으로 연결하지 않는다.
2. 완료 판정: PATCH_STAGE_2/3/5.json을 별도 기록한다. 단일 단계 완료는 PATCH_PROGRESS.json의 PARTIAL_TECHNICAL_QA_PASS로 표시하며 PATCH_V2_FINAL.json을 만들지 않는다. 세 단계가 모두 끝나고 코드·입력·설정 계약, 기록 해시 및 각 단계 검사를 다시 통과해야 최종 판정을 만든다. 기존 최종 기록을 다른 내용으로 덮어쓰지 않는다.
3. 표본 부족: case/bias/arm별 whole/near/mid/far × all/accepted_A_B의 8행을 유지한다. 0개는 NA_NO_SAMPLES, 1–7개는 NA_INSUFFICIENT_PACKETS로 명시한다. 표본 부족의 잔차 평균·분산·공분산 등은 NA이며 POWER R 평균은 존재하는 표본에 대해 기술통계로 남긴다. ACF는 별도의 유효쌍 수 기준, bootstrap은 별도의 packet/블록 수 기준을 유지한다.

## 검증 결과

- 기존 13개 + 추가 15개 회귀시험 = 28/28 PASS (깨끗한 패치 적용본, exit 0).
- near/mid/far/whole, 전체/수용 표본, lag 1/5를 독립적인 쌍 열거와 대조했다.
- 0/1/7개 구간과 수용 표본이 전혀 없는 경우를 확인했다.
- 단계별 실행과 all 실행의 호출 순서·누적 완료·최종 판정을 합성 실행기로 확인했다.
- Stage 5 단독 실행, 코드/입력/설정 혼합, 이전 결과·manifest·상태 파일 변조, 실패 검사에서 최종 판정을 차단했다.
- git apply --check 및 실제 apply PASS. 패치 후 Python 15개 SHA-256 일치. compileall PASS.
- Stage 1·4·6 함수 AST 동일, engine.py/numerics.py/run.py 바이트 동일을 확인했다.
- Windows Git의 core.autocrlf=true에서 발생한 적용 후 해시 불일치를 재현했다. APPLY_PATCH.py의 해당 git 명령에만 LF 옵션을 주어 해결했다. 전역 설정은 변경하지 않았다.

## 검증 범위와 보존

기준본은 이전 ZIP에 알려진 wrap import를 반영하여 재구성했고 제공된 실행본 manifest 11/11 해시와 일치했다. 실제 Git 원격 checkout을 새로 검증한 것은 아니다. APPLY_PATCH.py 통합시험에서는 HEAD 응답만 모의하고 나머지 복사·적용·해시·구문 검사는 실제 실행했다. 이 통합시험의 --skip-tests와 별도로 깨끗한 적용본에서 전체 28개 시험을 통과했다.

기존 ZIP, 실제 프로젝트 코드, 결과 415개에는 쓰지 않았다. 모든 작성과 합성시험은 새 빌드 폴더에서 수행했다. 실제 RF 데이터·CIR FFT·E1 replay·SourceFFD bank 기반 실제 검산은 실행하지 않았다. 따라서 기술적 패키지 QA만 완료이며 과학적 채택 판정은 아니다.

실제 실행은 별도 작업이다. v2 결과나 코드 폴더를 재사용하지 않고 새 CodeOut/OutputRoot를 사용한다. 이 ZIP은 v2 위에 덧붙이는 패치가 아니라 원래 450a21f 코드에 직접 적용하는 전체 수정 패치다.
