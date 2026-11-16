"""Stage-0 archived trace accounting; never imports or executes a filter/model."""
from pathlib import Path
import argparse, csv, hashlib, json, datetime
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path('D:/SLAM_bot/artifacts/G1_FINAL_MODEL_STAGE0_20261116')
OUT = Path(__file__).resolve().parent
M6 = Path('D:/SLAM_bot/artifacts/G1_GM_THETA_M6_20261116')
PUB = Path('D:/SLAM_bot/g1_m5_pub_20261116/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/gm_theta_m6/inputs')
DEG = 180 / np.pi
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def wrap(x): return (x + np.pi) % (2*np.pi) - np.pi
def csvwrite(path, rows):
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
def load(p):
    with np.load(p, allow_pickle=False) as z: return {k:z[k] for k in z.files}

def run(contract_path):
    contract_path=Path(contract_path)
    if not contract_path.is_file(): raise RuntimeError('Frozen root RUN_CONTRACT is required')
    contract=json.loads(contract_path.read_text(encoding='utf-8-sig'))
    assert sha(contract_path)=='3e6413fa4294ab8e5568b9811477504f02711eb8f8585846da989edff713eb59'
    lane=dict(question_id=contract['question_id']+'/R2',classification='DIAGNOSTIC_ONLY',root_contract=dict(path=str(contract_path),sha256=sha(contract_path)),code=dict(path=str(Path(__file__)),sha256=sha(__file__)),seeds=[10,11,12,13,14],primary_seeds=[10,11],no_replay=True,frozen_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    lane_path=OUT/'RUN_CONTRACT_ATTEMPT02.json'
    if lane_path.exists():
        old=json.loads(lane_path.read_text(encoding='utf-8'))
        if old['code']!=lane['code']: raise RuntimeError('Lane code changed after freeze; use a new attempt')
    else: lane_path.write_text(json.dumps(lane,indent=2),encoding='utf-8')
    pinned={str(Path(r['path'])).casefold():r['sha256'] for r in contract['bindings']}
    lock_path=M6/'characterization/RUN_CONTRACT.json'
    lock=json.loads(lock_path.read_text(encoding='utf-8-sig'))
    evaluator=PUB/'R2_evaluator.npz'; ev=load(evaluator)
    t=ev['t']; truth=ev['truth']; dtrue=np.r_[0.,wrap(np.diff(truth[:,2]))]
    inputs={str(p):sha(p) for p in [contract_path,lock_path,evaluator]}
    source_paths=[M6/'gm_replay.py', Path('D:/SLAM_bot/artifacts/G1_HFKI_M5_STAGE0_20261116/check_seed_data.py'),Path('D:/SLAM_bot/artifacts/G1_HFKI_M5_STAGE0_20261116/SEED_DATA_READINESS.json'),Path('D:/SLAM_bot/artifacts/G1_HFKI_M5_20261116/run_stage3.py')]
    sources={str(p):sha(p) for p in source_paths}
    sources[str(Path(__file__))]=sha(__file__)
    rows=[]; summaries=[]; checks=[]; arrays={}
    common_mask=None
    for seed in (10,11,12,13,14):
        binding=next(c for c in lock['cells'] if c['route']=='R2')['online'] if seed==10 else lock['online_packets'][str(seed)]['R2']
        online_path=Path(binding['path'])
        online=load(online_path); inputs[str(online_path)]=sha(online_path)
        assert sha(online_path)==binding['sha256']
        np.testing.assert_array_equal(t,online['t'])
        noise=online['gy']-dtrue
        for arm in ('G0','G1_LORO','G1_KI'):
            sub='implementation' if arm=='G0' else ('seed10/seed10' if seed==10 else f'seed11_14/seed{seed}')
            trace_path=M6/'attempt_02'/sub/(f'seed{seed}' if arm=='G0' else '')/f'R2_{arm}.npz'
            a=load(trace_path); inputs[str(trace_path)]=sha(trace_path)
            if arm=='G0':
                a.update(Knu=np.einsum('nij,nj->ni',a['K'],a['nu']),R_ref=a['Reff'],b_theta=np.zeros(len(t)),b_theta_prior=np.zeros(len(t)),q_s=np.zeros(len(t)),causal=np.zeros(len(t)),g=np.abs(a['H'][:,1,2]),distance=np.linalg.norm(a['prior'][:,:2]-np.array([10.,0.]),axis=1))
            np.testing.assert_array_equal(t,a['t']); np.testing.assert_array_equal(ev['pose_id'],a['pose_id'])
            if common_mask is None: common_mask=a['mask'].copy()
            np.testing.assert_array_equal(common_mask,a['mask'])
            c=a['S'][:,1,0]/a['S'][:,0,0]
            cond=a['nu'][:,1]-c*a['nu'][:,0]
            dr=(a['K'][:,:,0]+c[:,None]*a['K'][:,:,1])*a['nu'][:,0,None]
            ds=a['K'][:,:,1]*cond[:,None]
            np.testing.assert_allclose(dr+ds,a['Knu'],rtol=0,atol=1e-10)
            bg=np.r_[0.,a['x'][:-1,3]]
            bgterm=-bg*online['dt']; bgterm[0]=0
            prednoise=noise.copy(); prednoise[0]=0
            error=wrap(a['x'][:,2]-truth[:,2])
            priorerror=wrap(a['prior'][:,2]-truth[:,2])
            prev=np.r_[priorerror[0],error[:-1]]
            pres=wrap(priorerror-prev-prednoise-bgterm)
            ures=wrap(error-priorerror-dr[:,2]-ds[:,2])
            np.testing.assert_allclose(pres,0,rtol=0,atol=1e-10)
            np.testing.assert_allclose(ures,0,rtol=0,atol=1e-10)
            bt=a['b_theta']; bp=a['b_theta_prior']; decay=np.r_[0.,bp[1:]-bt[:-1]]
            bdr=np.zeros(len(t)); bds=bdr.copy()
            if 'K_aug' in a:
                bdr=(a['K_aug'][:,4,0]+c*a['K_aug'][:,4,1])*a['nu'][:,0]
                bds=a['K_aug'][:,4,1]*cond
                np.testing.assert_allclose(bt-bp,bdr+bds,rtol=0,atol=1e-10)
                np.testing.assert_allclose(bp[1:],a['alpha'][1:]*bt[:-1],rtol=0,atol=1e-10)
            infl=a['Reff'][:,1,1]/a['R_ref'][:,1,1]
            data=dict(error=error,priorerror=priorerror,noise=prednoise,bgterm=bgterm,dr=dr[:,2],ds=ds[:,2],bt=bt,bp=bp,decay=decay,bdr=bdr,bds=bds,infl=infl,q=a['q_s'],causal=a['causal'],distance=a['distance'])
            arrays[seed,arm]=data
            for i,time in enumerate(t):
                rows.append(dict(seed=seed,arm=arm,t_s=float(time),pose_id=int(a['pose_id'][i]),accepted=bool(a['mask'][i]),distance_m=float(a['distance'][i]),g=float(a['g'][i]),heading_error_deg=float(error[i]*DEG),prior_error_deg=float(priorerror[i]*DEG),sigma_heading_deg=float(np.sqrt(a['P'][i,2,2])*DEG),gyro_white_deg=float(prednoise[i]*DEG),bg_est_deg_s=float(bg[i]*DEG),bg_correction_deg=float(bgterm[i]*DEG),range_update_deg=float(dr[i,2]*DEG),conditional_s_update_deg=float(ds[i,2]*DEG),btheta_deg=float(bt[i]*DEG),btheta_prior_deg=float(bp[i]*DEG),btheta_decay_deg=float(decay[i]*DEG),btheta_range_update_deg=float(bdr[i]*DEG),btheta_s_update_deg=float(bds[i]*DEG),s_inflation=float(infl[i]),q_s=float(a['q_s'][i]),causal_s=float(a['causal'][i]),Rref_ss=float(a['R_ref'][i,1,1])))
            for lo,hi in [(0,float(t[-1])+1),(80,120),(120,160)]+[(x,x+20) for x in range(0,int(t[-1])+1,20)]:
                m=(t>=lo)&(t<hi); idx=np.flatnonzero(m)
                if not len(idx): continue
                j=idx[0]; end=idx[-1]
                s=dict(seed=seed,arm=arm,start_s=lo,end_s=hi,n=int(m.sum()),heading_rmse_deg=float(np.sqrt(np.mean(error[m]**2))*DEG),sigma_heading_rms_deg=float(np.sqrt(np.mean(a['P'][m,2,2]))*DEG),heading95=float(np.mean(error[m]**2/a['P'][m,2,2]<=3.841458820694124)),btheta_mean_deg=float(bt[m].mean()*DEG),btheta_rms_deg=float(np.sqrt(np.mean(bt[m]**2))*DEG),s_inflation_median=float(np.median(infl[m])),s_inflation_remote_median=float(np.median(infl[m&(a['distance']>=3)])) if np.any(m&(a['distance']>=3)) else None,q_median=float(np.median(a['q_s'][m])),remote_fraction=float(np.mean(a['distance'][m]>=3)),error_start_prior_deg=float(prev[j]*DEG),error_end_deg=float(error[end]*DEG))
                for k in ('noise','bgterm','dr','ds','decay','bdr','bds'): s[k+'_sum_deg']=float(data[k][m].sum()*DEG)
                s['ledger_residual_deg']=float(wrap(error[end]-prev[j]-sum(data[k][m].sum() for k in ('noise','bgterm','dr','ds')))*DEG)
                summaries.append(s)
            checks.append(dict(seed=seed,arm=arm,prediction_max_abs_rad=float(np.max(np.abs(pres))),update_max_abs_rad=float(np.max(np.abs(ures))),conditional_update_max_abs=float(np.max(np.abs(dr+ds-a['Knu']))),rejected_update_max_abs=float(np.max(np.abs(a['Knu'][~a['mask']]))) if np.any(~a['mask']) else 0.))
    for path,digest in {**inputs,**sources}.items():
        if path.casefold() in pinned: assert digest==pinned[path.casefold()], path
        assert sha(path)==digest, 'Input/source changed during analysis: '+path
    csvwrite(OUT/'PACKET_TIMELINE.csv',rows); csvwrite(OUT/'WINDOW_SUMMARY.csv',summaries)
    fig,axes=plt.subplots(4,2,figsize=(14,11),sharex=True)
    for col,seed in enumerate((10,11)):
        for arm,color in [('G0','0.5'),('G1_LORO','tab:blue'),('G1_KI','tab:red')]:
            d=arrays[seed,arm]; axes[0,col].plot(t,d['error']*DEG,label=arm,color=color,lw=1)
        d=arrays[seed,'G1_KI']; axes[1,col].plot(t,d['bt']*DEG,label='b_theta'); axes[1,col].plot(t,d['bp']*DEG,label='prior',alpha=.6)
        axes[2,col].plot(t,d['infl'],label='R_ss / Rref_ss'); axes[2,col].set_yscale('log')
        for k,label in [('noise','gyro white'),('bgterm','estimated bg correction'),('dr','conditional range'),('ds','conditional s')]: axes[3,col].plot(t,np.cumsum(d[k])*DEG,label=label)
        for row in range(4):
            axes[row,col].axvspan(80,120,color='tab:blue',alpha=.04); axes[row,col].axvspan(120,160,color='tab:orange',alpha=.04); axes[row,col].grid(alpha=.25); axes[row,col].legend(fontsize=8)
        axes[0,col].set_title(f'R2, seed {seed}'); axes[3,col].set_xlabel('Time (s)')
    for ax,label in zip(axes[:,0],['Heading error (deg)','b_theta (deg)','s inflation','Cumulative increment (deg)']):ax.set_ylabel(label)
    fig.tight_layout(); fig.savefig(OUT/'R2_SEED_DECOMPOSITION.png',dpi=180); plt.close(fig)
    result=dict(classification='DIAGNOSTIC_ONLY',root_contract_sha256=sha(contract_path),definitions=dict(prediction='gyro_white - previous_estimated_bg * dt; true bias=0 per archived noise_pair config',conditional_channels='c=S_sr/S_rr; range=(K_r+c*K_s)*nu_r; s=K_s*(nu_s-c*nu_r)',remote='prior distance >=3m, descriptive only',truth_use='offline scoring and exact arithmetic accounting only; no replay',causal_limit='Archived additive accounting identifies contributions to realized error, not intervention effects or population causality.'),windows=summaries,checks=checks,inputs=inputs,sources=sources)
    (OUT/'SUMMARY.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    receipt=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command='python analyze_r2.py --contract '+str(contract_path),exit_code=0,no_replay=True,inputs=inputs,sources=sources,outputs={p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.name not in ('EXECUTION.json','analyze_r2.py')})
    (OUT/'EXECUTION.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(dict(checks=checks,windows=[s for s in summaries if (s['start_s'],s['end_s']) in [(80,120),(120,160)]]),indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--contract',required=True); run(p.parse_args().contract)
