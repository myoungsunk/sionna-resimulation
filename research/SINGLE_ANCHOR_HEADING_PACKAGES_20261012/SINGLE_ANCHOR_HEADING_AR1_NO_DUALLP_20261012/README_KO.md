# Single Anchor Heading & Temporal Ranging Study (No Dual-LP)

현재 GitHub 복도 환경(20×2.4×2.7m, 앵커 (4,0,2.65)m, 태그 z=0.45m)의 **합성** range-only + relative DR + EKF 시뮬레이션.

- `REPORT_KO.md`: 수식부터 실험 결과, 표, 검증 한계까지 포함한 한국어 연구 보고서
- `study.py`: 1,000회 paired Monte Carlo, Heading prior/gyro drift, Gaussian white vs AR(1) colored ranging, 알려진 AR(1) 모델을 사용하는 4-state EKF 대조 실험, 앵커의 횡방향 offset 비교
- `base_corridor_ekf.py`: 앞선 GitHub 복도 실험의 **변경 없는** range-only 3-state EKF 구현 사본
- `all_scenarios.csv`: 각 시나리오별 x/y/2D RMSE, NIS, NEES, coverage, ACF, 경계 이탈률
- `ranging_temporal_correlation.csv`, `ar1_aware_vs_unaware.csv`: **시간 상관관계 실험** 별도 상세 테이블
- `PAIRED_BOOTSTRAP.json`: 전체 주행을 독립 표본 단위로 2,000번 부트스트랩한 차이와 95% CI
- `MANIFEST.json`: GitHub 참조, 전체 설정, 시드, 코드 SHA256, 조건 레지스트리
- `QA_REPORT.json`, `QA_REPORT_KO.md`: 실제 실행한 검사와 수행하지 않은 검증 구분

```bash
python3 -m pip install -r requirements.txt
python3 study.py --runs 1000 --seed 20261012
python3 qa_checks.py
```

**금지된 해석:** RF 다중경로의 실제 시뮬레이션 결과 아님, Dual-LP orientation 아님, Sionna RT 아님, 벽 충돌 검증 아님. GitHub 기본 치수는 원본 코드가 placeholder라고 명시함.
