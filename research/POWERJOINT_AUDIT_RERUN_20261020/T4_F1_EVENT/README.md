# T4 실행 연결

이 폴더는 실행 준비물이다. `PROTOCOL_LOCK.json` 커밋 후 Mother의 워크플로에서 실행한다. 준비 단계의 AST/JSON 검사는 수치 검증이나 F1 판정이 아니다.

기존 주로:

```powershell
python run_events.py --bundle EXEC/old_bundle/BUNDLE.json --source-root EXEC/source --execution-root EXEC --out OUT
```

신규 주로는 T2 seed0 B0 trace와 case metadata를 그대로 사용한다. 한 주로씩 별도 작업에서 실행할 수 있다.

```powershell
python run_events.py --new-traces T2/traces --case-config C01_CASES.json --source-root EXEC/source --execution-root EXEC --out OUT_C01
```

`C01_CASES.json` 스키마:

```json
{"range_model":"B_OLD","cases":[{"case":{"id":"C01_A_M45_FULL","anchor":[4,0,2.65],"mount_deg":45,"robot_z_m":0.45},"trace":"C01_A_M45_FULL_B0.npz","bias":"B0"}]}
```

case의 실제 key 이름과 값은 T2 baseline runner의 동일 case 객체를 복사한다. 위 예시는 문서 스키마이며 임의 geometry 추정에 사용하지 않는다. trace는 원래 `state/cov/names/accepted`와 `t/initial_pose/controls_dt/controls_ds/controls_dyaw/observations/mu_input/C_input/radio_mask/truth_for_offline_scoring_only`를 포함해야 한다. 신규 trace에 실제 RF 행만 식별하는 mask가 필요하며 radio pose ID와 motion ID를 같은 인덱스로 추정하지 않는다. 고정 이벤트의 좌표 membership만 저장된 pose에서 복구한다. 오차나 skip 성능으로 이벤트를 선택하지 않는다.

기존 BUNDLE은 T1 `prepare_old.py` 그대로 사용한다. B0만 처리하며, `historical_power1_trace`와 KEY_B0가 모두 있어야 기존 기준선 검사가 통과한다. 신규는 입력 T2 trace의 POWER1 및 gate에 대해 재현 검사한다. 모든 arm은 기존 T1의 행렬 scorer와 독립 scalar scorer를 비교한다. D4 포함 모든 prior/posterior의 양정성을 매 frame 검사하며 실패 arm의 수치를 판정에 쓰지 않는다. 각 arm은 별도로 실행되어 한 arm 오류가 다른 개입을 지우지 않는다.

최종 병합:

```powershell
python run_events.py --aggregate OUT_OLD/INTERVENTIONS.csv OUT_C01/INTERVENTIONS.csv OUT_C02/INTERVENTIONS.csv OUT_O02/INTERVENTIONS.csv OUT_O03/INTERVENTIONS.csv --out OUT_ALL
```

동일 event/arm/scope 중복은 오류다. 입력 부분집합만으로 전체 F1 지지 판정을 만들지 않는다. 판정 분모는 고정 유해 5개/유익 5개이며 유익 부호 변경은 안전성 미확립이다. 원래 역할을 바꾸거나 이벤트를 대체하지 않는다. B_OLD 한 버전만 고정한다. T6 범위 관측식과 재학습 파라미터를 사용할 때에는 별도 lock/version 및 결과 디렉터리가 필요하다.

CSV: `INTERVENTIONS`(모든 11 지표, global motion/RF·event·post30 scopes, skip/개입 이득), `PACKET_LOG_<event>`(RF 실제 update window), `DIVERGENCE`(전체 motion 시점), `GROWTH`, `FIRST_HARMFUL_UPDATE`, `EVENT_RECEIPT`, `BASELINE_CHECKS`. `ERRORS.json`은 재시도 여부와 traceback을 보존한다. NPZ는 Actions artifact에만 두고 publisher가 `MANIFEST.json`의 artifact id/archive SHA를 채운다. 소규모 CSV와 모든 코드는 git에 보존한다. run 결과를 보고 threshold를 변경하지 않는다.
