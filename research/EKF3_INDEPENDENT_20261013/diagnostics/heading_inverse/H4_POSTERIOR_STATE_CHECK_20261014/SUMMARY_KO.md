# H4 사후 상태 독립 검산 추가 결과

판정: **PASS**. 1,337,904개 업데이트, 1,512개 그룹. 허용치 1e-8 유지, scientific_PASS=false.

이전 H1–H4 결과의 NIS·gate·공분산 검산에 저장된 사후 상태 검산을 추가했다. 기존 결과 파일·필터·관측·임계값은 수정하지 않았다.

| 모델 | 최대 x 오차 (m) | 최대 y 오차 (m) | 최대 Heading 오차 (rad) | 실패 시점 |
|---|---:|---:|---:|---:|
| M0 | 1.77635684e-15 | 2.22044605e-16 | 4.4408921e-16 | 0 |
| RF_CAUCHY | 1.77635684e-15 | 8.8817842e-16 | 8.8817842e-16 | 0 |
| RF_HUBER_ONLY | 3.55271368e-15 | 8.8817842e-16 | 8.8817842e-16 | 0 |

수용 1,082,088개, 거부 255,816개. 실제 보정에서 ±π 경계 통과 123개. 양방향 wrap 및 잘못된 상태 주입 검사는 합성 검사에서도 수행했다.

## 방법 및 주장 범위

- 이전 저장 posterior와 동결 motion으로 prior를 독립 계산했다. 현재 posterior 또는 정답 상태를 prior 생성에 사용하지 않았다.
- 동일 prior에서 H, innovation, NIS, gate, gain 및 Joseph covariance를 재계산했다. 수용 시 x_prior + K innovation을, 거부 시 prior 그대로를 저장된 x/y/psi와 비교했다. Heading 차이는 wrap 후 라디안 단위로 비교했다.
- 강건 모델은 저장된 최종 RF 가중치로 R_effective를 구성했다. 최적화 상태 보정량과 해당 gain 보정량의 일치성을 검산한 것이며, 강건 가중치 최적화를 독립 재실행한 검사는 아니다.
- 각 그룹의 첫 저장 시점은 직전 posterior가 없어 제외했다. 기존 H4와 동일한 전체 평가 집합이다. 새로운 재귀 주행 실행 또는 독립 과학적 확증으로 표현하지 않는다.
- 8개 합성 검사와 단일 조건 smoke 후 전체 H4 검산을 수행했다. 원본 source/input/trace 해시를 확인했다.

[전체 증빙](FULL/RECEIPT.json) · [그룹별 검산](FULL/GROUP_PARITY.csv) · [시점별 상태와 잔차](FULL/STATE_RESIDUALS.csv.gz) · [기존 H1–H4](../H1_H4_20261014/SUMMARY_KO.md)

## 재실행

check_posterior.py는 실제 실행된 Windows source snapshot이다. 원래 실험 폴더 아래에서 실행했으며 ../OPT/run_heading.py 및 원본 동결 입력 경로를 사용한다. 다른 환경에서는 기존 H1_H4_20261014의 OPT를 해당 위치로 매핑하고 입력 경로를 준비해야 한다. python -B check_posterior.py --smoke 후 python -B check_posterior.py 순서로 실행한다. 이미 존재하는 출력은 덮어쓰지 않는다.
