# R3 solver + 원래 P2 600 paired trial 전체 결과 (2026-10-14)

## 사전 검증·입력 불변
실행 코드 `f67b79580b4c961cd4242e52154b7d73e390e290`, [GitHub Actions Run 38535078022](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38535078022).
원본 [artifact 11879309046](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38535078022/artifacts/11879309046), SHA256 `d7fe8ed13fd9d49dee7af43bbf9c7f750f0912783584d8c50fcfea75c11d428b`; 다운로드 ZIP SHA256/CRC PASS, 내부 요약/CI/최종 receipt를 원시 ZIP에서 확인. 원본 `P2_SPEC.json`, `synthetic.py`, 초기상태, Q/R, 3경로×2 bias×100 trial, 60s/0.5s, 동일 seed, gradient 1e-8, 최대 반복 80 모두 유지.

- Audit (source/input) GO; P0 16 PASS, P1 8 PASS, R1 5 PASS, R2 10 PASS, R3 6 PASS.
- 원본 네 실패 × 저장 iterate/Range-first 각각 R3 `CONVERGED` 8/8.
- 대표 P2 6개 동결 조건×4모델 24/24 정상 완료.
- 전체 600 paired-trial (=3×2×100) ×4 추정기 = **2,400 model-trial SUCCESS**, invalid 0, paired trial 600/600, 종료 상태 `FULL_P2_COMPLETED`.
- 과거 R1/R2에 있던 float64 직접비용 차의 잘못된 부호를 동일 목적함수의 적응적인 gradient line-integral step acceptance로 분리. 임계값을 완화하거나 실험 실패 trial을 삭제하지 않음.

## 3/4-state EKF와 MAP Heading RMSE, 각도 (°)

| 경로 | 참 gyro bias deg/s | EKF3 | EKF4 | MAP3 | MAP4 |
|---|---:|---:|---:|---:|---:|
| straight | 0 | 0.4423 | 0.5592 | **0.4425** | 0.5594 |
| straight | +0.05 | 0.9941 | 0.5702 | 0.9961 | **0.5699** |
| turn | 0 | 0.4485 | 0.5853 | **0.4480** | 0.5849 |
| turn | +0.05 | 1.0284 | 0.5923 | 1.0329 | **0.5918** |
| return | 0 | 0.4513 | 0.5703 | **0.4518** | 0.5709 |
| return | +0.05 | 0.9549 | 0.5736 | 0.9563 | **0.5738** |

실제 bias +0.05 조건의 MAP4–MAP3 paired trial Heading MSE Δ(단위 deg², CI는 seed를 반복단위로 한 10,000 bootstrap, 전체 100 paired 비교):
- straight: -0.66751, CI95 [-0.72221,-0.61486], `SUPPORT`
- turn: -0.71673, CI95 [-0.78611,-0.65015], `SUPPORT`
- return: -0.58521, CI95 [-0.64479,-0.52782], `SUPPORT`.
세 경로 모두 `ALL_THREE_ROUTES_SUPPORT`는 **합성 +0.05 bias 조건의 전 경로 유효성 주장**에 국한됨.

## Position RMSE (m), MAP3 → MAP4
- straight / bias0: 0.0658 → 0.0656; bias+.05: 0.0688 → 0.0657.
- turn / bias0: 0.0541 → 0.0551; bias+.05: 0.0650 → 0.0550.
- return / bias0: 0.0572 → 0.0593; bias+.05: 0.0764 → 0.0594.

## Heading 95% 포함률, MAP3 → MAP4
- straight bias0: 95.21% → 96.87%; bias+.05: **35.14% → 96.42%**.
- turn bias0: 95.62% → 96.58%; bias+.05: **37.42% → 96.49%**.
- return bias0: 95.32% → 95.57%; bias+.05: **37.53% → 95.68%**.
Pose95 bias+.05는 straight 35.65%→95.52%, turn 36.57%→95.82%, return 38.42%→94.77%.

**과신 해소는 합성 세계에서 강한 긍정 신호**지만, 이는 true bias를 0 또는 +0.05로 고정하고 noise/초기 prior를 샘플링한 조건부 빈도다. 독립 calibrated RF Full 채널의 실제 일관성·일반화 검증을 대체하지 않는다. 또한 gyro bias=0에서는 MAP4 Heading 정확도가 26–31% 정도 악화해, 자율 보정 상태를 추가했을 때의 비용을 함께 보고해야 한다.

## 실험이 답하지 않는 것
- 실제 FFD LoS/Full multipath, R0 오차 분포, RF negative tail, s/r 상관 및 간섭에 관한 진실.
- R3 solver의 전역수렴 증명, 다봉/위치 주변화, independent RF scenes.
- 현행 R0 gate의 큰 DR error 상황에서 RF를 무조건 버리는 문제.
- matched synthetic `MAP4 < MAP3` 결과만으로 실제 RF P6 채택/과학 PASS 주장 불가.

**최종 P2 상태:** `P2_FULL_COMPLETED_SYNTHETIC`, 600/600 complete, 미해결 수치 사례 0, 사전등록 bias+.05 가설 지지. 별도 `scientific_PASS=false`는 실제 RF 독립 검증이 완료되지 않았다는 사실을 의미한다.
