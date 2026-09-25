# Sionna 기본 평판 모델용 형상 전환

101장면을 새 revision으로 생성하고, 기하 검사와 실제 Sionna 2.0.1 로딩·재질 결속 검증을 완료했다. **형상 전환 범위 완료**이며 새 형상의 채널·CIR 재계산, 전체 G2 PASS, 최종 봉인은 수행하지 않았다.

## 적용 결과

| 항목 | 결과 |
| --- | --- |
| 전체 입력 | 101장면, 원본 2,383부품 대응 유지 |
| 출력 mesh | 326개, 삼각형 25,438개 |
| 건축 우선 접촉 처리 | 가구 면 350개를 건축면과 겹치는 영역만큼 제거, 총 12.75555446193604 m² |
| 기둥 | 72개, 측면 288개를 중공 콘크리트 판재로 재정의 |
| 기준면 | 7,755개 원래 위치 유지; 바닥 윗면 z=0, 바닥 두께 0.2 m 유지 |
| 변경 장면 | 80개; 나머지 21개는 기존 mesh·재질·두께와 동일 |
| 좌표와 동적 물체 | TX/RX 41행과 동적 패널 12개 보존; 가구 배치 이동 없음 |
| 실제 소비 코드 검증 | 기존 `sionna_native_runtime.make_scene`으로 101장면 및 동적 overlay 12건 로딩 |
| 재질 대조 | 실제 scene에 결속된 값 102,286건, 257주파수 대조 통과 |
| 시험 | 신규 6개 포함 관련 시험 17개 통과 |
| RF 실행 | PathSolver 0회, 새 채널/CIR 계산 0회 |

## 형상과 물리 계약

- 벽·바닥·천장·유리는 기존 단일 기준면과 두께를 유지했다. 판재 한 장의 앞·뒷면을 각각 전체 두께를 가진 RF 면으로 추가하지 않았다.
- 가구는 기존 원래 부품들의 외곽 합집합을 유지한다. 책상 아래·다리 사이·서랍 사이의 빈 공간을 전체 상자로 채우지 않았다. 기존 중공 판재 구조와 같은 가구의 단일 재질 정책을 유지했다.
- 바닥 등과 공면으로 겹치는 가구 면만 제거했다. 건축면이 그 위치의 유일한 RF 면을 소유한다. 비공면 면과 겹치지 않는 영역은 보존했다. 이 처리는 가구와 바닥 사이의 실제 결합 매질 해석이 아니라 Sionna 기준면 표현을 위한 단순화다.
- 기둥 외곽 크기와 위치는 유지하되 **속이 찬 기둥에서 중공 콘크리트 판재 구조로 변경**했다. 두께는 `min(0.05 m, 최소 수평 외곽 폭/4)`이며, 맞은편 판 사이에 최소 외곽 폭의 절반만큼 공기 공간을 남긴다. 위·아래에는 별도의 중복 마감면을 추가하지 않았다. 원래 고체 기둥의 투과나 구조 하중을 재현한다는 주장은 하지 않는다.
- 실제 구현은 Sionna의 독립적인 공기–평판–공기 계수다. 모서리의 결합 전파, 재료 체적 합집합, 내부 매질 상태 추적을 요구하지 않는다. 판재 모서리는 기본 국소 평판 근사의 한계로 명시한다.
- 기존 이상 PEC 면 38개는 앞선 native 계산과 같은 ITU metal 1 mm로 명시했다. 이는 이상 PEC와의 정확한 등가가 아니다. EPS4 무손실 기준면 3개는 이전 native 기본값인 0.1 m를 명시해 암묵적 두께를 제거했다.

Sionna의 [공식 RadioMaterial 설명](https://nvlabs.github.io/sionna/_modules/sionna/rt/radio_materials/radio_material.html)은 교차 표면 하나가 지정 두께의 평판을 나타내며, 그 계수에 평판 내부 다중반사가 포함됨을 명시한다. 실행 버전은 문서 최신 버전과 구분하여 **2.0.1**로 고정했다.

## 검증과 증거

- [변경 목록 CSV](GEOMETRY_CHANGES.csv) / [상세 변경 목록](GEOMETRY_CHANGES.json)
- [기둥별 두께·공기 공간](COLUMN_DECISIONS.json)
- [전체 기하 검사](GEOMETRY_AUDIT.json): 공면 양의 면적 중복, 퇴화, 법선 방향, 원래 면 밖의 기하 추가 검사 통과.
- [별도 검증](INDEPENDENT_VERIFICATION.json): 제거 영역이 정확히 건축 소유 면과의 교집합인지 확인. 원본 입력 SHA 319건과 생성 산출물 SHA 338건 대조 통과. 부품 대응, 단일 판재 12개, 좌표·동적 패널 보존 확인.
- [실제 런타임 대조](RUNTIME_READBACK.json): Sionna RT 2.0.1, Mitsuba 3.8.0, Dr.Jit 1.3.1. 정점은 float32 변환값, 면 인덱스는 원본과 대조. 실제 결속된 재질의 유전율·전도도·두께를 원래 ITU 계수 계약과 비교.
- [시험 로그](TESTS.log) / [저장소 검사](REPOSITORY_CHECKS.json): 관련 17개 시험, inventory·manifest·dataset 검사 통과. 전체 회귀는 이번 형상 변경의 관련 검사로 범위를 한정해 실행하지 않았다.

첫 런타임 검사는 읽기 전용 컨테이너에서 Dr.Jit 캐시 디렉터리를 생성하지 못해 종료됐다. 기하 로딩 실패가 아니다. 최초 로그를 보존하고 컨테이너 내부 캐시 전용 임시 공간을 제공한 두 번째 실행에서 통과했다. 기존 호스트 파일과 접근 권한은 변경하지 않았다.

## 생산 입력 및 기존 채널의 유효 범위

[CONFIG.json](CONFIG.json)은 새 [SCENE_MESH_MANIFEST.json](SCENE_MESH_MANIFEST.json)을 가리키며, 실제 소비 코드의 로딩을 검증했다. [INPUTS.zip](INPUTS.zip)에 전체 형상과 기존 동적 패널·native 런타임을 묶었다. FFD bank는 복제하지 않았으며 기존 `CONFIG.bank_root`와 SHA를 사용한다. RF 실행용 원격 배치 시에는 기존과 같이 bank를 `bank/`에 준비해야 한다.

**기존 41행 모두 변경 장면에 포함되므로 새 형상에 사용할 채널·CIR은 재계산해야 한다.** 이전 채널 파일은 수정하지 않았고, 이전 형상에 대한 결과로 남는다. [CHANNEL_INVALIDATION.json](CHANNEL_INVALIDATION.json)에 변경 장면과 41행을 명시했다. 이번 작업은 형상 변경이므로 전대역 RF·레이블 재계산을 실행하지 않았다.

FFD, 전력, 잡음, 검출 설정과 기존 레이블은 변경하지 않았다. RD/HB 기준의 미정 상태도 유지한다. 새 geometry는 사용자 정의 volume loader용이 아니며, 해당 체적 정의 파일을 제공하지 않는다.

## 파일 및 보존 범위

추가한 구현:

- `rt_cp_uwb_py/g2_native_geometry.py`
- `scripts/g2_completion/build_native_slab_geometry.py`
- `scripts/g2_completion/check_native_slab_runtime.py`
- `scripts/g2_completion/verify_native_slab_geometry.py`
- `tests/test_g2_native_geometry.py`

새 결과는 이 revision 폴더에만 작성했다. 파일 이동·삭제는 없으며 기존 G1/P1/P2·체적 모델·native41 결과·원자료를 보존했다. 기존 생산 런타임 코드는 수정하지 않았다.

재현 명령은 `RUN_CONFIG.json`, `TEST_RECEIPT.json`, `RUNTIME_A02_INVOCATION.json`에 기록했다. 다른 새 출력 경로로 생성해야 하며 기존 revision에 덮어쓰지 않는다.

다음 읽기 전용 확인 명령:

```powershell
Get-Content -Raw 'D:/codex/raytracing_modules/rt_cp_uwb/results/SIONNA_NATIVE_GEOMETRY_20260925_01a0d83b/CHANNEL_INVALIDATION.json'
```
