"""One revised parameter fitted on existing Stage-A development data only.
Stationary AR(1) latent RF offset with fixed observation noise and stationary Vc.
C segments are selected from already-frozen Stage-A HMM posterior (>0.5), not GT risk.
"""
import argparse,json
from pathlib import Path
import numpy as np
from scipy.optimize import minimize_scalar

def estimate(source,out):
    source,out=Path(source),Path(out);out.mkdir(exist_ok=True,parents=True)
    cfg=json.loads((source/'FROZEN_CALIBRATION.json').read_text())
    z=np.load(source/'CALIBRATION_DIAGNOSTIC.npz');y=z['residual'];g=z['gamma'];xi=z['xi']
    assert len(y)==600
    mask=g[:,1]>.5;edges=np.diff(np.r_[False,mask,False].astype(int))
    runs=[(int(a),int(b)) for a,b in zip(np.where(edges==1)[0],np.where(edges==-1)[0]) if b-a>=2]
    if len(runs)<2:raise RuntimeError('insufficient C-segment calibration')
    R=cfg['normal_Rs'];Vc=cfg['Rc']-R
    def nll(rho):
        total=0.
        for a,b in runs:
            m=0.;P=Vc
            for k in range(a,b):
                if k>a:m*=rho;P=rho*rho*P+(1-rho*rho)*Vc
                S=P+R;res=y[k]-m;total+=.5*(np.log(2*np.pi*S)+res*res/S)
                m+=P/S*res;P=P*R/S
        return float(total)
    fit=minimize_scalar(nll,bounds=(0,.999),method='bounded',options={'xatol':1e-10})
    assert fit.success and np.isfinite(fit.fun)
    rho=float(fit.x);raw=float(np.sum(xi[:,1,1]*y[:-1]*y[1:])/np.sum(xi[:,1,1]*(y[:-1]**2-R)))
    audit=dict(status='DEVELOPMENT_ONLY_CONDITIONAL_AR_FIT',rho_C=rho,Vc=Vc,Qc=(1-rho*rho)*Vc,
        segments=runs,segment_frames=sum(b-a for a,b in runs),candidate_C_mass=float(g[:,1].sum()),
        nll_independent=nll(0.),nll_best=nll(rho),rho_boundary_hit=bool(rho<1e-5 or rho>.99899),
        naive_noise_corrected_rho=raw,naive_rho_not_used=True,
        profile=[dict(rho=float(v),nll=nll(v)) for v in [0,.5,.8,.9,.95,.98,.999]],
        note='5 short selected development events, not independent validation; scalar latent c may confound heading/bias')
    cfg.update(rho_C=rho,revision='B: add one persistent c only, T/pi/Rc/Rs unchanged',rho_fit=audit)
    (out/'FROZEN_CALIBRATION.json').write_text(json.dumps(cfg,indent=2))
    (out/'RHO_FIT_AUDIT.json').write_text(json.dumps(audit,indent=2));print(json.dumps(audit,indent=2))
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--source',type=Path,required=True);a.add_argument('--out',type=Path,required=True);args=a.parse_args();estimate(args.source,args.out)
