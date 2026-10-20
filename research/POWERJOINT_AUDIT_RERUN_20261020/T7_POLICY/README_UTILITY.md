# T7B 효용 정책 실행 연결

이 runner는 T7A 회수 결과를 변경하지 않는다. T4 **전체** DECISION/MANIFEST의 완료를 먼저 검사한다. F1 지지/기각/미확립 어느 판정이어도 실행할 수 있지만 미완료 T4는 차단한다. 아직 RF 수치 실행을 하지 않았다.

T4 완료는 모든 개입의 TECHNICAL_PASS를 요구하지 않는다. 고정10 이벤트 각각 baseline/SKIP/D1/D2/D3/D5/D6의 모든11지표와 독립 scorer, baseline parity가 있어야 한다. D4는 성공 지표 또는 `ERRORS.json`의 해당 event에 대한 `arm=D4`, `NONSPD` 오류 보존이면 완료다. D4를 PSD 보정하거나 다시 실행할 필요가 없다. D4 이외 오류·baseline/gate/scorer 오류는 계속 차단한다. T4 final은 INTERVENTIONS.csv, BASELINE_CHECKS.csv와 flat-list ERRORS.json도 포함한다.

커밋할 lock은 이 폴더 `PROTOCOL_LOCK.json`이다. shared `canonical_engine.py`에는 끝의 선택 인자 `initial_state4=None`, `decision_provider=None`만 추가했다. 기본 인자를 생략하면 기존 수치 경로를 유지한다. 선택 provider 시 `decisions` 배열을 추가로 반환한다. source projection/dynamics/gate/관측 모델은 바꾸지 않았다.

provider 계약:

```python
decision_provider(i, prior4, Pprior4, predicted_h2, H2x4, power_mu2, power_C2x2, spec)
# -> 'POWER' | 'R0' | 'INFLATE4' | 'SKIP'
```

현재 RF packet의 prior와 POWER 후보 NIS를 얻고, 최종 mu/R/innovation/K/gate 전에 행동을 적용한다. 원래 gate를 강제로 통과시키지 않는다. non-RF 시점은 callback을 호출하지 않는다. 일반 physical joint-update 전용이며 memory/sequential/diagnostic spec과 혼용하면 오류다. `initial_state4`는 counterfactual의 저장된 prior x/y/psi/b_g를 그대로 복원하며, `initial_cov`는 기존 physical4 행렬을 받는다. segment의 첫 frame에는 예측을 한 번 더 하지 않는다.

프로토콜 커밋 뒤 synthetic interface 검사부터 실행한다. 이 검사는 RF 결과나 과학 판정이 아니다.

```powershell
python interface_checks.py
```

POWER callback/default, R0, INFLATE4, SKIP 및 prior로 재시작한 continuation에 대해 상태/공분산 1e-10, gate0을 검사한다. 실제 label마다 counterfactual POWER branch와 원래 nested baseline의 continuation도 같은 오차로 검사한다.

Nested label은 4개 job으로 나눌 수 있다. `OUTER`는 `R2`, `R4`, `R5`, `ALL_OLD` 중 하나다.

```powershell
python utility_policy.py labels --outer OUTER --source-root EXEC/source --execution-root EXEC --t4-final T4_FINAL --out LABEL_OUTER
python utility_policy.py train --labels LABEL_R2/UTILITY_LABELS.csv LABEL_R4/UTILITY_LABELS.csv LABEL_R5/UTILITY_LABELS.csv LABEL_ALL_OLD/UTILITY_LABELS.csv --t4-final T4_FINAL --out MODELS
```

외부 R2 정책 학습의 예: R4 label의 POWER prior는 R5만 학습하고 R4와 같은 위치는 제외한다. R5 label prior는 R4만 학습하고 R5 같은 위치를 제외한다. 외부 R2의 RF label/특징은 이 학습에 없다. ALL_OLD 신규 평가 모델에서는 일반 old route-heldout priors를 사용한다. 값비싼 RF 재생성 없이 캐시 SourceLabels의 고정 측정 feature와 허용 학습 label을 사용한다.

`ScalarPower`는 기존 P1 Ridge/tertile full covariance fitter 그대로다. 정책은 fixed HGB 상대 효용 회귀 4개다. Utility label은 네 행동에서 현재 packet만 바꾸고 이후 10초는 원래 POWER로 재귀한 Heading MSE 차이다. t≥30, 5초 간격 thinning과 full10s 가용 조건을 label 전에 적용한다. GT는 센서 생성·학습 label·평가에만 사용한다. 온라인 입력 열은 고정한 측정17개+내부4개이며 pose/route/label 칼럼을 넣지 않는다.

모델은 trusted own pickles와 MODELS.json hash를 함께 보존한다. load 전에 파일 경로·SHA256·protocol hash·sklearn 버전을 검사한다. 원래 code 및 utility label CSV가 결정론적 재학습 입력이므로 opaque model만 유일 근거로 남기지 않는다. 모델 binary/NPZ는 workflow artifact에 포함하고 모든 실행 code·CSV·JSON은 git에 보존한다.

평가:

```powershell
python utility_policy.py evaluate --models MODELS/MODELS.json --old-bundle EXEC/old_bundle/BUNDLE.json --source-root EXEC/source --execution-root EXEC --t4-final T4_FINAL --out OLD_EVAL
python utility_policy.py evaluate --models MODELS/MODELS.json --new-config T2_COMBINED/NEW_CASES.json --source-root EXEC/source --execution-root EXEC --t4-final T4_FINAL --out NEW_EVAL
python utility_policy.py aggregate --aggregate OLD_EVAL/POLICY_RESULTS.csv NEW_EVAL/POLICY_RESULTS.csv --t4-final T4_FINAL --out FINAL
```

old bundle은 T1 prepare_old.py의 7×4bias 입력이다. NativeLoS R2 A0/A45×4는 original frozen inputs와 cached NativeLoS feature/parameters로 자동 추가한다. old Full POWER1은 입력 historical trace와 gate/RMSE 및 B0 KEY를 재현해야 한다. T2 trace는 입력 저장 POWER1 gate/RMSE를 재현해야 한다. POLICY는 자기 재귀 prior로 특징을 재계산한다.

신규 config schema (경로는 config 파일 부모 기준):

기존 추출 T2 artifact들과 검증된 release 디렉터리에서 helper로 직접 조립할 수 있다.

```powershell
python assemble_new_inputs.py --t2-root DOWNLOADED_T2 --release-root VERIFIED_ROUTES --source-root EXEC/source --out T2_COMBINED
```

`VERIFIED_ROUTES`에는 여섯 restore_route 결과의 ARCHIVE_CONTENTS_AND_SHA.json과 data 트리가 있다. helper는 receipt hash가 일치하는 기존 H_FULL.npy와 RADIO_POSE의 pose_id만 읽고 원래 `features.extract` 및 고정 request 주파수로 측정 feature를 계산한다. request의 anchor/mount/height를 metadata로 쓴다. NativeLoS H, GT pose/error는 feature 생성에 사용하지 않는다. trace와 관측 r/s·RF row id 일치를 확인하고 T2 NPZ를 이름/byte 그대로 복사한다. NEW_CASES.json은36입력, features는9CSV다. RF 생성·센서 재실행은 없다.

```json
{"range_model":"B_OLD","cases":[{"case":{"id":"C01_A_M45_FULL","anchor":[4,0,2.65],"mount_deg":45,"robot_z_m":0.45},"bias":"B0","bias_dps":0,"npz":"traces/C01_A_M45_FULL_B0.npz","features":"FULL_FEATURES.csv"}]}
```

신규9×4bias를 모두 넣는다. 같은 RF feature CSV는 4 bias에서 공유한다. feature CSV는 T2의 Full-only `features.extract` 결과17개와 `s_fp`, `pose_id`, `case`를 담아야 한다. `pose_id`는 `radio_pose_ids`와 join하고 관측 r/s 일치도 검사한다. 모든 trace는 T2 seed0의 t/state/cov/names/accepted,initial_pose,controls*,observations,mu_input,C_input,radio_mask,radio_pose_ids,truth_for_offline_scoring_only가 필요하다. config case 객체는 T2와 정확히 같아야 한다.

각 evaluation cell은 POWER1/R0/POLICY 3arm, motion/RF 2scope 및 11지표를 보존한다. 전체 final은 Full64 및 NativeLoS8 cell의 고정 집합을 요구한다. 하나라도 Full policy/POWER1>1.10 또는 NativeLoS policy/R0>1.10이면 NO_GO다. 누락/오류도 승인하지 않는다. 분할 실행의 과학 판정은 NOT_ESTABLISHED/NO_GO 상태를 유지한다.

`UTILITY_LABELS.csv`, `TRAIN_FOLDS.json`, `MODELS.json`, `POLICY_RESULTS.csv`, `BASELINE_CHECKS.csv`, case/channel/bias별 `ACTIONS_*.csv`, `ERRORS.json`, `DECISION.json`, `MANIFEST.json`을 보존한다. CSV 각각20MB 이하여야 하며 실패도 지우지 않는다. publisher가 archive SHA와 artifact id를 manifest에 추가한다. `workflow_template.yml`은 root가 실제 workflows 위치에 옮겨 prerequisite artifact 위치를 연결할 준비물이다.
