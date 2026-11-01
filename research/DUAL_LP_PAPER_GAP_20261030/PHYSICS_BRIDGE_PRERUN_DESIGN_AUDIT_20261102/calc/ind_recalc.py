# Independent auditor recalculation from RA4_336_ARMS.csv (does not import recompute_review.py)
import csv, sys, json, math
ra4, sel = sys.argv[1], sys.argv[2]
rows = list(csv.DictReader(open(ra4)))
def get(case,bias,arm,gate):
    m=[r for r in rows if r['case']==case and r['bias']==bias and r['arm']==arm and r['gate']==gate]
    assert len(m)==1,(case,bias,arm,gate,len(m)); return m[0]
cases=['R2_aB_m0','R4_aB_m0','R5_aB_m0']; biases=['B0','L0','L1','L2']
out=[]; cnt={'MB_ORIG':[0,0],'BB_VAR_LEGACY':[0,0],'MB_VAR_LEGACY':[0,0],'BB_VAR_PRIOR':[0,0],'MB_VAR_PRIOR':[0,0]}
both_beat=0; varonly_beats_comb_both=[]
for c in cases:
  for b in biases:
    base=get(c,b,'BB_ORIG','SELF_NIS'); H0=float(base['head_rmse_deg']); X0=float(base['xy_rmse_cm'])
    rec={'case':c,'bias':b,'H0':H0,'X0':X0}
    for a in cnt:
      r=get(c,b,a,'SELF_NIS'); H=float(r['head_rmse_deg']); X=float(r['xy_rmse_cm'])
      rec[a+'_H']=H; rec[a+'_X']=X
      cnt[a][0]+=H<H0; cnt[a][1]+=X<X0
    cb=rec['MB_VAR_LEGACY_H']<min(rec['MB_ORIG_H'],rec['BB_VAR_LEGACY_H']) and rec['MB_VAR_LEGACY_X']<min(rec['MB_ORIG_X'],rec['BB_VAR_LEGACY_X'])
    both_beat+=cb
    if rec['BB_VAR_LEGACY_H']<rec['MB_VAR_LEGACY_H'] and rec['BB_VAR_LEGACY_X']<rec['MB_VAR_LEGACY_X']: varonly_beats_comb_both.append(c+'/'+b)
    rec['comb_H_red_pct']=100*(H0-rec['MB_VAR_LEGACY_H'])/H0
    out.append(rec)
print('improvement counts (H,XY) vs BB_ORIG/self:',cnt)
print('combined beats both single arms on H and XY:',both_beat)
print('var-only beats combined on both:',varonly_beats_comb_both)
for r in out: print(r['case'],r['bias'],'H %.4f->%.4f (%.2f%%)'%(r['H0'],r['MB_VAR_LEGACY_H'],r['comb_H_red_pct']),'XY %.3f->%.3f'%(r['X0'],r['MB_VAR_LEGACY_X']))
# compare with supplied SELECTED_12 table
S=list(csv.DictReader(open(sel))); mx=0
for s in S:
  r=[o for o in out if o['case']==s['case'] and o['bias']==s['bias']][0]
  for k1,k2 in [('baseline_H_deg','H0'),('baseline_XY_cm','X0'),('combined_H_deg','MB_VAR_LEGACY_H'),('combined_XY_cm','MB_VAR_LEGACY_X'),('variance_only_H_deg','BB_VAR_LEGACY_H'),('variance_only_XY_cm','BB_VAR_LEGACY_X'),('mean_only_H_deg','MB_ORIG_H'),('mean_only_XY_cm','MB_ORIG_X')]:
    mx=max(mx,abs(float(s[k1])-r[k2]))
print('max abs diff vs supplied SELECTED_12 table:',mx)
