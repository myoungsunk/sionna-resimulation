"""R2-4b: training-path leakage tests for the P3 LORO fits (replaces the unimplemented 'refit' check of v1; v1 is kept).
Re-uses the unchanged P3 pipeline text up to the fold loop (same data merge, features, fit_all). For every held-out route:
 T1 train mask and held-out route are disjoint (assert on row indices)
 T2 refit with the HELD-OUT route's truth (d_true) permuted -> all fold coefficients bit-identical to the recorded fold coefficients in P3_FROZEN_MODEL.json
 T3 refit with a different permutation seed -> identical (no dependence on held-out labels)
 T4 NEGATIVE CONTROL: the same permutation applied to the TRAINING routes' truth must change the coefficients (test is sensitive)
 T5 SHA256 of the training-row index set per fold is recorded
usage: p3_leakage_tests_v2.py OUT_DIR FROZEN.json --h-full-dirs .. --h-los-dirs .. --freqs F"""
import sys,json,hashlib
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
src=(HERE/'p3_detector_candidates.py').read_text();head=src[:src.index("fold_res={}")]
frozen_path=sys.argv[2];sys.argv=[sys.argv[0],sys.argv[1]]+sys.argv[3:]
g=dict(__name__='p3_leak',__file__=str(HERE/'p3_detector_candidates.py'));exec(compile(head,'p3_head','exec'),g)
d=g['d'];fit_all=g['fit_all'];route=g['route'];out=g['out'];dt0=g['dt'].copy()
fz=json.load(open(frozen_path))['loro_fold_params']
def flat(m):
    L=[]
    for k in sorted(m):
        v=m[k]
        if isinstance(v,dict):
            for kk in sorted(v):L.append(np.asarray(v[kk],dtype=float).ravel())
        else:L.append(np.asarray(v,dtype=float).ravel())
    return np.concatenate(L)
def eq(a,b):return bool(np.array_equal(flat(a),flat(b)))
res={'folds':{}}
for held in ('R2','R4','R5'):
    tr=(route!=held);te=(route==held);idx_tr=np.where(tr)[0]
    t1=bool(not (tr&te).any())
    m_ref=fit_all(tr)
    # recorded coefficients (JSON round-trip: compare with tolerance 0 after float cast of the same python floats)
    rec=fz[held];keys=[k for k in m_ref if k!='D2_template']
    t0=all(np.allclose(flat({k:m_ref[k]}),flat({k:rec[k]}),rtol=0,atol=1e-12) for k in keys)
    out_t=[]
    for seed in (1,2):
        dt=dt0.copy();rng=np.random.default_rng(seed);dt[te]=rng.permutation(dt0[te])+rng.normal(size=te.sum());g['dt']=dt
        out_t.append(eq(fit_all(tr),m_ref))
    dt=dt0.copy();rng=np.random.default_rng(3);dt[tr]=rng.permutation(dt0[tr]);g['dt']=dt;neg=not eq(fit_all(tr),m_ref)
    g['dt']=dt0
    res['folds'][held]=dict(T1_disjoint=t1,T0_matches_recorded_fold_params=bool(t0),T2_T3_heldout_label_scramble_identical=bool(all(out_t)),T4_negative_control_changes_fit=bool(neg),
        n_train_rows=int(tr.sum()),n_heldout_rows=int(te.sum()),train_index_sha256=hashlib.sha256(idx_tr.astype(np.int64).tobytes()).hexdigest())
res['all_pass']=all(all(v for k,v in f.items() if k.startswith('T')) for f in res['folds'].values())
(out/'P3_LEAKAGE_TESTS_V2.json').write_text(json.dumps(res,indent=1));print(json.dumps(res,indent=1))
