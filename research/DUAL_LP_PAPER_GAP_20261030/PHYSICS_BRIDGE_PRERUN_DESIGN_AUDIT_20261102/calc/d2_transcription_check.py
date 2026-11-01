# Auditor check: supplied D2 transcription vs D2_GATE_SCORES.csv @6c720009 (blob efe55ff9)
import csv,json,sys
D=list(csv.DictReader(open(sys.argv[1]))); T=json.load(open(sys.argv[2])); n=0; bad=[]
for c,vals in T.items():
  for b,(h0,h1,x0,x1) in zip(['B0','L0','L1','L2'],vals):
    g=lambda arm:[r for r in D if r['case']==c and r['bias']==b and r['arm']==arm and r['gate']=='self'][0]
    for got,exp in [(g('BB_ORIG')['head_rmse'],h0),(g('MB_VAR')['head_rmse'],h1),(g('BB_ORIG')['xy_rmse_cm'],x0),(g('MB_VAR')['xy_rmse_cm'],x1)]:
      n+=1; bad += [] if float(got)==float(exp) else [(c,b,got,exp)]
print('checks',n,'mismatches',len(bad),bad)
