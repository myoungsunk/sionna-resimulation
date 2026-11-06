"""Self-check S1 stored rows only. No evaluator, reference labels or S2/S3."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import sys,json,gzip,hashlib,collections,pathlib,datetime
import numpy as np
root=pathlib.Path(__file__).resolve().parents[2]
sys.path[:0]=[str(root/'src'),str(root/'scripts')]
import fp_sc_vab_shadow_stages as s
from qclean_uwb.fp_sc.followup.numerics import cir_from_spectrum,factorial,raw_detection
from qclean_uwb.fp_sc.followup.contracts import STEP_M,Support
from qclean_uwb.fp_sc.followup.bridge import RevisionEvidenceAdapter
from qclean_uwb.fp_sc.followup.detection import binding_for
from qclean_uwb.fp_sc.followup.selection import prepare_candidate_set
out=pathlib.Path(__file__).resolve().parent
summaries=[];checked=0;max_score_error=0.
adapter=RevisionEvidenceAdapter(arm='VAB',mode='TWO_PORT_UNION')
for f in sorted((root/'research/FP_SC_S1_PREPARATION_20261106/FINAL_002').glob('*_S1_MANIFEST.json')):
    m,p=s.inspect_manifest(f);cid=m['case_id'];rdir=out/'RESULTS'/cid
    receipt=json.loads((rdir/'RUN_RECEIPT.json').read_text())
    assert receipt['status']=='COMPLETE_TECHNICAL_ONLY'
    assert receipt['identity_sha256']==s.identity(m)
    assert receipt['manifest_sha256']==s.sha256(f)
    assert receipt['approval_sha256']==s.sha256(out/'APPROVALS'/f'{cid}.json')
    assert receipt['result_sha256']==s.sha256(rdir/'ROWS.json.gz')
    with gzip.open(rdir/'ROWS.json.gz','rt',encoding='utf-8') as h:rows=json.load(h)
    n=m['case']['expected_rows'];assert len(rows)==n*4==receipt['row_count']
    assert {(r['k'],r['mode']) for r in rows}=={(k,mode) for k in range(n) for mode in ('C','P','M','PM')}
    # np.load NPZ access decompresses a member on every indexing operation.
    # Cache only the online arrays needed for this verification, once per case.
    with np.load(root/m['case']['online_npz'],allow_pickle=False) as archive:
        a={key:archive[key] for key in ('Hrf','t','pose_id')}
    report={mode:dict(n=0,changed=0,reasons=collections.Counter()) for mode in ('C','P','M','PM')}
    last_k=-1;cir=None
    for r in rows:
        k=r['k'];mode=r['mode'];d=r['decision'];selected=r['hypothetical_selected_tap']
        assert r['case_id']==cid and r['t']==a['t'][k] and r['pose_id']==a['pose_id'][k]
        assert r['provider_allowed'] is False and r['integrity']['state']!='VALID'
        assert r['scope']=='OFFLINE_COUNTERFACTUAL_NO_VALID_NO_PRODUCTION_WRITE'
        assert selected==d['selected_tap'] and r['raw_tap']==d['raw_tap']
        assert not ({'reference_tap','truth','raw_correct','proposed_correct'}&set(r))
        if k!=last_k:
            cir=cir_from_spectrum(a['Hrf'][k]);last_k=k
            evidence=adapter.evidence(cir,m['case']['metadata']['noise_variance'])
        assert raw_detection(cir)[0]==r['raw_tap']
        prepared=prepare_candidate_set(evidence,mode,p,binding=binding_for(evidence,p),
            prior=None if r['p_interval'] is None else Support(**r['p_interval']),
            motion=None if r['m_interval'] is None else Support(**r['m_interval']))
        assert prepared.sha==r['candidate_set_sha256'] and evidence.pool_hash==d['pool_hash']
        assert selected==r['raw_tap'] or selected in {x['tap'] for x in prepared.eligible}
        obs=factorial(cir,r['raw_tap'],selected)
        for arm,v in obs.items():
            if v is None:assert r['observations'][arm] is None
            else:np.testing.assert_array_equal(v,r['observations'][arm])
        candidates=d['scores']
        for c in candidates:
            residuals=[]
            for typ,key in [('P','p_interval'),('M','m_interval')]:
                active=(typ=='P' and mode in ('P','PM')) or (typ=='M' and mode in ('M','PM'))
                if active:
                    bounds=r[key];assert bounds is not None
                    rr=max(bounds['low']-c['tap']*STEP_M,c['tap']*STEP_M-bounds['high'],0)/bounds['scale']
                    np.testing.assert_allclose(rr,c[typ.lower()],atol=1e-12,rtol=0)
                    residuals.append(rr)
            expected=p.rf_weight*(-np.log(max(c['support'],1e-12)))+p.prior_weight*max(residuals,default=0)**2
            err=abs(expected-c['score']);max_score_error=max(max_score_error,err)
            assert err<1e-10
        changed=selected!=r['raw_tap']
        if changed:
            assert d['action']=='REPLACE_SUPPORTED'
            raw=next(c for c in candidates if c['tap']==r['raw_tap'])
            best=next(c for c in candidates if c['tap']==selected)
            assert d['wrong_score']>=p.wrong_cut and raw['score']-best['score']>=p.replace_gain
            assert d['margin'] is None or d['margin']>=p.margin
            assert d['group_margin'] is None or d['group_margin']>=p.margin
            assert max(best['p'] or 0,best['m'] or 0)<=1
        else:assert d['action']=='KEEP_ORIGINAL'
        report[mode]['n']+=1;report[mode]['changed']+=int(changed);report[mode]['reasons'][d['reason']]+=1
        checked+=1
    summaries.append(dict(case=cid,packet_count=n,rows=len(rows),modes=report))
    print('CHECKED',cid,len(rows),flush=True)
assert checked==25088
result=dict(status='PASS_S1_SELF_CHECK',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    role='IMPLEMENTER_SELF_CHECK',independent_audit=False,rows_checked=checked,max_score_error=max_score_error,
    checks=['all six common locks reverified','row count and exact packet-mode keys','receipt and result hashes',
            'time pose raw detector equality','CIR regenerated VAB pool and candidate set hashes',
            'all four observation arrays exact','all candidate score formulas',
            'replacement gain margin conflict gates','no VALID or evaluator labels'],cases=summaries,
    claim='Technical S1 completion only. No accuracy or correction-success evaluation. S2/S3 not run.')
s.write_json(out/'CHECK_001.json',result)
print(json.dumps(result,ensure_ascii=False))
