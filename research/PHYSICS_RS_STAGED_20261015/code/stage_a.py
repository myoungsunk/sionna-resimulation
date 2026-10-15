"""Audited batch extraction and truth-only matched offline feature diagnostics."""
from __future__ import annotations
import hashlib,io,json,sys,zipfile
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from common import ROOT,INPUT,OUT,AUDIT,sha,write_json,require_gate,setup_original
from features import extract,FEATURES

def run():
 require_gate('A');setup_original()
 from p3_rf_adapter4 import FrozenLut
 from qclean_uwb.drivesim.observation import cir_batch
 manifest=json.loads((INPUT/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
 rec=json.loads((INPUT/'BUNDLE_AUDIT.json').read_text())
 freqs=[r for r in rec['files'] if 'freq' in Path(r['path']).name and r['path'].endswith('.npy')]
 assert freqs,'FREQUENCY_SOURCE_MISSING'
 freq=np.load(INPUT/freqs[0]['path'],allow_pickle=False)
 for r in freqs:np.testing.assert_array_equal(freq,np.load(INPUT/r['path'],allow_pickle=False))
 lut=FrozenLut(root=INPUT)
 archive=ROOT.parent/'ekf3_frozen_rf_original.zip'
 assert sha(archive)=='88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63'
 frames=[];parity=[];shapeinfo=[]
 with zipfile.ZipFile(archive) as za:
  summary=json.loads(za.read('P2_OUT/P2_ONE_STEP_SUMMARY.json'))
  desc={(d['case'],d['channel']):d for d in summary['per_case']}
  for case in manifest['cases']:
   name=case['id'];samples=json.loads((INPUT/case['samples_path']).read_text())
   pose_ids=np.array([r['pose_id'] for r in samples],int)
   assert len(pose_ids)==case['rf_count'] and len(set(pose_ids))==len(pose_ids)
   truth=np.array([[r['x'],r['y'],np.deg2rad(r['yaw_body_deg'])] for r in samples])
   model=np.array([lut.model(x,case)[0] for x in truth])
   base=pd.DataFrame({'case':name,'route':case['route'],'pose_id':pose_ids,'x_eval':truth[:,0],
      'y_eval':truth[:,1],'yaw_eval_rad':truth[:,2],'mount':case['mount_deg'],'lut_s_eval':model[:,1]})
   combined={}
   for channel,key in [('los','los_path'),('full','full_path')]:
    h=np.load(INPUT/case[key],mmap_mode='r',allow_pickle=False)
    assert tuple(h.shape)==tuple(case['H_shape'])
    parts=[]
    for k in range(0,len(h),64):parts.append(extract(h[k:k+64,:,:,0],freq))
    feats={c:np.concatenate([p[c] for p in parts]) for c in parts[0]}
    assert feats['valid'].all(),('INVALID_REAL_PACKET',name,channel,int((~feats['valid']).sum()))
    tab=pd.concat([base.copy(),pd.DataFrame(feats)],axis=1);tab['channel']=channel
    assert np.isfinite(tab[FEATURES].to_numpy()).all()
    d=desc[name,channel];raw=za.read('P2_OUT/'+d['trace_file'])
    assert hashlib.sha256(raw).hexdigest()==d['trace_sha256']
    with np.load(io.BytesIO(raw),allow_pickle=False) as old:
     ix=tab.set_index('pose_id').loc[old['pose_id']]
     ds=float(np.max(abs(ix.s_fp.to_numpy()-old['z_s'])));dr=float(np.max(abs(ix.range_m.to_numpy()-old['z_r_m'])))
     assert ds<1e-12 and dr<1e-12,('OBSERVATION_PARITY',name,channel,ds,dr)
     # Source SAMPLES serializes six decimal places; compare serialized geometry exactly.
     ot=old['truth_for_offline_scoring_only']
     np.testing.assert_array_equal(np.round(ix[['x_eval','y_eval']].to_numpy(),6),np.round(ot[:,:2],6))
     dy=(ix.yaw_eval_rad.to_numpy()-ot[:,2]+np.pi)%(2*np.pi)-np.pi
     np.testing.assert_array_equal(np.round(np.rad2deg(dy),6),np.zeros(len(dy)))
     parity.append({'case':name,'channel':channel,'count':len(ix),'max_s_diff':ds,'max_range_diff_m':dr})
    # Independent original CIR constructor on every 53rd sample, source not edited.
    inds=np.arange(0,len(h),53)
    orig=cir_batch(np.asarray(h[inds,:,:,0]))
    a=abs(orig);b=a.max(axis=1).argmax(axis=1);i=np.arange(len(inds));strong=a[i,:,b]
    kk=(strong>=.3*strong.max(axis=1)[:,None]).argmax(axis=1)
    pp=abs(orig[i,kk,:])**2;ss=(pp[:,0]-pp[:,1])/pp.sum(axis=1)
    np.testing.assert_allclose(ss,feats['s_fp'][inds],atol=1e-12,rtol=0)
    combined[channel]=tab
    print('A_CASE',name,channel,len(tab),flush=True)
   los=combined['los'];full=combined['full']
   emp=full.s_fp.to_numpy()-los.s_fp.to_numpy();elut=los.s_fp.to_numpy()-model[:,1]
   for channel in ('los','full'):
    tab=combined[channel]
    tab['e_MP_eval']=emp if channel=='full' else 0.
    tab['e_LUT_eval']=elut
    tab['e_total_eval']=tab.s_fp.to_numpy()-model[:,1]
    assert np.max(abs(tab.e_total_eval-(tab.e_MP_eval+tab.e_LUT_eval)))<1e-12
    frames.append(tab)
 data=pd.concat(frames,ignore_index=True)
 assert len(data)==19038 and not data.duplicated(['case','channel','pose_id']).any()
 OUT.mkdir(exist_ok=True)
 data.to_csv(OUT/'A_FEATURES_LABELS.csv.gz',index=False)
 pd.DataFrame(parity).to_csv(OUT/'A_OBSERVATION_PARITY.csv',index=False)
 corr=[]
 for name,g in data[data.channel=='full'].groupby('route'):
  for f in FEATURES:
   corr.append({'route':name,'feature':f,'n':len(g),'spearman_abs_MP':float(spearmanr(g[f],abs(g.e_MP_eval)).statistic),
        'spearman_total_sq':float(spearmanr(g[f],g.e_total_eval**2).statistic)})
 pd.DataFrame(corr).to_csv(OUT/'A_FEATURE_ASSOCIATION.csv',index=False)
 ranges=[]
 # Within-case identical XY grouping: only genuinely varying yaw groups counted.
 data['site_x']=data.x_eval.round(5);data['site_y']=data.y_eval.round(5)
 for (case,channel,x,y),g in data.groupby(['case','channel','site_x','site_y']):
  if len(g)>=5 and np.ptp(g.yaw_eval_rad)>np.deg2rad(5):
   for f in ['s_fp','jones_diversity','freq_s_var','eta_fp_win80','tap_pol_var80','early8','detector_s_span']:
    ranges.append({'case':case,'channel':channel,'x_eval':x,'y_eval':y,'feature':f,'n':len(g),'yaw_span_deg':float(np.rad2deg(np.ptp(g.yaw_eval_rad))),'feature_span':float(np.ptp(g[f]))})
 pd.DataFrame(ranges).to_csv(OUT/'A_WITHIN_SITE_YAW_SPANS.csv',index=False)
 stats=[]
 for (ch,case),g in data.groupby(['channel','case']):
  for f in FEATURES:
   stats.append({'channel':ch,'case':case,'feature':f,'n':len(g),'p05':float(g[f].quantile(.05)),'median':float(g[f].median()),'p95':float(g[f].quantile(.95)),'max':float(g[f].max())})
 pd.DataFrame(stats).to_csv(OUT/'A_FEATURE_DISTRIBUTIONS.csv',index=False)
 write_json(OUT/'A_FINAL.json',{'status':'EXTRACTION_AND_PARITY_PASS','rows':len(data),'paired_RF_poses':len(data)//2,
  'archived_timesteps_parity':sum(r['count'] for r in parity),'max_s_diff':max(r['max_s_diff'] for r in parity),
  'raw_noise':'noise-free H','features':FEATURES,'scientific_PASS':False,'feature_file_sha256':sha(OUT/'A_FEATURES_LABELS.csv.gz')})
if __name__=='__main__':run()
