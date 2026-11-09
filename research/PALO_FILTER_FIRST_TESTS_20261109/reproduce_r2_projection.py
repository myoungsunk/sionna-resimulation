#!/usr/bin/env python3
"""PALO three-filter proposal: representative R2 cases and simple one-dimensional rank proxy.
Original data: GitHub Actions #42466288321 artifact single-metric-inputs ZIP.
This is an OFFLINE diagnostic, not a new filter. Truth and LoS are for scoring.
"""
import argparse, hashlib, json, math, sys, tempfile, zipfile
from pathlib import Path
import numpy as np
import pandas as pd

EXPECTED_SHA='46c6070a138f181d73f21796160fba1d52291faef1097f77d205963ddc12e140'
DEG=180/np.pi
def wrap(x):return (np.asarray(x)+np.pi)%(2*np.pi)-np.pi
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input-zip',required=True,type=Path)
    ap.add_argument('--output',required=True,type=Path)
    a=ap.parse_args()
    b=a.input_zip.read_bytes()
    assert hashlib.sha256(b).hexdigest()==EXPECTED_SHA,'SOURCE_ARTIFACT_MISMATCH'
    a.output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='palo_r2_projection_') as tmp:
        with zipfile.ZipFile(a.input_zip) as z:z.extractall(tmp)
        sys.path.insert(0,str(Path(tmp)/'vendor'))
        import common
        e=common.Engine(Path(tmp)/'cache')
        T=e.t
        delta=e.trace['full']['z_s']-e.trace['los']['z_s']
        heading_prior=e.saved['B0','s4']['prior_X']
        true4=np.c_[e.truth,np.zeros(len(T))]
        gs={'S4_prior':e.observe(heading_prior)[1][:,2],
            'GT':e.observe(true4)[1][:,2]}
        rows=[]
        for source,g in gs.items():
            for sec,n in ((1,5),(2,10),(5,25)):
                for st in range(200,len(T)-n+1,n):
                    segment=slice(st,st+n);v=g[segment]
                    den=float(np.dot(v,v))
                    eta=float(np.dot(v-v.mean(),v-v.mean())/den) if den>1e-8 else float('nan')
                    mm=delta[segment]
                    rows.append(dict(source=source,window_s=sec,
                        k0=st,k1=st+n-1,t0=float(T[st]),t1=float(T[st+n-1]),
                        eta_1d=eta,delta_s_mean=float(mm.mean()),delta_s_std=float(mm.std()),
                        delta_s_rms=float(np.sqrt(np.mean(mm*mm)))))
        d=pd.DataFrame(rows)
        d.to_csv(a.output/'PROJECTION_WINDOWS_ALL.csv',index=False)
        cases=[]
        for lv in ('B0','L2'):
            for donor in ('dr','s4','heading'):
                z=e.saved[lv,donor]
                for k in (201,483,484,485,523,524):
                    epre=float(wrap(z['prior_X'][k,2]-z['truth'][k,2])*DEG)
                    epost=float(wrap(z['candidate_X'][k,2]-z['truth'][k,2])*DEG)
                    correction=float(wrap(z['candidate_X'][k,2]-z['prior_X'][k,2])*DEG)
                    cases.append(dict(level=lv,donor=donor,k=k,t_s=float(T[k]),
                        e_prior_deg=epre,delta_psi_deg=correction,e_candidate_deg=epost,
                        abs_heading_gain_deg=abs(epre)-abs(epost),
                        NIS=float(z['nis'][k]),accepted=bool(z['accepted'][k]),
                        s_full_minus_los=float(delta[k])))
        pd.DataFrame(cases).to_csv(a.output/'KEY_FRAMES.csv',index=False)
        summary={}
        for (donor,sec),part in d.groupby(['source','window_s']):
            v=part.eta_1d.dropna()
            summary[f'{donor}_{sec}s']={'n':len(v),'eta_median':float(v.median()),
                'n_below_0p1':int((v<.1).sum()),'fraction_below_0p1':float((v<.1).mean())}
        result=dict(status='OFFLINE_DIAGNOSTIC_1D_PROXY_NOT_FILTER',
            source_sha256=EXPECTED_SHA,lag1_delta_s=float(np.corrcoef(delta[200:-1],delta[201:])[0,1]),
            heading_only_projection='eta = sum((g-mean(g))^2)/sum(g^2), missing positional/bias cross covariance and state propagation',
            windows=summary)
        (a.output/'SUMMARY.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
        print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
