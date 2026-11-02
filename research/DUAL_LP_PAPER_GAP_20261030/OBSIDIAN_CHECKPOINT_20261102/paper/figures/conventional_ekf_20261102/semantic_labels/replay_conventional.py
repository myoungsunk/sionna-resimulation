import os,sys,json,hashlib,datetime,platform
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent/'DualLP_Physics_Link_Validation_20261101'
OUT=Path(sys.argv[1]); PKG=Path(sys.argv[2]); OUT.mkdir(parents=True,exist_ok=True)
os.environ['REFLECT_ROOT']=str(ROOT/'recovered/inputs')
sys.path.insert(0,str(ROOT/'recovered/legacy/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/code'))
import diag_mbvar as DG
from p3_rf_adapter4 import R0
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
cases=['R2_aB_m0','R4_aB_m0','R5_aB_m0']; biases=['B0','L0','L1','L2']
contract=dict(question_id='DLP-CONVENTIONAL-THREE-STAGE-20261102',roles='PROPOSER then IMPLEMENTER, self-check only',
    source_code_commit='9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13',evidence_commit='6c7200091028fd3f0e55aa83b777d0f10b7cf063',
    cases=cases,biases=biases,intervention='LOS and Full: mu=[0,0], constant R0, no added variance, same SourceFFD observer',
    R0=R0.tolist(),retained_observer_range_offset_m=-0.5315983906250129,
    offset_scope='Fixed raw-range observation convention shared by all arms, not BB/MB multipath mean correction',
    proposed='Archived MB_VAR self gate, unchanged frozen Full donor means and previous-posterior variance lookup',
    controls='Original sensor generator, seed0, same x0/P0, Q, 4 states, sampling, self NIS 9.210340371976184',
    scoring='all samples t>=30-1e-9, including rejected packets',parity='BB_ORIG and MB_VAR B0, all3routes; X/P 1e-10, mask exact, R 1e-12',
    no_RT=True,no_refit=True,expected_new_replays=24,allowed_claim='Retrospective one-scene simulation; improvement is not assumed',
    governance={n:sha(Path('C:/Users/Myoungsun Kim/.codex/research-governance')/n) for n in ['COMMON_CONTRACT.md','ROLE_PROPOSER.md','ROLE_IMPLEMENTER.md']},
    script_sha256=sha(Path(__file__)),started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),python=sys.version,platform=platform.platform())
(OUT/'CONTRACT.json').write_text(json.dumps(contract,indent=2),encoding='utf-8')
model=DG.C.base_model(); rows=[]; parity=[]; packets=[]
ledger=pd.read_csv(PKG/'tables/PHYSICAL_LOS_FULL_PACKET_3136.csv')
for case in cases:
    D0=DG.load(case,'B0',model)
    for arm,bg,mode in [('BB_ORIG','BB','orig'),('MB_VAR','MB','var')]:
        X,P,L=DG.run(D0,bg,mode,'self',model=model)
        ref=np.load(ROOT/f'results/traces/{case}__B0__{arm}__self.npz')
        dx=float(abs(X-ref['X']).max()); dp=float(abs(P-ref['PX']).max()); dm=int(np.count_nonzero(L['used']!=ref['used']))
        dr=float(np.nanmax(abs(L['Ru']-ref['Ru'])))
        assert dx<1e-10 and dp<1e-10 and dm==0 and dr<1e-12,(case,arm,dx,dp,dm,dr)
        parity.append(dict(case=case,arm=arm,X_max_abs=dx,P_max_abs=dp,mask_mismatch=dm,R_max_abs=dr))
        print('PARITY',parity[-1],flush=True)
    for bias in biases:
        D=dict(D0);D['bias']=bias
        if bias!='B0':
            ds,gy,dt,x0=DG.PB.build_controls(D['t'],D['gt'][:,:3],bias)
            D.update(ds=ds,gy=gy,dt=dt,x0=np.r_[x0,0.])
        los=np.load(PKG/f'tables/{case}_{bias}_LOS_ZERO_MEAN.npz')
        Z=los['z_los']; phys=ledger[ledger.case==case]
        assert np.max(abs(Z[:,0]-phys.LoS_r_m.to_numpy()))<1e-9
        assert np.max(abs(Z[:,1]-phys.LoS_s.to_numpy()))<1e-12
        assert np.max(abs(D['z'][:,0]-phys.Full_r_m.to_numpy()))<1e-9
        assert np.max(abs(D['z'][:,1]-phys.Full_s.to_numpy()))<1e-12
        for stage,z in [('LOS_EKF',Z),('MULTIPATH_EKF',D['z']),('PROPOSED_MB_VAR',D['z'])]:
            if stage=='PROPOSED_MB_VAR':
                saved=np.load(ROOT/f'results/traces/{case}__{bias}__MB_VAR__self.npz');X=saved['X'];P=saved['PX'];L={k:saved[k] for k in ['used','nis','Ru']}
            else:
                E=dict(D,z=z,R=np.broadcast_to(R0,(len(z),2,2)).copy(),mu={'BB':np.zeros_like(z)})
                X,P,L=DG.run(E,'BB','orig','self',model=model)
                assert np.array_equal(L['Ru'],E['R']) and not np.any(E['mu']['BB'])
                np.savez_compressed(OUT/f'{case}_{bias}_{stage}.npz',X=X,PX=P,t=D['t'],gt=D['gt'],z=z,**L)
            assert np.isfinite(X).all() and np.isfinite(P).all()
            metrics=DG.scores(D,X,P)
            e=D['gt'][:,:3]-X[:,:3];e[:,2]=np.angle(np.exp(1j*e[:,2])); score=D['t']>=30-1e-9
            row=dict(case=case,route=case[:2],bias=bias,stage=stage,n_total=len(z),n_score=int(score.sum()),n_used=int(L['used'].sum()),**metrics); rows.append(row)
            rho=np.hypot(D['gt'][:,0]-D['anchor'][0],D['gt'][:,1]-D['anchor'][1])
            packets.append(pd.DataFrame(dict(case=case,bias=bias,stage=stage,t_s=D['t'],rho_true_m=rho,travel_m=np.r_[0,np.cumsum(np.linalg.norm(np.diff(D['gt'][:,:2],axis=0),axis=1))],heading_error_deg=np.degrees(e[:,2]),xy_error_cm=100*np.linalg.norm(e[:,:2],axis=1),used=L['used'],nis=L['nis'],scored=score)))
            print('RESULT',case,bias,stage,metrics['head_rmse'],metrics['xy_rmse_cm'],row['n_used'],flush=True)
        pd.DataFrame(rows).to_csv(OUT/'THREE_STAGE_SCORES.csv',index=False)
pd.DataFrame(parity).to_csv(OUT/'BASELINE_PARITY.csv',index=False)
pd.concat(packets,ignore_index=True).to_csv(OUT/'TIME_DISTANCE_ERRORS.csv.gz',index=False)
assert len(rows)==36 and len({(r['case'],r['bias'],r['stage']) for r in rows})==36
inputs={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'recovered').rglob('*') if p.is_file() and p.suffix in ['.py','.npz','.npy','.json']}
(OUT/'INPUT_HASHES.json').write_text(json.dumps(inputs,indent=2),encoding='utf-8')
(OUT/'RUN_QA.json').write_text(json.dumps(dict(status='PASS',new_replays=24,archived_proposed=12,baseline_parity=6,score_rows=36,finite=True,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),independent_audit=False),indent=2),encoding='utf-8')
print('COMPLETE',flush=True)
