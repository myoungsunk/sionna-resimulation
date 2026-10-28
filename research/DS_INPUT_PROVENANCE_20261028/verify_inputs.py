"""Read-only validation of committed source mapping and frozen input joins."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import pandas as pd
import numpy as np

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
def digest(data): return hashlib.sha256(data).hexdigest()
def read_repo(path):
    # Works with sparse checkouts; do not import/run the historical scripts.
    data=subprocess.check_output(['git','-C',str(REPO),'show','HEAD:'+path])
    if data.startswith(b'version https://git-lfs.github.com/spec/v1'):
        raise RuntimeError('LFS_POINTER_NOT_DATA '+path)
    return data
def verify():
    manifest=json.loads((HERE/'INPUT_SOURCE_MAP.json').read_text())
    content={}
    for item in manifest['files']:
        data=(REPO/item['repo_path']).read_bytes() if item['new_in_this_package'] else read_repo(item['repo_path'])
        if digest(data)!=item['sha256']: raise RuntimeError('HASH_MISMATCH '+item['repo_path'])
        content[item['name']]=data
    tables={name:pd.read_csv(io.BytesIO(data),compression='gzip') for name,data in content.items() if name.endswith('.csv.gz')}
    feat=tables['OBSERVATION_FEATURES_LABELS.csv.gz'];par=tables['OOF_PARAMETERS.csv.gz']
    mr=tables['MR_SERIES.csv.gz'];hg=tables['HG_SERIES.csv.gz']
    cases=sorted(feat.case.unique())
    details=[]
    for case in cases:
        d=feat[(feat.case==case)&(feat.channel=='full')].set_index('pose_id')
        p=par[(par.case==case)&(par.channel=='full')&(par.model=='POWER_DIAG')].set_index('pose_id')
        assert d.index.is_unique and p.index.is_unique
        assert set(d.index)==set(p.index)
        p=p.loc[d.index]
        assert np.all(p.Crs==0)
        for bias in ('B0','L2'):
            q=mr[(mr.case==case)&(mr.channel=='full')&(mr.bias==bias)].set_index('pose_id')
            g=hg[(hg.case==case)&(hg.bias==bias)].set_index('pose_id')
            assert q.index.is_unique and g.index.is_unique
            # Replay uses a time-resampled subset of the RF feature packets.
            # Match run_stage.load_case's pose_id selection, not full-table equality.
            assert set(q.index)==set(g.index) and set(q.index)<=set(d.index)
            ds=d.loc[q.index];ps=p.loc[q.index];g=g.loc[q.index]
            np.testing.assert_allclose(q.t_s,g.t_s,atol=0,rtol=0)
            delta=np.asarray(ds.e_r-q['BASE__meas_r_cm']/100-ps.mu_r)
            np.testing.assert_allclose(delta,0,atol=1e-12,rtol=0)
            np.testing.assert_allclose(g.e_r,ds.e_r,atol=1e-12,rtol=0)
            pred=ds.e_r-q['MU_R_EXDS__meas_r_cm']/100
            assert np.isfinite(pred).all()
            details.append(dict(case=case,bias=bias,feature_rows=len(d),replay_rows=len(q),base_mu_max_abs=float(np.max(np.abs(delta)))))
    return dict(status='HASH_AND_SOURCE_JOIN_PASS',files=len(content),conditions=details,
                table_rows={k:len(v) for k,v in tables.items()},
                case_rows={k:v.groupby('case').size().to_dict() for k,v in tables.items()})
if __name__=='__main__': print(json.dumps(verify(),indent=2))
