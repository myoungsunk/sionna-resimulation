# 편파 헤딩 연구: 접근 → 계산 → 분석

2026-11-07 통합 기록. 원래 로컬 실험은 Git checkout에서 실행되지 않았다. 이 브랜치는 **이미 실행된 증거를 보존하는 패키징 커밋**이며, 과거 실행을 이 커밋에서 수행했다고 주장하지 않는다.

## 현재 결론

v3의 격자 수렴은 통과했다. 그러나 다중경로에서 S4보다 헤딩 RMSE가 크고 95% 구간 포함률이 부족하다. **과신 해결 및 모델 채택은 보류**다. 모든 검증은 자기검사이며 독립 감사가 아니다.

현재 모델은 `편파비 s의 가변 관측분산을 사용하는 원형 헤딩 혼합 추정기`다. 헤딩 각도 후보를 추정하지만 직접적인 각도 관측 zψ와 그 분산 Rψ를 사용하는 모델은 아니다. s-domain 분산 후보를 주변화하여 헤딩 불확실성을 얻는다. 시간상관과 지속적인 각도 편향은 이 모델에 별도 상태로 들어가 있지 않다.

## 접근의 순서와 증거

|단계|접근·계산|검증·분석 결과|원본 보고서|
|---|---|---|---|
|S4|원본 DR + 편파 + 자이로 바이어스 EKF|비교 기준. 상태·공분산·수용 mask 재현 확인|inputs/original_run/|
|FGO|고정창 그래프, 기본/iid/AR(1) 상관 오차 모델; 전체 관측 및 S4 matched gate 대조|다중경로 성능 악화. 모델·게이트·국소 최적화의 영향을 구분한 진단. 일반화 및 채택 불가|[FGO 보고서](experiments/POL_FGO_CORR_20261106_v1/REPORT_KO.md), [진단](experiments/POL_FGO_CORR_20261106_v1/diagnosis_20261106/)|
|Heading v1|원형 각도 격자 + 조건부 위치·bias + 가변 s 분산 IMM|단일 조건 grid check 통과였으나 45도 모드 병합과 주기별 조건부 계산 결함 발견|[v1](experiments/POL_HEADING_VAR_20261106_v1/REPORT_KO.md)|
|Heading v2|모드 ID 보존, 각 2π winding의 조건부 분포를 각각 계산|결함 회귀 통과. 일부 다중경로 RMSE 개선, 그러나 grid 수렴 FAIL. 개선 수치를 안정된 성능으로 채택하지 않음|[v2](experiments/POL_HEADING_VAR_20261106_v2/REPORT_KO.md)|
|Heading v3|검출만 1도 Gaussian 평활화, prominence 1%, subcell 봉우리, 온도 1도 연속 분할|전체8조건 간격/시작점 및 B0 추가 정밀화 17개 비교 PASS. 헤딩 정확도·과신 문제는 남음|[v3](experiments/POL_HEADING_VAR_20261106_v3/REPORT_KO.md)|

v3는 실제 관측 likelihood를 평활화하지 않는다. 검출 해상도 변경은 근접/얕은 모드를 하나로 표현할 수 있다. Full B0의 복수 모드 검출 시점은 v2 196개에서 v3 0개로 바뀌었다. 이를 물리적인 각도 모호성 해소로 해석하면 안 된다.

## 비교 조건과 지표

- 기존 R2 Loop, Anchor B, mount0, seed0. LOS/Full × gyro bias 0/0.01/0.05/0.2 deg/s.
- 979시점 처리, t>=30의 829시점 평가. 알려진 초기 헤딩 표준편차 5도.
- matched 비교는 원래 인과적인 S4 수용 mask를 공유한다. 독립적인 새 gate의 성능이 아니다.
- 헤딩 RMSE는 wrap된 각도 오차, XY RMSE는 sqrt(mean(dx²+dy²)).
- 헤딩 RMS σ=sqrt(mean(Pψψ)), XY RMS σ=sqrt(mean(Pxx+Pyy)). pose 포함률은 x,y,ψ 3자유도 영역이며 XY 단독 포함률이 아니다.
- FGO 오차 파라미터 식별에는 t<30의 참값 기반 잔차를 사용했다. 온라인 추정에서 참값을 관측으로 쓰지는 않는다. 단일 경로/seed이며 독립 RF 환경 검증이 아니다.
- [최종 S4/v2/v3 비교 CSV](experiments/POL_HEADING_VAR_20261106_v3/COMPARISON.csv), [수렴 결과](experiments/POL_HEADING_VAR_20261106_v3/CONVERGENCE.json).

수렴 최대 변화: 헤딩 RMSE 0.00374869도(허용0.02), XY RMSE 0.00122692m(허용0.005), 헤딩 RMS σ 0.209834%, XY RMS σ 0.664174%(각 허용2%). Full v3 헤딩 95% 포함률은 70.2~73.3%다.

## 보존과 재현

`experiments/`에는 코드, 계약, 원본 결과 NPZ, 지표 CSV, 검사 및 실행 기록을 바이트 단위로 보존했다. `inputs/original_run/`에는 원본 입력과 S4 replay 결과 및 원본 실행 패키지를 포함했다. `SOURCE_MANIFEST.json`은 원래 위치와 패키지 경로, SHA256을 연결한다. __pycache__와 pyc만 제외했다. 기존 로컬 파일을 이동/삭제/수정하지 않았다.

과거 manifest와 스크립트에는 당시 절대 경로가 그대로 남아 있다. 이 경로를 증거에서 수정하지 않고 `portable.py`가 이사된 입력 경로와 해시 조회를 연결한다. 새 실행은 반드시 별도 출력 폴더를 사용한다.

```powershell
python -X utf8 portable.py verify
python -X utf8 portable.py tests --output local_runs/math_checks
python -X utf8 portable.py replay-v3 --output local_runs/replay_v3
```

Python 3.13.15, NumPy 2.2.4, SciPy 1.15.2로 원 실행했다. 의존성은 requirements.txt에 고정했다. replay-v3는 33개 실행 결과를 생성하므로 몇 분 걸린다. 이미 생성된 결과 검증만 필요하면 verify를 사용한다. 테스트 명령은 LUT/선형 Gaussian/대칭 모호성 및 topology 검사를 실행한다. 원래 v2 주기별 회귀 증거는 REGRESSION.json에 보존되어 있다.

기존 v2 replay는 모든 40결과 저장 후 UTF-8 manifest를 cp949로 읽다가 exit1로 종료했다. 별도 finalize/validate가 입력 해시와 결과를 재검증하여 복구했다. 이 실패 이력은 삭제하지 않았다. v3는 exit0이다.

패키징 검사는 PACKAGING_VALIDATION.json 참조. 원래 실험의 채택 기준과 실패 판정을 바꾸지 않았으며, 푸시는 채택/논문 주장 승인이 아니다.
