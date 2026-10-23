# 구현 후 감사 및 수정 기록

## 판정 범위

S0–S7의 실행 코드, 요구사항별 계약, 합성 단위/학습/직렬화 시험을 감사했습니다.
**실제 RF 실험, 실제 학습 데이터 적합, 원본 SourceFFD 통합 실행은 하지 않았습니다.**
실행 가능한 감사 진입점은 `audit-code`입니다. 결과는 지정한 work_dir에 저장하며, 코드/설정이 달라지면 이전 PASS를 재사용하지 않습니다.

## 발견·보완 사항

| 항목 | 발견/위험 | 수정 및 재시험 |
|---|---|---|
| 거부된 갱신 | 불필요한 angle wrap이 원본 refusal 분기와 미세하게 달랐음 | gate 거부 시 x/P를 그대로 복사 반환, K=0 |
| 후보 특징 | PCIR3 이름이 P 계열 조건에 잘못 들어갈 수 있었음 | 모드별 명시적 allowlist/차원시험 |
| 학습 그룹 | upstream group 열과 새 split group 병합 시 group_x/group_y 발생 | 기존 group 제거 후 owner split을 one-to-one 병합 |
| common gate | 다른 prior arm의 과거 수용 mask를 그대로 쓰면 common BASE 의미가 달라짐 | 각 공통 prior에서 보정 0의 BASE gate를 다시 계산 |
| 전체 예산 | closure를 맞추기 위한 임의 잔차 보정은 구현 오류를 숨길 수 있음 | x/y/b 불일치 즉시 실패, 각도 2π chart 항만 명시적으로 허용 |
| 학습 비교 | P1–P4의 라벨·augmentation·teacher 변화가 섞일 위험 | 원 POWER 및 frozen P0 refit parity, target/augmentation 해시 검사 |
| 조립 진입점 | 모듈 단위시험만으로 stage orchestration의 문법 오류를 놓쳤음 | 전 단계 import 시험 및 전체 AST/compile 추가, 괄호 오류 수정 |
| 최종 지표 | RMSE/NEES만 판정하면 포함률·긴 꼬리 악화를 놓침 | coverage deviation, q95/q99/peak와 threshold-duration 곡선도 paired 판정 |
| 비유한값 | NaN correction이 gate 거부로 보일 위험 | update/solve의 비유한 입력은 QA_FAIL로 중단 |
| 시간 축 | 부동소수점 때문에 정확한 horizon 경계의 마지막 패킷 누락 가능 | timestamp 허용오차·120초 검열·route_end 시험 |
| nuisance 단위 | x/y/bias 단위에 따라 SVD rank 판정이 달라질 위험 | nuisance 열 정규화 및 단위 불변성 시험 |
| 원본 보존 | 출력이 원본 입력 폴더와 겹칠 위험 | 입출력 루트 겹침 사전 차단 |
| 통계 범위 | 단일 seed/부분 case를 전체 안전성으로 오인할 위험 | 단일 seed INCONCLUSIVE, partial scope 명시 |
| simple comparator | eta를 gate 또는 표준편차 배수로 오해할 위험 | 원 코드 그대로 update R만 2배, 별도 비교표 |
| mutable 상태 | branch 간 PRNG/모델 공유 가능성 | corrector와 mutable model deep copy, PRNG 반복성 시험 |

## 원 계획과의 대응

`manifest.json`은 S0–S7 진입점·조건·산출 범위와 필수 R01–R20 시험 이름을 연결합니다.
코드 감사는 해당 시험이 실제 suite에 존재하는지, stage 함수가 정의되는지, runtime이 truth/training 모듈을 import하지 않는지 확인합니다.
S3는 이전 두 route 기반 teacher와 새 spatial-crossfit teacher를 분리합니다. 부족한 내부 fold를 삭제하지 않고 BLOCKED로 기록합니다.
S2의 직교성만으로 성공을 판단하지 않고 S3의 P2/P4 절대 residual 예측, S4의 heading 반응, S5의 실제 재귀 효과를 함께 요구합니다.
S7은 결과를 자동 채택하지 않으며 mechanism review를 별도로 요구합니다.

## 검증하지 않았으며, 이후 반드시 필요한 것

- clean 0686b23/원 artifact/고정 환경에서 S0 실제 통합·중간 상태 parity.
- 실제 SourceFFD의 극점·observer FP 전환 및 복원된 GRID 완전성.
- 168개 paired 조건 및 native LoS의 신규 후보 성능, 실패·오차 지속시간.
- 모형 기반 Ω/시간 metric의 타당성, 비정상성, 새 장면·실측 일반화.

합성 시험에서 HGB를 작은 인공 표에 적합한 것은 학습 코드·누수 차단·직렬화 계약을 확인한 것입니다. 실제 학습 route를 사용한 새로운 RF 모델은 생성하지 않았습니다. 기존 GitHub Actions workflow를 수정·dispatch하지 않았습니다.
