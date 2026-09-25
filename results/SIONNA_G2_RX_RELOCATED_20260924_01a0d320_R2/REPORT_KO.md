# RX 26곳 이동 및 41행 적용 완료

**새 입력 revision에서 충돌 RX 26곳을 이동해 41개 링크 행에 적용했다. 전수 재검사에서 실제 입력 165,000링크의 TX·RX 배치 이상은 모두 0건이다.** 기존 입력을 덮어쓰지 않았다.

## 수정 내용

- 수평 이동 1.2–5.0 cm. RX 높이와 모든 TX 좌표는 유지했다.
- 가구 부품 외곽·재료·건축 경계로부터 1 cm 이상 떨어지는 후보를 선택했다. 8개 수평 방향을 1 mm 간격의 거리 순으로 탐색한 결과이며 연속 공간의 전역 최소 이동을 보장한다고 주장하지 않는다.
- 독립적인 점–삼각형 최단거리 계산으로 26곳과 모든 실제 재료 경계면을 다시 대조했다. 최소 이격 **0.0101300013 m(약 1.013 cm)**.
- L1 14행, L1multi 12행, C1_static 7행, C1_multi 8행 변경. 다른 **164,959개 링크 행은 내용이 동일**하다.
- 대응 C계열 프레임 **9개**의 RX를 함께 변경하고 physical content의 canonical SHA를 다시 계산했다. 링크 scene_hash도 대응 프레임 해시와 일치시켰다.
- L계열 실제 거리와 source_row의 RX 좌표·거리도 갱신했다. 원래 source_row는 명시적인 이전 값 필드로 보존했다. 높이 차이와 TX는 그대로다.
- 변경 C계열 링크의 기존 LoS·패널 기하 판정은 null 및 `RX_RELOCATED_REQUIRES_RECOMPUTE`로 표시했다. 변경 L계열에도 기존 RF·기하 분류의 재검증 필요를 표시했다. 과거 RF 결과나 통계 레이블을 새 좌표의 결과로 재사용하지 않는다.

## 전수 재검증

| 범위 | 결과 |
|---|---|
| 실제 165,000 TX | 실내 공기 영역, 배치 이상 0 |
| 실제 165,000 RX | 가구 재료·표면·부품 외곽 내부 및 방 밖 배치 이상 0 |
| 개방형 기본 물리 시험 9개 | TX·RX 모두 사용자 예외에 적합 |
| C계열 원본 37,500프레임 | 누락 없이 대응, 링크–프레임 RX 불일치 0 |
| 동적 패널–TX/RX 표면 충돌 | 0 |
| 별도 바닥 관통 진단 | 기존 RX z=−0.3 m 1링크를 보존하고 실내 케이스와 분리 |

마지막 진단 링크는 실제 165,000링크에 포함되지 않는다. 이전 보고의 '손실 관통 2경로'는 이 링크의 두 주파수 결과다. 이번에 승인된 실제 RX 26곳의 이동 범위에 이 별도 진단은 포함하지 않았다.

단말은 점으로 검사했다. 안테나·로봇 몸체의 크기, 프레임 사이 연속 궤적 충돌, 이동에 따른 RF·분류 레이블 영향은 별도 검증 범위다. 새 revision의 POST_AUDIT CSV에서 `FROZEN`은 원래 7개 계열 코호트를 가리키는 분류 이름이며, 원본 동결 파일을 덮어썼다는 뜻이 아니다. `coordinate_changes=0`은 재감사 과정에서 좌표를 추가 변경하지 않았다는 뜻이다.

## 산출물과 재현

- [26곳의 이동 전후 좌표](MOVES.json)
- [변경 41행](CHANGED_LINKS.json)
- [전수 재감사 요약](POST_AUDIT/SUMMARY.json), [전체 TX/RX 판정표](POST_AUDIT/ALL_ENDPOINTS.csv)
- [독립 이격 검사](CLEARANCE_INDEPENDENT.json), [입력 차이 검사](INPUT_DIFF_VALIDATION.json)
- 실제 새 입력: `inputs_v6/{L1,L1multi,L2static,L2multi}/INPUT.json`, `common/LINKS.jsonl`, `common/FRAMES.jsonl`.
- [생성·출처 해시](MANIFEST.json)

현재 생산 실행기가 자동으로 이 입력으로 전환됐다고 주장하지 않는다. 다음 소비 단계는 이 revision 경로를 명시적으로 결속하고, 변경된 41행의 파생 RF·기하·레이블을 재계산해야 한다. 좌표 보정 자체는 완료됐다.

전수 재감사 재현 명령(출력은 새 폴더 지정):

```powershell
py -3.10 -X utf8 -B D:/codex/raytracing_modules/rt_cp_uwb/scripts/g2_completion/audit_all_endpoint_placement.py --input-root D:/codex/raytracing_modules/rt_cp_uwb/results/SIONNA_G2_RX_RELOCATED_20260924_01a0d320_R2 --out D:/codex/raytracing_modules/rt_cp_uwb/results/SIONNA_G2_RX_RELOCATED_20260924_01a0d320_R2/POST_AUDIT_RECHECK
```

## 종료 상태

`POSITION_CORRECTION_VALIDATED_UNSEALED`. 새 스크립트·입력·검사 결과·보고서만 추가했다. 기존 원본·기하·bank·생산 코드·과거 증거의 수정, 이동·삭제는 없다. 처음 생성한 빈 출력 폴더는 UTF-8 읽기 오류 후 보존했고 완료 결과는 이 R2이다.

전수 위치 감사, 독립 26곳 최단거리 검사, 165,000링크 차이 검사, inventory·manifest·dataset 및 보고서 링크 검사를 통과했다. 전체 pytest·RF 재실행·Sionna PathSolver·생산 CIR·G3·최종 봉인은 미수행이다. **G2 PARTIAL 유지**.
