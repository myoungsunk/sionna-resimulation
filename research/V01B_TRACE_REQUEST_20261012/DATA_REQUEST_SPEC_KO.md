# 레거시 trace 요청 사양서 — `traces_R4_aB`

2026-10-12. 대상: 레거시 Method-B의 ray-trace 입력(조건 R4, 앵커 B). 기계가 읽는 사양은 `TRACE_REQUEST_MANIFEST.json`, 요청 위치 목록은 `TAGS_TIER1.txt`(40개)와 `TAGS_ALL_547.txt`, 전달 전 점검은 `verify_traces.py`. **이 문서는 요청서이며 결과가 아니다. 게이트 판정을 바꾸지 않는다(V01b FAIL, `stage_B_allowed=false` 유지).**

## 1. 왜 필요한가
레거시와 Native의 차이는 정반사 3회 경로, 특히 **같은 허상을 공유하는(퇴화) 경로**에 몰려 있다(차이 에너지의 45–69%, 경로 에너지는 4%). 원인 가설은 (1) 레거시의 노드 간 경로 매칭이 방향·지연이 같은 경로를 구분하지 못함, (2) 편파 기저의 반사 횟수 누적 차이, (3) Native의 고차 경로 계산 정밀도다. 레거시 H에서는 경로별 값을 꺼낼 수 없어서, 경로 단위 비교는 **레거시 trace 원본**이 있어야 가능하다. R4_aB를 고른 이유: 922 pose로 가장 작고, 3회 경로에 차이가 98% 몰려 있어 가장 깔끔하며, 레거시 H(m0·m45)와 Native H(m45)가 모두 있다.

## 2. 무엇을 요청하는가 (두 단계)
trace는 **마운트와 무관**하다(등방 포트, 단위 방향으로 한 번 trace하고 mount와 안테나 yaw는 `rf_b_apply.py`가 오프라인으로 적용). 따라서 하나의 디렉터리가 m0와 m45를 모두 만든다.

| 단계 | 요청 | 위치 수 | 목적 |
|---|---|---:|---|
| **Tier 1 (최소)** | `TAGS_TIER1.txt`의 위치만 | 40 (106 pose) | 가설 시험(경로 단위 비교). 규모가 작아 먼저 요청 |
| **Tier 2 (전체)** | `TAGS_ALL_547.txt` 전부 | 547 (922 pose) | 비트 단위 재생성 자가 검증(`rf_b_apply.py`는 모든 위치를 요구) |

Tier 1 선정 규칙(데이터 도착 전에 고정): 위치별 점수 = 그 위치의 pose 중 레거시–Native 상대 채널 오차의 최대값. 최고 20개, 최저 10개, 중앙값에 가장 가까운 10개의 합집합(최고 20개의 최소 점수 0.273).

### 위치마다 필요한 파일
- `<tag>_trace.npz` (`tag = x{x:.4f}_y{y:.4f}`, 예 `x1.2000_y-0.4500`). 필수 키: `jones`(노드×경로×3×3, 복소), `tau`, `ang`(4×경로), `node_bins`, `node_freq_hz`, `x`, `y`, `signature`, `unmatched`, `status`(`OK`), `flagged_bins`, `path_counts`, `present`, `max_dropped_rel_amp`.
- `<tag>_trace_receipt.json`: `versions`(sionna-rt, mitsuba, drjit), `solver`, `materials`, `runner_sha256`, `command`, `dropped_audit` 포함.
- (선택) `scene_shard*/`의 메시 PLY. 장면은 Native 아카이브에도 있어서 필수는 아니다.

### 사용자께서 확인해 주셔야 하는 것
1. 원래 디렉터리 `…/SNOWBALL_ROUTES_01a11669/S2/traces_R4_aB`가 실제로 남아 있는가(전달 문서는 "원격에 존재, 내용 미검증"이라고만 적었다).
2. 용량(위치당 파일 크기, 총합). 저는 모른다. 95 MB 이하로 분할을 권장한다.
3. trace를 만든 환경 버전(영수증에 있으면 불필요).

## 3. 수용 기준 (사전 고정)
- **A. 형식(Tier 1, 2 공통)**: `verify_traces.py`가 모든 요청 위치에서 PASS. 즉 두 파일 존재, 필수 키, `status == OK`, 배열 shape 일관(`jones [K,n,3,3]`, `tau [n]`, `ang [4,n]`, `present [K,n]`), **노드 bin 128 포함**, 값이 유한, 영수증과 npz의 tag·x·y 일치.
- **B. 재생성 자가 검증(Tier 2만)**: `rf_b_apply.py --mount 0`과 `--mount 45` 출력의 SHA256이 각각 저장소의 R4_aB_m0(`30743ca0…fe1b0`)와 전달된 R4_aB_m45(`3f76d713…c791d`)와 **비트 단위로 일치**. 불일치하면 그 환경에서 만든 결과는 자동 수용하지 않고 별도 판단으로 넘긴다.
- **C. 가설 시험(Tier 1이면 충분)**: Native `PATHS_CENTER_BIN.npz`(bin 128)와 레거시 노드 128의 경로를 허상 클래스 단위로 대조한다.
  1. 클래스별 경로 개수: Native의 클래스 멤버 수 대 레거시 trace의 경로 수(가설 1: 퇴화 클래스에서 레거시가 경로를 합치거나 다르게 센다).
  2. 클래스별 결합 계수: 레거시 Jones에 FFD 패턴을 적용해 같은 pose의 Native 경로 계수 `a`의 클래스 합과 비교(진폭과 위상 분리).
  3. 반사 횟수별 편파 성분 오차(가설 2).
  판정 규칙은 데이터를 보기 전에 고정한다: 클래스별 상대 복소 오차 ≤ 1e-3이면 "일치", 그 외는 "불일치"로 분류하고, 가설 1은 "불일치 클래스의 개수 차이가 퇴화 클래스에 편중되고 비퇴화 클래스는 일치"일 때만 지지로 기록한다.
- 이 시험은 원인 후보를 좁힐 뿐이며 **어느 쪽이 물리적으로 맞는지는 판정하지 못한다**.

## 4. 전달 방법
- 저장소 LFS 업로드는 이 세션에서 `Forbidden`이었으므로 **LFS를 쓰지 않는다**(`.npz`는 저장소 규칙으로 LFS를 탄다). 지난번처럼 전용 디렉터리의 `.gitattributes`로 LFS를 끄거나, Drive 링크나 Release 자산을 쓴다.
- `SHA256SUMS.txt`(`sha256sum` 출력 형식)를 함께 보낸다.
- 전달 전: `python verify_traces.py <traces_R4_aB 폴더> --tier 1` (읽기 전용, 모두 PASS여야 종료코드 0).

## 5. 회신 양식
```
traces_R4_aB 보유: 예 / 아니오 (아니오면 traces_R4_aA 등 다른 조건 보유 여부)
Tier 1 전달 위치: verify_traces.py 결과: ALL_PASS / NOT_ALL_PASS
Tier 2 전달: 예 / 아니오   용량:   환경 버전(sionna-rt/mitsuba/drjit):
```
trace가 없을 때의 대안: (a) 12조건 Native 통일(7개 추가 생성), (b) 한 계통 선택. 어느 쪽이든 원인 규명은 보류된다.

## 6. 하지 않는 것
trace가 없는 상태에서 레거시 경로 값을 추정으로 만들기, Tier 1 결과를 전체(547)로 일반화하기, 가설 지지를 원인 확정으로 기록하기, 시험 결과로 V01b 판정을 바꾸기.
