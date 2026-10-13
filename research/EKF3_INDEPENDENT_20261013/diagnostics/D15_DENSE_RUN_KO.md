# D15 세밀한 단일 tap LoS 검증

코드는 추가 전용이다. 기준 포트는 원본 FP 시점의 우세 포트, 시작점은 기존 co-reference FP, local bracket은 직전 tap~해당 tap, 16N 보간 및 30% crossing을 사용한다. 양 RX는 동일 시점에서 평가한다. 실제 다중패킷 결합이 아니다.

## 실행

```powershell
$D='research/EKF3_INDEPENDENT_20261013/diagnostics'
python -m pytest -q "$D/test_d15_dense.py"
python "$D/d15_dense_observations.py" --out artifacts/D15_OBS
python "$D/d15_dense_los_validation.py" --d11 artifacts/D15_OBS --p2-dir PATH_TO_P2_OUT --out artifacts/D15_P2 --baseline-only
# 아래 모델 검증은 실제 FFD bank 2개와 BANK_MANIFEST.json이 있어야 함
python "$D/d15_dense_los_validation.py" --d11 artifacts/D15_OBS --p2-dir PATH_TO_P2_OUT --out artifacts/D15_SMOKE --cases R2_aA_m0 --stride 20 --max-eval-per-case 10
python "$D/d15_dense_los_validation.py" --d11 artifacts/D15_OBS --p2-dir PATH_TO_P2_OUT --out artifacts/D15_FULL
```

bank 위치와 SHA 계약은 기존 d12_los_window_model.py와 같다. LoS H는 추정 x,y,heading에서 합성하고 같은 DENSE_SINGLE 추출기를 적용한다. Truth는 scoring에만 사용한다. heading finite difference .0005rad 및 절반 step, 기존 7개 gate/1e-8 P2 parity는 유지한다. 모든7조건 stride1 비절단만 gate판정 대상이다. --baseline-only는 후보 gate를 만들지 않는다. 원본 D14 runner는 adaptive용이므로 DENSE_SINGLE에 그대로 연결하지 않는다. 후보 gate PASS 후에만 해당 후보용 융합 연결/검증을 수행해야 한다.

## 현재 결과

단위 테스트 28 PASS(기존EKF3 26+신규2), P0 39자산 검사PASS, 전체 DENSE_SINGLE RMS 0.1475826782 재현. 기존 P2 7조건×LoS/Full×A/C 24804개 state/cov/status 비교PASS. 실제 FFD bank 파일이 없으므로 LoS 모델/Heading 민감도/gate는 NOT_RUN, 재귀 EKF는 NOT_RUN, scientific_PASS=false.

Git LFS 확보가 지연되어 취소했고, 같은 파일을 별도 폴더에 내려받는 대안은 자동 승인 검토가 blocked by policy로 거절했다. 파일을 대체하거나 해시/허용치를 완화하지 않았다. 입력 확보 후 smoke부터 재개한다.

D11 형식 출력의 window_width_taps는 coarse-grid 단위이다. DENSE_SINGLE의 .25는 fine-grid 한 샘플 폭 표기이며 네 tap 적분을 의미하지 않는다. cross-rise 부가 열은 원래 adaptive extractor의 진단값으로, dense 후보의 종료 규칙이 아니다.
