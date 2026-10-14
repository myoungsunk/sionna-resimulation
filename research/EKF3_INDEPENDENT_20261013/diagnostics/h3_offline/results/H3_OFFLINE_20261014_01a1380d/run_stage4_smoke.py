"""Frozen R0 stage4 preflight; final angular grid checks XY quadrature too."""
import json,sys,time,traceback
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
import h3_offline as h
import run_full as r

out=h.ROOT/'STAGE4_SMOKE_01'

def integrated(lut,x,P,zs,zr,case,R,conditional,context):
    post=h.integrated_posterior(lut,x,P,zs,zr,case,np.zeros(2),R,conditional)
    orders=h.C['position_quadrature_orders'];i=orders.index(post['position_order'])
    confirm=orders[i+1] if i+1<len(orders) else orders[i-1]
    fn=h.integrated_logfun(lut,x,P,zs,zr,case,np.zeros(2),R,confirm,conditional)
    lp=fn(post['grid']);prob=np.exp(lp-logsumexp(lp))
    tv=float(.5*np.abs(prob-post['prob']).sum())
    r.save_csv(out/'QUADRATURE_CHECKS.csv',CHECKS+[dict(context,chosen_order=post['position_order'],confirmation_order=confirm,final_grid_n=len(prob),final_grid_position_TV=tv)])
    CHECKS.append(dict(context,chosen_order=post['position_order'],confirmation_order=confirm,final_grid_n=len(prob),final_grid_position_TV=tv))
    if tv>h.C['position_quadrature_TV_tolerance']:raise RuntimeError('Final-grid position quadrature gate TV='+str(tv))
    post['confirmation_position_TV']=tv
    return post

def main():
    global CHECKS
    out.mkdir(exist_ok=False);CHECKS=[];rows=[];context={};start=time.time()
    h.c.atomic_json(out/'STAGE_CONTRACT.json',dict(scope='STAGE4_FROZEN_R0_PREFLIGHT_ONLY',parent_contract_sha256=h.c.file_sha(h.ROOT/'CONTRACT.json'),case='R2_aA_m0',seed=0,conditions=h.C['conditions'],RF_pairs=h.C['RF_pairs'],samples='FIRST_MIDDLE_LAST_EVALUATION_INDEX',order='CONDITION_THEN_SAMPLE_THEN_RF_PAIR_THEN_G0_G1_G2H_G2X_G3',additional_numeric_check='ADJACENT_HIGHER_GH_ORDER_ON_FINAL_ANGULAR_GRID_OR_PREVIOUS_IF_MAX_ORDER',tolerance=h.C['position_quadrature_TV_tolerance'],full_stage4='NOT_COMPLETE_BY_SMOKE',recursive_fusion='REQUIRES_FULL_STAGE4_REVIEW_GATE',learned_RF_model='BLOCKED_EXISTING_SPATIAL_BUFFER',R_sr=0,scientific_PASS=False))
    receipt=dict(stage=4,scope='SMOKE_ONLY',recursive_fusion='NOT_RUN',scientific_PASS=False)
    try:
        audit=json.loads((h.ROOT/'STAGE3_01/REVIEW_01/RESULT_AUDIT.json').read_text())
        if audit['status']!='PASS':raise RuntimeError('Stage3 audit prerequisite failed')
        p0=h.c.check_inputs();caches,im=r.load_caches(p0);lut=h.c.original_lut(p0)
        h.c.atomic_json(out/'INPUT_MANIFEST.json',dict(command=sys.argv,source_sha256={p.name:h.c.file_sha(p) for p in (Path(__file__),h.ROOT/'h3_offline.py',h.ROOT/'run_full.py')},cache_sha256=im['sha256'],frozen_blobs=h.c.check_frozen_baseline_files(),stage3_audit_sha256=h.c.file_sha(h.ROOT/'STAGE3_01/REVIEW_01/RESULT_AUDIT.json')))
        priors,parity=r.prepare_priors(p0,caches,out);case=next(q for q in p0['cases'] if q['id']=='R2_aA_m0');R=np.diag([h.c.RS,h.c.RR])
        for condition,level in h.C['conditions']:
            t,tr,xs,Ps=priors[(case['id'],condition,level,0)];indices=np.flatnonzero(t>=h.C['evaluation_start_s']);samples=[indices[0],indices[len(indices)//2],indices[-1]]
            for k in samples:
                for channel,range_model in h.C['RF_pairs']:
                    x,P=xs[k],Ps[k];data=caches[(case['id'],channel)];zs=float(data['s'][k]);zr=float(data[range_model][k])
                    context=dict(case=case['id'],condition=condition,level=level,seed=0,channel=channel,range_model=range_model,sample=int(k),t_s=float(t[k]))
                    for method in ('G0','G1','G2H','G2X','G3'):
                        context['method']=method;gate='not_used';shift=0.;geometry='valid'
                        print(json.dumps(dict(context,status='START')),flush=True)
                        if method=='G0':post=h.posterior(h.fixed_logfun(lut,x,P,zs,case))
                        elif method=='G1':
                            height=case['anchor'][2]-case['robot_z_m']
                            if zr<=0 or zr<abs(height):
                                rows.append(dict(context,geometry='unrealizable_slant_range'));r.save_csv(out/'SMOKE_PARTIAL.csv',rows);continue
                            theta=float(np.arctan2(np.sqrt(max(zr*zr-height*height,0)),height)*h.RAD)
                            post=h.posterior(h.fixed_logfun(lut,x,P,zs,case,override_theta=theta));geometry='partial_geometry_diagnostic'
                        elif method in ('G2H','G2X'):
                            xp,pp,gate=h.range_update(x,P,zr,case,0.,h.c.RR,method=='G2X');shift=float(h.wrap(xp[2]-x[2])*h.RAD)
                            post=integrated(lut,xp,pp,zs,zr,case,R,True,context)
                            geometry='EKF_range_approximation_conditional_s_once'
                        else:
                            gate='likelihood_no_gate';post=integrated(lut,x,P,zs,zr,case,R,False,context)
                        rows.append(dict(context,range_gate=gate,heading_prior_shift_deg=shift,geometry=geometry,**h.scored(post,tr[k,2])))
                        r.save_csv(out/'SMOKE_PARTIAL.csv',rows)
        receipt.update(status='PASS',exit_code=0,rows=len(rows),D0_parity_max=max(q['max_metric_difference'] for q in parity) if parity and 'max_metric_difference' in parity[0] else None)
    except Exception as exc:
        traceback.print_exc();receipt.update(status='FAIL_CLOSED',exit_code=1,failure_reason=str(exc),failure_context=dict(context),rows=len(rows))
    receipt['elapsed_s']=time.time()-start
    receipt['next_action']='FULL_STAGE4_REQUIRED_BEFORE_FUSION' if receipt['status']=='PASS' else 'STOP_STAGE4_AND_RECURSIVE_FUSION'
    h.c.atomic_json(out/'VALIDATION_RECEIPT.json',receipt)
    print(json.dumps(receipt),flush=True);return receipt['exit_code']

if __name__=='__main__':sys.exit(main())
