# 유한 반사면 검사를 적용한 재생성과 G4

질문 ID는 G1-RT-TB3-001과 G1-RT-TB3-002다. 2026-11-15 Snowball에서 G6를 통과한 전계 계산 전 유한 반사면 검사를 기존 0° F1 생산 경로에 적용했다. 기존 형상·pose·F1 설정을 사용했다. 본 데이터 52,218 pose와 추가 P-D 5,400, P-E 2,430, P-F 1,944 pose를 생성했다. 총 11개 조합, 61,992 pose다. [실행 설정](results/RUN_MANIFEST.json) · [생성 결과](results/GENERATION_RESULT.json) · [조합별 산출물](results/CASES.json).

## 추적과 채널

332 pose 사전 확인에서 동결한 G1 LoS 계수와 지연을 그대로 재현했고, 기록으로 재구성한 LoS 채널의 최대 절대오차는 0이었다. 전체 26,460개 XY와 17개 노드에서 솔버를 449,820회 호출했다. PATHS_NEAR를 내보낸 27,810 pose에 동일 추적을 사용했으며, 경로 내보내기를 위한 추가 솔버 호출은 0회였다. 164개 작업이 생성과 조립을 완료했다. [사전 확인](canary01/CANARY.json) · [생성 대조](post_generation/GENERATION_CHECK.json).

G6에서 확인한 문제 경로 4개가 생산에서도 각 17개 노드에서 전계 계산 전에 제외됐다. 나머지 XY의 경로 수는 보관한 생산 기록과 일치했다. H_full의 SHA-256은 G-T2 × B와 × C에서 달라졌고, 11개 조합의 H_LoS는 기존 SHA-256과 일치했다. [필터 적용 기록](post_generation/GENERATION_CHECK.json).

## G4와 봉인

**G4 PASS.** 11개 조합과 71,136관측을 검사했다. 조합·항목별 p90 |Δs|의 최댓값은 G-T1 × C의 P-D에서 1.0373873 × 10⁻⁶이었고, 기준은 0.005다. 새 G-T2·G-V 봉인 파일 18개의 읽기 전용 상태와 SHA-256을 확인했다. 새 봉인 접근 기록에는 생성 단계의 봉인, G4 계산, 저장 확인이 기록됐다. 기존 0°·+45°의 봉인 명세와 접근 기록, 두 G6 FAIL 기록의 해시는 실행 전후 일치했다. [G4 판정](results/gates/G4.json) · [새 봉인 확인](results/gates/SEAL_STORAGE_CHECK.json) · [기존 기록 확인](post_generation/HISTORICAL_VERIFY.log).

## 실행 기록

- 생산 코드는 `a2dff24f603c2460fcf7cabf5597cbf0da7ad551`이며, 산출물 대조를 고정 컨테이너에서 이어서 실행한 코드는 `894e81faa6071cac656163974df39bb161d3d6f8`이다. 최초 사전 확인의 메시 로더 누락과 호스트 Python의 검증 시작 실패를 기록했다. 검증은 이미 생성한 데이터에 대해 다시 시작했다. [사전 확인 재시작 기록](PREVIOUS_ATTEMPT.txt) · [검증 재시작 사유](continuation/REASON.txt).
- 생산에는 84개 작업 슬롯과 CPU 상한 84개를 사용했다. 재생성·조립은 **1시간 5분 26초**, G4와 봉인 확인은 **2분 27초**, 사전 확인과 재시작을 포함한 전체는 **1시간 14분 30초**였다.
- 최종 산출물은 3,956,627,475 B(3.68 GiB)다. 원시 배열과 경로 기록은 Snowball의 `/home/KMS/G1_RT_TB3_FINITE_FACE_PRODUCTION_20261115T122037Z_HS1vMs/results`에 보관한다. [고정 입력 해시](PINNED_INPUTS.sha256) · [실행 입력 해시](RUN_INPUTS.sha256) · [G4 산출물 해시](post_generation/OUTPUTS.sha256).
