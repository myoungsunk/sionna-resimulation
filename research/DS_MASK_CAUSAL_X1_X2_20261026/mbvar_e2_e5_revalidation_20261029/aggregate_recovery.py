#!/usr/bin/env python3
"""Aggregate the completed compute shards without matching E2R_ACF files.
The first aggregator failed before emitting a verdict because E2R_*_lo.csv also
matched E2R_ACF_*_lo.csv. No compute shard is modified or rerun by this program.
"""
import argparse,hashlib,json,sys,time
from pathlib import Path
import numpy as np
import pandas as pd
CASES=['R2_aA_m0','R2_aB_m0','R4_aA_m0','R4_aB_m0','R5_aA_m0','R5_aB_m0']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(src,out):
    out.mkdir(parents=True,exist_ok=True)
    fs=[src/f'E2R_{c}_{p}.csv' for c in CASES for p in ('lo','hi')]
    assert all(f.is_file() for f in fs)
    d=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
    assert len(d)==504 and not d.duplicated(['case','seed','arm','treat']).any()
    base=d[d.treat=='BASE'];counts=base.groupby(['case','arm']).seed.nunique()
    assert len(counts)==12 and (counts==10).all()
    d.to_csv(out/'E2R_ALL.csv',index=False,float_format='%.12g');rows=[]
    for (c,a,tr),g in d.groupby(['case','arm','treat'],dropna=False):
        if tr=='BASE':continue
        b=base[(base.case==c)&(base.arm==a)].set_index('seed');g=g.set_index('seed')
        dh=g.head_rmse-b.loc[g.index].head_rmse;dx=g.xy_rmse_cm-b.loc[g.index].xy_rmse_cm
        expected=1 if tr.startswith('LEGACY') else 10
        assert len(g)==expected
        rows.append(dict(case=c,arm=a,treat=tr,n_seed=len(g),head_median=g.head_rmse.median(),xy_median=g.xy_rmse_cm.median(),delta_head_median=dh.median(),delta_xy_median=dx.median(),head_min=g.head_rmse.min(),head_max=g.head_rmse.max(),n_head_improve=int((dh<0).sum()),n_both_improve=int(((dh<0)&(dx<0)).sum()),head_z_rms_median=g.head_z_rms.median(),nees4_median=g.nees4.median()))
    j=pd.DataFrame(rows);j.to_csv(out/'JUDGE_E2R.csv',index=False,float_format='%.12g')
    geo=pd.concat([pd.read_csv(src/f'E5R_{c}_lo.csv') for c in CASES],ignore_index=True)
    geo.to_csv(out/'E5R_ALL.csv',index=False,float_format='%.12g')
    gf=geo[(geo.window=='FAIL')&(geo.method=='DYNAMIC_Q')]
    gf.to_csv(out/'JUDGE_E5R_FAIL.csv',index=False,float_format='%.12g')
    qa=pd.concat([pd.read_csv(src/f'QA_JAC_{c}_lo.csv') for c in CASES],ignore_index=True)
    qa.to_csv(out/'JACOBIAN_QA_ALL.csv',index=False)
    par=pd.concat([pd.read_csv(src/f'PARITY_{c}_{p}.csv') for c in CASES for p in ('lo','hi')],ignore_index=True)
    assert len(par)==120;par.to_csv(out/'PARITY_ALL.csv',index=False)
    acf=pd.concat([pd.read_csv(src/f'E2R_ACF_{c}_lo.csv') for c in CASES],ignore_index=True)
    acf.to_csv(out/'E2R_ACF_ALL.csv',index=False)
    hashchecks=[];mathchecks=[]
    for c in CASES:
        for p in ('lo','hi'):
            mf=src/f'MANIFEST_{c}_{p}.json';m=json.loads(mf.read_text())
            mathchecks.append(m['math_qa']['process_marginalization_max_abs_error'])
            for name,wanted in m['outputs'].items():
                actual=sha(src/name);assert actual==wanted,(name,actual,wanted)
                hashchecks.append(dict(file=name,sha256=actual))
    pd.DataFrame(hashchecks).to_csv(out/'RAW_HASH_VERIFICATION.csv',index=False)
    checks=dict(compute_run=40830330560,original_run=40820579727,source_ref='422b6c0',aggregate_recovery=True,
        aggregate_bug='E2R_*_lo also matched E2R_ACF; fixed by explicit case/part filenames',
        n_compute_shards=12,n_score_rows=len(d),n_full_jacobian_new_runs=int(d.treat.str.startswith('FULL_JAC').sum()),n_frozen_new_runs=int((d.treat=='FROZEN_COND').sum()),
        n_baseline_replays=len(base),n_legacy_replays=int(d.treat.str.startswith('LEGACY').sum()),
        n_hash_checks=len(hashchecks),hash_failures=0,baseline_max_score_delta=float(par.max_score_difference_vs_original_csv.max()),
        n_jacobian_samples=len(qa),n_branch_crossings=int(qa.branch_crossing.sum()),
        jacobian_relative_error_p95=float(qa.loc[~qa.branch_crossing,'relative_full_jacobian_error'].quantile(.95)),
        jacobian_relative_error_max=float(qa.relative_full_jacobian_error.max()),
        decomposition_max_abs_error=float(d.decomposition_max_abs_error.max()),
        info_unit_invariance_max_rel=float(geo.unit_invariance_rel_error.max()),process_Q_direct_stacked_max_abs=float(max(mathchecks)),
        geometry_seeds=[0],filter_seeds=list(range(10)),bias='B0',same_RF=True,new_environment=False,nested_loro=False)
    (out/'COMPLETION_CORRECTED.json').write_text(json.dumps(checks,indent=2))
    (out/'RESULTS_CORRECTIVE.md').write_text('# E2/E5 corrective rerun\n\nAll 12 compute shards completed; the filename-selection aggregation error was repaired separately.\nE2 full-Jacobian and frozen-donor mean models have different contracts.\nE5 reports nominal white-Q/R information, not empirical RF Fisher. Only seed0 geometry was rerun.\nNo nested LORO or new environment.\n\n'+j.to_markdown(index=False)+'\n\n'+gf.to_markdown(index=False))
    (out/'MANIFEST_AGGREGATION.json').write_text(json.dumps(dict(utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),command=sys.argv,config=checks,code_sha256=sha(Path(__file__)),inputs={f.name:sha(f) for f in fs},outputs={p.name:sha(p) for p in out.iterdir() if p.is_file()}),indent=2))
    print(json.dumps(checks,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True);a=p.parse_args();main(Path(a.input),Path(a.out))
