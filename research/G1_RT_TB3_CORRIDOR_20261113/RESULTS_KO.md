
# G1-RT-TB3-001 G0–G3 실행 기록

Snowball의 Method B 환경은 기준 커밋 `047cce2acb244ec2d7badc563345ccdd1f48613f`의 실행 입력과 대조했다. 형상과 pose는 [사양서](SPEC_KO.md)와 G0 실행 산출물에 기록했다.

| 단계 | 판정 | 근거 |
|---|---|---|
| G0 | PASS | 형상 3종 × 앵커 3곳의 형상·pose 규칙 위반 0건. 두 실행의 산출물 SHA256 63건이 일치한다. [판정](evidence/G0/gates/G0.json) · [최초 실행](evidence/G0_first_run/RUN_MANIFEST.json) · [후속 실행](evidence/G0/RUN_MANIFEST.json) |
| G1 | PASS | G-T1 × A × P-A 처음 3 station의 TEACH·REPEAT pilot. [산출물](evidence/G1/output/G1.json) · [전체 생성 시간·용량 추정](evidence/G1/G1_ESTIMATE.json) |
| G2 | PASS | BLOCK_C `R2_aA_m0` 원본 pose 50개, 복소 H 값 51,400개가 비트 단위로 일치했다. 최대 상대 오차 0.0. [판정](evidence/G2/output/G2.json) · [로컬 재검산](evidence/G2/LOCAL_VERIFICATION.json) |
| G3 | FAIL | 고정 표본 195개 위치와 두 trace 방식의 출력 390개를 확보했다. 9개 조합 중 8개가 통과했다. G-T2 × A의 5개 위치, 188개 pose의 257-bin 기준 trace가 사용 불가여서 완전성 검사에 실패했다. [판정](evidence/G3/analysis/G3.json) · [로컬 재검산](evidence/G3/LOCAL_VERIFICATION.json) |

G3에서 비교 가능한 4,879개 pose의 최대 |Δs|는 1.257 × 10⁻⁶, 첫 경로 인덱스 일치율은 100%, 최대 거리 차이는 0 m였다. 나머지 188개 pose는 원래 G3 집계에서 비교 불가로 기록했다. G4 및 전체 생성은 착수 전이다.

## G3 실패 원인

- 실패 5개 위치의 원본 trace에서 **천장 → 음의 y 측벽 → 첫 오목부 목재면** 순서의 정반사 경로가 0부터 세는 bin **139–143**(6.52145–6.52925 GHz)에서 사라졌다. 138번과 144번에서 같은 경로가 확인됐다. 해당 경로의 등장 시 최대 상대 진폭은 위치별로 약 1.13–1.36%였다.
- 같은 장면, pose, 버전, solver 설정으로 경계 bin을 재추적했다. 5개 위치 모두 Sionna의 image-method 직후 경로 수가 해당 구간에서 1개 줄었고 전계 계산 이후에도 수가 같았다. 후처리 매칭 전의 경로 반환 단계에서 이미 발생했다. 이 진단은 후보 생성과 image method 내부의 개별 판단을 더 세분하지 않았다.
- 17-node 표본은 128번과 144번 bin 사이를 건너뛰어 경로가 사라진 5개 bin을 관측하지 못했다. 기존 `rf_b_trace.py` 경계 탐색은 표본 노드에서 경로의 유무가 한 번 바뀔 때 동작한다. 257-bin 쪽에서는 두 번의 전환을 검출해 `PATH_SET_CHANGED_WITH_FREQUENCY`로 기록했다.
- 사후 영향 계산에서는 저장된 257-bin Jones 행렬의 실제 유무를 보존해 188개 pose를 비교했다. 최대 |Δs|는 1.099 × 10⁻⁴, 첫 경로 인덱스 일치율은 100%, 최대 거리 차이는 0 m였다. 이 비교는 원래 G3의 표본 적격성이나 판정을 변경하지 않는다. [진단 요약](evidence/G3_diagnosis/SUMMARY.json)

## 재현 기록

- G0 입력·출력은 실행 파일별 SHA256으로 대조할 수 있다. G1·G2의 H 배열과 모든 단계에서 생성한 trace 및 로그를 `evidence/`에 보관했다. 원본 FFD 및 BLOCK_C 참조 입력은 실행 manifest에 기록한 SHA256으로 식별한다.
- 최초 G3 평가 단계는 모듈 배치 오류로 종료됐다. 보존된 trace로 판정만 재실행했으며, 최초 실행 로그와 최종 평가 로그를 모두 남겼다. 진단 시도 1·2의 로그와 실행 3의 상세 JSON도 보관했다.
- `.npz`는 저장소의 Git LFS 규칙을 따르며, `git lfs pull`로 바이너리를 받는다. 원본 실행에서 생성된 해시를 유지하기 위해 증거 파일의 줄바꿈을 보존했다.
