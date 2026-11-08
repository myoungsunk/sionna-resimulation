"""Separate stored-output arithmetic checker, NOT an independent science audit."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from common import Engine, sha256, errors, DEG, GATE, RS, wrap, dump


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);a=p.parse_args();O=a.output
    manifest=json.loads((O/'OUTPUT_SHA256.json').read_text())
    for rel,record in manifest.items():
        data=(O/rel).read_bytes();assert len(data)==record['bytes'] and sha256(data)==record['sha256'],rel
    assert json.loads((O/'EXECUTION_COMPLETE.json').read_text())['status']=='COMPLETE_SELF_CHECK_PASS'
    E=Engine(a.cache)
    C=pd.read_csv(O/'factorial_candidates.csv.gz')
    assert len(C)==74784 and int(C.primary.sum())==24928
    assert not C.duplicated(['level','pair','k','mask']).any()
    assert C.groupby(['level','pair','k']).size().eq(8).all()
    comp=pd.read_csv(O/'innovation_components.csv.gz')
    assert len(comp)==9348
    innovation_error=np.max(np.abs(comp.z-comp.hEE-comp.RF_model_residual-comp.position_component-comp.heading_component))
    assert innovation_error<1e-10
    facts=pd.read_csv(O/'factual_events.csv.gz')
    assert np.max(abs(facts.heading_gain_deg2-(facts.e_deg**2-facts.post_e_deg**2)))<1e-8
    stored=pd.read_csv(O/'D_horizon_outcomes.csv.gz')
    index={(r.level,r.donor,int(r.k),r.future,int(r.horizon_s),r.arm):r for r in stored.itertuples()}
    assert len(index)==len(stored)
    metric_error=0.;scalar_error=0.;scalar_checks=0;recount=0;trace_steps=0
    for file in sorted((O/'history_rollouts').glob('*.npz')):
        with np.load(file,allow_pickle=False) as f:
            X=f['X'];P=f['P'];valid=f['valid'];starts=f['event_k'];limits=f['limits'];arms=f['arm_names'].tolist();future=str(f['future']);donor=str(f['donor']);lv=str(f['level'])
            assert np.linalg.eigvalsh(P[valid]).min()>0
            trace_steps+=int(valid.sum()*len(arms))
            if future=='off':
                assert np.array_equal(X[:,:,0][valid],X[:,:,2][valid])
                assert np.array_equal(X[:,:,1][valid],X[:,:,3][valid])
            # Frozen ORIGINAL scalar primitives spot-check the batched evolution.
            for i in sorted(set([0,len(starts)-1])):
                for q in sorted(set([1,min(7,int(limits[i]-starts[i]))])):
                    if q<1 or not valid[i,q]:continue
                    k=int(starts[i]+q);ctrl=E.controls['full',lv]
                    for arm in (0,3,7):
                        prevx,prevP=X[i,q-1,arm],P[i,q-1,arm]
                        Q=np.diag([2e-5*abs(ctrl['ds_odom'][k]),np.deg2rad(.015)**2*ctrl['dt_s'][k],0.])
                        xp,Pp,_,_=E.core.predict(prevx,prevP,float(ctrl['ds_odom'][k]),float(ctrl['dtheta_gyro'][k]),float(ctrl['dt_s'][k]),Q)
                        if future=='s4':
                            def model(x):
                                h,H=E.scalar_lut.model(x,E.case);return h[1:],H[1:]
                            xp,Pp,diag=E.core.gaussian_update(xp,Pp,np.array([E.trace['full']['z_s'][k]]),model,np.array([[RS]]),gate_threshold=GATE)
                            assert bool(diag['accepted'])==bool(f['accepted'][i,q,arm])
                        scalar_error=max(scalar_error,float(np.max(abs(xp-X[i,q,arm]))),float(np.max(abs(Pp-P[i,q,arm]))));scalar_checks+=1
            for i,start in enumerate(starts):
                for horizon in (0,1,5,10,20):
                    k=int(np.searchsorted(E.t,E.t[start]+horizon-1e-9));q=k-int(start)
                    if k>limits[i] or k>=len(E.t):continue
                    assert valid[i,q]
                    e=X[i,:q+1,:,:3]-E.truth[start:k+1,None,:];e[:,:,2]=wrap(e[:,:,2]);pp=P[i,:q+1]
                    h=e[:,:,2]*DEG;xy2=np.sum(e[:,:,:2]**2,axis=-1)
                    HN=e[-1,:,2]**2/pp[-1,:,2,2]
                    # Explicit 2x2 inverse; independent of the producer's solve().
                    ex,ey=e[-1,:,0],e[-1,:,1];v=pp[-1,:,:2,:2]
                    XN=(v[:,1,1]*ex*ex-2*v[:,0,1]*ex*ey+v[:,0,0]*ey*ey)/(v[:,0,0]*v[:,1,1]-v[:,0,1]**2)
                    dt=np.diff(E.t[start:k+1])[:,None]
                    hi=np.sum(.5*(h[:-1]**2+h[1:]**2)*dt,axis=0) if q else np.zeros(len(arms))
                    xi=np.sum(.5*(xy2[:-1]+xy2[1:])*dt,axis=0) if q else np.zeros(len(arms))
                    for j,arm in enumerate(arms):
                        r=index[lv,donor,int(start),future,horizon,arm]
                        expected=dict(heading_error_deg=h[-1,j],xy_error_m=np.sqrt(xy2[-1,j]),heading_nees=HN[j],xy_nees=XN[j],heading_ise_deg2_s=hi[j],xy_ise_m2_s=xi[j],heading_gain_vs_off_deg2=h[-1,0]**2-h[-1,j]**2,xy_gain_vs_off_m2=xy2[-1,0]-xy2[-1,j])
                        for key,val in expected.items():
                            # Scaled error records agreement even for large NEES.
                            metric_error=max(metric_error,abs(float(val)-getattr(r,key))/max(1.,abs(float(val))))
                        recount+=1
    assert recount==len(stored)
    assert scalar_error<1e-7 and metric_error<1e-9,(scalar_error,metric_error)
    receipt=dict(status='PASS',manifest_files=len(manifest),factorial_rows=len(C),D_horizon_rows=recount,raw_branch_steps=trace_steps,scalar_source_spot_checks=scalar_checks,max_scalar_error=scalar_error,max_scaled_metric_error=metric_error,innovation_error=float(innovation_error),independent_science_audit=False,coverage='All hashes and horizon metrics; frozen-scalar recursion is sampled, not every step.')
    dump(O/'VERIFY_RECEIPT.json',receipt)
    # Receipt is appended without invalidating already checked files.
    data=(O/'VERIFY_RECEIPT.json').read_bytes();manifest['VERIFY_RECEIPT.json']=dict(bytes=len(data),sha256=sha256(data));dump(O/'OUTPUT_SHA256.json',manifest)
    print(json.dumps(receipt,indent=2),flush=True)

if __name__=='__main__':main()
