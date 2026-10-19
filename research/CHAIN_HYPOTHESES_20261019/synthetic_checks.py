"""Known-generative-model tests, explicitly NOT Sionna RF performance."""
import numpy as np


def run():
    rng=np.random.default_rng(811019);nrep=1200;T=260;f=.85;q=.002
    rows=[]
    for true_a in [0.,.97]:
        truth=rng.normal(size=nrep);beta=rng.normal(size=nrep)
        states={'white':np.zeros((nrep,2)),'colored':np.zeros((nrep,2))}
        covs={k:np.eye(2) for k in states};errs={k:[] for k in states};vars_={k:[] for k in states}
        for step in range(T):
            truth+=rng.normal(size=nrep)*np.sqrt(q)
            beta=true_a*beta+np.sqrt(1-true_a**2)*rng.normal(size=nrep)
            y=truth+np.sqrt(f)*beta+np.sqrt(1-f)*rng.normal(size=nrep)
            for name,a in [('white',0.),('colored',true_a)]:
                A=np.diag([1.,a]);Q=np.diag([q,1-a*a]);h=np.array([1.,np.sqrt(f)])
                x=states[name]@A.T;P=A@covs[name]@A.T+Q
                S=h@P@h+(1-f);K=P@h/S
                x+=(y-x@h)[:,None]*K;L=np.eye(2)-np.outer(K,h)
                P=L@P@L.T+np.outer(K,K)*(1-f)
                states[name]=x;covs[name]=P
                if step>=80:errs[name].append((x[:,0]-truth).copy());vars_[name].append(P[0,0])
        for name in states:
            e=np.asarray(errs[name]);v=np.asarray(vars_[name])[:,None];d=e*e/v
            rows.append({'test':'known_linear_colored_measurement','true_a':true_a,'filter':name,'replicates':nrep,'scored_steps':180,'rmse':float(np.sqrt(np.mean(e*e))),'mean_reported_sigma':float(np.mean(np.sqrt(v))),'nees':float(d.mean()),'coverage95':float(np.mean(d<=3.841458820694124))})
    # Fixed g: one instant cannot distinguish angle and signed RF offset.
    # With a=1 and fixed g across time, the two-column observation matrix remains rank one.
    N=40;t=np.arange(N);g=np.ones(N);mat=np.column_stack([g,np.ones(N)])
    changing=np.column_stack([1+.8*np.sin(t/6),np.ones(N)])
    ident={'static_heading_and_constant_rf_offset_rank':int(np.linalg.matrix_rank(mat)),'changing_sensitivity_rank':int(np.linalg.matrix_rank(changing)),'changing_sensitivity_singular_values':np.linalg.svd(changing,compute_uv=False).tolist(),'interpretation':'toy rank diagnostic only; actual RF augmented observability must be tested with motion and gyro-bias nuisance'}
    good=[r for r in rows if r['filter']=='colored']
    if not all(.8<r['nees']<1.2 and .92<r['coverage95']<.98 for r in good):raise AssertionError('Known-model calibration failed')
    return rows,ident

if __name__=='__main__':
    import json
    print(json.dumps(run(),indent=2))
