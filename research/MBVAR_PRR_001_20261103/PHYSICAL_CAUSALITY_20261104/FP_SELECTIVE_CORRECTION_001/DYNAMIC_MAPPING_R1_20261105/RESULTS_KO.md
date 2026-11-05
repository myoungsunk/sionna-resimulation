# 동적 mapping R1 로컬 검증 및 static 48개 준비 결과

**판정: NUMERICAL_PASS_REVIEW_HOLD. 동결한 nominal mapping 수치 기준은 통과했다.**
**잘못된 prior의 안전성은 통과한 것이 아니다.** 과신·오위치 음성대조에서 좁은 구간이 참조를
제외한 경우가 11,095/43,904행(25.27%)이다. E1-02/E2는 실행하지 않았고 실행 권한도 닫혀 있다.

## 결과 전에 고정한 기준과 실제 결과

수용 계약은 계산 전에 `72a5e4c`로 커밋했고, 구현·검사 코드는
`061ecf9ecef9222ba131b9ea79a2eb6dbf5f2b19`에서 실행했다.
계약 SHA256은 `7fb011230159959464fb5d75577497b8553ca1b9283a478fea76cdbe0d60dfdc`다.
관측 결과를 보고 sigma=2, slack=0.15m, 최대 폭=1.5m, 95% 기준을 바꾸지 않았다.

| 관문 | 동결 기준 | 결과 |
|---|---|---|
| G0 정체성·분모 | 고정 입력/모델 SHA, 6,272행, 중복·누락·비유한 0 | PASS |
| G1 구현·수학 | 생산 native_support endpoint 차이≤1e-10m 및 특수/인과 검사 | 최대 차이 **0m**, PASS |
| G2 추가 방향 | 각 prior의 20방향 probe 전부 포함 | **125,440/125,440 포함**, 구간 이탈 0 |
| G3 참조 포함·폭 | 각 비어 있지 않은 route/channel/error 층에서 ≥95% | **6,272/6,272**, 모든 비어 있지 않은 층 100% |
| G4 음성대조 | 고정 7조건×6,272행 전수 기록, 누락 0 | **43,904행 기록 PASS**, 안전성 승인은 아님 |
| G5 static 준비 | 24조건×2채널, exact 스펙트럼·참조 분리·C-only | **48/48 PASS** |

nominal 지원구간 폭은 최소 약 0.300m, 중앙값 약 0.300m, 최대 0.748657m이다.
폭 1.5m 초과 HOLD는 0건이다. 영 공분산 검사와 yaw±2π 주기성 검사의 실제 모델 차이는 0m였다.
이 결과는 고정된 20방향 유한 probe domain의 통과다. 연속 타원체 전체나 통계적 confidence region의
보장으로 확대하지 않는다. packet은 독립 표본이 아니며 모집단 안전 확률/신뢰구간을 주장하지 않는다.

| 동적 Full 큰 오류 층 | 유효 폭 내 참조 포함 |
|---|---:|
| R2 | 19/19 |
| R4 | 14/14 |
| R5 | 54/54 |
| 합계 | 87/87 |

이는 mapping 구간의 포함 결과다. 실제 후보 선택·정정 성공을 뜻하지 않는다.
전체 normal/one-tap/large-error 층과 빈 층 NOT_TESTED는 `CHECK_001/STRATA.json`에 공개했다.

## 음성대조에서 드러난 한계

모든 음성대조는 P를 0.01배로 축소한다. 위치/방향 오프셋은 아래처럼 고정했다.

| 조건 | 검사 행 | 좁지만 참조를 제외한 행 |
|---|---:|---:|
| 공분산 축소만 | 6,272 | 0 |
| x −0.5m | 6,272 | 5,520 |
| x +0.5m | 6,272 | 5,493 |
| y −0.5m | 6,272 | 13 |
| y +0.5m | 6,272 | 69 |
| yaw −15° | 6,272 | 0 |
| yaw +15° | 6,272 | 0 |
| 합계 | 43,904 | **11,095** |

음성대조에서도 폭 초과 HOLD는 0건이었다. 따라서 폭 gate만으로 잘못된 위치 prior를
보호할 수 없다는 반례가 확인됐다. x축 오차의 큰 영향은 이 데이터와 고정 anchor/경로 geometry에
조건부인 결과이며 다른 환경에 일반화하지 않는다.
G4는 애초부터 **음성대조 기록의 완전성** 기준이었다. 이 11,095행을 감추거나 G4를 정정 안전성
PASS로 해석하지 않는다. 잘못된/과신 prior와 raw-only 이력의 전체 동적 안전성은 별도 후속 검증 대상이다.
실제 FP 교체가 없었으므로 이 수치는 오정정률도 아니다.

## static 48개와 실행 전 manifest

원래 24개 G4 조건 각각에서 Full/Native_LoS 스펙트럼을 별도 canonical 입력으로 만들었다.
온라인 NPZ는 `Hrf`만, evaluator NPZ는 `reference_H`만 가진다. time·pose prior·controls·truth state를
만들지 않았다. 각 payload는 원본 스펙트럼과 정확히 일치한다.

새 `static_detection.py`의 loader와 C-only 경로를 실행기에 연결했다. 미래에 별도로 승인된 E1-02에서만
실행하며, P/M/PM을 요청하면 거부한다. 참조를 바꿔도 온라인 결정이 변하지 않는 합성 반례도 통과했다.
이번에는 실제 static RF에 detect/select를 실행하지 않았다.

`FINAL_PREPARATION_MANIFEST.json`은 동적 6,272개와 static 48개, **총 6,320개 파형**을 함께 결속한다.
향후 출력 대상은 동적 C/P/M/PM 25,088행 + static C 48행 =25,136행이다. 아직 이 행들을 실행한 것은 아니다.
현재 최종 manifest를 사용하며, `STATIC48/MANIFEST_PREP_ONLY.json`은 초기 형식 준비 snapshot으로 보존한다.

static canonical 96개 NPZ는 `STATIC48_PAYLOADS.tar.gz`에 게시했다. `restore_static48.py`로 기존 파일을
덮어쓰지 않고 복원/검증할 수 있다. 동적 canonical과 FFD bank는 검증한 로컬 payload를 재사용하며 중복 업로드하지 않았다.

## 실행과 검산 근거

- 로컬 Windows, Python 3.13.15 / NumPy 2.2.4 / SciPy 1.15.2. 논리 CPU affinity [0,1,2], 라이브러리 스레드 1.
- 이전 Snowball Linux runtime과 구분한 새 검증이다. Linux에서 동일 수치가 나온다는 재실행 주장은 하지 않는다.
- 합성 **78/78 PASS**: 신규 mapping/static 9 + 검출 준비 13 + bridge 18 + reach 14 + legacy 24.
- 기존 결정 **1,000/1,000 정확 일치**. 생산 mapping 함수와 독립 batch 집계의 endpoint를 전 행 대조했다.
- 모델 mapping query 476,683개 상태, mapping 계산 약 194.6초. batch 후 측정 RSS의 표본 최대 약 589MiB.
- `RUN_001/NOMINAL.csv` 6,272행, `STRESS.csv` 43,904행을 별도 checker가 재집계했다.
  원본 RF mapping을 별도 모델로 재계산한 독립 감사는 아니다. 동일 작업자 자체검사다.
- 원래 E1 실패, 후보 R1, bridge/reach 증거, VAB 주안, 기존 모델/후보/정책 임계값을 보존했다.

## 남은 판단

이번 범위의 nominal mapping 수치 검증과 static 준비는 완료됐다. 잘못된 prior에 대한 안전성,
검출 성능, FP 정정 성능, EKF 개선은 별개다. 수치 검증 결과와 음성대조 한계를 검토하고,
실행 환경·최종 manifest를 확정한 뒤 사용자 승인으로 E1-02 단일단계에 진입할 수 있다.
`mapping_reviewed=false`, `execute_science=false`, `stages=[]`를 유지했다.
E1-02/E2 실행 승인으로 자동 승격하거나, E2–E5를 일괄 진행하지 않았다.
