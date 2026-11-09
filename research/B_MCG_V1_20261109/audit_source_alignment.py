"""Evaluator-only audit of finite profile search, using exact SourceFFD costs.

The current target may appear ONLY in a feasibility diagnostic objective. Such a
candidate is NEVER returned to the runtime monitor or used as a policy result.
This isolates numerical underexploration from inherent observational ambiguity.
"""
from pathlib import Path
import argparse,json
import numpy as np
from scipy.optimize import minimize,Bounds
from experiment import context,packet_for,config_for,read_npz
from mcg import motion_path,wrap
from stress_source import clean_json,save


def main(a):
    r45,core,online,model,hashes=context();cfg=config_for();rows=[];feasibility=[]
    for route,k in [('R2',489),('R4',370),('R5',707)]:
        packet,_,_=packet_for(r45,route,'B_FROZEN',a.archives)
        tr=read_npz(a.archives/route/f'{route}_B_FROZEN.npz')
        ht=read_npz(a.model_truth/f'{route}_htruth.npz');truth=ht['truth']
        aa=int(np.searchsorted(packet['t'],packet['t'][k]-5.-1e-9));tt=packet['t'][aa:k+1]
        cs=np.column_stack([packet[v][aa:k+1] for v in ('ds','gy','dt')]);anchor=np.r_[truth[aa],0.]
        delta=.3;rot=np.array([[np.cos(delta),-np.sin(delta)],[np.sin(delta),np.cos(delta)]])
        world=np.column_stack([truth[aa:k+1],np.zeros(k-aa+1)])
        world[:,:2]=(truth[aa:k+1,:2]-truth[aa,:2])@rot.T+truth[aa,:2]+[.3,.3]
        world[:,2]=wrap(world[:,2]+delta)
        hz,_=model.batch(world,r45.SPEC,gradient=False);hz+=packet['muMB'][aa:k+1]
        q0,_=motion_path(core,anchor,cs);_,H0=model.batch(q0,r45.SPEC)
        elapsed=(tt-tt[0])/cfg.span_s
        env=np.column_stack([np.full(len(tt),cfg.motion_xy_m),np.full(len(tt),cfg.motion_xy_m),cfg.motion_yaw_rad*elapsed,np.zeros(len(tt))])
        extra=np.einsum('nci,ni->nc',H0**2,env**2)
        R=tr['Reff'][aa:k+1].copy();R[:,0,0]+=extra[:,0];R[:,1,1]+=extra[:,1]
        L=np.linalg.cholesky(R);scale=np.sqrt(np.diag(R[-1]));bounds=np.asarray(cfg.bounds)
        source=json.loads((a.stress/f'{route}_SOURCE_STRESS.json').read_text())
        prior_row=next(r for r in source['rows'] if r['name']=='COHERENT_WRONG_HISTORY_IDEAL_RETURN')
        mu=packet['muMB'][aa:k+1];target=ht['htruth'][k]
        cache={}

        def eval_u(u):
            key=np.asarray(u,float).tobytes()
            if key in cache:return cache[key]
            q,T=motion_path(core,anchor+bounds*u,cs)
            h,H=model.batch(q,r45.SPEC)
            J=np.einsum('nci,nij->ncj',H,T)*bounds[None,None,:]
            res=np.linalg.solve(L[:-1],(hz[:-1]-h[:-1]-mu[:-1])[...,None])[...,0]
            whJ=np.linalg.solve(L[:-1],J[:-1])
            denom=np.sqrt(1+np.sum(res*res,axis=1))
            cost=float(np.sum(2*(denom-1))+cfg.regularizer*np.dot(u,u))
            grad=-2*np.einsum('nc,nci->i',res/denom[:,None],whJ)+2*cfg.regularizer*u
            et=np.linalg.solve(L[-1],target-h[-1]);jt=np.linalg.solve(L[-1],J[-1])
            rec={'u':u.copy(),'theta':anchor+bounds*u,'cost':cost,'gradient':grad,
                'current_clean_marginal_scores':abs(target-h[-1])/scale,
                'current_clean_joint_score':float(np.linalg.norm(et)),
                'target_prediction':h[-1],'joint_objective':float(et@et),'joint_gradient':-2*et@jt,
                's_objective':float(((target[1]-h[-1,1])/scale[1])**2),
                's_gradient':-2*(target[1]-h[-1,1])/scale[1]**2*J[-1,1]}
            cache[key]=rec;return rec

        known=np.array([.3,.3,.3,0.])/bounds
        prior=(np.array(prior_row['theta'])-anchor)/bounds
        cases=[]
        for name,u in [('known_generating_alignment',known),('true_alignment',np.zeros(4)),('finite_search_best',prior)]:
            rec=eval_u(u);cases.append({'name':name,**rec})
        rows.append({'route':route,'k':k,'profile_best_cost':prior_row['profile_cost'],
            'profile_config_sha256':prior_row['config_sha256'],'slack':cfg.fit_slack_per_sample*(len(tt)-1),
            'cases':cases})
        if route!='R5':continue
        # R5 only: bounded, predeclared budget; no tuning of operational thresholds.
        opt=[]
        for seed_name,u in [('known_generator',known),('runtime_best',prior)]:
            res=minimize(lambda x:eval_u(x)['cost'],u,jac=lambda x:eval_u(x)['gradient'],
                method='L-BFGS-B',bounds=Bounds(-np.ones(4),np.ones(4)),
                options={'maxiter':60,'ftol':1e-12,'gtol':1e-7,'maxls':20})
            opt.append({'seed':seed_name,'success':bool(res.success),'message':str(res.message),
                'nfev':int(res.nfev),'nit':int(res.nit),'result':eval_u(res.x)})
        best=min([eval_u(known),eval_u(prior)]+[v['result'] for v in opt],key=lambda v:v['cost'])
        ceiling=best['cost']+cfg.fit_slack_per_sample*(len(tt)-1)
        found=[]
        for objective in ['joint','s']:
            for seed_name,u in [('best_history',best['u']),('known_generator',known)]:
                res=minimize(lambda x:eval_u(x)[objective+'_objective'],u,
                    jac=lambda x:eval_u(x)[objective+'_gradient'],method='SLSQP',
                    bounds=Bounds(-np.ones(4),np.ones(4)),
                    constraints=[{'type':'ineq','fun':lambda x:ceiling-eval_u(x)['cost'],
                        'jac':lambda x:-eval_u(x)['gradient']}],
                    options={'maxiter':80,'ftol':1e-10})
                rec=eval_u(res.x);feasible=bool(rec['cost']<=ceiling+1e-7 and np.max(abs(res.x))<=1+1e-8)
                found.append({'objective':'TARGET_INFORMED_DIAGNOSTIC_'+objective,'seed':seed_name,
                    'optimizer_success':bool(res.success),'message':str(res.message),'nit':int(res.nit),'nfev':int(res.nfev),
                    'history_constraint_verified_exact':feasible,'history_ceiling':ceiling,
                    'clean_s_below_tau':bool(feasible and rec['current_clean_marginal_scores'][1]<=cfg.tau_s),
                    'both_marginals_below_tau':bool(feasible and np.all(rec['current_clean_marginal_scores']<=cfg.tau_s)),
                    'result':rec})
        feasibility.append({'route':route,'k':k,'history_optimizers':opt,'best_history_cost_found':best['cost'],
            'history_ceiling':ceiling,'target_feasibility_diagnostics':found,
            'any_compatible_history_feasible_witness':any(v['both_marginals_below_tau'] for v in found),
            'warning':'This is a current-target-informed evaluator feasibility check, not a causal runtime search or a deployable policy.'})
    report={'scope':'Exact SourceFFD finite-search audit; only R5 target feasibility is optimized.',
        'rows':rows,'feasibility':feasibility,'source_hashes':hashes,
        'no_global_optimality_claim':True,'runtime_policy_modified':False}
    save(a.out,report)
    print(json.dumps(clean_json({'rows':[{'route':r['route'],'costs':{c['name']:c['cost'] for c in r['cases']}} for r in rows],
        'feasibility':feasibility}),ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archives',type=Path,required=True);p.add_argument('--model-truth',type=Path,required=True);p.add_argument('--stress',type=Path,required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
