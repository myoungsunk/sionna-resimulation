# T5 초기화 실행 연결

protocol 커밋 뒤 실행한다. 준비 상태는 실행·과학 판정이 아니다. T2 정본 B0 seed0 trace와 동일 case metadata를 사용한다. T4의 입력 정규화·고정 RF visit 찾기·기준선 재현 검사·독립 scorer 함수를 재사용한다. 이 의존 코드의 SHA256도 MANIFEST에 남긴다.

```powershell
python run_initialization.py --new-traces T2/traces --case-config C03_CASES.json --source-root EXEC/source --execution-root EXEC --out OUT_C03
python run_initialization.py --new-traces T2/traces --case-config O01_CASES.json --source-root EXEC/source --execution-root EXEC --out OUT_O01
python run_initialization.py --aggregate OUT_C03/RESULTS.csv OUT_O01/RESULTS.csv --out OUT_ALL
```

case config는 T4와 같은 스키마다. 예:

```json
{"range_model":"B_OLD","cases":[{"case":{"id":"C03_A_M45_FULL","anchor":[4,0,2.65],"mount_deg":45,"robot_z_m":0.45},"trace":"C03_A_M45_FULL_B0.npz","bias":"B0"}]}
```

실제 case 객체는 T2 runner에서 복사한다. C03 B와 O01 객체도 T2의 동일 객체여야 한다. trace 필드는 T2 전체 `state/cov/names/accepted/t/initial_pose/controls_dt/controls_ds/controls_dyaw/observations/mu_input/C_input/radio_mask/truth_for_offline_scoring_only`를 포함해야 한다. 입력 데이터와 seed0를 바꾸지 않는다. 초기 상태 평균·학습 파라미터·센서 제어는 고정하고 초기 physical4 공분산만 바꾼다.

초기 P 변형은 ψ 또는 b_g 한 대각 원소의 **분산**을 0.5/2/4배 한다. σ 변형은 b_g 표준편차를 deg/s에서 rad/s로 변환하여 제곱한다. 초기 교차항은 정본과 같은 0이다. 0.1 deg/s σ arm은 정본 초기 P와 같아도 요청된 대조군으로 남긴다.

`RESULTS.csv`는 3조건 × 10설정 × 2arm × 6scope(5/10/30 s, 전체 motion 및 radio) = 360행의 모든 11지표를 제공한다. `SKIP_EFFECTS.csv`에 각 설정 skip 이득과 baseline 대비 절대크기 소실 비율을 기록한다. 주 판정은 C03 A `MOTION_T30`이며 비교 조건으로 주 조건을 교체하지 않는다. sign reversal만으로 효과 소실을 선언하지 않는다. 모든 설정을 보존하며 최적 설정을 후속 기본값으로 채택하지 않는다.

NPZ는 Actions artifact에만 저장한다. 소규모 CSV·code·lock·receipt·error를 git에 보존하고 publisher가 artifact ID와 archive SHA256를 MANIFEST에 추가한다. 실패 arm은 ERROR에 보존하고 고치거나 수치에서 은폐하지 않는다. 한 조건씩 실행할 경우 technical=PARTIAL_CASE_SET이며 병합 후 전체 360행을 확인한다. 개별 입력의 BASELINE_CHECKS는 개별 작업 산출물에 보존한다.
