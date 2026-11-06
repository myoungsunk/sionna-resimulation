"""Posthoc six-case audit; no science stage execution or policy changes."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import sys,json,gzip,math,hashlib,subprocess,datetime
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(root/'src'),str(root/'scripts')]
import fp_sc_vab_shadow_stages as stages
from qclean_uwb.fp_sc.followup.bridge import RevisionEvidenceAdapter
from qclean_uwb.fp_sc.followup.numerics import cir_from_spectrum,raw_detection
from qclean_uwb.fp_sc.followup.contracts import Support,STEP_M
from qclean_uwb.fp_sc.followup.detection import binding_for
from qclean_uwb.fp_sc.followup.selection import prepare_candidate_set,decide_prepared_candidate_set
out=Path(__file__).parent
changes=json.loads((root/'research/FP_SC_S2_RUN_20261106/CHANGED_CASES.json').read_text())
results=[];hashes={}
adapter=RevisionEvidenceAdapter(arm='VAB',mode='TWO_PORT_UNION')
for cid in sorted({x['case_id'] for x in changes}):
    mf=root/f'research/FP_SC_S1_PREPARATION_20261106/FINAL_002/{cid}_S1_MANIFEST.json'
    manifest,policy=stages.inspect_manifest(mf)
    sources=[]
    for stage in ('S1','S2'):
        folder=root/f'research/FP_SC_{stage}_RUN_20261106/RESULTS/{cid}'
        path=folder/'ROWS.json.gz';receipt=json.loads((folder/'RUN_RECEIPT.json').read_text())
        assert stages.sha256(path)==receipt['result_sha256']
        hashes[str(path.relative_to(root))]=stages.sha256(path)
        sources.append(json.load(gzip.open(path,'rt')))
    s1,s2=sources
    with np.load(root/manifest['case']['online_npz']) as a: H=a['Hrf']
    with np.load(root/manifest['case']['evaluator_npz']) as a: clean=a['clean_H']
    for change in [x for x in changes if x['case_id']==cid]:
        k=change['k'];r=next(x for x in s1 if x['k']==k and x['mode']=='PM')
        ref=raw_detection(cir_from_spectrum(clean[k]))[0]
        assert ref==change['reference_tap']
        cir=cir_from_spectrum(H[k]);e=adapter.evidence(cir,manifest['case']['metadata']['noise_variance'])
        prepared=prepare_candidate_set(e,'PM',policy,binding=binding_for(e,policy),prior=Support(**r['p_interval']),motion=Support(**r['m_interval']))
        assert prepared.sha==r['candidate_set_sha256'] and e.pool_hash==r['decision']['pool_hash']
        decision=decide_prepared_candidate_set(e,'PM',policy,prepared)
        assert decision.selected_tap==r['hypothetical_selected_tap'] and decision.reason==r['decision']['reason']
        ranked=list(prepared.eligible);rank={x['tap']:i+1 for i,x in enumerate(ranked)}
        rows={x['tap']:x for x in prepared.rows};best=ranked[0];raw=rows[r['raw_tap']]
        detail=[]
        for role,tap in [('raw',r['raw_tap']),('selected',decision.selected_tap),('reference',ref)]:
            c=rows[tap];rf=.7*-math.log(max(c['support'],1e-12));p2=c['p']**2;m2=c['m']**2
            assert abs(c['score']-(rf+max(p2,m2)))<1e-10
            candidate=next(x for x in e.candidates if x.tap==tap)
            detail.append(dict(role=role,**c,rank=rank.get(tap),rf_cost=rf,p_squared=p2,m_squared=m2,pm_cost=max(p2,m2),support_records=json.loads(candidate.support_records_json),cir_amplitude=abs(cir[tap]).tolist(),reference_conflict_gate_would_pass=max(c['p'],c['m'])<=1))
        previous=next(x for x in s1 if x['k']==k-1 and x['mode']=='PM')
        prev_ref=raw_detection(cir_from_spectrum(clean[k-1]))[0]
        gates=dict(wrong=raw['score'],gain=raw['score']-best['score'],margin=decision.margin,group_margin=decision.group_margin,best_conflict=max(best['p'],best['m']))
        assert gates['wrong']>=2 and gates['gain']>=.8 and gates['margin']>=.5 and (gates['group_margin'] is None or gates['group_margin']>=.5) and gates['best_conflict']<=1
        result=dict(case_id=cid,k=k,t=r['t'],reference_in_eligible=ref in rank,n_eligible=len(ranked),p_interval=r['p_interval'],m_interval=r['m_interval'],previous_raw=previous['raw_tap'],previous_reference=prev_ref,previous_t=previous['t'],gates=gates,candidates=detail,all_ranked=ranked,other_modes=[dict(mode=x['mode'],selected=x['hypothetical_selected_tap'],reason=x['decision']['reason']) for x in s1 if x['k']==k])
        results.append(result)
        print(cid,k,'prev',previous['raw_tap'],prev_ref,'gates',gates)
        for c in detail: print(c['role'],c['tap'],'rank',c['rank'],'q %.4f RF %.4f P2 %.4f M2 %.4f J %.4f'%(c['support'],c['rf_cost'],c['p_squared'],c['m_squared'],c['score']))
        print('modes',result['other_modes'])
assert len(results)==6
report=dict(question_id='S2-SIX-REFERENCE-RANK',role='AUDITOR_SELF_CHECK',independent_audit=False,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),scope='POSTHOC_SAVED_S1_S2_DIAGNOSIS_NO_S3',checks='source locks, result hashes, six CIR/VAB pool and prepared-set hashes, clean-H reference, decision and formula/gates',source_hashes=hashes,cases=results)
gov=Path('C:/Users/Myoungsun Kim/.codex/research-governance/COMMON_CONTRACT.md')
report['governance_sha256']=hashlib.sha256(gov.read_bytes()).hexdigest()
(out/'ANALYSIS.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
