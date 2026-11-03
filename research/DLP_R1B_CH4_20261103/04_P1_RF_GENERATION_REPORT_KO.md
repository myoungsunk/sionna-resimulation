# DLP-R1B-CH4-001 — P1 RF 생성 상태 보고서

**작성일:** 2026-11-03 KST  
**현재 판정:** `HOLD_RF_PARITY`  
**917-pose 생산 실행:** `NOT_RUN`  
**실제로 생성된 범위:** P0에서 사전 지정한 8개 pose의 Native LoS/Full canary

## 1. 실행 범위와 중단 근거

R1·Anchor B의 동결 canary 8개 pose는 모두 생성되었다. 그러나 SourceFFD–Native LoS 복소 채널의 pose별 상대오차 RMS가 `1.0051515145524099e-4`로, 사전 동결 한계 `1.0e-4`를 초과했다. 따라서 전체 917개 pose를 구성하기 위한 나머지 909개 pose의 RF 계산과 전체 배열 조립은 실행하지 않았다. [동결 V2 계약](00_REQUEST_CONTRACT_FROZEN_V2.json), [실제 canary 판정](runs/P0_CANARY_V2/03_RF_CANARY_QA.json)

독립 계산 검토자는 원시 배열에서 동일 RMS와 HOLD 판정을 재현했다. 해당 감사의 `raw_accounting_status`는 `PASS`이며, 최종 상태는 `HOLD_INDEPENDENT_RAW_AUDIT`, `production_permitted=false`이다. 원시 데이터 보존·재구성 검증의 통과와 생산 허용 여부를 각각 기록한다. [최종 원시 배열 감사](audits/P0_CANARY_RAW_AUDIT_FINAL.json)

| 구분 | 상태 | 범위 |
|---|---|---|
| P0 Native canary | 계산 완료, RF parity HOLD | 8 pose × LoS/Full, 각각 257 주파수 bin |
| 추가 Native RF 생산 | `NOT_RUN` | canary 외 909 pose |
| 917-pose 전체 H 조립 | `NOT_RUN` | 생산용 `native_full_los.npz` 없음 |
| 생산 비용·분할 계획 동결 및 승인 | 미완료 | 실제 canary 비용은 확보했으나 생산 실행을 허용하는 계획·감사 없음 |
| P2 전체 관측오차 분석 | `NOT_RUN` | 승인된 전체 917쌍 입력 없음 |
| P3 실제 4상태 EKF 재귀 비교 | `NOT_RUN` | B0/L2 Heading·XY RMSE 없음 |

현재 결과는 8개 진단 pose의 실행 근거와 실패 기록을 제공한다. 이를 R1 전체 관측오차 분포나 주행 성능의 검증 완료로 인용할 수 없다.

## 2. 실제 canary 입력·채널 명세

실행은 V2 계약에 동결된 pose ID `[0,150,221,440,458,476,696,916]`를 사용했다. 참 궤적은 원본 `y0.35/Tnone`의 917개 시점을 보존하며, canary 선택은 RF 결과를 보기 전에 기하와 주행 phase로 정했다. 실제 실행 코드 commit은 `24d657af7773d1c0347e843ece6b49e9c2d55ac2`이다. [계약](00_REQUEST_CONTRACT_FROZEN_V2.json), [실행 환경](runs/P0_CANARY_V2/ENVIRONMENT.json)

- Anchor B: `(10,0,2.65) m`; tag 높이 `0.45 m`; mount `0°`.
- Native LoS는 `max_depth=0`, Full은 기존 C0 설정의 `max_depth=3`으로 각각 호출했다.
- 주파수 축: `6,250,400,000 + 1,950,000 × bin` Hz, 257개 bin.
- 각 pose의 H 축: `[frequency, rx(+45,-45), tx(+45,-45)]`, shape `(257,2,2)`.
- 관측에는 TX `+45°` 열을 사용한다. symmetric Hann, 4배 IFFT 길이 1,028, strongest RX의 30% leading edge가 두 RX에 공통인 tap을 결정한다.
- 원시 채널에 추가 RF 잡음을 넣지 않았다. Native LoS와 Full을 각각 계산했고, 사후 공통 위상·이득 fitting을 적용하지 않았다.

각 pose의 NPZ에는 `H_full`, `H_los`, 선택 TX의 CIR, 주파수·pose·anchor, SourceFFD 참조와 모델값, 주파수별 path offsets 및 counts, path별 복소 진폭 `a`, 지연 `tau`, interactions, object IDs가 보존되어 있다. object ID와 장면 표면명의 대응 및 6개 mesh/material binding은 [ENVIRONMENT.json](runs/P0_CANARY_V2/ENVIRONMENT.json)에 있다. [생성 코드](runtime/r1b_native.py), [독립 재구성 감사](audits/P0_CANARY_RAW_AUDIT_FINAL.json)

| pose ID | 시각 (s) | phase | 원시 파일 | SHA-256 |
|---:|---:|---|---|---|
| 0 | 0.0 | drive_out | [pose_0000.npz](runs/P0_CANARY_V2/pose_0000.npz) | `f969ed5caf54b288d71303cc9cca035c4d112e6ece048a3fa8517f837b820600` |
| 150 | 30.0 | drive_out | [pose_0150.npz](runs/P0_CANARY_V2/pose_0150.npz) | `f281da1643c8089c219697a438df3e23176b979fa2b9a9698524a33d763319b7` |
| 221 | 44.2 | drive_out | [pose_0221.npz](runs/P0_CANARY_V2/pose_0221.npz) | `6e8642df8c5f474562bb3e5c9b03db0167db5edba4c6703a658e9ec7fb833cf9` |
| 440 | 88.0 | drive_out | [pose_0440.npz](runs/P0_CANARY_V2/pose_0440.npz) | `7deb58f8fc7cbbd0b7c0cc972dd1b34c1285bae6328ec4703e5f66f8a1fc5f98` |
| 458 | 91.6 | turn | [pose_0458.npz](runs/P0_CANARY_V2/pose_0458.npz) | `19d1dbe2151f786a06c99c84cd00fad0dd3d8eba346459cda71a3e72a36a8e45` |
| 476 | 95.2 | turn | [pose_0476.npz](runs/P0_CANARY_V2/pose_0476.npz) | `a80ed71f86895c7c55f8a4a89ed3a973eac5f2ae875d99b000b51711f8f0a82a` |
| 696 | 139.2 | drive_back | [pose_0696.npz](runs/P0_CANARY_V2/pose_0696.npz) | `601f3562a4bcde862736b7f38661e1a1ed9aa311c89f81ff2ff3768911148a8a` |
| 916 | 183.2 | drive_back | [pose_0916.npz](runs/P0_CANARY_V2/pose_0916.npz) | `231fdd55b6a79a193d2fc1d13c12034fa1dbc775b822233b27d2b60d5fc3edaa` |

## 3. 사전 동결 기준에 대한 실제 판정

복소 상대오차는 각 pose의 Native LoS TX `+45°` 두 RX 채널과 SourceFFD 물리 채널 사이의 상대 L2 오차이며, 아래 RMS는 8개 pose별 상대오차의 제곱평균제곱근이다. 관측 편파 오차와 구분한다. [canary QA](runs/P0_CANARY_V2/03_RF_CANARY_QA.json)

| 검사 | 동결 한계 | 실제 canary 값 | 판정 |
|---|---:|---:|---|
| 복소 채널 상대오차 최댓값 | `5e-4` | `1.5950092587162026e-4` | PASS |
| 복소 채널 상대오차 RMS | `1e-4` | `1.0051515145524099e-4` | **HOLD** |
| signed s 절대오차 최댓값 | `2e-5` | `5.364072267477482e-7` | PASS |
| signed s RMSE | `2e-6` | `2.0947930308467728e-7` | PASS |
| SourceFFD–Native LoS tap 불일치 | 0개 | 0개 | PASS |
| strongest RX branch 불일치 | 0개 | 0개 | PASS |

총 12개 canary 판정 중 11개가 통과했고 복소 RMS 1개가 실패했다. 지연·Full 직접경로 존재 및 standalone LoS와의 일치, SourceFFD 내부 직접경로 비교, stable-cell Jacobian 검사는 각 pose별 기록과 최종 감사에 보존되어 있다. 허용오차는 실패 결과를 확인한 뒤 변경하지 않았다. RMS는 한계를 약 `0.51515%` 초과했으며, 이 초과를 무시하거나 기준을 반올림하여 PASS로 바꾸지 않았다. [QA](runs/P0_CANARY_V2/03_RF_CANARY_QA.json), [원시 재계산](audits/P0_CANARY_RAW_AUDIT_FINAL.json)

## 4. 실제 측정 비용

8-pose canary의 기록된 경과 시간은 `510.4004 s`, pose별 중앙값은 `37.7229 s`, 최댓값은 `246.0802 s`, 최대 RSS는 `1,208.9609 MiB`였다. QA에 기록된 `9.6089 h`는 중앙값에 917을 곱한 순차 실행 환산치이다. 전체 주행을 실제 실행한 시간이나 확정된 생산 비용은 아니다. max 기반 환산치 `62.6821 h`도 같은 성격의 참고값이다. 현재 HOLD에서 생산 비용 계획을 동결하거나 실행을 개시하지 않았다. [측정값 및 산술](runs/P0_CANARY_V2/03_RF_CANARY_QA.json), [독립 산술 확인](audits/P0_CANARY_RAW_AUDIT_FINAL.json)

## 5. 준비된 생산 실행기와 알려진 제한

[r1b_acquire.py](runtime/r1b_acquire.py)는 8개 canary와 909개 추가 pose의 해시 연결, 동결된 shard 목록, 별도 계산 감사, 원시 배열 조립 및 검사를 위한 준비 코드다. SHA-256은 `0377a0df44636469d8ce1d1c28fba6e232f33b4b5300240bd9284cf17780ff35`이다. 해당 코드의 source review 상태는 `PREPARED_ONLY_UNEXECUTED`이며, `production_authorized_by_this_receipt=false`이다. 생산·조립·실제 HOLD 입력을 이용한 실행 차단 시험은 수행하지 않았다. [준비 코드 검토](audits/P1_PRODUCTION_DRIVER_PREPARED_REVIEW.json)

**향후 수정·재검토가 필요한 구체적 제한:** 현재 준비 실행기의 `validate_raw_pose`는 anchor 좌표에 `np.array_equal`을 사용한다. 실제 canary 원시 배열과 `(10,0,2.65)` 상수의 최대 차이는 `4.440892098500626e-16 m`이며, 동결된 Native 초기화는 절대 허용오차 `1e-12 m`를 사용한다. 따라서 이 준비 코드의 엄격한 완전일치 검사는 허용되는 좌표 표현 차이에도 향후 조립을 중단시킬 수 있다. 현 HOLD에서는 코드를 수정하지 않았으며, 미래 실행 전에 별도 수정과 검토가 필요하다. 이 준비 코드의 제한은 **이미 실행된 canary의 복소 RMS 초과와 독립된 문제**다. [준비 실행기](runtime/r1b_acquire.py), [원시 감사의 좌표 오차 및 erratum](audits/P0_CANARY_RAW_AUDIT_FINAL.json)

준비 실행기는 여러 프로세스의 중단을 총괄하는 supervisor가 아니다. 향후 병렬 생산을 검토할 경우 전체 중단 방식과 비용·분할 계획이 추가로 명세되어야 한다. 현재 문서와 source review는 생산 승인 또는 실제 생산 검증을 부여하지 않는다. [검토 범위와 제한](audits/P1_PRODUCTION_DRIVER_PREPARED_REVIEW.json)

## 6. 핵심 근거 해시

| 근거 | SHA-256 |
|---|---|
| [V2 계약](00_REQUEST_CONTRACT_FROZEN_V2.json) | `a31a537dd35823d10c1d74ee0cf488d439b7ba2c70114309e024b451a9468596` |
| [실행 canary QA](runs/P0_CANARY_V2/03_RF_CANARY_QA.json) | `ac5959437500c480e0b3d93cd6a4c4988d537f76b331eecb1de0a5764062f5d0` |
| [실행 환경](runs/P0_CANARY_V2/ENVIRONMENT.json) | `88b8545cba6e59490af758b60365a5df6dfcb91b87959972d0eac6fbd39e2375` |
| [Native 실행 코드](runtime/r1b_native.py) | `68c3982e7513f8dc89a0775d866f27460c7a75bea76ce72b767f10779f376700` |
| [최종 원시 감사](audits/P0_CANARY_RAW_AUDIT_FINAL.json) | `ebc52f40dd45148cfb6b34483a729f3bc54d4e59d763503a3867b745de5151ef` |

P1 생산 실행과 제IV장용 전체 관측 데이터 검증은 미완료다. 현재 보존된 8개 원시 canary와 실패 기록은 다음 정합성 조사 및 독립 검토의 입력으로 사용할 수 있다.
