"""V5: archived HG/MR mean prediction -> original CONTROL, no fresh model inference."""
from __future__ import annotations
import json,time
from pathlib import Path
import numpy as np
import pandas as pd
from bootstrap import ROOT,REC,INPUT,RESULTS,TABLES,CASES,digest,write_json

def main() -> None:
    start=time.time(); folder=REC/'lineage'
    lock=json.loads((folder/'LINEAGE_INPUT_LOCK.json').read_text())
    for row in lock:
        assert digest(folder/row['path'])==row['sha256'],row['path']
    hg=pd.read_csv(folder/'HG_SERIES.csv.gz')
    mr=pd.read_csv(folder/'MR_SERIES.csv.gz')
    rows=[];groups=[]
    for case in CASES:
        for bias in ('B0','L2'):
            with np.load(INPUT/'traces'/f'{case}_{bias}_CONTROL.npz',allow_pickle=False) as z:
                d=dict(z)
            ids=d['pose_id'];t=d['t_s'];names=d['names'].tolist()
            jb=names.index('OFF_BB');jm=names.index('OFF_MB')
            h=hg[(hg.case==case)&(hg.bias==bias)].set_index('pose_id')
            m=mr[(mr.case==case)&(mr.bias==bias)&(mr.channel=='full')].set_index('pose_id')
            assert h.index.is_unique and m.index.is_unique
            assert set(h.index)==set(ids) and set(m.index)==set(ids)
            h=h.loc[ids];m=m.loc[ids]
            assert np.array_equal(h.index.to_numpy(),ids) and np.array_equal(m.index.to_numpy(),ids)
            assert np.array_equal(h.t_s.to_numpy(),t) and np.array_equal(m.t_s.to_numpy(),t)
            # Exact equation in archived x1/run_stage.py::load_case, not a fitted model.
            bb=h.e_r.to_numpy()-m['BASE__meas_r_cm'].to_numpy()/100
            mb=h.e_r.to_numpy()-m['MU_R_EXDS__meas_r_cm'].to_numpy()/100
            db=bb-d['mu'][:,jb,0];dm=mb-d['mu'][:,jm,0]
            passed=(np.abs(db)<=1e-12)&(np.abs(dm)<=1e-12)
            assert np.isfinite(bb).all() and np.isfinite(mb).all()
            frame=pd.DataFrame(dict(case=case,bias=bias,pose_id=ids,t_s=t,
               archived_e_r=h.e_r.to_numpy(),archived_BASE_meas_r_cm=m['BASE__meas_r_cm'].to_numpy(),
               archived_EXDS_meas_r_cm=m['MU_R_EXDS__meas_r_cm'].to_numpy(),
               recovered_mu_BB_r=bb,CONTROL_mu_BB_r=d['mu'][:,jb,0],diff_BB_r=db,
               recovered_mu_MB_r=mb,CONTROL_mu_MB_r=d['mu'][:,jm,0],diff_MB_r=dm,pass_check=passed))
            rows.append(frame)
            groups.append(dict(case=case,bias=bias,rows=len(ids),max_abs_BB_r=float(np.max(np.abs(db))),
                               max_abs_MB_r=float(np.max(np.abs(dm))),pass_check=bool(passed.all())))
    out=pd.concat(rows,ignore_index=True)
    out.to_csv(TABLES/'V5_ARCHIVED_PREDICTION_TO_CONTROL_6272.csv.gz',index=False,float_format='%.17g')
    pd.DataFrame(groups).to_csv(TABLES/'V5_ARCHIVED_MEAN_LINEAGE_SUMMARY.csv',index=False,float_format='%.17g')
    qa=dict(rows=len(out),groups=groups,archived_prediction_replay='PASS' if bool(out.pass_check.all()) else 'FAIL',
            max_abs_BB_r=float(out.diff_BB_r.abs().max()),max_abs_MB_r=float(out.diff_MB_r.abs().max()),
            exact_keys_and_timestamps=True,tolerance_m=1e-12,
            source_commit='9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13',
            source_loader_blob='79411df8de0612f06133ffd0a46775b7e126b065',
            fresh_model_inference='BLOCKED_MODEL_SCALER_FOLD_ARTIFACTS_NOT_RECOVERED',
            model_retraining=0,audit='SELF_REVIEW_ONLY',seconds=time.time()-start)
    write_json(RESULTS/'MEAN_LINEAGE_QA.json',qa)
    print(json.dumps(qa,indent=2),flush=True)
    assert len(out)==6272 and bool(out.pass_check.all())
if __name__=='__main__': main()
