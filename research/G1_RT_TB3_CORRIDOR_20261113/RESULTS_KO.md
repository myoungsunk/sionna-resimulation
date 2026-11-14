
# G1-RT-TB3-001·002 실행 기록

Snowball의 Method B 환경은 기준 커밋 `047cce2acb244ec2d7badc563345ccdd1f48613f`의 실행 입력과 대조했다. 형상과 pose는 [사양서](SPEC_KO.md)와 G0 실행 산출물에 기록했다.

| 단계 | 판정 | 근거 |
|---|---|---|
| G0 | PASS | 형상 3종 × 앵커 3곳의 형상·pose 규칙 위반 0건. 두 실행의 산출물 SHA256 63건이 일치한다. [판정](evidence/G0/gates/G0.json) · [최초 실행](evidence/G0_first_run/RUN_MANIFEST.json) · [후속 실행](evidence/G0/RUN_MANIFEST.json) |
| G1 | PASS | G-T1 × A × P-A 처음 3 station의 TEACH·REPEAT pilot. [산출물](evidence/G1/output/G1.json) · [전체 생성 시간·용량 추정](evidence/G1/G1_ESTIMATE.json) |
| G2 | PASS | BLOCK_C `R2_aA_m0` 원본 pose 50개, 복소 H 값 51,400개가 비트 단위로 일치했다. 최대 상대 오차 0.0. [판정](evidence/G2/output/G2.json) · [로컬 재검산](evidence/G2/LOCAL_VERIFICATION.json) |
| G3 | FAIL | 고정 표본 195개 위치와 두 trace 방식의 출력 390개를 확보했다. 9개 조합 중 8개가 통과했다. G-T2 × A의 5개 위치, 188개 pose의 257-bin 기준 trace가 사용 불가여서 완전성 검사에 실패했다. [판정](evidence/G3/analysis/G3.json) · [로컬 재검산](evidence/G3/LOCAL_VERIFICATION.json) |

G3에서 비교 가능한 4,879개 pose의 최대 |Δs|는 1.257 × 10⁻⁶, 첫 경로 인덱스 일치율은 100%, 최대 거리 차이는 0 m였다. 나머지 188개 pose는 원래 G3 집계에서 비교 불가로 기록했다. 이 집계는 F1 도입 전 실행의 결과다.

## G3 실패 원인

- 실패 5개 위치의 원본 trace에서 **천장 → 음의 y 측벽 → 첫 오목부 목재면** 순서의 정반사 경로가 0부터 세는 bin **139–143**(6.52145–6.52925 GHz)에서 사라졌다. 138번과 144번에서 같은 경로가 확인됐다. 해당 경로의 등장 시 최대 상대 진폭은 위치별로 약 1.13–1.36%였다.
- 같은 장면, pose, 버전, solver 설정으로 경계 bin을 재추적했다. 5개 위치 모두 Sionna의 image-method 직후 경로 수가 해당 구간에서 1개 줄었고 전계 계산 이후에도 수가 같았다. 후처리 매칭 전의 경로 반환 단계에서 이미 발생했다. 이 진단은 후보 생성과 image method 내부의 개별 판단을 더 세분하지 않았다.
- 17-node 표본은 128번과 144번 bin 사이를 건너뛰어 경로가 사라진 5개 bin을 관측하지 못했다. 기존 `rf_b_trace.py` 경계 탐색은 표본 노드에서 경로의 유무가 한 번 바뀔 때 동작한다. 257-bin 쪽에서는 두 번의 전환을 검출해 `PATH_SET_CHANGED_WITH_FREQUENCY`로 기록했다.
- 사후 영향 계산에서는 저장된 257-bin Jones 행렬의 실제 유무를 보존해 188개 pose를 비교했다. 최대 |Δs|는 1.099 × 10⁻⁴, 첫 경로 인덱스 일치율은 100%, 최대 거리 차이는 0 m였다. 이 비교는 원래 G3의 표본 적격성이나 판정을 변경하지 않는다. [진단 요약](evidence/G3_diagnosis/SUMMARY.json)

## 재현 기록

- G0 입력·출력은 실행 파일별 SHA256으로 대조할 수 있다. G1·G2의 H 배열과 모든 단계에서 생성한 trace 및 로그를 `evidence/`에 보관했다. 원본 FFD 및 BLOCK_C 참조 입력은 실행 manifest에 기록한 SHA256으로 식별한다.
- 최초 G3 평가 단계는 모듈 배치 오류로 종료됐다. 보존된 trace로 판정만 재실행했으며, 최초 실행 로그와 최종 평가 로그를 모두 남겼다. 진단 시도 1·2의 로그와 실행 3의 상세 JSON도 보관했다.
- `.npz`는 저장소의 Git LFS 규칙을 따르며, `git lfs pull`로 바이너리를 받는다. 원본 실행에서 생성된 해시를 유지하기 위해 증거 파일의 줄바꿈을 보존했다.

## F1 본 생성·G4 및 002 추가 G3

| 실행 | 판정 | 범위·결과 | Snowball 소요 시간 |
|---|---|---|---:|
| F1 생성·조립 | PASS | 본 52,218 pose, 추가 9,774 pose, 합계 61,992 pose. 26,460 XY × 17 node, 솔버 호출 449,820회. `PATHS_NEAR` 대상 27,810 pose에서 H와 같은 trace를 사용했다. [생성 결과](evidence/Production/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa/GENERATION_RESULT.json) | 52분 36초 |
| G4 | PASS | 11개 조합·71,136관측, 조합·항목별 p90 &#124;Δs&#124; 최댓값 1.0374 × 10⁻⁶(기준 0.005). [G4 판정](evidence/Production/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa/G4.json) | 검증 58.43초, 봉인 확인 포함 61초 |
| 002 추가 G3a | PASS | P-D·P-E·P-F의 고정 표본 195개 XY × 257 bin에서 경로 집합 불일치·무효 0건. [집계](evidence/G3_diag/G1_RT_TB3_DIAG_G3_20261114T112524Z_QzP8yY/DIAG_G3_RESULT.json) | 966.36초 |
| 002 추가 G3b | PASS | 직접 추적한 17 node와 G3a 257 bin을 비교. 2,739/2,739 yaw, 최대 &#124;Δs&#124; = 6.4926 × 10⁻⁷, 첫 경로 index 일치율 100%, 최대 거리 차이 0 m. [집계](evidence/G3_diag/G1_RT_TB3_DIAG_G3_20261114T112524Z_QzP8yY/DIAG_G3_RESULT.json) | 49.80초 |
| 002 추가 G3c | PASS | 같은 XY·bin에서 100,000·400,000 광선 비교. 추가·누락 경로 0건, 추가 경로 최대 에너지 비율 0%, 최대 &#124;Δs&#124; = 2.3789 × 10⁻⁵. [집계](evidence/G3_diag/G1_RT_TB3_DIAG_G3_20261114T112524Z_QzP8yY/DIAG_G3_RESULT.json) | 1,770.36초 |

최종 산출물은 Snowball에서 3.68 GiB였다. `H_full`·`H_LoS`는 2,039,291,648 B, `PATHS_NEAR`는 1,310,231,068 B, `PATHS_LoS`는 535,153,116 B를 사용했다. 중간 산출물과 캐시를 포함한 전체 실행 폴더는 7.66 GiB였다. 원본 배열과 trace는 Snowball의 해당 실행 폴더에 보관한다. [조합별 파일과 바이트](evidence/Production/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa/CASES.json).

생성 설정, 동결 G0·G7과 FFD, 이미지 및 코드 SHA-256은 [생성 manifest](evidence/Production/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa/RUN_MANIFEST.json)에 기록했다. 추가 G3는 [사전 고정 표본](evidence/G3_diag/G1_RT_TB3_DIAG_G3_20261114T112524Z_QzP8yY/SAMPLE_MANIFEST.json)과 단계별 실행 기록 [G3a](evidence/G3_diag/G1_RT_TB3_DIAG_G3_20261114T112524Z_QzP8yY/G3A_RUN.json) · [G3b](evidence/G3_diag/G1_RT_TB3_DIAG_G3_20261114T112524Z_QzP8yY/G3B_RUN.json) · [G3c](evidence/G3_diag/G1_RT_TB3_DIAG_G3_20261114T112524Z_QzP8yY/G3C_RUN.json)을 보관한다. 본 G3의 후속 F1 결과와 표본은 [RT v1.1](SPEC_V1_1_KO.md#생산-설정-확정-근거), 추가 G3의 표본 선정 규칙은 [002 사양](SPEC_DIAG_KO.md#3-추가-gate)에 기록했다.

G-T2·G-V의 6개 조합, 파일 18개는 생산 직후 봉인했다. G4 및 추가 G3 종료 후의 읽기 전용 상태와 SHA-256 재검증이 모두 완료됐다. [봉인 기록](evidence/Production/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa/SEAL_MANIFEST.json) · [G4 후 저장 확인](evidence/Production/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa/SEAL_STORAGE_CHECK.json) · [추가 G3 후 확인](evidence/G3_diag/G1_RT_TB3_DIAG_G3_20261114T112524Z_QzP8yY/DIAG_G3_RESULT.json).
