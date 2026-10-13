"""Read-only result checks and Korean report for completed R1 V2 runs."""
from pathlib import Path
import json,hashlib,datetime
import numpy as np
H=Path(__file__).resolve().parent;O=H/'out/i2_r1_cdf_tail_v2_cached_01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 receipt=json.loads((O/'EXECUTION_RECEIPT.json').read_text());assert receipt['exit_code']==0
 assert receipt['original_inputs_unchanged'] and receipt['code_inputs_unchanged']
 assert all(sha(H/n)==v for n,v in receipt['input_sha256'].items())
 assert all(sha(O/n)==v for n,v in receipt['output_sha256'].items())
 gate=json.loads((O/'R1_V2_GATE.json').read_text());rows=[];details=[]
 for c in gate['cases']:
  cell=c['cell'];a,b=c['comparisons'];r=json.loads((O/f'{cell}_2_CDF.json').read_text())
  rows.append(f"| {cell.split('_')[4]} | {a['quantile_change_sd']:.4g} | {b['quantile_change_sd']:.4g} | {c['tail_upper']:.4g} | {'PASS' if c['passed'] else 'INCONCLUSIVE'} |")
  details.append(dict(cell=cell,normalization_relative_error_estimate=r['normalization_relative_error_estimate'],max_cdf_error_estimate=float(np.max(r['quantile_cdf_error_estimates'])),warnings=r['integration_warnings'],quantiles=r['marginal_quantiles']))
 text='''# R1 CDF·posterior 꼬리 보완 V2 결과

실행 범위는 R1 재검증이다. 기존 R1 V1의 실패 결과와 I2 결과를 보존했다. 단일 Range/PF/Batch 참조 승인, I3/I7은 수행하지 않았다.

## 변경과 실행

CDF는 bg의 좁은 조건부 Gaussian 전이부를 나눈 적응 적분으로 계산한다. SF/eps CDF도 적분 상한을 직접 바꾸므로 marginal PCHIP 보간을 사용하지 않는다. posterior 꼬리는 수치 evidence가 아닌 interval 하한으로 분모를 제한한다. 수식은 `I2_R1_V2_MATH_KO.md`, 실행 전 계약은 `I2_R1_CDF_TAIL_V2_DESIGN.json`이다.

기존 Gaussian R2/R4 d2 seed8000 DR 센서 입력을 그대로 사용했다. 각 셀에 대해 ±32/1e-6, ±32/1e-8, ±40/1e-8의 세 설정을 비교했다. 과학적 기준을 사후 변경하지 않았다. 초기 구현 단위시험7개 PASS, 캐시 동등성·꼬리 검사4개 PASS이다.

첫 R2 설정은 419.55초에 완료했다. 반복 함수 평가 비용이 커서 진행 중이던 R2 엄격 설정을 관리자로 종료한 뒤, 별도 bounded-cache 구현으로 재개했다. 캐시는 동일 함수 입력의 결과를 저장하며 목표 분포·허용오차를 변경하지 않는다. 예제에서 normalization·median·오차추정·적분기록이 정확히 일치했다. 첫 완료 결과는 해시가 기록된 채 재사용했고 중단 실행도 보존했다. `I2_R1_V2_CACHE_AMENDMENT.json`은 첫 결과 확인 후 작성한 계산 구현 변경 기록이며 사전등록으로 부르지 않는다.

## 실제 검증 결과

bg는 전체 실수축에서 해석적으로 적분하며, 꼬리 상한은 표준화 SF/eps의 [-40,40]² 밖 질량에 해당한다. 분위수 비교 단위는 기존 안정된 posterior SD이다. 0은 표시 정밀도 내 0을 뜻한다.

| 경로 | tolerance 강화 분위수 최대 변화/SD | 영역 확대 분위수 최대 변화/SD | 표준화 SF/eps ±40 밖 posterior 질량 상한 | R1 수치 판정 |
|---|---:|---:|---:|---|
'''+ '\n'.join(rows)+f"\n\nR1 결과: **{gate['R1']}**. 허용 기준은 분위수 변화≤0.01 SD, 정규화 상대 변화≤1e-6, posterior 꼬리 상한≤1e-6이다. 정규화 비교와 CDF 오차 추정 상세는 `out/i2_r1_cdf_tail_v2_cached_01/R1_V2_GATE.json` 및 각 CDF JSON에 있다.\n"
 text+='''
R2의 ±32 영역 tail 상한은 1로 정보가 없었다. 사전 동결한 최종 ±40 영역에서 tail 기준을 통과했으며, 모든 시험 영역에서 tail 기준을 통과했다는 뜻은 아니다.

## 판정 경계

R1이 PASS인 경우에도 승인 범위는 **시험한 두 DR 조건의 conditional measured-input 모델에서 marginal CDF/quantile·영역 밖 질량에 대한 수치 참조 검증**이다. 실제 물리적 생성모델과의 일치, Range의 결합 초기화/잠재 궤적/kernel, PF·Batch 수렴을 승인하지 않는다. I2 전체 참조 추정기는 계속 REFERENCE_NOT_VALIDATED이다.

QUADPACK 오차는 추정치이고, 전이 root scan은 접하는 root나 한 scan 구간 내 복수 교차를 놓칠 수 있다. refinement/domain 비교와 해석 예제 시험이 전역 CDF 오차의 형식적 증명이 되지는 않는다. 꼬리 상한은 명시한 모델의 부등식과 50자리 interval 계산으로 평가했으며 사용 라이브러리 전체의 형식 검증을 수행했다는 뜻은 아니다. 운용 요구 정밀도는 여전히 미정이다.

## 증거와 보존

- `out/i2_r1_cdf_tail_v2_01/`: 초기 실행·완료된 R2 loose 결과·취소 영수증.
- `out/i2_r1_cdf_tail_v2_cached_01/`: 재개 결과 6개 설정, tail 계산, 게이트, TESTS.log, EXECUTION_RECEIPT.json.
- 코드: `repair_r1_cdf_v2.py`, `repair_r1_cdf_v2_cached.py`, `repair_r1_tail_v2.py`; 실행기·테스트 및 동결 계약도 함께 보존.
- 기존 감사 입력 26개와 새 실행 코드/입력의 SHA 불변을 확인했다. 기존 실험 파일의 이동·삭제·덮어쓰기는 없다.

R1 이후의 짧은 Range 독립 적분·커널 검증은 별도 단계로 남긴다. 이번 요청에서는 실행하지 않는다.
'''
 (H/'I2_R1_CDF_TAIL_V2_RESULT_KO.md').write_text(text,encoding='utf-8')
 (O/'FINAL_VERIFICATION.json').write_text(json.dumps(dict(timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),hashes_pass=True,details=details,I2_reference='REFERENCE_NOT_VALIDATED',short_range='NOT_RUN',I3='NOT_RUN',I7='NOT_RUN'),indent=2)+'\n')
 print(gate['R1']);print(json.dumps(details,indent=2))
if __name__=='__main__':main()
