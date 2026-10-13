from pathlib import Path
import ast, datetime, hashlib, json, subprocess, sys, traceback
import numpy as np

OUT=Path(__file__).resolve().parent
REPO=OUT.parent/'checkout'
DIAG=REPO/'research/EKF3_INDEPENDENT_20261013/diagnostics'
sys.path[:0]=[str(DIAG),str(DIAG.parent)]
import run_d0_d4 as d4
import run_d5_regimes as d5
import p2_frozen_rf_one_step as p2
import p3_compat as compat

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    start=datetime.datetime.now(datetime.timezone.utc).isoformat()
    evidence=OUT/'MOTION_INPUTS_P2';evidence.mkdir(exist_ok=False)
    p0=d4.read_p0();timelines=d5.timelines(p0);records=[]
    original=p2.generate
    active={}
    def capture(t,ds,dy,cfg,seed):
        values,evaluation=original(t,ds,dy,cfg,seed)
        np.savez_compressed(evidence/(active['route']+'.npz'),**values,
            initial_noise=p2.sensor_rng(seed,'initial').standard_normal(3)*np.array([.1,.1,np.radians(5)]))
        return values,evaluation
    p2.generate=capture
    for route,(t,truth,ids) in timelines.items():
        active['route']=route
        xp,pp,meta=p2.dr_only_pred(t,truth,0)
        case=next(c for c in p0['cases'] if c['route']==route)
        prior=np.load(OUT/'P2_DOWNLOAD/P2_OUT'/f"{case['id']}_full_seed0_ONE_STEP.npz")
        np.testing.assert_allclose(xp,prior['xminus'],rtol=0,atol=1e-9)
        np.testing.assert_allclose(pp,prior['Pminus'],rtol=0,atol=1e-9)
        records.append({'route':route,'metadata':meta,'input_file':route+'.npz','sha256':digest(evidence/(route+'.npz')),
            'max_x_difference':float(np.max(abs(xp-prior['xminus']))),'max_P_difference':float(np.max(abs(pp-prior['Pminus'])))})
    (evidence/'MANIFEST.json').write_text(json.dumps({'status':'PASS_RECONSTRUCTED_P2_PRIORS','seed':0,'condition':'noise_pair','level':1,'routes':records},indent=2))
    source=subprocess.check_output(['git','show','5058368123d40e621405113803816a749c19368f:research/LOS_RANGE_RECAL_20261012/p3_common.py'],cwd=REPO)
    (OUT/'p3_common_reference.py').write_bytes(source)
    tree=ast.parse(source);nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['tap_m','cir_mag','detect','e1_features','ridge_pred']]
    ns={'np':np,'O':d4.O,'C0':299792458.,'LEAD':.3};exec(compile(ast.Module(body=nodes,type_ignores=[]),'p3_common_reference.py','exec'),ns)
    freqs=np.load(REPO/'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/freqs_hz.npy')
    frozen=json.loads(d4.P3_MODEL.read_text());parity=[]
    for case in p0['cases']:
        for channel in ['los','full']:
            h=np.load(REPO/case[channel+'_path'],mmap_mode='r');sample=np.asarray(h[[0,len(h)//2,len(h)-1]])
            got=compat.frozen_detector(sample,freqs,case['mount_deg'],d4.O)
            st,_=ns['cir_mag'](sample);det=ns['detect'](st,ns['tap_m'](freqs))
            feat=ns['e1_features'](det,np.full(3,case['mount_deg']),ns['tap_m'](freqs))
            pred=ns['ridge_pred'](frozen['loro_fold_params'][case['route']]['E1'],feat)
            np.testing.assert_allclose(got['features'],feat,rtol=1e-12,atol=1e-12)
            np.testing.assert_allclose(got['r_d1_m'],det['r_d1'],rtol=1e-12,atol=1e-12)
            np.testing.assert_allclose(compat.predict_e1_bias(got['features'],frozen['loro_fold_params'][case['route']]),pred,rtol=1e-12,atol=1e-12)
            parity.append({'case':case['id'],'channel':channel,'samples':3})
    (OUT/'P3_REFERENCE_PARITY.json').write_text(json.dumps({'status':'PASS','reference_revision':'5058368123d40e621405113803816a749c19368f','checks':parity},indent=2))
    print('P2 motion reconstruction and P3 frozen feature/D1/E1 reference parity PASS',flush=True)
    result=d4.run(p2_dir=OUT/'P2_DOWNLOAD/P2_OUT',output_dir=OUT/'OUTPUT_D0_D4_SEED0',seed=0,include_los_e1_control=True)
    (OUT/'D04_EXECUTION_RECEIPT.json').write_text(json.dumps({'started_utc':start,'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO).decode().strip(),'python':sys.version,'numpy':np.__version__,'command':sys.argv,'harness_sha256':digest(__file__),'exit_code':0,'status':result['status'],'scientific_PASS':False},indent=2))
    print(json.dumps({k:result[k] for k in ['status','anchor_case_count','replayed_B_C_one_step_count','B0_matrix_max_abs_replay_difference','scientific_PASS']},indent=2),flush=True)

if __name__=='__main__':main()
