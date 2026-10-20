# T9 실행 연결

protocol 커밋 후 다음을 실행한다. 아직 이 준비 단계에서 RF 계산을 하지 않았다.

```powershell
python run_q_distance.py --source-root EXEC/source --execution-root EXEC --out OUT
```

복원 구조는 `EXEC/source`가 정확한 원래 CHAIN 소스 트리이고, 부모 `EXEC`에 `rf_frozen.zip`, `reference_ae/PACKETS_SOURCE_LABELS.csv.gz`, `OOF_PARAMETERS.csv.gz`, `traces/{case}_{B0|L2}.npz`, FFD bank가 있어야 한다. `KEY_B0_RESULTS.csv`는 기본 저장소 경로 또는 `--key-b0`로 전달한다. `ScalarPower`는 공통 루트 기존 helper를 변경 없이 재사용하며 내부 원래 fitter 일치가 1e-12를 넘으면 중단한다. 원래 Q 학습 결과와 캐시 mu/C 일치 및 기존 Full POWER1 재귀 RMSE/gate 재현도 필수다. SourceFFD 관측식은 B_OLD 고정이며 T6용 재학습 파라미터를 혼용하지 않는다.

SourceLabels의 train label와 training pose만 offline GT를 사용한다. 각 Full 학습 fold의 (case,pose_id)와 정확히 같은 NativeLoS train 행으로 기대 q 회귀를 학습한다. 온라인 `parameter_provider(i,x_prior,spec)`는 해당 시점 실제 RF q, 현재 prior와 고정 mount/anchor만 받는다. 미래·평가 pose·NativeLoS H를 입력하지 않는다. NativeLoS safety는 별도 관측 조건이며 Full 추론에 NativeLoS 자료를 합치지 않는다. Δq 기대 모델의 held-route NativeLoS RMSE는 진단으로 보고하고 이를 보고 모델을 조정하지 않는다.

3D 거리와 상대 방위 θ의 정의, 회귀 feature 및 모든 hyperparameter는 lock에 있다. q·Δq·거리 각 scalar에 같은 P1 Ridge/tertile mean·full covariance fitter를 적용한다. 채널별 μr만 바꾸거나 cross covariance를 없애는 추가 변형은 없다. R0 대조도 같은 동역학·gate를 사용한다.

산출물 `RESULTS.csv`: Full 7×2bias×4arm=56행 + NativeLoS 2×2bias×4arm=16행, 총72행의 모든11지표. `GAIN_COMPARISON.csv`: 양의 POWER 이득에만 회수율 계산, 비양수/미소 이득은 별도 표기. `ONLINE_FEATURES_<case>_<channel>_<bias>.csv`: prior·q·기대q·Δq·거리·θ·실제 μ/C. 파일을 분할하여 각각20MB 이하로 보존한다. `TRAIN_PARAMS.json`은 고정 train keys와 회귀/scalar 파라미터를 담는다. `CHECKS.csv`, `ERRORS.json`, `DECISION.json`, `MANIFEST.json`, `RESULTS_KO.md`를 함께 보존한다. 큰 NPZ는 Actions artifact만 두고 publisher가 artifact id/archive SHA를 MANIFEST에 채운다.

거리 가설 지지는 모든 양의 POWER 이득 cell에서 ≥80%를 요구하는 보수적 해석이다. pooled 비율은 설명용이다. Δq는 모든 Full cell에서 Q와 같거나 낫고 모든 LoS cell에서 양의 악화가 더 크지 않으며 한 LoS cell에서는 엄격히 줄어야 이후 채택 후보가 된다. 이 runner가 공통 모델을 자동 변경하지 않는다. 기대-q 근사 품질과 공유 장면의 한계를 보고한다.
