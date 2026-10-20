"""Fit four immutable old-route folds once, before any S2 recursive evaluation."""
from pathlib import Path
import argparse,hashlib,json,os,sys,traceback
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];AUDIT=ROOT/'research/POWERJOINT_AUDIT_RERUN_20261020'
sys.path.insert(0,str(ROOT/'research/R5_N4B_20261015'));sys.path.insert(0,str(AUDIT))
from n4b_rf_errors import site_weights
from scalar_power import ScalarPower
from model import ARMS,PowerModel,geometry,frame_features,inputs
from prepare_contract import splits,hash_keys

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('--execution-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    checks=[];errors=[];models={};inputs_proof={}
    try:
        assert os.environ.get('GITHUB_SHA'),'COMMITTED_ACTIONS_REQUIRED'
        lock=json.loads((HERE/'PROTOCOL_LOCK.json').read_text());labels=a.execution_root/'reference_ae/PACKETS_SOURCE_LABELS.csv.gz';cached_path=a.execution_root/'reference_ae/OOF_PARAMETERS.csv.gz'
        assert sha(labels)==lock['labels_sha256'];assert sha(cached_path)==lock['cached_oof_sha256']
        for f in [labels,cached_path,HERE/'PROTOCOL_LOCK.json',HERE/'TRAIN_SPLITS.json',Path(sys.modules['n4b_rf_errors'].__file__)]:inputs_proof[str(f)]=sha(f)
        df=pd.read_csv(labels);full=df[df.channel=='full'].copy().reset_index(drop=True);cached=pd.read_csv(cached_path)
        expected=json.loads((HERE/'TRAIN_SPLITS.json').read_text());got=splits(full);assert got==expected['folds'],'FROZEN_SPLITS_MISMATCH'
        cases={c['id']:c for c in json.loads((HERE/'CASE_METADATA.json').read_text())['legacy']}
        d,theta,X=geometry([[3.,4.,np.pi/2]],dict(anchor=[0.,0.,2.],robot_z_m=0.,mount_deg=45.))
        assert abs(d[0]-np.sqrt(29))<1e-14 and X.shape==(1,10)
        assert np.allclose(X[0,2:6],[np.cos(theta[0]),np.sin(theta[0]),np.cos(2*theta[0]),np.sin(2*theta[0])],atol=0,rtol=0)
        assert inputs('GEOM',[1],d,X)[0].tobytes()==inputs('GEOM',[999],d,X)[0].tobytes()
        checks.append(dict(check='FEATURE_ORDER_3D_DISTANCE_RADIANS_GEOM_Q_INDEPENDENCE',status='PASS'))
        t9=json.loads((AUDIT/'T9_SPEC/TRAIN_PARAMS.json').read_text())
        for fold,split in got.items():
            keys=pd.MultiIndex.from_tuples([tuple(x) for x in split['training_keys']]);index=pd.MultiIndex.from_frame(full[['case','pose_id']]);train=full.loc[index.isin(keys)].copy()
            assert hash_keys(train)==split['training_key_sha256']
            w=site_weights(np,pd,train);dd,XX=frame_features(train,cases);q=train.log_fp_power.to_numpy();Y=train[['e_r','e_s']].to_numpy()
            fold_models={}
            for arm in ARMS:
                A,b=inputs(arm,q,dd,XX);fit=PowerModel.fit(A,b,Y,w,arm,split['training_key_sha256']);mu,C=fit.predict(A,b)
                reloaded=PowerModel(json.loads(json.dumps(fit.record)));mm,cc=reloaded.predict(A,b)
                reload_diff=max(float(abs(mm-mu).max()),float(abs(cc-C).max()));assert reload_diff==0
                checks.append(dict(fold=fold,arm=arm,check='MODEL_SAVE_RELOAD_PREDICTION',max_abs_difference=reload_diff,status='PASS'))
                if arm in ['Q_POWER1','DIST_ONLY']:
                    scalar=ScalarPower(train,q if arm=='Q_POWER1' else dd,w,{})
                    sm,sc=scalar.predict(q if arm=='Q_POWER1' else dd);delta=max(float(abs(sm-mu).max()),float(abs(sc-C).max()))
                    assert delta<=1e-12,('SCALAR_ADAPTER_PARITY',fold,arm,delta)
                    checks.append(dict(fold=fold,arm=arm,check='EXISTING_SCALARPOWER_PARITY',max_abs_difference=delta,status='PASS',reference_fit_only=True))
                    if fold!='ALL_OLD':
                        old=next(x for x in t9 if x['held_route']==fold)['power_models']['Q_POWER1' if arm=='Q_POWER1' else 'DISTANCE_ONLY_POWER1']
                        delta=max(float(np.max(abs(np.asarray(old[k])-np.asarray(fit.record['cuts' if k=='cuts' else k])))) for k in ['scaler_mean','scaler_scale','ridge_coef','ridge_intercept','cuts','offsets','covs'])
                        assert delta<=1e-10,('T9_FIT_PARAMETER_PARITY',fold,arm,delta)
                        checks.append(dict(fold=fold,arm=arm,check='T9_FIT_PARAMETER_PARITY',max_abs_difference=delta,status='PASS'))
                fold_models[arm]=fit.record
            if fold!='ALL_OLD':
                target=df[df.route==fold];tc=cached[cached.route==fold] if 'route' in cached else cached[cached.case.str.startswith(fold+'_')]
                target=target.set_index(['case','channel','pose_id']).loc[pd.MultiIndex.from_frame(tc[['case','channel','pose_id']])].reset_index()
                tq=target.log_fp_power.to_numpy();mm,cc=PowerModel(fold_models['Q_POWER1']).predict(tq[:,None],tq)
                cm=tc[['mu_r','mu_s']].to_numpy();C=np.zeros_like(cc);C[:,0,0]=tc.C00;C[:,1,1]=tc.C11;C[:,0,1]=C[:,1,0]=tc.C01
                delta=max(float(abs(mm-cm).max()),float(abs(cc-C).max()));assert delta<=1e-10,('CACHED_Q_PARITY',fold,delta)
                checks.append(dict(fold=fold,check='CACHED_Q_MU_C_FULL_LOS_PARITY',max_abs_difference=delta,status='PASS',n=len(target)))
            models[fold]=dict(training_key_sha256=split['training_key_sha256'],n_train=len(train),models=fold_models)
        assert len(models)==4 and got['ALL_OLD']['includes_R2_A_M45']
    except Exception as e:errors.append(dict(error=str(e),traceback=traceback.format_exc(),retry=False))
    dump(a.out/'TRAIN_PARAMS.json',models);pd.DataFrame(checks).to_csv(a.out/'TRAIN_CHECKS.csv',index=False);dump(a.out/'ERRORS.json',errors)
    dump(a.out/'MANIFEST.json',dict(task='S2_TRAIN_ONLY',technical='TECHNICAL_PASS' if not errors else 'ERROR',source_commit=os.environ.get('GITHUB_SHA'),actions_run_id=os.environ.get('GITHUB_RUN_ID'),inputs=inputs_proof,trained_folds=list(models),recursive_filters_executed=False,outputs={f.name:sha(f) for f in a.out.iterdir() if f.is_file() and f.name!='MANIFEST.json'}))
    if errors:raise SystemExit(1)
    print('S2_TRAIN_ONLY_PASS',len(models),len(checks),flush=True)
if __name__=='__main__':main()
