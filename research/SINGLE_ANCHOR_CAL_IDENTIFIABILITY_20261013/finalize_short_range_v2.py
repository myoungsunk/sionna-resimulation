"""Post-run evidence verification; does not modify frozen experiment outputs."""
from pathlib import Path
import hashlib, json, datetime
import numpy as np

H = Path(__file__).resolve().parent
O = H / 'out/i2_short_range_kernel_v2_01'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    old = json.loads((H/'out/i2_short_range_kernel_01/PACKAGE_SHA256.json').read_text())
    for name, digest in old['files'].items():
        assert sha(H/name) == digest, name
    receipt = json.loads((O/'EXECUTION_RECEIPT.json').read_text())
    assert receipt['exit_code'] == 0 and receipt['inputs_unchanged'] and receipt['legacy_outputs_unchanged']
    for name, digest in receipt['input_sha256'].items():
        assert sha(H/name) == digest, name
    for name, digest in receipt['output_sha256'].items():
        assert sha(O/name) == digest, name
    rows = []
    for case in ['SYNTHETIC', 'R2', 'R4', 'SEPARATED_TOY']:
        r = json.loads((O/f'{case}_RESULT.json').read_text())
        a = r['pf_statistics']; b = r['batch_statistics']
        qa = np.array([s['quantiles'] for s in a]); qb = np.array([s['quantiles'] for s in b])
        sd = np.sqrt((np.mean([np.square(s['sd']) for s in a],0)+np.mean([np.square(s['sd']) for s in b],0))/2)
        raw = abs(qa.mean(0)-qb.mean(0))/sd[:,None]
        var = np.maximum(qb.var(0,ddof=1)/len(b),np.sum(np.square([s['mcse']['quantiles'] for s in b]),0)/len(b)**2)
        margin = 1.96*np.sqrt(qa.var(0,ddof=1)/len(a)+var)/sd[:,None]
        upper = np.array(r['comparison']['PF_vs_BATCH']['quantile_upper_sd'])
        assert np.allclose(raw+margin, upper)
        j,k = np.unravel_index(np.argmax(upper),upper.shape)
        rows.append(dict(case=case,gate=r['gate'],quantile_raw=float(raw[j,k]),quantile_mc_margin=float(margin[j,k]),quantile_upper=float(upper[j,k]),cdf=r['simultaneous']['PF_vs_BATCH'],modes=r['mode_comparison'],basin_count=len(r['basin_definition']['edges']),branch_crossings_min=min(r['branch_crossings']),mean_mcse=r['normalized_batch_mean_mcse'],quantile_mcse=r['normalized_batch_quantile_mcse'],failed=r['failed_or_missing']))
    summary = dict(timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),old_package_verified=len(old['files']),input_hashes_verified=len(receipt['input_sha256']),output_hashes_verified=len(receipt['output_sha256']),elapsed_seconds=receipt['elapsed_seconds'],cases=rows,I2='REFERENCE_NOT_VALIDATED',I3='NOT_RUN')
    (H/'out/I2_SHORT_RANGE_V2_FINAL_CHECK.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    lines = ['# 짧은 Range V2 감사·재검증 결과', '', '기존 판정 기준을 유지하고 Monte Carlo 정밀도와 반사 모드 이동을 보완한 개발 검증이다. I3는 실행하지 않았다.', '', '## 원인 감사', '', 'V1의 분포 합의 미통과에는 실제 추정 차이와 큰 Monte Carlo 오차 상한이 함께 포함됐다. 미통과 자체로 서로 다른 posterior 또는 모드 갇힘을 확정할 수 없다. 795개 CDF·공동 영역 동시 비교에서 기존 held-out 반복 자유도 2의 보정계수는 126.089였으며, V2는 실제 독립 반복 수 증가에 따라 자유도 14, 보정계수 5.623을 사용한다. 신뢰수준·보정 방식·허용차는 유지했다. 직접 PF–Batch 비교는 양쪽 16회로 자유도 15를 사용한다. 표본 수 증가와 반사 이동을 함께 적용했으므로 개선 원인의 기여율은 분리하지 않는다.', '', '## 실행 및 범위', '', f"27개 테스트 통과 후 4조건을 실행했다. 종료 코드 0, 실행 시간 {receipt['elapsed_seconds']:.1f}초. 각 조건 QMC 2^17/2^19 × 16회, PF 80,000입자 × 16회, Batch 16체인 × 유지 32,000표본(체인별 burn-in 4,000)이다.", '', '기존 SYNTHETIC/R2/R4 첫 transition을 보존하고 별도의 SEPARATED_TOY를 추가했다. 반사 이동은 한 transition의 전체 목표 밀도를 보존하며 로그 반경 Jacobian과 실제 역 CDF 제안밀도 보정을 유지한다. 초기 Range는 한 번만 사용한다. Heading 투영 basin과 정확한 반사 branch만 검증하며 전체 7차원 미방문 모드의 부재는 주장하지 않는다.', '', '## PF–Batch 직접 합의', '', '| 조건 | 판정 | 최악 분위수: 실제 차이 + MC 여유 = 상한 (SD) | CDF 상한 | 공동 HPD 최대 상한 |', '|---|---|---|---|---|']
    for r in rows:
        lines.append(f"| {r['case']} | {r['gate']} | {r['quantile_raw']:.4f} + {r['quantile_mc_margin']:.4f} = {r['quantile_upper']:.4f} | {r['cdf']['cdf_upper']:.4f} | {max(r['cdf']['hpd_upper']):.4f} |")
    lines += ['', '분위수 허용 상한은 0.1 SD, CDF·공동 영역 질량 허용 상한은 0.05다. 위 표는 직접 PF–Batch 비교이며 각 조건의 최종 판정은 독립 적분 기준·수렴·MCSE·모드 검증까지 모두 포함한다.', '']
    for r in rows:
        lines.append(f"- {r['case']}: 체인당 최소 반사 branch 전환 {r['branch_crossings_min']:,}회, 최대 평균/분위수 MCSE {r['mean_mcse']:.4f}/{r['quantile_mcse']:.4f} SD. 미통과: {', '.join(r['failed']) or '없음'}.")
    lines += ['', '## 증거 및 제한', '', f"기존 V1 패키지 {len(old['files'])}개 SHA256, 실행 입력 {len(receipt['input_sha256'])}개 및 출력 {len(receipt['output_sha256'])}개 SHA256을 재검증했다. 세부 판정은 out/i2_short_range_kernel_v2_01/SHORT_RANGE_V2_GATE.json, 실행·해시는 EXECUTION_RECEIPT.json, 원시 표본은 같은 폴더 NPZ에 보존한다. 최종 검사: out/I2_SHORT_RANGE_V2_FINAL_CHECK.json.", '', '한 transition, 유한 12σ 반경 영역, conditional measured-input 모델의 개발 검증에 한정된다. PF는 이 구간에서 importance cloud이며 장기 재표집에 따른 Calibration 입자 붕괴 해결을 증명하지 않는다. 반경 prior 민감도·전체 경로 posterior·실용적 요구 정밀도 판정으로 확장하지 않는다. 전체 I2 참조는 REFERENCE_NOT_VALIDATED, I3/I7은 NOT_RUN이다.']
    lines += ['', '## 분리 모드 조건의 잔여 실패 해석', '', 'SEPARATED_TOY의 두 Heading 봉우리는 약 ±1.6144 rad다. 격자 해상도 및 모드 질량 합의는 통과했고, 각 체인은 두 반사 branch 사이를 최소 15,857회 전환했다. 그러나 sin(Heading)의 중앙 분위수가 PF–Batch 최악 항목이었다. 실제 차이 0.13646 SD와 MC 여유 0.58024 SD를 합친 상한 0.71670 SD로 미통과다. 독립 적분 해상도 2^17/2^19 사이에서도 같은 중앙 분위수 상한이 0.48387 SD로 미통과했다.', '', 'QMC 2^19의 음의 Heading 질량은 반복별 0.499912–0.500081에 불과한 차이를 보이지만, sin(Heading) 중앙 분위수는 -0.54183–0.55135로 흔들렸다. 두 모드 사이의 낮은 밀도에서 중앙 분위수 추정이 작은 질량 변동에 민감하다는 해석을 지지한다. 이것을 잔여 실패의 유일한 원인으로 확정하지 않으며, Batch 평균·분위수 MCSE 및 CDF 미통과는 그대로 남긴다. read-only 근거는 out/I2_SHORT_RANGE_V2_MEDIAN_DIAGNOSTIC.json에 보존했다.', '', '후속 보완은 임계값을 변경하지 않고 중앙 분위수의 적분 오차와 체인 Monte Carlo 오차를 따로 제어하는 설계를 먼저 동결해야 한다. 이번 실행에서는 추가 표본 튜닝이나 후속 단계를 실행하지 않았다.']
    (H/'I2_SHORT_RANGE_V2_RESULT_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__ == '__main__':
    main()
