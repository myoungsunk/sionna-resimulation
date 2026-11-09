"""Post-run arithmetic reviewer; does not call production score/update helpers."""
import argparse,json,math,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import logsumexp

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    df=pd.concat([pd.read_csv(p) for p in a.out.glob('*_METRICS.csv') if p.name!='ALL_METRICS.csv'],ignore_index=True)
    mm=mc=ml=0.;nrows=steps=0
    for p in a.out.glob('*.npz'):
        z=dict(np.load(p,allow_pickle=False));N=len(z['t']);steps+=N
        assert all(k in z for k in ('X','P','truth','t'))
        parts=p.stem.split('_');i=next(i for i,v in enumerate(parts) if v in ('full','los'))
        case='_'.join(parts[:i]);ch=parts[i];lv=parts[i+1];method='_'.join(parts[i+2:])
        X=z['X'][:,:4];P=z['P'][:,:4,:4];gt=z['truth'];t=z['t']
        assert np.isfinite(X).all() and np.isfinite(P).all() and np.linalg.eigvalsh(P).min()>0
        e=(X[:,2]-gt[:,2]+np.pi)%(2*np.pi)-np.pi;ep=X[:,:2]-gt[:,:2];bias={'B0':0,'L0':.01,'L1':.05,'L2':.2}[lv]
        for _,r in df.query('case==@case and channel==@ch and level==@lv and method==@method').iterrows():
            if r.window=='all_ge40':mask=t>=40
            elif r.window=='development_lt120':mask=t<120
            elif r.window=='evaluation_ge140':mask=t>=140
            elif r.window=='event_96_100':mask=(t>=96)&(t<=100)
            else:st=float(r.window.split('_')[1]);mask=(t>=st)&(t<st+10)
            h=math.sqrt(sum(float(v)**2 for v in e[mask])/sum(mask))*180/np.pi
            xy=math.sqrt(sum(float(v@v) for v in ep[mask])/sum(mask))
            b=math.sqrt(sum((float(v)*180/np.pi-bias)**2 for v in X[mask,3])/sum(mask))
            mm=max(mm,abs(h-r.heading_rmse_deg),abs(xy-r.xy_rmse_m),abs(b-r.bias_rmse_deg_s));nrows+=1
        if 'mode_X' not in z:continue
        for k in range(N):
            for j in range(2):
                H=z['H'][k,j];pr=z['prior_P'][k,j];nu=z['nu'][k,j];S=z['S'][k,j]
                R=(.0081 if j==0 else float(z['Rc'])) if len(H)==4 else .0081
                ph=pr@H;C=pr-np.outer(ph,ph)/S;mc=max(mc,float(abs(C-z['mode_P'][k,j]).max()))
                ll=-.5*math.log(2*math.pi*S)-.5*nu*nu/S;ml=max(ml,abs(ll-z['logL'][k,j]))
                assert abs(S-(H@pr@H+R))<1e-10
            assert abs(z['weights'][k].sum()-1)<1e-12
    assert mm<1e-10 and mc<1e-9 and ml<1e-10
    report=dict(status='PASS',scored_rows=nrows,stored_steps=steps,max_metric_error=mm,max_update_covariance_error=mc,max_loglikelihood_error=ml,author_independence='same author, separately coded arithmetic checks; not external independent review')
    (a.out/'INDEPENDENT_ARITHMETIC_AUDIT.json').write_text(json.dumps(report,indent=2));df.to_csv(a.out/'ALL_METRICS.csv',index=False)
    manifest={p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(a.out.glob('*')) if p.is_file()}
    (a.out/'RESULT_MANIFEST.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
