"""P2: causal decomposition of the first-arrival range error with the SAME frozen observer on three channels for every pose:
 (1) flat   : ideal unit-amplitude flat-spectrum LoS at the true delay (isolates window/threshold/tap-grid behaviour)
 (2) FFD LoS: stored complex LoS H (pattern + frequency dependence of the two LP ports)
 (3) full   : stored multipath H
 e_flat = r_flat - d ; e_FFD = r_los - r_flat ; e_MP = r_full - r_los ; sum = e_full.   (true delay is used for SCORING / the ideal-flat construction only)
Separate experiments: noise-free, SNR 30 dB, SNR 10 dB (seed fixed, independent noise per pose). Dependent samples: between-site vs within-site variance of e_MP (same XY, different yaw) and reference to the
timestamp-based drive-only ACF (V05).  usage: p2_detector_components.py OUT_DIR --h-full-dirs ... --h-los-dirs ... --freqs F"""
import argparse,json,sys,time,zlib
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2];G7=ROOT/'research/V01B_CLOSURE_20261012/G7/out';OBS_SRC=ROOT/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src'
C0=299792458.0
ap=argparse.ArgumentParser();ap.add_argument('out');ap.add_argument('--h-full-dirs',nargs='+',required=True);ap.add_argument('--h-los-dirs',nargs='+',required=True);ap.add_argument('--freqs',required=True);a=ap.parse_args()
out=Path(a.out);assert not out.exists();out.mkdir(parents=True)
sys.path.insert(0,str(OBS_SRC));from qclean_uwb.drivesim import observation as O
freq=np.load(a.freqs);df=float(freq[1]-freq[0]);n_tap=4*len(freq);tap_m=C0/(n_tap*df)
f=pd.read_csv(G7/'01_FEATURES_12.csv');l=pd.read_csv(G7/'02_LABELS_EVAL_ONLY_12.csv');d=f.merge(l,on=['case','route','pose_id'],validate='one_to_one')
find=lambda dirs,n:next(p for dd in dirs for p in [Path(dd)/n] if p.exists())
rows=[];t0=time.time()
def flat_H(dist):
    tau=dist/C0;h=np.exp(-2j*np.pi*freq[None,:]*tau[:,None]);return np.stack([h,h],axis=-1)[...,None].repeat(1,axis=-1)    # (B, bin, rx, tx=1)
for case,g in d.groupby('case'):
    g=g.sort_values('pose_id').reset_index(drop=True);ids=g.pose_id.to_numpy();Hf=np.load(find(a.h_full_dirs,f'H_{case}.npy'),mmap_mode='r');Hl=np.load(find(a.h_los_dirs,f'H_LoS_{case}.npy'),mmap_mode='r')
    dist=g.true_distance_m.to_numpy()
    res={'flat':O.observe(flat_H(dist),freq,None,None,tx=0),'los':O.observe(np.asarray(Hl[ids]),freq,None,None,tx=0),'full':O.observe(np.asarray(Hf[ids]),freq,None,None,tx=0)}
    r=pd.DataFrame(dict(case=case,pose_id=ids,route=g.route,site=[f'{a_}|{x:.4f}|{y:.4f}' for a_,x,y in zip(g.route,g.true_x,g.true_y)],true_x=g.true_x,true_y=g.true_y,yaw_deg=g.true_yaw_deg,d_true=dist,
        frac_tap=np.mod(dist/tap_m,1.0),r_flat=res['flat']['range_m'],r_los=res['los']['range_m'],r_full=res['full']['range_m'],tap_flat=res['flat']['index'],tap_los=res['los']['index'],tap_full=res['full']['index'],
        s_los=res['los']['s'],s_full=res['full']['s'],peak_los=res['los']['peak'],peak_full=res['full']['peak']))
    r['e_flat']=r.r_flat-r.d_true;r['e_ffd']=r.r_los-r.r_flat;r['e_mp']=r.r_full-r.r_los;r['e_full']=r.r_full-r.d_true
    # noisy experiments (separate experiment groups, independent noise per pose; detection threshold from the production rule)
    for snr in (30,10):
        nv=O.noise_var_from_snr(snr)
        for kind,H in (('los',Hl),('full',Hf)):
            rng=np.random.default_rng([20261012,snr,0 if kind=='los' else 1,zlib.crc32(case.encode())]);ob=O.observe(np.asarray(H[ids]),freq,nv,rng,tx=0)
            r[f'r_{kind}_snr{snr}']=ob['range_m'];r[f'det_{kind}_snr{snr}']=ob['detected'];r[f'tap_{kind}_snr{snr}']=ob['index']
    rows.append(r);print(case,len(r),'%.0fs'%(time.time()-t0),flush=True)
D=pd.concat(rows,ignore_index=True);assert len(D)==16432
D['tap_switch']=D.tap_full!=D.tap_los;D['dbin']=pd.cut(D.d_true,[0,5,10,np.inf],right=False).astype(str);D['mount']=D.case.str.extract(r'_m(\d+)')[0].astype(int);D['anchor']=D.case.str.extract(r'_(a[AB])_')[0]
D.to_csv(out/'P2_RANGE_ERROR_COMPONENTS.csv',index=False,float_format='%.10g')
ident=float(np.abs(D.e_full-(D.e_flat+D.e_ffd+D.e_mp)).max())
def summ(g):return pd.Series(dict(n=len(g),mean_e_flat=g.e_flat.mean(),sd_e_flat=g.e_flat.std(),mean_e_ffd=g.e_ffd.mean(),sd_e_ffd=g.e_ffd.std(),mean_e_mp=g.e_mp.mean(),sd_e_mp=g.e_mp.std(),mean_e_full=g.e_full.mean(),sd_e_full=g.e_full.std(),tap_switch=g.tap_switch.mean()))
cb=[]
for key in ('dbin','anchor','mount','case'):
    t=D.groupby(key).apply(summ).reset_index().rename(columns={key:'level'});t.insert(0,'group',key);cb.append(t)
yb=pd.cut(np.abs(((D.yaw_deg+180)%360)-180),[-1,15,45,90,135,181]);t=D.groupby(yb,observed=True).apply(summ).reset_index().rename(columns={'yaw_deg':'level'});t.insert(0,'group','abs_yaw_deg_bin');t['level']=t['level'].astype(str);cb.append(t)
fb=pd.cut(D.frac_tap,np.linspace(0,1,9),include_lowest=True);t=D.groupby(fb,observed=True).apply(summ).reset_index().rename(columns={'frac_tap':'level'});t.insert(0,'group','frac_tap_bin');t['level']=t['level'].astype(str);cb.append(t)
pd.concat(cb).to_csv(out/'P2_CONDITIONAL_BIAS.csv',index=False)
tt=[]
for key in ('dbin','anchor','mount'):
    for lv,g in D.groupby(key):
        sw=g[g.tap_switch];tt.append(dict(group=key,level=lv,n=len(g),tap_switch_rate=float(g.tap_switch.mean()),mean_tap_shift_when_switch=float((sw.tap_full-sw.tap_los).mean()) if len(sw) else 0.,frac_full_later=float(((sw.tap_full-sw.tap_los)>0).mean()) if len(sw) else 0.))
for snr in (30,10):
    for kind in ('los','full'):
        tt.append(dict(group=f'snr{snr}_{kind}',level='all',n=len(D),tap_switch_rate=float((D[f'tap_{kind}_snr{snr}']!=D[f'tap_{kind}']).mean()),detection_rate=float(D[f'det_{kind}_snr{snr}'].mean()),
            range_rmse_vs_noisefree=float(np.sqrt(np.nanmean((D[f'r_{kind}_snr{snr}']-D[f'r_{kind}'])**2))),range_sd_added_by_noise=float(np.nanstd(D[f'r_{kind}_snr{snr}']-D[f'r_{kind}']))))
pd.DataFrame(tt).to_csv(out/'P2_DETECTOR_TAP_TRANSITIONS.csv',index=False)
# dependent-sample audit: between-site vs within-site variance of e_mp (one-way ANOVA, sites with >=2 poses = same XY with different yaw) + reference to the timestamp-based ACF
multi=D.groupby(['case','site']).filter(lambda x:len(x)>=2);gm=multi.groupby(['case','site']).e_mp
within=float(np.mean(gm.var(ddof=1)));between=float(multi.groupby(['case','site']).e_mp.mean().var(ddof=1))
tc=json.load(open(ROOT/'research/STAGE_B_EXPLORATORY_20261012/out/v05_timecorr.json')) if (ROOT/'research/STAGE_B_EXPLORATORY_20261012/out/v05_timecorr.json').exists() else None
aud=dict(n_case_sites_with_multiple_yaw=int(multi.groupby(['case','site']).ngroups),within_site_var_e_mp=within,between_site_var_of_site_means_e_mp=between,
    note='within-site variation = yaw dependence at one XY (turn samples); poses at the same XY, adjacent drive ticks and repeated yaws are NOT independent',
    drive_only_timestamp_acf_reference=None if tc is None else {k:{ser:{kk:vv for kk,vv in v[ser].items() if kk in('iat_samples','iat_s','iat_95ci_samples')} for ser in v} for k,v in tc['routes'].items()},
    unique_sites=int(D.site.nunique()),n_poses=int(len(D)),pose_id_order_not_used_as_time=True)
(out/'P2_ACF_SITE_AUDIT.json').write_text(json.dumps(aud,indent=1,default=float))
gate=dict(identity_flat_ffd_mp_sum_max_abs=ident,identity_ok=ident<=1e-9,observer='frozen RUN_01a124ff observation.py, same code for flat/FFD/full',tap_switch_full_vs_los=float(D.tap_switch.mean()),tap_switch_matches_V04=abs(float(D.tap_switch.mean())-0.39398734)<1e-6,
   mean_e_flat=float(D.e_flat.mean()),sd_e_flat=float(D.e_flat.std()),mean_e_ffd=float(D.e_ffd.mean()),sd_e_ffd=float(D.e_ffd.std()),mean_e_mp=float(D.e_mp.mean()),sd_e_mp=float(D.e_mp.std()),tap_m=tap_m)
ok=gate['identity_ok'] and gate['tap_switch_matches_V04']
(out/'P2_GATE.md').write_text('# P2 gate (cause audit, NOT a performance PASS)\n\nresult: **%s**\n\n```json\n%s\n```\n'%('PASS' if ok else 'FAIL',json.dumps(gate,indent=1)))
print('P2','PASS' if ok else 'FAIL',json.dumps(gate,indent=1))
