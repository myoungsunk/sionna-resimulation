"""Separate CSV aggregation checker; never reruns SourceFFD or selector."""
import argparse,csv,json,math,sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from qclean_uwb.fp_sc.followup.contracts import sha256,write_json,STEP_M

def check(run,static,tests,out):
    out.mkdir(exist_ok=False)
    receipt=json.loads((run/'RUN_RECEIPT.json').read_text())
    assert receipt['status']=='COMPLETE_NUMERICAL_REVIEW_PENDING'
    for p,h in receipt['files'].items():assert sha256(run/p)==h
    rows=list(csv.DictReader((run/'NOMINAL.csv').open()))
    stress=list(csv.DictReader((run/'STRESS.csv').open()))
    assert len(rows)==6272 and len(stress)==43904
    keys={(r['case_id'],int(r['k'])) for r in rows};assert len(keys)==6272
    expected={(f'{route}_B0_{channel}_10',k) for route,n in [('R2',979),('R4',742),('R5',1415)]
              for channel in ('Full','Native_LoS') for k in range(n)}
    assert keys==expected
    stress_names={'COV_001','X_PLUS','X_MINUS','Y_PLUS','Y_MINUS','YAW_PLUS','YAW_MINUS'}
    skeys={(r['case_id'],int(r['k']),r['stress']) for r in stress}
    assert len(skeys)==43904 and skeys=={(*k,s) for k in keys for s in stress_names}
    groups=defaultdict(lambda:dict(n=0,reference_in=0,usable=0,width_hold=0))
    failures=[];endpoint_max=0;probe_max=0.;nominal_by_key={}
    for r in rows:
        floats={k:float(r[k]) for k in ('low','high','width','native_min','native_max','probe_min','probe_max','probe_excess_m','endpoint_error_m')}
        assert all(math.isfinite(v) for v in floats.values())
        lo,hi=floats['low'],floats['high'];width=hi-lo
        assert abs(width-floats['width'])<1e-10 and lo<=hi
        err=max(abs(lo-(floats['native_min']-.15)),abs(hi-(floats['native_max']+.15)),floats['endpoint_error_m'])
        endpoint_max=max(endpoint_max,err)
        excess=max(0.,lo-floats['probe_min'],floats['probe_max']-hi)
        assert abs(excess-floats['probe_excess_m'])<1e-10
        probe_max=max(probe_max,excess)
        if excess>1e-10:failures.append(r)
        valid=bool(int(r['ref_valid']));held=width>1.5
        inside=valid and lo-1e-10<=int(r['ref_tap'])*STEP_M<=hi+1e-10
        if valid and r['raw_tap']:
            diff=abs(int(r['raw_tap'])-int(r['ref_tap']))
            assert r['stratum']==('normal' if diff==0 else 'one_tap' if diff==1 else 'large_error')
        assert int(r['ref_in_support'])==inside and int(r['usable_ref'])==(inside and not held)
        assert int(r['hold_width'])==held
        nominal_by_key[(r['case_id'],int(r['k']))]=r
        if valid:
            for key in [('ALL','ALL','ALL'),(r['route'],r['channel'],r['stratum'])]:
                g=groups[key];g['n']+=1;g['reference_in']+=inside;g['usable']+=inside and not held;g['width_hold']+=held
    summary=[]
    for key,g in sorted(groups.items()):
        summary.append(dict(route=key[0],channel=key[1],stratum=key[2],**g,
                            usable_fraction=g['usable']/g['n'],passed=g['usable']/g['n']>=.95))
    for route in ('R2','R4','R5'):
        for channel in ('Full','Native_LoS'):
            for stratum in ('normal','one_tap','large_error'):
                if (route,channel,stratum) not in groups:
                    summary.append(dict(route=route,channel=channel,stratum=stratum,n=0,status='NOT_TESTED'))
    sg=defaultdict(lambda:dict(n=0,hold=0,narrow_exclusion=0,reference_in=0))
    for r in stress:
        lo,hi=float(r['low']),float(r['high']);assert math.isfinite(lo) and math.isfinite(hi) and hi>=lo
        n=nominal_by_key[(r['case_id'],int(r['k']))];valid=bool(int(n['ref_valid']))
        inside=valid and lo-1e-10<=int(n['ref_tap'])*STEP_M<=hi+1e-10;hold=hi-lo>1.5
        assert int(r['ref_valid'])==valid and int(r['ref_in_support'])==inside
        assert int(r['hold_width'])==hold and abs(float(r['width'])-(hi-lo))<=1e-10
        assert int(r['narrow_reference_exclusion'])==(valid and not inside and not hold)
        g=sg[(r['route'],r['channel'],r['stress'])];g['n']+=1;g['hold']+=hold
        g['narrow_exclusion']+=valid and not inside and not hold;g['reference_in']+=inside
    static_receipt=json.loads((static/'STATIC_PREPARATION.json').read_text())
    assert static_receipt['status']=='PASS_STATIC48_FORMAT_ONLY' and static_receipt['static_cases']==48
    for p,h in static_receipt['files'].items():assert sha256(static/p)==h
    test_receipt=json.loads(tests.read_text());assert test_receipt['failures']==0
    gates=dict(G0=True,G1=endpoint_max<=1e-10 and all(v<=1e-10 for v in receipt['special_cases'].values()),
               G2=len(failures)==0,G3=all(g['passed'] for g in summary if 'passed' in g),G4=True,G5=True)
    with (out/'PROBE_COUNTEREXAMPLES.csv').open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(failures)
    write_json(out/'STRATA.json',summary)
    write_json(out/'STRESS_SUMMARY.json',[dict(route=k[0],channel=k[1],stress=k[2],**v) for k,v in sorted(sg.items())])
    write_json(out/'GATE.json',dict(verdict='NUMERICAL_PASS_REVIEW_HOLD' if all(gates.values()) else 'FAIL_FROZEN_MAPPING_R1',
        gates=gates,nominal_rows=6272,stress_rows=43904,static_waveforms=48,probe_failure_packets=len(failures),
        probe_max_excess_m=probe_max,max_endpoint_error_m=endpoint_max,
        source_run_receipt_sha256=sha256(run/'RUN_RECEIPT.json'),test_receipt_sha256=sha256(tests),
        contract_sha256=receipt['contract_sha256'],independent_audit=False,
        mapping_reviewed=False,E1_02_started=False,E2_started=False))
    print(json.dumps(json.loads((out/'GATE.json').read_text()),indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('run','static','tests','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();check(a.run,a.static,a.tests,a.output)
