"""Single-event evaluator-only feasible-set audit of the R4 clean return.

The online implementation and policy are not modified. Current target enters
only a diagnostic optimization to find a constructive compatible witness. A
failed search is never reported as proof of global incompatibility.
"""
from pathlib import Path
import argparse,json,hashlib,time
import numpy as np
from scipy.optimize import minimize,Bounds
from experiment import context,packet_for,read_npz
from mcg import Config,motion_path,profile_history,score_current,wrap
from stress_source import save,clean_json


def main(a):
    started=time.perf_counter();runtime_path=Path(__file__).with_name('mcg.py')
    runtime_sha=hashlib.sha256(runtime_path.read_bytes()).hexdigest()
    result_path=a.recovery/'R4_A186_ACTIVE_RS_TAU2.npz';tr=read_npz(result_path)
    report=json.loads((a.recovery/'R4_RECOVERY.json').read_text())
    assert report['runtime_code_sha256']['mcg.py']==runtime_sha
    cfg=Config(**report['configs']['ACTIVE_RS_TAU2'])
    r45,core,online,model,source_hashes=context();packet,_,_=packet_for(r45,'R4','B_FROZEN',a.archives)
    k=26;aa=int(tr['anchor_index'][k]);orig=tr['original_k'][aa:k+1].astype(int)
    assert k==26 and aa==1 and int(tr['original_k'][k])==212
    controls=np.column_stack([packet[v][orig] for v in ('ds','gy','dt')]);tt=tr['t'][aa:k+1]
    anchor=tr['prior'][aa].copy();history=tr['constructed_z'][aa:k];mu=tr['mu'][aa:k+1]
    Rbase=tr['Rbase'][aa:k+1];current=tr['constructed_z'][k]
    assert np.array_equal(current,tr['ideal_z'][k])
    p=profile_history(core,model,r45.SPEC,anchor,controls,tt,history,mu[:-1],Rbase,cfg)
    score=score_current(p,current,mu[-1])
    np.testing.assert_allclose(score['scores'],tr['scores'][k],rtol=0,atol=1e-10)
    q0,_=motion_path(core,anchor,controls);_,H0=model.batch(q0,r45.SPEC)
    elapsed=(tt-tt[0])/cfg.span_s
    env=np.column_stack([np.full(len(tt),cfg.motion_xy_m),np.full(len(tt),cfg.motion_xy_m),cfg.motion_yaw_rad*elapsed,np.zeros(len(tt))])
    extra=np.einsum('nci,ni->nc',H0**2,env**2);R=Rbase.copy();R[:,0,0]+=extra[:,0];R[:,1,1]+=extra[:,1]
    L=np.linalg.cholesky(R);scale=np.sqrt(np.diag(R[-1]));bounds=np.asarray(cfg.bounds);nh=len(history);cache={}

    def ev(u):
        u=np.asarray(u,float);key=u.tobytes()
        if key in cache:return cache[key]
        q,T=motion_path(core,anchor+bounds*u,controls);h,H=model.batch(q,r45.SPEC)
        J=np.einsum('nci,nij->ncj',H,T)*bounds[None,None,:]
        residual=np.linalg.solve(L[:-1],(history-h[:-1]-mu[:-1])[...,None])[...,0]
        Jw=np.linalg.solve(L[:-1],J[:-1]);den=np.sqrt(1+np.sum(residual*residual,axis=1))
        cost=float(2*np.sum(den-1)+cfg.regularizer*np.dot(u,u))
        grad=-2*np.einsum('nc,nci->i',residual/den[:,None],Jw)+2*cfg.regularizer*u
        err=current-h[-1]-mu[-1];e=err/scale;j=J[-1]/scale[:,None]
        et=np.linalg.solve(L[-1],err);jt=np.linalg.solve(L[-1],J[-1])
        rec={'u':u.copy(),'theta':anchor+bounds*u,'cost':cost,'gradient':grad,
            'current_signed_marginal':e,'current_marginal_scores':abs(e),'current_joint_score':float(np.linalg.norm(et)),
            'target_prediction':h[-1],'target_J_scaled':j,'target_white_error':et,'target_white_J':jt}
        cache[key]=rec;return rec

    # Known transformed pose at the actual rolling anchor, not the episode pivot.
    truth=tr['truth'];theta=np.r_[truth[aa],0.];delta=.3
    rot=np.array([[np.cos(delta),-np.sin(delta)],[np.sin(delta),np.cos(delta)]])
    theta[:2]=(truth[aa,:2]-truth[0,:2])@rot.T+truth[0,:2]+[.3,.3]
    theta[2]=anchor[2]+float(wrap(truth[aa,2]+delta-anchor[2]))
    known=(theta-anchor)/bounds
    true_theta=np.r_[truth[aa],0.];true_theta[2]=anchor[2]+float(wrap(true_theta[2]-anchor[2]));truth_u=(true_theta-anchor)/bounds
    runtime_u=(p['theta']-anchor)/bounds
    seeds=[('runtime_profile',runtime_u),('known_generator_clipped_if_needed',np.clip(known,-1,1))]
    basecases=[]
    for name,u in [('runtime_profile',runtime_u),('known_generating_alignment',known),('true_alignment',truth_u)]:
        basecases.append({'name':name,'inside_bounds':bool(np.max(abs(u))<=1+1e-12),'result':ev(u)})
    opts=[]
    for name,u in seeds:
        opt=minimize(lambda x:ev(x)['cost'],u,jac=lambda x:ev(x)['gradient'],method='L-BFGS-B',
            bounds=Bounds(-np.ones(4),np.ones(4)),options={'maxiter':60,'maxls':20,'ftol':1e-12,'gtol':1e-7})
        opts.append({'seed':name,'success':bool(opt.success),'message':str(opt.message),'nfev':int(opt.nfev),'nit':int(opt.nit),'result':ev(opt.x)})
    available=[c['result'] for c in basecases if c['inside_bounds']]+[o['result'] for o in opts]
    best=min(available,key=lambda r:r['cost']);ceiling=best['cost']+cfg.fit_slack_per_sample*nh

    def constraints(v):
        rec=ev(v[:4]);b=v[4];e=rec['current_signed_marginal'];et=rec['target_white_error']
        return np.r_[ceiling-rec['cost'],b-e,b+e,2*b*b-et@et]

    def cjac(v):
        rec=ev(v[:4]);j=rec['target_J_scaled'];et=rec['target_white_error'];jt=rec['target_white_J']
        return np.vstack([np.r_[-rec['gradient'],0.],np.column_stack([j,np.ones(2)]),np.column_stack([-j,np.ones(2)]),np.r_[2*et@jt,4*v[4]]])

    feasible=[]
    for name,u in [('best_history',best['u']),('runtime_profile',runtime_u)]:
        rec=ev(u);b=max(np.max(rec['current_marginal_scores']),rec['current_joint_score']/np.sqrt(2))+.01
        opt=minimize(lambda v:v[4],np.r_[u,b],jac=lambda v:np.array([0.,0.,0.,0.,1.]),method='SLSQP',
            bounds=Bounds(np.r_[-np.ones(4),0.],np.r_[np.ones(4),np.inf]),
            constraints=[{'type':'ineq','fun':constraints,'jac':cjac}],options={'maxiter':90,'ftol':1e-10})
        rec=ev(opt.x[:4]);ok=bool(rec['cost']<=ceiling+1e-7 and np.max(abs(opt.x[:4]))<=1+1e-8)
        minimum_tau=max(np.max(rec['current_marginal_scores']),rec['current_joint_score']/np.sqrt(2))
        feasible.append({'seed':name,'optimizer_success':bool(opt.success),'message':str(opt.message),'nit':int(opt.nit),'nfev':int(opt.nfev),
            'history_constraint_verified_exact':ok,'history_ceiling':ceiling,'minimum_tau_for_this_witness':float(minimum_tau),
            'compatible_at_tau2_witness':bool(ok and minimum_tau<=2.+1e-9),
            'compatible_at_tau3_witness':bool(ok and minimum_tau<=3.+1e-9),'result':rec})
    assert hashlib.sha256(runtime_path.read_bytes()).hexdigest()==runtime_sha
    out={'scope':'R4 original k212 episode k26, single-event evaluator-only feasible-set diagnostic',
        'current_target_used_only_in_diagnostic_objective':True,'runtime_policy_modified':False,
        'no_global_infeasibility_or_optimality_claim':True,'runtime_sha256':runtime_sha,
        'trace_sha256':hashlib.sha256(result_path.read_bytes()).hexdigest(),'source_hashes':source_hashes,
        'event':{'route':'R4','episode_anchor_original_k':186,'episode_k':26,'original_k':212,'rolling_anchor_episode_k':aa},
        'runtime_profile':p,'runtime_score':score,'config':report['configs']['ACTIVE_RS_TAU2'],
        'base_alignment_cases':basecases,'history_optimizers':opts,'best_exact_history_cost_found':best['cost'],
        'history_ceiling':ceiling,'feasibility':feasible,
        'compatible_tau2_witness_found':any(r['compatible_at_tau2_witness'] for r in feasible),
        'compatible_tau3_witness_found':any(r['compatible_at_tau3_witness'] for r in feasible),
        'elapsed_s':time.perf_counter()-started}
    save(a.out,out)
    print(json.dumps(clean_json({'runtime_profile_cost':p['profile_cost'],'runtime_scores':score['scores'],
        'best_history_cost':best['cost'],'history_ceiling':ceiling,'feasible':feasible,'elapsed_s':out['elapsed_s']})),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archives',type=Path,required=True);p.add_argument('--recovery',type=Path,required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
