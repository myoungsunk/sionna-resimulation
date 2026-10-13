# I2 S0 보완 지시 대조 — 실행 후 기록

이 문서는 I2 S0 실행 및 `bc91abb0d399f5d5b3f6f49d426ec853037356e8` 업로드 이후 도착한 보완 지시를 대조한 기록이다. **실행 전 사전등록으로 소급하지 않는다.** 기존 `I2_S0_DESIGN.json`, 코드, 결과, 해시 및 판정은 변경하지 않았고 추가 실험을 실행하지 않았다. 직접 사용자가 확정한 `S0_CONTRACT_KO.md`가 적용 계약이다.

## Gauge convention

DR는 초기 로봇 상대좌표를 (0,0,0)으로 정의한다. Ideal Range는 앵커 수평 원점과 초기 방사방향 +x를 선택하며, rho0와 delta0는 미지수다. 두 arm에 같은 절대 pose를 강제하지 않는다. Ideal Range 모델에는 지도·절대 방향·편파 관측이 없다. 전체 pose의 회전 gauge와 Calibration 식별성을 구분한다.

rho0=0에서는 초기 방사방향 자체가 정의되지 않는다. 사용한 연속 radial posterior에서 정확히 rho0=0은 확률 0이지만, 근접 퇴화 조건의 별도 실험은 수행하지 않았다. 이를 검증 완료로 표시하지 않는다. Full RF·편파의 회전 대칭성은 이번 실험 범위 밖이다.

## 초기 prior, posterior 및 proposal

무한 평면의 균일 공간밀도는 **정규화된 확률 prior가 아닌 부적절 사전측도**다. 회전 gauge를 제거한 기본 참조측도는 rho d rho × d delta이며 delta의 확률분포는 Uniform(-pi,pi]다. 첫 Range likelihood를 곱한 rho posterior를 정규화하여 사용했다.

sigma>0이고 관측 z0와 높이 차 h=|dz|가 유한할 때 정규화 적분은

```text
Z = integral_0^infinity rho exp(-(z0-sqrt(rho^2+h^2))^2/(2 sigma^2)) d rho
  = integral_h^infinity r exp(-(z0-r)^2/(2 sigma^2)) d r
```

이며 양수이고 유한하다. 그러므로 이 최초 관측 기반 반경 posterior는 정상적인 확률분포다. 이것이 유일한 무정보 prior이거나 전체 궤적 posterior의 수렴이 입증되었다는 뜻은 아니다.

PF proposal은 이 정규화된 초기 posterior 자체의 수치 근사이므로 초기 가중치는 균일하다. Batch의 rho 독립 proposal도 같은 초기 posterior에서 뽑아 MH 비율에서 초기 density와 proposal을 상쇄한다. 임의의 관측 기반 proposal을 별도 보정 없이 목표 posterior로 취급한 것이 아니다. 역 CDF 근사 오차와 꼬리 질량은 명시한 수치 기준으로 검증했다. 두 추정기 모두 첫 Range를 후속 likelihood에서 제외했다.

## 계산 경계와 실제 추가 정보

| 항목 | 적용 내용 | 의미 |
|---|---|---|
| 기본 공간 참조측도 | 면적 균일, rho Jacobian | 정규화된 무한 평면 prior가 아님 |
| 기본 수치 영역 | 첫 관측을 기준으로 slant 상한 12sigma 및 tail 검사 | 물리적 운용 영역 또는 알려진 초기 위치 아님 |
| 영역 민감도 | 6sigma/10sigma 상한 | 계산용 truncation 영향 검사 |
| 반경 균일 대안 | d rho 참조측도 | 기본 측도와 다른 prior 선택 |
| half-normal 대안 | scale10m/100m | 의도적으로 반경 선호 정보를 추가한 민감도 조건 |
| Calibration | 기존 동결 Gaussian prior | 허용된 Calibration 정보 |
| 참 초기 pose | 제공하지 않음 | 참 위치 중심의 경계 또는 truth 초기화 없음 |

저장소의 물리적 운용 영역을 추정하여 bounded uniform prior로 대체하지 않았다. 이번 실행에는 별도의 MAP 최적화 탐색 경계가 없다. 수치 상한은 확률질량 절단이고, half-normal scale 변경은 prior 민감도다.

## 비교 horizon 및 미해결 항목

PF는 시점별 누적 관측을 사용한다. Batch는 전체 공급 horizon을 사용하므로 terminal PF와 비교하며 중간 smoother를 online filter와 직접 비교하지 않는다. Calibration은 gauge-invariant하게 직접 평가하고, 절대 XY/Heading 오차를 S1과 비교하지 않았다. 원시 초기 Heading 분포·chain 원형 통계는 남겼으나 반사 mode의 완전 탐색은 입증하지 못했다.

기존 `tests/test_i1.py::test_exact_gauge_and_calibration_family`의 운동/Range 회전 대칭 및 반사 모호성 검사는 이번 40-test 실행에도 포함되었다. 그러나 **동일 S0 posterior 추정기를 여러 gauge convention으로 재실행해 Calibration 결과가 일치하는지 보는 검증은 NOT_RUN**이다. 구조적 모델 대칭성 테스트가 그 posterior 계산 검증을 대신하지 않는다.

수치 영역 확대에 따른 초기 반경 질량·정규화는 검증했지만, terminal 추정치의 안정성은 PF 퇴화 때문에 확보하지 못했다. Prior 변경에 따른 terminal 차이 역시 수렴 오차와 분리되지 않았다. 이 한계는 이미 REFERENCE_NOT_VALIDATED와 INCONCLUSIVE에 반영되어 있다. 필요한 것은 임의의 사용자 숫자 범위가 아니라 수렴한 참조 계산과 추가 계산 검증이다.

실용적 운용 오차 요구는 여전히 미정이므로 충분/부족 판정은 보류한다. I3·I7 및 새 스레드 생성은 수행하지 않았다. 다음 인계에서는 기존 S0 인계 보충과 이 실행 후 대조 기록을 함께 읽는다.
