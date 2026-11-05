# FP-SC-001 E0 — 원본 RF 잡음 계보와 후속 D4 구분

**역할:** IMPLEMENTER 소스 조사. 별도 세션의 독립 감사 판정이 아니다.  
**기준 커밋:** `c68dcdcdd01180617b827e1f6ebb58e6740a8e29`  
**문서 작성 시 상태:** `SOURCE_EVIDENCE_CLEAN_RF / RAW_TO_PACKET_PARITY_PENDING`.

## 1. 소스에서 확인한 사실

원래 필터의 seed10은 gyro/odom과 초기 상태의 실현을 구분한다. **seed10이라는 이름만으로 복소 RF 잡음이 주입된 관측이라고 해석하면 안 된다.** 현재 확인한 관측 생성 계보는 다음과 같다.

| 단계 | 실제 코드 동작 | 확인 범위 |
|---|---|---|
| `features.py::extract` | 입력 H를 complex128로 변환하고, 257-bin Hann·1,028-tap IFFT·강한 RX 진폭 30% 첫 crossing으로 range/s를 추출한다. RNG 인자나 잡음 추가 연산이 없다. | 생성기 소스 전체 |
| `stage_a.py::run` | 저장된 Full/LoS H의 TX0를 64행씩 `extract`에 전달한다. 원래 frozen-RF trace의 z_r/z_s와 1e−12 미만 차이를 요구하고, 산출 메타데이터에 `raw_noise="noise-free H"`를 기록하도록 구현됐다. | 코드의 검증 절차 확인. 과거 실행 결과의 독립 재검산은 아님 |
| `S1/materialize.py` | Full 관측을 보관된 `nu+h+mu`로 복원하고, Native-LoS 관측은 준비된 표의 `range_m,s_fp`에서 읽는다. 별도 RF 잡음을 추가하지 않는다. | R4/R5 입력 생성 코드 |
| R2 `full_input.py` | 같은 Full 복원식과 고정 평균/R을 사용한다. | R2 확장 입력 코드 |
| R2 Native `packets.py` | 준비된 LoS 관측값을 읽어 Native packet을 만든다. | R2 Native 입력 코드 |
| `exp_pb.build_controls`·`sensor_v2` | gyro/odom·초기오차 seed를 생성한다. 이 함수는 복소 RF H를 입력으로 받거나 변형하지 않는다. | controls와 RF-noise seed의 분리 |

따라서 **관측 RF는 clean이고 controls에는 잡음이 있는 기준선일 가능성을 뒷받침하는 구체적인 소스 근거가 있다.** 다만 준비된 표와 여러 단계의 archive를 거쳤으므로, 이 문서만으로 지금 받은 12개 packet의 원시 H까지 수치적 동일성을 확정하지 않는다.

## 2. E0에서 확정해야 할 수치 확인

원시 Full/LoS H를 원래 수신기로 읽어 얻은 `range_m,s`와, 동일 pose_id·timestamp의 `FROZEN_PACKETS/z`를 직접 비교한다. R2·R4·R5 × B0·L2 × Full·Native-LoS를 분리하고, tap/포트는 exact, 부동소수점 관측은 동결 허용오차로 판정한다. 원래 z가 `nu+h+mu`의 부동소수점 재구성값인 경우 그 연산 오차와 RF 잡음을 혼동하지 않는다.

| 실제 확인 결과 | 허용 판정 | 후속 처리 |
|---|---|---|
| 원시 clean H와 archived z가 계약 내 일치 | `BASELINE_RF_CLEAN_CONFIRMED` | 원본 복소 RF-noise replay는 `NOT_APPLICABLE_NO_RF_NOISE`; controls/초기오차 replay는 별도로 검증한다. |
| 원시 clean H와 archived z가 불일치하나 원 noise recipe·seed·batch 순서 확인 | `NOISY_REPLAY_PENDING` | 원 recipe로 재생성한 H/관측이 archived z와 일치하는지 별도 검사한다. |
| 불일치하며 원 recipe 또는 입력을 확인할 수 없음 | `BLOCKED_NOISE_LINEAGE` | 차이를 추정 잡음으로 덮지 않고 정확히 필요한 recipe/seed/배열을 요청한다. |

**잡음이 원래 없었던 것과, 있었지만 자료가 없는 것은 다른 상태다.** E0 결과가 아직 없는데 둘 중 어느 쪽도 미리 PASS로 채우지 않는다.

## 3. 후속 D4의 계약

`observation.py::observe`에는 실제로 복소 RF 잡음을 넣는 기능이 있다. `sqrt(noise_var/2)`를 곱한 실수부 전체 draw와 허수부 전체 draw를 H에 더한 뒤 Hann/IFFT를 수행한다. 따라서 RNG 형식·seed·shape·frame 순서·배치 경계가 바뀌면 관측 실현도 바뀔 수 있다.

기준선이 clean으로 확인되면 D4는 원본 noisy waveform의 재현이 아니라 **동일 clean RF에서 새로 생성한 noise realization 시험**이다. 실행 전 noise variance/SNR 정의, generator·namespace·seed, draw 순서, 배열 dtype/shape/hash를 동결해야 한다. 모든 대조 arm은 같은 packet noise 배열을 공유하며, 후보 수나 처리 순서에 따라 RNG가 더 진행되면 안 된다. 원래 통계에는 새 noise 결과를 섞지 않는다.

D4가 아직 실행되지 않았다면 `NOT_RUN_NEW_NOISE_BRANCH`로 기록한다. 기존 12개 clean-RF W0 기준선 재현에 성공하더라도 noisy selector나 noisy closed-loop 성능을 입증한 것으로 해석하지 않는다.

## 4. 읽은 원전과 실제 파일 SHA256

아래 해시는 이 조사에서 읽은 기준 커밋의 실제 소스 바이트에 대한 값이다. 기존 Windows registry의 CRLF 파일과 일부 현재 LF 파일은 raw SHA가 다르므로, 줄바꿈 동등성과 바이트 동일성을 구분한다.

| ID | 원전 | SHA256 |
|---|---|---|
| 1 | [research/PHYSICS_RS_STAGED_20261015/code/features.py](https://github.com/myoungsunk/sionna-resimulation/blob/c68dcdcdd01180617b827e1f6ebb58e6740a8e29/research/PHYSICS_RS_STAGED_20261015/code/features.py) | `c2913abc9347286ad83812c0f84beadb5b2c0d7ce2a9ee57bc1ae6bd44ac2466` |
| 2 | [research/PHYSICS_RS_STAGED_20261015/code/stage_a.py](https://github.com/myoungsunk/sionna-resimulation/blob/c68dcdcdd01180617b827e1f6ebb58e6740a8e29/research/PHYSICS_RS_STAGED_20261015/code/stage_a.py) | `a140c67aa279851dd79c33d99e6d8fee8579f2caf3aa5555f86ff82af4806705` |
| 3 | [research/MBVAR_PRR_001_20261103/S1/materialize.py](https://github.com/myoungsunk/sionna-resimulation/blob/c68dcdcdd01180617b827e1f6ebb58e6740a8e29/research/MBVAR_PRR_001_20261103/S1/materialize.py) | `9423dec8b621b11469bc373575d336d524eba431a630c47d4b1deb25e12c80ef` |
| 4 | [research/MBVAR_PRR_001_20261103/POST_S3_PROPOSER_20261104/R2_EXTENSION/full_input.py](https://github.com/myoungsunk/sionna-resimulation/blob/c68dcdcdd01180617b827e1f6ebb58e6740a8e29/research/MBVAR_PRR_001_20261103/POST_S3_PROPOSER_20261104/R2_EXTENSION/full_input.py) | `07009ceadd0417267d896ffa2aa3bffbefb95b88e890c909aaa23ec232db0a2f` |
| 5 | [research/MBVAR_PRR_001_20261103/POST_S3_PROPOSER_20261104/R2_EXTENSION/native_inputs/packets.py](https://github.com/myoungsunk/sionna-resimulation/blob/c68dcdcdd01180617b827e1f6ebb58e6740a8e29/research/MBVAR_PRR_001_20261103/POST_S3_PROPOSER_20261104/R2_EXTENSION/native_inputs/packets.py) | `7f7b515be63a400cbca814784ecb055272f2da13ea0c602d949d47e6033b9ed3` |
| 6 | [src/qclean_uwb/drivesim/observation.py](https://github.com/myoungsunk/sionna-resimulation/blob/c68dcdcdd01180617b827e1f6ebb58e6740a8e29/src/qclean_uwb/drivesim/observation.py) | `8770f45df4c7f34ed5ff18ff9102a9a6ccc2cd377a9d9db4b0dfb21b805c8f22` |
| 7 | [src/qclean_uwb/drivesim/sensor_v2.py](https://github.com/myoungsunk/sionna-resimulation/blob/c68dcdcdd01180617b827e1f6ebb58e6740a8e29/src/qclean_uwb/drivesim/sensor_v2.py) | `56ea1c8f5afbd1c9662885366155c490d7ad01009d8a0bf8ebe3d7f85647c2ac` |
| 8 | [research/DS_MASK_CAUSAL_X1_X2_20261026/pol_bias_model/exp_pb.py](https://github.com/myoungsunk/sionna-resimulation/blob/c68dcdcdd01180617b827e1f6ebb58e6740a8e29/research/DS_MASK_CAUSAL_X1_X2_20261026/pol_bias_model/exp_pb.py) | `a637c3ef0322546215cab7aef76889f1e6e256048bb2821f1b9967679e534972` |
