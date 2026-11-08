#!/usr/bin/env python3
"""Verified saved-row endpoint diagnostics. Cross e/d combinations are algebraic,
not state-consistent nonlinear model interventions. No new estimator is run.
"""
from pathlib import Path
import argparse, hashlib, json, os, base64, urllib.request
import numpy as np
import pandas as pd

KEY=['group','level','donor','k','t','pose_id','gate','split','block']
TOL=1e-10
SOURCE='bcb6da12b06987b737b14bf61ce8cd4bee3fb0bd'
REPO='myoungsunk/sionna-resimulation'
DEST='research/PALO_MECHANISM_CD_20261108'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
def gain(e,d):return -2*e*d-d*d

def main(src,out):
 out.mkdir(parents=True,exist_ok=True)
 man=json.loads((src/'results/OUTPUT_SHA256.json').read_text());receipts=[]
 for name in ['online_features.csv.gz','offline_labels.csv.gz','same_frame_prior_comparison.csv']:
  p=src/'results'/name;spec=man[name]
  assert sha(p)==spec['sha256'] and p.stat().st_size==spec['bytes'],name
  receipts.append(dict(file=name,sha256=sha(p),bytes=p.stat().st_size))
 f=pd.read_csv(src/'results/online_features.csv.gz');y=pd.read_csv(src/'results/offline_labels.csv.gz')
 z=f.merge(y,on=KEY,validate='one_to_one')
 assert len(z)==15664 and not z.duplicated(KEY).any()
 z['d_deg']=np.rad2deg(z.delta_psi);z['e_deg']=z.prior_h_deg
 z['no_wrap']=np.abs(z.e_deg+z.d_deg-z.post_h_deg)<1e-8
 z['g_formula']=gain(z.e_deg,z.d_deg)
 err=np.abs(z.loc[z.no_wrap,'g_formula']-z.loc[z.no_wrap,'gh']);assert err.max()<1e-7
 z['Kpsi_abs']=np.where(z.innovation_abs>1e-12,np.abs(z.delta_psi)/z.innovation_abs,np.nan)
 z['sigma_deg']=np.rad2deg(np.sqrt(z.Ppsi))
 z['S']=np.where(z.nis>1e-14,z.innovation_abs**2/z.nis,np.nan)
 pairs=[]
 for lv in ['B0','L0','L1','L2']:
  for a,b in [('s4','dr'),('s4','heading'),('dr','heading')]:
   x=z[(z.group=='baseline')&(z.level==lv)&(z.donor==a)&(z.t>=40)].set_index('k')
   v=z[(z.group=='baseline')&(z.level==lv)&(z.donor==b)&(z.t>=40)].set_index('k')
   assert len(x)==len(v)==779 and np.array_equal(x.index,v.index)
   assert np.array_equal(x.pose_id,v.pose_id) and np.array_equal(x.t,v.t)
   ea=x.e_deg.to_numpy();eb=v.e_deg.to_numpy();da=x.d_deg.to_numpy();db=v.d_deg.to_numpy()
   local=(np.abs(ea+da)<180)&(np.abs(ea+db)<180)&(np.abs(eb+da)<180)&(np.abs(eb+db)<180)
   gaa=gain(ea,da);gbb=gain(eb,db);gba=gain(eb,da);gab=gain(ea,db)
   ca=-(da+db)*(eb-ea);cb=-(ea+eb+da+db)*(db-da)
   assert np.max(np.abs(ca+cb-(gbb-gaa)))<1e-7
   gooda=gaa>TOL;goodb=gbb>TOL;discord=gooda!=goodb
   neutral=(np.abs(gaa)<=TOL)|(np.abs(gbb)<=TOL)|(np.abs(gba)<=TOL)|(np.abs(gab)<=TOL)
   ef=(gba>TOL)==goodb;df=(gab>TOL)==goodb
   pattern=np.full(len(x),'not_a_disagreement',dtype=object);target=discord&local&~neutral
   pattern[target&ef&~df]='error_swap_only_sufficient'
   pattern[target&~ef&df]='correction_swap_only_sufficient'
   pattern[target&ef&df]='either_swap_sufficient'
   pattern[target&~ef&~df]='both_required'
   pattern[discord&(~local|neutral)]='wrap_or_tie_unresolved'
   p=pd.DataFrame(dict(level=lv,from_prior=a,to_prior=b,k=x.index,t=x.t.to_numpy(),pose_id=x.pose_id.to_numpy(),
    gate_a=x.gate.to_numpy(),gate_b=v.gate.to_numpy(),both_gate=x.gate.to_numpy()&v.gate.to_numpy(),
    e_a_deg=ea,e_b_deg=eb,d_a_deg=da,d_b_deg=db,
    prior_xy_a=x.prior_xy.to_numpy(),prior_xy_b=v.prior_xy.to_numpy(),
    abs_innovation_a=x.innovation_abs.to_numpy(),abs_innovation_b=v.innovation_abs.to_numpy(),
    Kpsi_abs_a=x.Kpsi_abs.to_numpy(),Kpsi_abs_b=v.Kpsi_abs.to_numpy(),
    sigma_a_deg=x.sigma_deg.to_numpy(),sigma_b_deg=v.sigma_deg.to_numpy(),
    heading_fraction_a=x.heading_fraction.to_numpy(),heading_fraction_b=v.heading_fraction.to_numpy(),
    nis_a=x.nis.to_numpy(),nis_b=v.nis.to_numpy(),
    gain_aa_deg2=gaa,gain_bb_deg2=gbb,gain_error_only_deg2=gba,gain_correction_only_deg2=gab,
    effect_error_deg2=ca,effect_correction_deg2=cb,
    label_disagreement=discord,error_sign_diff=np.sign(ea)!=np.sign(eb),
    correction_sign_diff=np.sign(da)!=np.sign(db),cross_no_wrap=local,cross_pattern=pattern))
   pairs.append(p)
 p=pd.concat(pairs,ignore_index=True);summary=[]
 for (lv,a,b),g in p.groupby(['level','from_prior','to_prior'],sort=False):
  q=g[g.both_gate];u=q[q.label_disagreement]
  summary.append(dict(level=lv,from_prior=a,to_prior=b,n=len(g),both_gate_n=len(q),
   disagreements_all=int(g.label_disagreement.sum()),disagreements_both_gate=len(u),
   error_sign_disagreements=int(u.error_sign_diff.sum()),correction_sign_disagreements=int(u.correction_sign_diff.sum()),
   **{name:int((u.cross_pattern==name).sum()) for name in ['error_swap_only_sufficient','correction_swap_only_sufficient','either_swap_sufficient','both_required','wrap_or_tie_unresolved']},
   median_prior_abs_error_a=float(np.median(np.abs(q.e_a_deg))),median_prior_abs_error_b=float(np.median(np.abs(q.e_b_deg))),
   median_abs_innovation_a=float(np.median(q.abs_innovation_a)),median_abs_innovation_b=float(np.median(q.abs_innovation_b)),
   median_Kpsi_abs_a=float(np.median(q.Kpsi_abs_a)),median_Kpsi_abs_b=float(np.median(q.Kpsi_abs_b))))
 summ=pd.DataFrame(summary)
 keys=[('B0',201),('B0',483),('B0',485),('B0',525),('B0',973),('L2',630),('L2',962)]
 examples=z[(z.group=='baseline')&z.donor.isin(['s4','dr','heading'])].set_index(['level','k'])
 cols=['donor','t','gate','e_deg','d_deg','post_h_deg','gh','prior_xy','post_xy','innovation_abs','Kpsi_abs','sigma_deg','nis','heading_fraction','mechanism']
 examples=examples.loc[keys,cols].reset_index()
 p.to_csv(out/'paired_endpoint_diagnostics.csv.gz',index=False,compression={'method':'gzip','mtime':0})
 summ.to_csv(out/'endpoint_summary.csv',index=False);examples.to_csv(out/'illustrative_events.csv',index=False)
 old=pd.read_csv(src/'results/same_frame_prior_comparison.csv')
 chk=p[(p.from_prior=='s4')&(p.to_prior=='dr')].merge(old,on=['level','k','t'],validate='one_to_one')
 assert len(chk)==3116
 assert np.array_equal(chk.label_disagreement.to_numpy(),(chk.s4_good!=chk.dr_good).to_numpy())
 assert np.max(np.abs(chk.gain_aa_deg2-chk.s4_gh))<1e-7
 assert np.max(np.abs(chk.gain_bb_deg2-chk.dr_gh))<1e-7
 outsum=dict(status='EXISTING_ROW_ENDPOINT_DIAGNOSIS_COMPLETE; PHYSICAL_FACTOR_INTERVENTIONS_NOT_RUN',
  input_commit=SOURCE,raw_input_commit='16450dc14366ba4ed2cb4e151952493f0efc944f',
  scope='R2/Anchor B/seed0; all physical paired baseline frames t>=40',
  rows=len(z),local_factual_rows=int(z.no_wrap.sum()),max_endpoint_formula_error_deg2=float(err.max()),
  paired_rows=len(p),cross_wrapping_pairs=int((~p.cross_no_wrap).sum()),source_sha256=receipts,
  main_results=summ[(summ.from_prior=='s4')&(summ.to_prior=='dr')].to_dict('records'),
  warning='Error/correction swaps and symmetric decomposition are algebraic cross-combinations, NOT state-consistent physical interventions. No predictor or new closed-loop policy was run.')
 dump(out/'SUMMARY.json',outsum)
 dump(out/'OUTPUT_SHA256.json',{f.name:dict(sha256=sha(f),bytes=f.stat().st_size) for f in sorted(out.iterdir()) if f.is_file() and f.name not in ('OUTPUT_SHA256.json','run.log')})
 print(json.dumps(outsum,indent=2,ensure_ascii=False),flush=True)
 print(examples.to_string(index=False),flush=True)

def request(url,method='GET',body=None,token=None):
 headers={'User-Agent':'PALO-mechanism-diagnosis','Accept':'application/vnd.github+json'}
 if token:headers['Authorization']='Bearer '+token
 if body is not None:headers['Content-Type']='application/json'
 req=urllib.request.Request(url,headers=headers,data=None if body is None else json.dumps(body).encode(),method=method)
 with urllib.request.urlopen(req,timeout=120) as r:return r.read()

def download_source(src):
 target=src/'results';target.mkdir(parents=True,exist_ok=True)
 for n in ['OUTPUT_SHA256.json','online_features.csv.gz','offline_labels.csv.gz','same_frame_prior_comparison.csv']:
  url=f'https://raw.githubusercontent.com/{REPO}/{SOURCE}/research/PALO_RISK_AB_20261108/results/{n}'
  (target/n).write_bytes(request(url))

def publish(out):
 token=os.environ['GITHUB_TOKEN'];branch=os.environ['BRANCH'];expected=os.environ['SOURCE_SHA']
 def api(method,path,body=None):return json.loads(request('https://api.github.com/repos/'+REPO+path,method,body,token))
 head=api('GET','/git/ref/heads/'+branch)['object']['sha'];assert head==expected,'branch moved: refusing publication'
 tree=api('GET','/git/commits/'+head)['tree']['sha'];entries=[]
 for p in sorted(out.iterdir()):
  if not p.is_file() or p.name=='run.log':continue
  b=p.read_bytes();blob=api('POST','/git/blobs',dict(content=base64.b64encode(b).decode(),encoding='base64'))['sha']
  entries.append(dict(path=DEST+'/results/'+p.name,mode='100644',type='blob',sha=blob))
 tr=api('POST','/git/trees',dict(base_tree=tree,tree=entries))['sha']
 commit=api('POST','/git/commits',dict(message='Verify saved-row mechanism decomposition; preserve unexecuted physical C/D design',tree=tr,parents=[head]))['sha']
 assert api('GET','/git/ref/heads/'+branch)['object']['sha']==head
 api('PATCH','/git/refs/heads/'+branch,dict(sha=commit,force=False))
 assert api('GET','/git/ref/heads/'+branch)['object']['sha']==commit
 print('PUBLISHED',commit,flush=True)

if __name__=='__main__':
 pa=argparse.ArgumentParser();pa.add_argument('--source',type=Path,required=True);pa.add_argument('--output',type=Path,required=True)
 pa.add_argument('--download',action='store_true');pa.add_argument('--publish',action='store_true');a=pa.parse_args()
 if a.download:download_source(a.source)
 main(a.source,a.output)
 if a.publish:publish(a.output)
