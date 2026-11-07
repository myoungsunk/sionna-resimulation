"""Validate completeness and invariants of a downloaded run; no estimator rerun."""
from pathlib import Path
import csv,gzip,hashlib,io,json,math,zipfile
import numpy as np
R=Path(__file__).resolve().parent
OUT=R/'run_v1_results'
METHODS=('DR3','DR4','S3','S4','J3','J4','SR3','SR4')
MODES=('one_step','recursive')
BIAS={'B0':0.,'L0':.01,'L1':.05,'L2':.2}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def validate():
    job=json.loads((OUT/'replay/FINAL.json').read_text())
    score=json.loads((OUT/'score/FINAL.json').read_text())
    preflight=json.loads((OUT/'PREFLIGHT.json').read_text())
    audit=json.loads((OUT/'audit/AUDIT.json').read_text())
    assert audit['decision']=='GO' and preflight['status']=='PASS'
    assert job['status']=='RUN_COMPLETED' and job['total_case_level_channels']==8
    assert score['metrics_count']==128 and score['contrasts_count']==144 and score['technical_PASS']
    assert not job['scientific_PASS'] and not score['scientific_PASS']
    rows=list(csv.DictReader((OUT/'score/R2_BIAS_METRICS.csv').open()))
    keys={(r['case'],r['rf_channel'],r['level'],r['evaluation_mode'],r['method']) for r in rows}
    expected={('R2_aB_m0',c,b,m,a) for c in ('los','full') for b in BIAS for m in MODES for a in METHODS}
    assert keys==expected and len(rows)==len(keys)==128
    for r in rows:
        assert int(r['eval_frames_expected'])==829 and int(r['frames_valid'])==829
        for key in ('pose_rmse_m','heading_rmse_deg','pose_nees_mean','heading95_coverage'):
            assert math.isfinite(float(r[key]))
        if not r['method'].startswith('DR'):assert int(r['gate_applied'])+int(r['gate_rejected'])==829
    with zipfile.ZipFile(R/'input/anchor_b_frozen.zip') as arc:
        raw=arc.read('P2_OUT/R2_aB_m0_los_seed0_ONE_STEP.npz')
        with np.load(io.BytesIO(raw)) as z:t=z['t_s'].copy();ids=z['pose_id'].copy();gt=z['truth_for_offline_scoring_only'].copy()
    travel=np.r_[0,np.cumsum(np.linalg.norm(np.diff(gt[:,:2],axis=0),axis=1))]
    rho=np.hypot(gt[:,0]-10,gt[:,1]);n=len(t)
    all_dr={};files=[];minimum_cov_eig=float('inf')
    export=OUT/'FIGURE_TIME_DISTANCE.csv.gz'
    with gzip.open(export,'wt',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['channel','level','mode','method','t_s','pose_id','travel_m','horizontal_anchor_distance_m','heading_error_deg','xy_error_m','estimated_bias_dps','heading_sigma_deg','status','nis','scored'])
        for channel in ('los','full'):
            for bias in BIAS:
                for mode in MODES:
                    p=OUT/f'replay/R2_aB_m0_{channel}_{bias}_seed0_{mode}.npz';files.append(p)
                    with np.load(p,allow_pickle=False) as z:
                        assert np.array_equal(z['t_s'],t) and np.array_equal(z['pose_id'],ids)
                        assert tuple(z['names'].tolist())==METHODS
                        X=z['estimate'];P=z['covariance'];status=z['status'];nis=z['nis']
                        assert X.shape==(n,8,4) and P.shape==(n,8,4,4)
                        assert not np.char.startswith(status,'INVALID').any()
                        for j,arm in enumerate(METHODS):
                            dim=int(arm[-1]);x=X[:,j,:dim];cov=P[:,j,:dim,:dim]
                            assert np.isfinite(x).all() and np.isfinite(cov).all()
                            assert np.allclose(cov,cov.transpose(0,2,1),rtol=0,atol=1e-12)
                            eig=float(np.linalg.eigvalsh(cov).min());minimum_cov_eig=min(minimum_cov_eig,eig);assert eig>0
                            e=x[:,:3]-gt;e[:,2]=(e[:,2]+np.pi)%(2*np.pi)-np.pi
                            if arm.startswith('DR'):
                                assert np.all(status[:,j]=='DR_ONLY')
                                if dim==4:assert np.all(x[:,3]==0)
                                key=(bias,arm)
                                if key in all_dr:
                                    assert np.array_equal(x,all_dr[key][0]) and np.array_equal(cov,all_dr[key][1])
                                else:all_dr[key]=(x.copy(),cov.copy())
                            else:assert set(status[:,j])<= {'APPLIED','REJECT'}
                            for k in range(n):
                                w.writerow([channel,bias,mode,arm,t[k],ids[k],travel[k],rho[k],np.degrees(e[k,2]),np.linalg.norm(e[k,:2]),np.degrees(x[k,3]) if dim==4 else '',np.degrees(np.sqrt(cov[k,2,2])),status[k,j],nis[k,j],int(t[k]>=30)])
    assert len(files)==16
    for c in job['cases']:
        assert c['timepoints']==979 and all(v==0 for v in c['invalid_model_frames'].values())
        if c['level']=='B0':assert max(c['B0_archived_DR_prior_parity'])<=1e-7
    interesting=[r for r in rows if r['evaluation_mode']=='recursive' and r['level'] in ('B0','L2') and r['method'] in ('DR3','DR4','S3','S4','J3','J4')]
    with (OUT/'FIGURE_MAIN_COMPARISON.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=interesting[0].keys());w.writeheader();w.writerows(interesting)
    hashes={p.relative_to(OUT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file()}
    receipt={'question_id':'DLP-ANCHORB-8ARM-20261102','execution':'COMPLETED','validation':'PASS_SELF_CHECK',
             'npz_files':16,'metric_rows':128,'contrast_rows':144,'samples_per_trace':979,'scored_per_trace':829,
             'minimum_active_covariance_eigenvalue':minimum_cov_eig,'DR_channel_and_mode_identity':True,
             'finite_states_and_covariances':True,'invalid_model_frames':0,'scientific_PASS':False,'independent_audit':False,
             'file_sha256':hashes}
    (OUT/'RESULT_VALIDATION.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k!='file_sha256'},indent=2))
    for r in interesting:print(r['rf_channel'],r['level'],r['method'],'heading_deg',r['heading_rmse_deg'],'xy_m',r['pose_rmse_m'])

if __name__=='__main__':validate()
