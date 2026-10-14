"""Independent final output audit. No new scientific model or estimator execution.

This is the ONLY workflow finalizer. stages.py's convenience final branch is
not authorized for execution. Missing evidence never becomes a vacuous PASS.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OUT=REPO/'outputs/g2g3_minimal'


def main():
    audit=json.loads((OUT/'PRE_RUN_final.json').read_text())
    if not audit['audited_code_matches_execution_sha'] or audit['run_decision']!='GO_WITH_CLAIM_LIMITATION':
        raise RuntimeError('HARD_EXECUTION_BLOCK: final audit authorization mismatch')
    for rel,sha in audit['source_sha256'].items():
        if hashlib.sha256((REPO/rel).read_bytes()).hexdigest()!=sha:
            raise RuntimeError('HARD_EXECUTION_BLOCK: changed source before final audit')
    stages={};findings=[];checks=[]
    for name in ('math','controls','shadow','diagnosis'):
        file=OUT/(name+'.json')
        if not file.exists():
            stages[name]=dict(execution='NOT_COMPLETED',calculation='NOT_EVALUATED',hypothesis='NOT_EVALUATED',scientific_claim='NOT_EVALUATED')
            findings.append(dict(severity='CASE_RESULT_INVALID',scope=name,reason='stage receipt absent'))
        else:stages[name]=json.loads(file.read_text())
    p=OUT/'shadow_predictions.csv.gz'
    replay_ok=False;false_count=None
    if p.exists():
        pred=pd.read_csv(p)
        raw=pd.read_csv(REPO/'inputs/range_audit/DR_RF_PAIRED_TRACE.csv.gz')
        keys=['case','channel','correction','condition','level','seed','sample']
        if pred.duplicated(keys).any() or raw.duplicated(keys).any():
            raise RuntimeError('CASE_RESULT_INVALID: duplicate comparison keys')
        df=pred.merge(raw[keys+['r_true_m','delta_dr_minus_rf_m','nis','r_DR_m','z_rf_m']],
                      on=keys,how='outer',validate='one_to_one',suffixes=('_out','_raw'),indicator=True)
        alignment=bool((df['_merge']=='both').all())
        checks.append(dict(check='all_original_keys_preserved',pass_check=alignment,n=len(df)))
        if alignment:
            true=df['r_true_m'].to_numpy()
            dr2=(df['r_DR_m_raw'].to_numpy()-true)**2
            rf2=(df['z_rf_m_raw'].to_numpy()-true)**2
            wins=rf2<dr2
            same=bool(np.array_equal(wins,df['rf_is_better_for_scoring'].to_numpy(bool)))
            checks.append(dict(check='independent_squared_error_win_labels',pass_check=same))
            eligibility=(df['delta_dr_minus_rf_m'].to_numpy()>0)&(df['nis'].to_numpy()>6.6348966010212145)
            priority=eligibility&(df['p_dr_fault_rf_inlier'].to_numpy()>=.95)
            same_priority=bool(np.array_equal(priority,df['would_prioritize_rf'].to_numpy(bool)))
            checks.append(dict(check='independent_priority_decision_mask',pass_check=same_priority))
            false_count=int((priority&~wins).sum())
            checks.append(dict(check='false_priority_count',pass_check=false_count==stages['shadow'].get('false_priority_count'),count=false_count))
            selected_count=int(priority.sum())
            checks.append(dict(check='selected_count',pass_check=selected_count==stages['shadow'].get('selected_count'),count=selected_count))
            replay_ok=bool(checks and all(x['pass_check'] for x in checks))
            if false_count:
                findings.append(dict(severity='CLAIM_BLOCK',scope='zero wrong-source preference',count=false_count,
                                     reason='The fixed exploratory model sometimes prioritizes the less accurate RF. This is not a source arithmetic error.'))
    else:
        findings.append(dict(severity='CASE_RESULT_INVALID',scope='shadow output verification',reason='raw predictions missing; no PASS asserted'))
    contradictions=[x['id'] for x in stages['controls'].get('fixtures',[]) if x.get('hypothesis')=='CONTRADICTED']
    sensitivity=[]
    f=OUT/'prior_sensitivity.csv'
    if f.exists():
        sens=pd.read_csv(f)
        for name,g in sens.groupby('fixture'):
            sensitivity.append(dict(fixture=name,min_probability=float(g['p_fault_inlier'].min()),
                               max_probability=float(g['p_fault_inlier'].max()),
                               decision_varies=bool(g['rf_dominant'].nunique()>1),tested_models=len(g)))
    for c in contradictions:
        findings.append(dict(severity='CLAIM_BLOCK',scope=c,reason='predeclared RF dominance expectation not met'))
    verdicts={name:{key:v.get(key,'NOT_EVALUATED') for key in ('execution','calculation','hypothesis','scientific_claim')}
              for name,v in stages.items()}
    maths=stages['math']
    complete=all(v['execution']=='PASS' for v in verdicts.values())
    verified=replay_ok and maths.get('radial_pass',False) and maths.get('linear_pass',False)
    result=dict(
        execution='PASS_COMPLETED_REQUESTED_MINIMAL_CHAIN' if complete else 'PARTIAL_STAGE_COMPLETION',
        calculation='PASS_FOR_VERIFIED_SCOPES' if verified else 'PARTIAL_OR_INVALID_OUTPUT_SCOPE',
        hypothesis='PARTIAL_SUPPORT_WITH_IDENTIFIABILITY_LIMIT',
        scientific_claim='CLAIM_BLOCK_FULL_G2G3_AND_EXTERNAL_GENERALIZATION',
        scientific_PASS=False,stage_verdicts=verdicts,
        independent_output_checks=checks,findings=findings,
        prior_sensitivity=sensitivity,contradicted_controls=contradictions,
        model_inputs='mu_DR, sigma_DR, RF Range only; no true bias, no truth, no new CIR feature',
        parameters='synthetic engineering assumptions, not independently calibrated',
        exact_linear_G2_G3='verified in local linear Gaussian scope only' if maths.get('linear_pass') else 'NOT_VERIFIED',
        nonlinear_G3_restored=False,recursive_pose_execution=False,
        amended_scientific_model_executed=False,
        policy_source_commit='9beb061f354edef18e1f977f5d462d7e0d8b1f2e',
        next_action='No unapproved feature/model alteration. Report bounded diagnostics; seek direction confirmation before replacing the scientific hypothesis.',
        allowed_claims=['Exact algebra and scoped numerical parity where passed',
                        'Descriptive performance of this frozen scalar surrogate on archived data',
                        'Identical observable inputs cannot uniquely identify different underlying truth worlds'],
        disallowed_claims=['Calibrated 95% source probability','Full nonlinear G2/G3 validated','Generalized gyro/CIR fault detection'])
    if (OUT/'FINAL_CONFIRMATION.json').exists():raise FileExistsError('final receipt overwrite')
    (OUT/'FINAL_CONFIRMATION.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file()}
    (OUT/'OUTPUT_SHA256.json').write_text(json.dumps(hashes,indent=2))
    lines=['# G2/G3 감사 기반 최소 단계 최종 브리핑','',
           '범위: 반경 최소 혼합모델·선형 3-state 수식·합성 대조·보관 데이터 진단. 실제 비선형 G3/재귀 융합 결과가 아님.','',
           '|단계|실행|계산|가설|과학 주장|','|---|---|---|---|---|']
    for n,v in verdicts.items():lines.append('|'+n+'|'+'|'.join(v[k] for k in ('execution','calculation','hypothesis','scientific_claim'))+'|')
    lines+=['','합성 가설 불일치: '+str(contradictions),
            '보관 데이터의 잘못된 RF 우선 건수: '+str(false_count),
            '사전확률 민감도: '+str(sensitivity),
            '', '감사 원칙: 실제 수식·입력 결함은 관련 실행 차단; 진단 오류와 가설 미지지는 해당 주장/진단만 제한.',
            '원래 G3 적분 실패는 재분류하거나 삭제하지 않음.',
            '', '다음 방향 확인 전 새 관측 특성, 사전분포, 알고리즘으로 변경하지 않음.']
    (OUT/'BRIEFING_KO.md').write_text('\n'.join(lines)+'\n')
    print('FINAL_CONFIRMATION',json.dumps({k:result[k] for k in ('execution','calculation','hypothesis','scientific_claim','contradicted_controls','prior_sensitivity')},ensure_ascii=False))
    if not verified:raise SystemExit(2)


if __name__=='__main__':main()
