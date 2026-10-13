# I0 구현·검증·실행 보고

**자료 위치 후속 정정:** [RF_LOCATION_ADDENDUM_KO.md](RF_LOCATION_ADDENDUM_KO.md). R23 실행기는 데이터 브랜치에서 확보했고, LoS m45 자료는 Release에서 찾았다. 아래 미확보 설명은 최초 감사 시점의 기록이며 현재 상태는 후속 정정을 따른다.

**RF-off 재현 PASS / 전체 I0 INCONCLUSIVE / I1 NOT_RUN.**

신규 연구 폴더에 public/truth 분리 생성기, public-only 재생 CLI, 입력 계약, arm/seed registry, DRAFT 사전등록 spec을 구현했다. 기존 D6/V3/V4 코드는 변경하지 않았다. 실험 대상은 기존 개발 seed 8000 하나, 2개 세계 × 3개 경로 × 3개 drift의 18 episode이다. 표본 독립성이나 과학적 원인에 관한 확증 실험이 아니다.

| 검증 | 실제 결과 |
|---|---|
| 문법·입력 계약 테스트 | compile 성공, pytest 12 passed |
| 전체 시간축 재현 | 18/18 PASS, 18,816 시점 |
| posterior 상태·공분산 차이 | 최대 절대 차이 각각 0 |
| 예측 상태·공분산, 게이트, 정규화 혁신 | 사전 고정 허용 오차 내 일치 |
| 공유 입력 Q/C 및 F/G | 일치 |
| range/s 적용·거절 | 모든 episode에서 0, trace disabled |
| truth 제거 후 별도 프로세스 재생 | 18/18 동일 |
| truth 파일 손상 후 재생 | 18/18 동일 |
| 기존 코드·입력 계보 | 43개 파일의 committed/local 정규화 내용 일치; 개별 SHA 저장 |
| 독립 읽기 전용 감사 | ACCEPT, 필수 수정 없음 |
| 실행 종료 | exit 0, 자연 종료, 관리 프로세스·supervisor·job 없음 |

생성/추론/평가는 분리되어 있다. 초기 pose는 외부 prior 측정으로 생성 후 public에 고정된다. 추론 중 참 pose나 참 이동량에 접근하지 않는다. 원본 full covariance와 trace, episode별 입력·truth·결과를 run_01에 보존했다. I0_INPUT_MANIFEST의 output_hashes 경로 기준은 run_01이다.

## 미완료 범위와 필요한 자료

1. R2-3 결과가 참조하는 정확한 r23_run.py 및 해당 실행 설정·의존 소스.
2. 12 case의 전체 full/LoS 채널 H와 주파수 배열. P0 해시와 실제 bytes를 대조할 수 있는 자료.
3. FFD/first-arrival/LUT/E1 계수와 학습 fold·scene·route의 완전한 고정 계보.
4. 신규 개발/확증 seed의 클라우드 포함 전역 사용 이력. 현재 registry는 조사한 기존 범위와의 불충돌만 나타낸다.

RF 계보 문서 9개의 커밋·SHA는 RF_SOURCE_INVENTORY.json에 기록했다. 문서 해시 확인은 RF 데이터 재현 성공이 아니다. P5는 12개 고정 채널 관측을 재사용했고 R2-3은 그 위에 seed별 열잡음을 추가했다. office 정적 35개 위치 자료는 동적 주행 입력으로 사용하지 않았다.

I1의 A_DR 모델 조사를 위한 기반은 마련됐지만, S0/S1 gauge 처리와 신규 Ideal Range anchor/관측 계약은 다음 단계에서 별도 고정해야 한다. 전체 I0를 PASS로 승격하거나 RF 비교군이 준비됐다고 해석하지 않는다. I1–I7 및 L1–L7은 미실행이며, 독립 확증 seed를 생성하거나 열지 않았다. 기존 D6 UNRESOLVED는 유지한다.

검증 후 기록 도구에서 Windows 경로 구분자 오류가 1회 발생했다. 경로 정규화 수정 후 기록 도구와 문법·테스트를 성공적으로 재실행했으며, 실험 계산 결과에는 영향이 없다.

재현 명령은 저장소 루트에서 `python research/SINGLE_ANCHOR_CAL_IDENTIFIABILITY_20261013/i0_build_paired_inputs.py --out <새로운_출력_폴더>`이다. 기존 폴더는 덮어쓰지 않는다. 실행 spec과 정확한 Python/NumPy·입출력 SHA·시각은 I0_INPUT_MANIFEST.json, 관리 종료는 PROCESS_RECEIPT.json을 참조한다.
