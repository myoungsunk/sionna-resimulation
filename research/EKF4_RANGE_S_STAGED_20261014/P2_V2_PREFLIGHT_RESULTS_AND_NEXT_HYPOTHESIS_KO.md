# V2 자동 사전감사 → P2 대표실행 결과, 미수렴 원인 분해 (2026-10-14)

## 최종 결정
**P0 16/16, P1 8/8, R1 5/5, R2 10/10 PASS.** 실행 전에 정적 사전감사가 `GO`를 승인했다. 반면 대표 P2 **6조건×4모델=24 모델 실험 중 20 VALID, 4 CASE_RESULT_INVALID_NUMERICAL, 완전한 네 모델 쌍은 3/6**이므로 비용이 큰 원본 600-trial 전체 실행은 진행하지 않았다. 주 과학 가설(gyrobias에 대한 MAP4-MAP3 효과)은 **NOT_EVALUATED**. `scientific_PASS=false`, P3–P6 NOT_RUN.

실행 소스 `99be5e38f8b68d2ed441b75222d8ff599db40a52`.
- [GitHub Actions Run 38526390416](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38526390416)
- [125-entry 원시 ZIP artifact 11875912063](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38526390416/artifacts/11875912063), ZIP SHA256 `d25e96077a6b487fd0d90591362e141ee3908457808edf8688a7d3a480bad26b`. 다운로드 SHA256 일치·ZIP CRC PASS.
- PRE_RUN_AUDIT.json에는 `decision=GO`/fatal=[] 기록, 각 validator에 동일 Git SHA·source SHA receipt 적용.
- 이전 사전감사 HOLD [run 38526067163](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38526067163)과 [run 38526261348](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38526261348)는 삭제·소급 PASS하지 않음. 최초는 잘못 적은 `synthetic.py` SHA/메타데이터 접근, 두 번째는 누락된 선택적 로그 출력 접근. 모델/실험 전에 HOLD했으며 감사지원 코드만 수정 후 새 run에서 통과.

## 1. 개정된 51항목 계약의 상태
[51개 항목 코드별 대응](P2_V2_CHANGE_RECONCILIATION.json): 원 상태 유지 26, V2 변경 대상으로 등록 16, 해당 미래 단계까지 개별 보류 9.
**실행 가능한 V2 P2 범위에 반영**: 원 P2 spec/synthetic.py·R/Q/seed 동결, 선택적 진단 로그 강제 제거, 검사와 과학 주장 게이트 분리, 모델별 실패 격리, 실행 전 source/코드 AST/참값 경로 audit, matched trial·입력·모델 성능/분모 보존, 사전 대표 6조건 gate.
**미구현/미검증**: 기존 전체 FFD/LUT pipeline의 audit gate, P3–P6 기능 자체, 기준분포 G3 적분, 실제 RF 성능, 모든 numerical optimizer 입력의 수렴 증명, 외부 독립 peer review. 51개 항목을 모두 '수정 완료'라고 주장하지 않는다.

## 2. 대표 조건 결과
| 경로 | 실제 bias deg/s | EKF3 | EKF4 | MAP3 | MAP4 | 완전 paired |
|---|---:|---|---|---|---|---|
| straight | 0 | VALID | VALID | VALID | VALID | YES |
| straight | +0.05 | VALID | VALID | INVALID | INVALID | NO |
| turn | 0 | VALID | VALID | VALID | VALID | YES |
| turn | +0.05 | VALID | VALID | INVALID | VALID | NO |
| return | 0 | VALID | VALID | VALID | VALID | YES |
| return | +0.05 | VALID | VALID | INVALID | VALID | NO |

대표 1 trial/조건은 성능 검증 집합이 아니다. 6개 조건·총 24개 모델 실행 중 실패율 4/24는 단지 **이번 작은 개발용 사전검사의 기술적 실패 비율**이지, 더 큰 표본의 통계적 실패 확률이나 gyro bias의 실제 성능 영향에 대한 결론이 아니다.

| 실패 조건 | 모델 | 중단 시각 | 단계 index | 기울기 infinity norm | 결과 |
|---|---|---:|---:|---:|---|
| straight / bias +0.05 | MAP3 | 28.0 s | 55 | 1.2963290885e-8 | LINE_SEARCH_FAILED |
| straight / bias +0.05 | MAP4 | 30.5 s | 60 | 1.7766059263e-8 | LINE_SEARCH_FAILED |
| turn / bias +0.05 | MAP3 | 32.0 s | 63 | 1.2214333364e-8 | LINE_SEARCH_FAILED |
| return / bias +0.05 | MAP3 | 32.0 s | 63 | 1.6660962249e-8 | LINE_SEARCH_FAILED |

동결 gradient 목표 1e-8, max 80 반복 등은 변경하지 않았다. 실패 모델에 추정 출력 fallback/가짜 RMSE를 채우지 않았으며 다음 알고리즘 결과는 독립적으로 저장했다.

## 3. 예상과 달랐던 상황을 코드·trace와 비교
가정: R2에서 `LINE_SEARCH_FAILED`된 두 고정 입력이 수렴하고, 이 솔버가 대표 재귀 갱신에도 안정적일 것이다.
관찰: 해당 두 입력은 R1/R2 회귀를 통과했으나, bias가 있는 조건에서 위 네 건이 다시 `LINE_SEARCH_FAILED`로 나타났다. 실패하는 경우들은 모두 10^-8 규모에서 기울기가 정체되고 `ARMIJO_DIRECT`에서 매우 작은 fraction까지 감쇠했다.

관찰된 극단적인 fraction 예: MAP3 `2^-24 = 5.960464477539063e-8`, MAP4 `2.384185791015625e-7`. MAP4 straight/bias+.05 마지막 단계의 **double로 표시된 목적함수는 일부 반복에서 증가**했지만, `ARMIJO_DIRECT`로 accept된 step 기록이 존재한다. 이는 실제 수치 로그의 동작 사실이다.

관련 구현 `core.map_update`:
```python
roundoff = 4*np.finfo(float).eps*max(1., abs(cost))
if np.isfinite(new_cost) and new_cost <= cost + 1e-4*t*directional + roundoff:
    y = candidate
    history[-1]['step_acceptance'] = 'ARMIJO_DIRECT'
    accepted = True
    break
# 비용 비교가 위 조건을 FAIL할 때만 integrated_descent(evaluate, ...)로 이동
```

**구현상의 의미:** `roundoff` 항 때문에 비용이 검증되게 감소하지 않은 아주 작은 step도 `ARMIJO_DIRECT`로 수용될 수 있고, 적분 기반 `integrated_descent` 분기는 호출되지 않는다. 따라서 기울기 감소가 유효하지 않은 미세 step이 누적되어 정체되는 메커니즘이 **높은 우선순위의 원인 후보**다. **MAP4의 비용 증가가 존재했다는 것은 직접 관찰되었으나, 네 실패 모두에 대해 고정밀 GN step을 검증한 것은 아니므로 유일 원인이라고 확정하지 않는다.**

이는 P2의 과학 가설 `bias-aware MAP4 improves heading accuracy`를 직접 반박하지 않는다. 모든 +0.05deg/s 조건에서 MAP3의 완전 결과가 없어 paired RMSE 비교가 불가능하다.

## 4. 다음 방향 제안 — 승인 전 미실행

**진단 D3(필수 사전감사 후)**: 저장된 네 실패의 `FAILED_STEP.npz`와 `FAILURE.json`을 소스 SHA에 연결해 읽기 전용으로 확보하고, 마지막 후보의 목적함수/수렴 gradient/double vs 독립 고정밀 ΔJ, direct acceptance vs integrated acceptance 차이, 이전 4.5/6.0 사례와 변화를 비교. 하드 스톱이 아니라 **원인 확인을 위한 국소 진단**이다.

진단이 지지되면 **가설적 solver R3(별도 수정 계획·감사)**:
1. 직접 Armijo는 실제 비용 감소가 수치적으로 확인되는 경우에만 사용.
2. 비용 차가 machine-roundoff 범위에서 불분명할 때는 적분 기반 감소 검사를 **직접 acceptance보다 앞서** 실행하여 유효한 감소가 있는지 확인.
3. 둘 다 신뢰할 수 없으면 `NUMERICALLY_STALLED`와 gradient·원시 step 근거를 반환; 조용한 fallback이나 이득 과장 금지.
4. 원 목적함수, bias 모델, Q/R, 1e-8, 80 iteration, seed, P2 원본을 그대로 두고 4개 실패의 관련 회귀 → 6조건 대표 → 원본 전체 P2 순서.
5. 새 과학 가설이 예상과 어긋나면 해당 가설에 한하여 사용자 방향 확인 후 진행. 이 문서는 새 solver 채택이나 P2 전체 실행을 승인하지 않는다.

## 5. 감사 범위
GitHub cloud에서 실제 수학 코드와 preflight를 실행했고, 다운로드한 ZIP의 SHA/CRC를 읽기 전용 확인했다. 현재 문서는 그 파일의 실패 로그와 원래 core 소스의 정적 검토를 바탕으로 작성했다. 로컬에서 모델·solver를 새로 실행하지 않았으며, 추가 실험이나 임계값 조정 없이 종료한다. 51개 원본 사전감사와 이전 R2 실패 기록도 유지한다.

**현재 결론: P2=DEVELOPMENT_PREFLIGHT_INCOMPLETE; 원본 600 trial=NOT_RUN; scientific_PASS=false. D3/R3은 사용자 확인 전 실행하지 않는다.**
