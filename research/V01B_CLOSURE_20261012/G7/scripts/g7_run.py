import sys,json,time,hashlib,types
import numpy as np,pandas as pd
from pathlib import Path
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad');G=S/'g7'
def load_module(src_path,name):
    src=open(src_path).read()
    for a,b in (("Path('/job')",f"Path('{G}/job')"),("Path('/input/BLOCK_C')",f"Path('{G}/input/BLOCK_C')"),("Path('/lut')",f"Path('{G}/lut')"),("Path('/routes/source/results/DRIVE_SIM_20261007/S1/routes')",f"Path('{G}/none')")):
        src=src.replace(a,b)
    m=types.ModuleType(name);m.__dict__['__name__']=name;exec(compile(src,str(src_path),'exec'),m.__dict__);return m
def run(cases_filter=None,features_script='features.py',outdir=None):
    audit=load_module(G/'pub/audit.py','g7_audit');feat=load_module(G/f'pub/{features_script}','g7_feat')
    cases=json.loads((G/'input/BLOCK_C/CASES.json').read_text())
    if cases_filter:cases=[c for c in cases if c['case'] in cases_filter]
    obs_dir=G/'job/OBS';obs_dir.mkdir(exist_ok=True,parents=True)
    for f in obs_dir.glob('*.npz'):f.unlink()
    t0=time.time();audits=[audit.work(c) for c in cases];print('observation audit (frozen audit.py work(), all parity asserts active):',len(audits),'cases %.0fs'%(time.time()-t0),flush=True)
    outs=[feat.calc(c) for c in cases];features=pd.concat([o[0] for o in outs],ignore_index=True);labels=pd.concat([o[1] for o in outs],ignore_index=True)
    assert not features.duplicated(['case','pose_id']).any();return features,labels,audits
if __name__=='__main__':
    case=sys.argv[1];script=sys.argv[2]
    f,l,a=run({case},script);pf=pd.read_csv(G/'pub/01_FEATURES.csv');pl=pd.read_csv(G/'pub/02_LABELS_EVAL_ONLY.csv')
    for name,new,pub in (('features',f,pf),('labels',l,pl)):
        pub=pub[pub.case==case].reset_index(drop=True);new=new.reset_index(drop=True);assert list(new.columns)==list(pub.columns),(name,set(new.columns)^set(pub.columns));worst=0.;bad=[]
        for c in pub.columns:
            if pub[c].dtype.kind in 'fc':
                d=np.nanmax(np.abs(new[c].to_numpy(float)-pub[c].to_numpy(float)));rel=d/max(np.nanmax(np.abs(pub[c].to_numpy(float))),1e-300);nan_same=bool((np.isnan(new[c])==np.isnan(pub[c])).all());worst=max(worst,rel)
                if d>1e-12*max(1,np.nanmax(np.abs(pub[c].to_numpy(float)))) or not nan_same:bad.append((c,float(d)))
            elif not (new[c].astype(str)==pub[c].astype(str)).all():bad.append((c,'non-float mismatch'))
        print(script,name,case,'rows',len(new),'| columns differing beyond 1e-12:',bad if bad else 'none','| worst relative %.1e'%worst)
