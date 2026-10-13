# I2 참조 보완 R0·R1 실행 결과

2026-10-13. 사용자 감사의 세 조건을 명문화한 뒤 R0→R1을 실행했다. **R0 PASS, R1 INCONCLUSIVE이며 후속 Range 진입 조건을 충족하지 못해 중단했다.** I3/I7은 NOT_RUN이다. REFERENCE_NOT_VALIDATED를 유지한다.

## 구현과 검증

- `I2_REFERENCE_REPAIR_DESIGN.json`: 전체 S0 목표 밀도, log-rho Jacobian, MH 제안비, 짧은 Range의 독립 적분 검증, 대칭적 SD비·pooled SD·MC 오차·CDF/공동영역/mode 허용차를 결과 전에 동결했다. 개발 계약이며 I7 사전등록이 아니다.
- `repair_target.py`: likelihood만 반환하는 기존 evaluate와 전체 밀도를 분리했다. 반경 독립 제안의 상쇄 조건과 결합 이동의 전체 prior 항을 검사했다. 실제 joint sampler는 아직 실행하지 않았다.
- `repair_r1_dr.py`: 기존 코드의 likelihood 함수를 호출하지 않는 DR 밀도 구현. bg는 조건부 Gaussian 적분으로 제거하고 SF/eps는 Gauss–Legendre 적분했다. 이는 현재 conditional measured-input 모델만 검증하며 물리적 생성모델 전체를 승인하지 않는다.
- 관련 단위시험 9개 PASS. 실제 R2/R4의 각 128개 parameter 지점에서 기존 밀도와의 최대 log 차이는 1.819e-12, 9.095e-13으로 1e-8 기준을 통과했다.
- 원격 기준 3b705cff883d3e126457d076d852721bba0b4c18, 로컬 HEAD 3032a58925ad4d1e3acec85865958e6580d79be7. 실행은 파일 SHA로 고정했다. 기존 감사 입력 26개를 변경하지 않았다.

## R1 실제 결과

Gaussian 세계 R2/R4, d2, seed8000의 기존 DR 관측을 사용했다. 각 사례에 대해 bound8에서 order96/192/384, order384에서 bound6/10으로 총 10회 적분했다. bg는 전체 실수축에 대해 적분하며 bound는 SF/eps의 prior 표준화 좌표 범위다.

| 검사 | R2 | R4 | 기준 |
|---|---:|---:|---:|
| 192→384 정규화 상대 변화 | 0(표시 정밀도) | 9.60e-11 | ≤1e-6 |
| 192→384 분위수 최대 변화/SD | 0.070344 | 0.088244 | ≤0.01 |
| bound8→10 분위수 최대 변화/SD | 0.029851 | 0.017063 | ≤0.01 |
| bound10의 보수적 tail 상한 수치식 | 1.0 | 1.0 | ≤1e-6 및 검증 가능한 bound |

정규화·평균·공분산의 안정성은 분위수까지 보장하지 않았다. 최대 분위수 변화는 두 사례 모두 bg에서 발생했다. bg CDF는 각 SF/eps 지점의 Gaussian CDF를 적분 가중치로 합산한다. **따라서 전체 실패를 PCHIP 보간 문제로만 설명하면 안 된다.** R4 SF/eps 분위수도 차수 변경에서 각각 .01731/.02993 SD 변했다. 해당 두 변수의 marginal CDF는 PCHIP 적분을 사용한다. CDF 적분 해상도와 보간 오차를 분리해 개선해야 한다.

Tail의 전역 likelihood 상한 S≥qo 자체는 타당하지만, 이를 나누는 내부 evidence는 수치 근사이다. 인증된 내부 evidence 하한이 없으므로 출력값을 엄밀하게 인증된 posterior 꼬리 상한이라고 주장하지 않는다. 1.0은 상한이 유용하지 않다는 뜻이며 실제 posterior 꼬리가 크다는 증거가 아니다. prior의 작은 tail 질량만으로 posterior tail을 승인하지 않는다.

## 실행 오류와 복구

첫 실행은 10개 원시 적분 결과를 모두 저장한 뒤 집계 JSON의 NumPy bool 직렬화에서 종료 코드 1로 끝났다. `out/i2_reference_repair_r0_r1_01/ERROR.log`와 원본 실행 영수증을 보존했다. 전체 계산 시간·시각·환경·명령·해시는 해당 `EXECUTION_RECEIPT.json`에 있다. 계산 성공과 프로그램 전체 정상 종료를 혼동하지 않는다.

`finalize_repair_r0_r1.py`로 이미 저장된 적분 결과만 집계하고 값싼 밀도 대조를 재계산했다. 적분 재실행 없이 별도 `out/i2_reference_repair_r0_r1_recovery_01/`에 정상 종료 코드 0의 집계·게이트·RECOVERY_RECEIPT를 남겼다. 원본 실패 파일을 덮어쓰지 않았다. 후처리 첫 호출은 파일이 없다는 오류로 계산 시작 전에 실패했고, 파일을 저장한 뒤 정상 실행했다.

관리 실행 run=1c4542f1-fbf4-458f-8986-059c7787f4a2, resource=b33d85b4-2f31-4935-a88c-c45841af412a. 종료 후 finish로 소유권을 해제했으며 실제 process/supervisor/job 부재를 확인했다.

## 다음 실행의 선행 조건

1. 현재 결과는 그대로 보존하고 다음 개발 버전에서 bg marginal CDF의 adaptive quadrature 또는 조건부 변수 적분 순서 변경을 검증한다. 평균/분산 수렴만으로 quantile을 승인하지 않는다.
2. SF/eps CDF도 독립 적분·세분화로 검증하고, 모든 주요 quantile의 .01 SD 기준을 유지한다.
3. 계산 영역 밖의 evidence를 더 타이트하게 제한하고 내부 evidence 오차를 제어한다. 인증이 불가능하면 유한영역 조건부 결과와 무한영역 posterior를 구분해 미승인을 유지한다.
4. R1 재검증 통과 후에만 짧은 Range 독립 적분·joint kernel 검증을 실행한다. 그 검증 전에는 PF/Batch 대규모 보완 및 prior 민감도 재실험을 시작하지 않는다.

새 개발 버전의 추가 차수·영역·시간 예산은 새 결과 전에 기록해야 한다. 이번 실행에서 동결된 차수/범위를 사후 확대하거나 통과 기준을 완화하지 않았다. 현 결과는 구조적 비식별성, practical 충분/부족, RF 오류의 확증이 아니다.

## 산출물

- 원시 수치·실패 기록: `out/i2_reference_repair_r0_r1_01/`
- 공식 후처리 집계·게이트: `out/i2_reference_repair_r0_r1_recovery_01/DR_REFERENCE_INTEGRATION.json`, `TARGET_DENSITY_CHECKS.json`, `I2_REFERENCE_REVALIDATION_GATE.json`, `RECOVERY_RECEIPT.json`
- 신규 테스트: `tests/test_repair_target.py`, `tests/test_repair_r1_dr.py`
- 기존 D6/V3/V4/I0/I1/I2 S1/S0 결과 및 판정은 변경하지 않았다. 이동·삭제한 파일은 없다.
