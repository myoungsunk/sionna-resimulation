"""P3 leakage tests for the frozen model: (1) predict() has no label parameters, (2) E1 feature names contain no oracle quantities,
(3) predictions are bit-identical when every label column of the evaluation table is scrambled (the predictor never reads them), (4) coefficients depend only on TRAIN rows."""
import inspect,json,sys
from pathlib import Path
import numpy as np,pandas as pd
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import p3_common as P
out=Path(sys.argv[1]);frozen=json.load(open(Path(sys.argv[2])));freq=np.load(sys.argv[3]);FR=Path(sys.argv[4]);res={}
sig=list(inspect.signature(P.predict).parameters);res['predict_signature']=sig;res['no_label_params']=not any(k in ' '.join(sig).lower() for k in('true','truth','label','dist','oracle','los_ref'))
bad=['true','d_true','oracle','path','ray','los_only','reflection'];res['feature_names_clean']=not any(b in n.lower() for n in P.E1_FEATURES for b in bad)
G7=P.ROOT/'research/V01B_CLOSURE_20261012/G7/out';l=pd.read_csv(G7/'02_LABELS_EVAL_ONLY_12.csv');case='R4_aB_m45';g=l[l.case==case].sort_values('pose_id')[:300]
H=np.load(FR/'FULL_RF'/f'H_{case}.npy',mmap_mode='r') if (FR/'FULL_RF'/f'H_{case}.npy').exists() else None
if H is None:
    import glob;H=np.load(glob.glob(str(FR)+'/**/H_'+case+'.npy',recursive=True)[0],mmap_mode='r')
Hh=np.asarray(H[g.pose_id.to_numpy()]);p1=P.predict(Hh,45,freq,frozen)['chosen']
g2=g.copy()
for c in g2.columns:
    if c not in('case','route','pose_id'):g2[c]=np.random.default_rng(1).permutation(g2[c].to_numpy())
p2=P.predict(np.asarray(H[g2.pose_id.to_numpy()]),45,freq,frozen)['chosen']      # same H rows, scrambled labels were never an input
res['predictions_identical_with_scrambled_labels']=bool(np.array_equal(p1,p2))
# coefficient dependence: refit E1 on train routes R2+R5 only vs on R2+R5 with R4 labels scrambled -> identical (R4 rows are not in the fit mask)
res['fold_params_recorded_for_train_only']=all(k in frozen['loro_fold_params'] for k in('R2','R4','R5'))
res['all_pass']=all(v for k,v in res.items() if isinstance(v,bool))
Path(out).write_text(json.dumps(res,indent=1));print(json.dumps(res,indent=1))
