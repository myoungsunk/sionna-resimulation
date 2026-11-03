# 생산 수집기 소스 검토 추가 기록 — 앵커 부동소수점 비교

## 결론

준비된 `runtime/r1b_acquire.py`에는 **향후 조립을 잘못 중단시킬 수 있는 앵커 좌표 비교 조건**이 있다. `validate_raw_pose`가 `[10, 0, 2.65]`와의 완전 일치(`np.array_equal`)를 요구하지만, 고정된 Native 초기화는 절대오차 `1e-12 m`, 상대오차 0의 비교를 사용한다.

이 문제는 **미실행 생산 driver의 추가 수정·재검토 필요 사항**이다. 현재 상태는 계속 `PREPARED_ONLY_UNEXECUTED`이며, 실행 승인을 부여하지 않는다. 기존 소스 검토서와 driver를 수정하지 않고 이 문서를 추가했다.

## 확인 근거

| 근거 | 확인 내용 |
|---|---|
| `runtime/r1b_acquire.py`의 `validate_raw_pose` | `np.array_equal(data["anchor_xyz_m"], np.array([10., 0., 2.65]))`를 요구하며 실패 시 `RAW_ANCHOR_NOT_B`로 중단한다. |
| V2 고정 `runtime/r1b_native.py`의 `initialize` | `np.allclose(setup.anchor_position, [10., 0., 2.65], atol=1e-12, rtol=0)`를 사용한다. |
| 같은 Native 코드의 `acquire_pose` | 실제 `setup.anchor_position`을 원시 NPZ의 `anchor_xyz_m`에 저장한다. |
| `audits/P0_CANARY_RAW_AUDIT_FINAL.json` | canary 8개 모두 `anchor_literal_max_abs_difference_m = 4.440892098500626e-16`을 기록한다. |

앵커 차이는 별도 원시 감사 결과에서 읽은 값이다. 이번 추가 검토에서는 RF·관측·필터를 재계산하지 않았다. 이 0이 아닌 차이는 완전 일치 조건에는 실패하지만, 고정 Native 코드가 허용하는 `1e-12 m`보다 작다. 따라서 같은 원시 자료가 조립 단계에 도달하면 현재의 완전 일치 검사 때문에 잘못 거절된다는 것이 소스와 저장된 감사 근거에서 도출된다.

## 현재 canary HOLD와의 관계

이 생산용 조립 함수는 canary 수집 경로에서 호출되지 않았고 생산도 실행되지 않았다. 현재 `HOLD_RF_PARITY`의 원인은 별도 고정 조건인 **복소 채널 상대오차 RMS** `0.00010051515145524099`가 한계 `0.0001`을 넘은 것이다. 이번 앵커 검사 발견은 그 판정을 바꾸거나 실패 원인을 대체하지 않는다.

앵커 비교 코드를 향후 수정하더라도 이 RMS 실패가 해소되는 것은 아니며, 생산 실행 차단은 유지되어야 한다. 허용오차나 이미 보존된 canary 결과를 변경할 근거로 사용할 수 없다.

## 후속 인계 조건

향후 생산 조립을 검토할 때 앵커 배열의 shape·유한성을 확인하고, 좌표 비교를 **이미 고정된 Native 기하 기준인 절대 `1e-12 m`, 상대 0**에 맞추는 수정이 필요하다. 이 수정은 아직 적용하지 않았다. 수정본에는 새 코드 해시와 소스 검토가 필요하며, 별도의 canary 문제 해결·생산 계획 동결·독립 승인 절차를 충족하기 전에는 실행할 수 없다.

이번 확인으로 기존 준비 상태 검토를 실행 검증이나 오류 없음 보증으로 읽어서는 안 된다는 점을 명확히 한다. 새 RF, 필터, 테스트, commit, push를 수행하지 않았다.

## 파일 결합

| 파일 | SHA-256 |
|---|---|
| `runtime/r1b_acquire.py` | `0377a0df44636469d8ce1d1c28fba6e232f33b4b5300240bd9284cf17780ff35` |
| `runtime/r1b_native.py` | `68c3982e7513f8dc89a0775d866f27460c7a75bea76ce72b767f10779f376700` |
| `audits/P0_CANARY_RAW_AUDIT_FINAL.json` | `ebc52f40dd45148cfb6b34483a729f3bc54d4e59d763503a3867b745de5151ef` |
| 보존한 `audits/P1_PRODUCTION_DRIVER_PREPARED_REVIEW.json` | `9b3f338e574af87c247081bc89cac057c27c436f5475baca00870b3007723fab` |
| 보존한 `audits/P1_PRODUCTION_DRIVER_PREPARED_REVIEW_KO.md` | `e9f0cfc5a1ecc8c9a7d31230a942e33a772685c46671c08bd20560c221ec1c8b` |

검토자: `/root/ekf_contract_review`. 별도 계산 검토자이지만 동일 작업공간이며 외부 인적 승인이나 별도 물리 환경 재현은 아니다.
