"""Record successful frozen R2 regressions; NOT a new scientific experiment."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,os
import xml.etree.ElementTree as ET
import numpy as np
from core import SyntheticRF,map_update
from validate import sha,write
HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--gates',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);a=p.parse_args()
    from pre_run_audit import require_audit_receipt
    audit=require_audit_receipt(a.audit)
    if os.environ.get('GITHUB_ACTIONS')!='true':raise RuntimeError('cloud only')
    gate=json.loads((a.gates/'FINAL.json').read_text())
    assert gate['git_sha']==os.environ['GITHUB_SHA'] and gate['exit_code']==0
    assert gate['source_sha256']['core.py']==sha(HERE/'core.py')
    root=ET.parse(a.out/'TESTS.xml').getroot();suites=root.findall('testsuite')
    counts={k:sum(int(s.get(k,'0')) for s in suites) for k in ['tests','failures','errors','skipped']}
    assert counts['tests']>0 and counts['failures']==counts['errors']==counts['skipped']==0
    cases=[]
    for f in ('FAILURE_SNAPSHOT.json','RESUME_FAILURE_SNAPSHOT.json'):
        obj=json.loads((HERE/f).read_text());mu,P,z,R=(np.asarray(obj[k]) for k in ('prior_x','prior_P','z','R'))
        for saved in (False,True):
            kw={'range_first':not saved}
            if saved:kw['initial_delta']=np.asarray(obj['prior_delta'])
            result=map_update(mu,P,z,SyntheticRF(),R,max_iter=80,gradient_tol=1e-8,**kw)
            assert result.status=='CONVERGED' and result.gradient_inf<=1e-8
            cases.append({'snapshot':f,'saved_start':saved,'status':result.status,'gradient_inf':result.gradient_inf,
                          'iterations':result.iterations,'state':result.x.tolist(),'covariance':result.P.tolist(),'history':result.history})
    rec={'stage':'R2_REGRESSION','status':'PASS','tests':counts,'cases':cases,'git_sha':os.environ['GITHUB_SHA'],
         'run_id':os.environ['GITHUB_RUN_ID'],'ended_utc':datetime.now(timezone.utc).isoformat(),
         'source_sha256':{p.name:sha(p) for p in HERE.glob('*.py')},'scientific_PASS':False,'P2':'NOT_RUN_YET',
         'output_sha256':{p.name:sha(p) for p in a.out.iterdir() if p.is_file()},
         'audit_receipt_sha256':sha(a.audit),'audit_status':audit['decision']}
    write(a.out/'FINAL.json',rec)
    print('R2_REGRESSION '+json.dumps({'status':'PASS','tests':counts,'cases':[{k:c[k] for k in ('snapshot','saved_start','gradient_inf','iterations')} for c in cases]}),flush=True)

if __name__=='__main__':main()
