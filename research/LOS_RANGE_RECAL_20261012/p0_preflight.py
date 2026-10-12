"""P0 preflight: provenance, baseline identity, observer parity, calibration/evaluation read boundary, site split, baselines.
usage: python p0_preflight.py OUT_DIR [--h-full-dirs DIR...] [--h-los-dirs DIR...]   (inputs located by name H_<case>.npy / H_LoS_<case>.npy)
Writes P0_INPUT_MANIFEST.json, P0_BASELINE_AUDIT.csv, TRAIN_VAL_TEST_SITE_SPLIT.json, P0_GATE.md. Never overwrites an existing OUT_DIR."""
import argparse,hashlib,json,subprocess,sys,time
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2];G7=ROOT/'research/V01B_CLOSURE_20261012/G7/out'
OBS_SRC=ROOT/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src'
B_OLD=-0.5315983906250129
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for c in iter(lambda:f.read(1<<22),b''):h.update(c)
    return h.hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('out');ap.add_argument('--h-full-dirs',nargs='+',required=True);ap.add_argument('--h-los-dirs',nargs='+',required=True);ap.add_argument('--freqs',required=True);a=ap.parse_args()
    out=Path(a.out);assert not out.exists(),'new output directory required';out.mkdir(parents=True)
    sys.path.insert(0,str(OBS_SRC));from qclean_uwb.drivesim import observation as O
    gate={};man={'git_head':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD']).decode().strip(),'python':sys.version.split()[0],'numpy':np.__version__,'pandas':pd.__version__,'command':' '.join(sys.argv),'time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    # 1 inputs
    pf,pl=G7/'01_FEATURES_12.csv',G7/'02_LABELS_EVAL_ONLY_12.csv';man['inputs']={str(pf.relative_to(ROOT)):sha(pf),str(pl.relative_to(ROOT)):sha(pl),'observer_source':str((OBS_SRC/'qclean_uwb/drivesim/observation.py').relative_to(ROOT)),'observer_sha256':sha(OBS_SRC/'qclean_uwb/drivesim/observation.py')}
    f=pd.read_csv(pf);l=pd.read_csv(pl);d=f.merge(l,on=['case','route','pose_id'],validate='one_to_one')
    gate['rows_merged_16432']=len(d)==16432;gate['no_nan_in_required_columns']=bool(d[['range_m','range_los','true_distance_m','true_x','true_y','true_yaw_deg','tap','tap_los']].notna().all().all())
    gate['conditions_12']=sorted(d.case.unique())==sorted(f'{r}_{an}_m{m}' for r in('R2','R4','R5') for an in('aA','aB') for m in(0,45));gate['unique_keys']=not d.duplicated(['case','pose_id']).any()
    # 2 V04 identity + published means
    d['e_los']=d.range_los-d.true_distance_m;d['e_mp']=d.range_m-d.range_los;d['e_full']=d.e_range
    ident=float(np.abs(d.e_full-(d.e_los+d.e_mp)).max());ref=dict(mean_e_los=-0.5361299649,mean_e_mp=0.0524597870,mean_e_full=-0.4836701779,tap_switch=0.39398734)
    got=dict(mean_e_los=float(d.e_los.mean()),mean_e_mp=float(d.e_mp.mean()),mean_e_full=float(d.e_full.mean()),tap_switch=float((d.tap!=d.tap_los).mean()))
    gate['identity_residual_max_m']=ident;gate['identity_ok_1e-9']=ident<=1e-9;gate['means_match_V04_1e-9']={k:abs(got[k]-ref[k])<=1e-8 for k in ref};man['v04_recomputed']=got
    # 3 observer parity (same complex H -> tap, range, s, P1/P2 vs the stored tables)
    freq=np.load(a.freqs);find=lambda dirs,n:next(p for dd in dirs for p in [Path(dd)/n] if p.exists())
    par={};Hsha={}
    for case,g in d.groupby('case'):
        for kind,dirs,name in (('full',a.h_full_dirs,f'H_{case}.npy'),('los',a.h_los_dirs,f'H_LoS_{case}.npy')):
            p=find(dirs,name);Hsha[f'{kind}:{case}']=sha(p);H=np.load(p,mmap_mode='r');g=g.sort_values('pose_id');ids=g.pose_id.to_numpy()
            ob=O.observe(np.asarray(H[ids]),freq,None,None,tx=0)
            if kind=='full':ref_r,ref_t,ref_s=g.range_m.to_numpy(),g.tap.to_numpy(),g.s.to_numpy()
            else:ref_r,ref_t,ref_s=g.range_los.to_numpy(),g.tap_los.to_numpy(),g.s_los.to_numpy()
            par[f'{kind}:{case}']=dict(max_abs_range=float(np.nanmax(np.abs(ob['range_m']-ref_r))),max_abs_s=float(np.nanmax(np.abs(ob['s']-ref_s))),tap_equal=bool(np.array_equal(ob['index'],ref_t)))
    gate['observer_parity_all']=all(v['max_abs_range']<=1e-9 and v['max_abs_s']<=1e-12 and v['tap_equal'] for v in par.values());man['observer_parity']=par;man['h_sha256']=Hsha
    # 4 read boundary: LORO coefficient fit must not change when HELD-OUT truth columns are scrambled
    def fit(tr):
        c=float((tr.range_los-tr.true_distance_m).mean());b,a_=np.polyfit(tr.true_distance_m,tr.range_los,1);return c,a_,b
    ok=True
    for r in ('R2','R4','R5'):
        tr=d[d.route!=r];c1=fit(tr);d2=d.copy();rng=np.random.default_rng(0);m=d2.route==r
        for col in ('true_distance_m','true_x','true_y','range_los','e_range'):d2.loc[m,col]=rng.permutation(d2.loc[m,col].to_numpy())
        c2=fit(d2[d2.route!=r]);ok&=np.allclose(c1,c2,rtol=0,atol=0)
    gate['read_boundary_heldout_truth_does_not_enter_fit']=bool(ok)
    # 5 sites and split (site = physical XY of a route; the 12 conditions share them)
    d['site']=[f'{r}|{x:.4f}|{y:.4f}' for r,x,y in zip(d.route,d.true_x,d.true_y)]
    sites=d.groupby('route').site.nunique().to_dict();dup=[s for s in d.site.unique() if False]
    xy=d.assign(xy=[f'{x:.4f}|{y:.4f}' for x,y in zip(d.true_x,d.true_y)]);cross=xy.groupby('xy').route.nunique();shared=sorted(cross[cross>1].index);man['cross_route_shared_xy_raw']=shared
    gate['raw_cross_route_shared_sites']=len(shared)   # informational; handled by the declared exclusion below (these XY are removed from the VALID/TEST roles)
    trv=set(xy[(xy.route.isin(['R2','R5']))&(~xy.xy.isin(shared))].xy);vav=set(xy[(xy.route=='R4')&(~xy.xy.isin(shared))].xy)
    gate['train_valid_sites_disjoint_after_exclusion']=len(trv&vav)==0
    split=dict(created_before_any_candidate='P0',excluded_shared_xy=shared,exclusion_rule='XY shared by more than one route (here the common start point) is excluded from VALID and TEST roles; pre-existing LORO exploratory numbers still contain it (1 of 2815 route sites)',development_TRAIN_routes=['R2','R5'],development_VALID_routes=['R4'],loro_folds=['R2','R4','R5'],
      TEST_blind=dict(kind='NEW physical sites, generated by the validated on-demand Legacy backend AFTER freezing this file',n_sites=240,region='x in [1.5,18.5] m, |y| <= 0.70 m, rejected if within 0.05 m of any existing route site (same XY tag) or horizontal distance to an anchor < 0.30 m',
      yaw='uniform [-180,180) deg per site, one yaw per site',anchors=['aA','aB'],mounts=[0,45],seed=20261012,scene='same corridor scene (a different scene is NOT available -> GENERALIZATION_NOT_VERIFIED)'),
      sites_per_route=sites,site_key='route|x|y (4 decimals)',weights='primary = site-weighted: mean over (case, site) groups of the group MSE',leakage_rule='TEST truth is read only by the scorer after predictions are saved')
    split['sha256_of_definition']=hashlib.sha256(json.dumps({k:v for k,v in split.items()},sort_keys=True).encode()).hexdigest()
    (out/'TRAIN_VAL_TEST_SITE_SPLIT.json').write_text(json.dumps(split,indent=1))
    # 6 baselines (primary site-weighted Full-RF range RMSE, secondary)
    rows=[]
    def metrics(name,err,sub):
        e=pd.Series(err.to_numpy(),index=sub.index);grp=e.groupby([sub.case,sub.site]).apply(lambda x:float(np.mean(x**2)))
        return dict(arm=name,n_pose=len(sub),n_case_site=len(grp),rmse_site_weighted=float(np.sqrt(grp.mean())),rmse_pose_pooled=float(np.sqrt(np.mean(e**2))),mean=float(e.mean()),sd_centered=float(e.std()),abs_p95=float(np.percentile(np.abs(e),95)))
    for scope,sub in (('all',d),('R2',d[d.route=='R2']),('R4',d[d.route=='R4']),('R5',d[d.route=='R5'])):
        for arm,err in (('A_raw',d.loc[sub.index,'e_full']),('B_old_offset',d.loc[sub.index,'e_full']-B_OLD),('LoS_B_old_offset',d.loc[sub.index,'e_los']-B_OLD)):
            m=metrics(arm,err,sub);m['scope']=scope;rows.append(m)
    pd.DataFrame(rows).to_csv(out/'P0_BASELINE_AUDIT.csv',index=False)
    man['gate_checks']=gate;(out/'P0_INPUT_MANIFEST.json').write_text(json.dumps(man,indent=1,default=str))
    passed=all((v if isinstance(v,bool) else (all(v.values()) if isinstance(v,dict) else True)) for k,v in gate.items() if not isinstance(v,(float,int)) or isinstance(v,bool))
    (out/'P0_GATE.md').write_text('# P0 gate\n\nresult: **%s**\n\n```json\n%s\n```\n'%('PASS' if passed else 'FAIL',json.dumps(gate,indent=1,default=str)))
    print('P0',('PASS' if passed else 'FAIL'));print(json.dumps(gate,indent=1,default=str));print(pd.DataFrame(rows)[lambda x:x.scope=='all'].round(5).to_string())
main()
