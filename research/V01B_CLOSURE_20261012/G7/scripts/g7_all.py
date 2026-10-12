import sys,json,hashlib
sys.path.insert(0,'/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad')
import numpy as np,pandas as pd
from pathlib import Path
import g7_run as R
G=R.G;out=G/'out';out.mkdir(exist_ok=True)
f,l,a=R.run(None,'features.py')
f.to_csv(out/'01_FEATURES_12.csv',index=False);l.to_csv(out/'02_LABELS_EVAL_ONLY_12.csv',index=False);json.dump(a,open(out/'AUDIT_PARITY_12.json','w'),indent=1,default=float)
pf=pd.read_csv(G/'pub/01_FEATURES.csv');pl=pd.read_csv(G/'pub/02_LABELS_EVAL_ONLY.csv');old=set(pf.case)
print('rows generated:',len(f),'(existing 7 cases:',int(f.case.isin(old).sum()),', new 5 cases:',int((~f.case.isin(old)).sum()),') | published rows:',len(pf))
rep={}
for name,new,pub in (('features',f,pf),('labels',l,pl)):
    new7=new[new.case.isin(old)].sort_values(['case','pose_id']).reset_index(drop=True);pub=pub.sort_values(['case','pose_id']).reset_index(drop=True)
    assert len(new7)==len(pub) and list(new7.columns)==list(pub.columns) and (new7[['case','pose_id']].values==pub[['case','pose_id']].values).all()
    cols={};worst_abs=0.;nonfloat_bad=[]
    for c in pub.columns:
        if pub[c].dtype.kind=='f':
            x,y=new7[c].to_numpy(float),pub[c].to_numpy(float);nan_ok=bool((np.isnan(x)==np.isnan(y)).all());d=float(np.nanmax(np.abs(x-y))) if np.isfinite(x).any() else 0.;scale=float(max(np.nanmax(np.abs(y)),1.0));cols[c]=dict(max_abs=d,max_rel_to_scale=d/scale,nan_pattern_equal=nan_ok);worst_abs=max(worst_abs,d/scale)
        else:
            if not (new7[c].astype(str)==pub[c].astype(str)).all():nonfloat_bad.append(c)
    rep[name]=dict(rows=len(pub),columns=len(pub.columns),worst_rel_to_scale=worst_abs,pass_1e12=bool(worst_abs<=1e-12 and not nonfloat_bad and all(v['nan_pattern_equal'] for v in cols.values())),nonfloat_mismatch=nonfloat_bad,worst_columns=sorted(((v['max_rel_to_scale'],k) for k,v in cols.items()),reverse=True)[:4])
    print(name,'regression on the 7 published cases:',json.dumps({k:v for k,v in rep[name].items()},default=float)[:420])
json.dump(rep,open(out/'REGRESSION_7.json','w'),indent=1,default=float)
print('sha256 01_FEATURES_12.csv',hashlib.sha256((out/'01_FEATURES_12.csv').read_bytes()).hexdigest()[:16],' 02_LABELS_12',hashlib.sha256((out/'02_LABELS_EVAL_ONLY_12.csv').read_bytes()).hexdigest()[:16])
print('new-case sanity: detected all',bool(f[~f.case.isin(old)].detected.all()),'| per-new-case rows',f[~f.case.isin(old)].groupby('case').size().to_dict())
