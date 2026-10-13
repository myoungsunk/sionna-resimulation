# M1 후속 실험 재현

수치 계약은 PLAN_KO.md에 고정했다. 기존 핵심 소스와 이전 실험 결과를 변경하지 않는 별도 runner이다. M2는 실행하지 않는다.

## 테스트와 합성 실험

저장소 루트에서 Python 3.10, NumPy, SciPy, pandas, pytest 및 기존 프로젝트 의존 환경을 사용한다.

```powershell
$followup = 'research/EKF3_INDEPENDENT_20261013/diagnostics/robust_fusion/followup'
python -m pytest -q "$followup/test_bias_synthetic.py" "$followup/test_rf_components.py"
python "$followup/bias_synthetic.py" --out artifacts/M1_FOLLOWUP_NEW/BIAS_SMOKE --smoke
python "$followup/bias_synthetic.py" --out artifacts/M1_FOLLOWUP_NEW/BIAS_FULL
```

기존 폴더가 있으면 중단한다. 합성 full은 직진·회전·왕복 × 실제 Bias 0/+0.05deg/s × (무잡음 1회+독립 잡음 100회) × M0/M1-A × D0/A/B/C = 4,848셀이다. 실제 RF 수신 성능으로 해석하지 않는다. 전체 trial의 지표를 저장하고, 자세한 trace는 각 시나리오의 무잡음 및 noisy trial0만 저장한다.

## 동결 RF 실험

결과 폴더 `results/M1_FOLLOWUP_20261013`의 `RESTORE_EVIDENCE.py`로 분할 archive를 연결하고 SHA 검증 후 새 디렉터리에 압축을 푼다. archive의 `inputs/M0`와 `inputs/STRUCTURE`는 이 실행에 사용한 캐시·기존 학습 모델이다. RF runner의 P0 입력 검사는 원본 저장소의 동결 데이터 및 LUT 접근도 요구한다.

```powershell
$rf = 'research/EKF3_INDEPENDENT_20261013/diagnostics/robust_fusion'
$evidence = 'artifacts/RESTORED_M1_FOLLOWUP'
python "$rf/followup/rf_components.py" --inputs "$evidence/inputs/M0" --structure "$evidence/inputs/STRUCTURE" --reference "$rf/results/NOISE_PAIR_ABLATION_20261013" --out artifacts/M1_FOLLOWUP_NEW/RF_SMOKE --smoke
python "$rf/followup/rf_components.py" --inputs "$evidence/inputs/M0" --structure "$evidence/inputs/STRUCTURE" --reference "$rf/results/NOISE_PAIR_ABLATION_20261013" --out artifacts/M1_FOLLOWUP_NEW/RF_FULL
python "$rf/followup/analyze_followup.py" --root artifacts/M1_FOLLOWUP_NEW
```

各 full は対応 smoke の成功を確認してから実行する。RF full は6モデル×252セル、M0/M1B_REPROは既存値に対する絶対許容値1e-8のparityが必須。失敗時に許容値を緩めない。分析は4つの smoke/full receiptと全 RF trace を検査し、合成 trace は保存された代表試行について検査する。

Windowsで長時間 helperを起動する際はワークスペースの managed-processes 契約に従う。この例は科学計算 runner の引数を示しており、無管理バックグラウンド起動を指示しない。

時点を独立実験として扱わず、合成はtrial、実RFは経路・seed単位で比較する。固定 true bias の含有率は条件付き評価である。単一RF sceneおよびE1の既存選択履歴・空間重複制限を維持し、scientific_PASS=falseとする。
