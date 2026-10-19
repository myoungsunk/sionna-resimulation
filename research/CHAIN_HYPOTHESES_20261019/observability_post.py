"""Offline scaled local observability diagnostic, not a posterior Fisher bound.
Process noise and prior information are deliberately excluded; no global claim.
"""
from pathlib import Path
import argparse,json,sys
import numpy as np
import pandas as pd


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--delivery',required=True);ap.add_argument('--model',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    model=Path(a.model);root=Path(a.delivery);out=Path(a.out);out.mkdir(exist_ok=True,parents=True)
    sys.path.insert(0,str(model/'source/research/EKF4_RANGE_S_STAGED_20261014'))
    from core import transition
    rows=[];scale=np.diag([.1,.1,np.radians(5),np.radians(.1),1.,1.])
    for p in root.rglob('*_TRACE.npz'):
        s=p.stem.split('_');cid='_'.join(s[:3]);bias=s[3]
        if bias not in ['B0','L2']:continue
        btruth=0. if bias=='B0' else np.radians(.2)
        with np.load(p,allow_pickle=False) as z:r={k:z[k] for k in ['state','prior_state','H','B','t','arms','cov']}
        with np.load(model/(cid+'_full.npz'),allow_pickle=False) as z:d={k:z[k] for k in ['H_truth','truth',bias+'_ds_odom',bias+'_dtheta_gyro',bias+'_dt_s','R']}
        cfg=json.loads((p.parent/'TRAIN_TEMPORAL_ACTUAL_CLOCK.json').read_text());names=r['arms'].tolist();N=len(r['t'])
        for arm in ['POWER1','MEM_RS']:
            j=names.index(arm)
            for linearization in ['filter_prior','truth_offline']:
                for start in range(0,N-39,40):
                    Phi=np.eye(6);blocks=[]
                    for k in range(start,start+40):
                        if k>start:
                            x=r['state'][k-1,j,:4] if linearization=='filter_prior' else np.r_[d['truth'][k-1],btruth]
                            dt=d[bias+'_dt_s'][k];_,F,_=transition(x,float(d[bias+'_ds_odom'][k]),float(d[bias+'_dtheta_gyro'][k]),float(dt))
                            A=np.zeros((6,6));A[:4,:4]=F
                            aa=cfg['temporal']['a_ref']**(float(dt)/cfg['temporal']['dt_ref']) if arm=='MEM_RS' else 0.
                            A[4:,4:]=np.eye(2)*aa;Phi=A@Phi
                        H=r['H'][k,j].copy()
                        if linearization=='truth_offline':H[:,:4]=d['H_truth'][k]
                        E=d['R'][k]-r['B'][k,j]@r['B'][k,j].T
                        block=np.linalg.solve(np.linalg.cholesky(E),H@Phi@scale)
                        blocks.append(block)
                    O=np.concatenate(blocks);sv=np.linalg.svd(O,compute_uv=False)
                    theta=O[:,2];nuisance=np.delete(O,2,axis=1)
                    coef=np.linalg.lstsq(nuisance,theta,rcond=1e-9)[0];res=theta-nuisance@coef
                    den=float(theta@theta);eff=float(res@res)
                    rows.append({'case':cid,'bias':bias,'arm':arm,'linearization':linearization,'start_frame':start,'x':float(d['truth'][start,0]),'y':float(d['truth'][start,1]),'nominal_heading_column_energy':den,'heading_energy_after_nuisance_projection':eff,'unexplained_heading_fraction':eff/max(den,1e-30),'rank_relative_1e8':int(np.sum(sv>max(sv[0],1e-30)*1e-8)),'singular_values':json.dumps(sv.tolist()),'scope':'40-frame deterministic sensitivity, omits process noise and priors; diagnostic not final observability proof'})
    df=pd.DataFrame(rows);df.to_csv(out/'LOCAL_OBSERVABILITY_WINDOWS.csv',index=False)
    ss=[]
    for (cid,b,arm,lin),g in df.groupby(['case','bias','arm','linearization']):
        ss.append({'case':cid,'bias':b,'arm':arm,'linearization':lin,'windows':len(g),'median_unexplained_heading_fraction':float(g.unexplained_heading_fraction.median()),'fraction_windows_lt001':float((g.unexplained_heading_fraction<.01).mean()),'median_projected_heading_energy':float(g.heading_energy_after_nuisance_projection.median())})
    pd.DataFrame(ss).to_csv(out/'LOCAL_OBSERVABILITY_SUMMARY.csv',index=False)
    print('LOCAL_INFORMATION_DIAGNOSTIC',json.dumps([r for r in ss if r['bias']=='B0']),flush=True)

if __name__=='__main__':main()
