"""Separate trace/CSV arithmetic checks; does not import the analysis implementation."""
from pathlib import Path
import csv
import hashlib
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
M6 = Path('D:/SLAM_bot/artifacts/G1_GM_THETA_M6_20261116')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    root = json.loads((ROOT/'RUN_CONTRACT.json').read_text(encoding='utf-8'))
    lane = json.loads((OUT/'RUN_CONTRACT.json').read_text(encoding='utf-8'))
    assert lane['root_contract_sha256'] == sha(ROOT/'RUN_CONTRACT.json')
    assert lane['implementation_sha256'] == sha(OUT/'analyze_rref.py')
    assert all(sha(x['path']) == x['sha256'] for x in root['bindings'])
    char = json.loads((M6/'characterization/RUN_CONTRACT.json').read_text(encoding='utf-8'))
    with (OUT/'DISTANCE_EXPOSURE.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    with (OUT/'PACKET_EXPOSURE.csv').open(encoding='utf-8-sig', newline='') as f:
        packets = list(csv.DictReader(f))
    worst = 0.
    for route in ('R2','R4','R5'):
        tr = np.load(M6/f'attempt_02/implementation/seed10/{route}_G0.npz')
        cell = next(c for c in char['cells'] if c['route'] == route)
        old = np.load(cell['loro_trace']['path'])
        for field in ('x','P','Reff','H','t','pose_id','mask'):
            assert np.array_equal(tr[field], old[field]), (route,field)
        d = np.load(char['d3'][route]['path'])
        r,dist = tr['Reff'][:,1,1], tr['rho_before']
        for row in (v for v in rows if v['route']==route):
            label=row['distance_bin_m']
            if label=='all': sel=np.ones(dist.size,bool)
            elif label.startswith('near'):sel=dist<3.
            elif label.startswith('far'):sel=(dist>=3.)&(dist<10.)
            else:
                lo,hi=map(float,label[1:-1].split(','));sel=(dist>=lo)&(dist<hi)
            sel &= tr['mask']
            if row['population']=='accepted_supported':sel &= d['decomposition_support']
            assert sel.sum()==int(row['packets'])
            e=d['eps'][sel,1]; rr=r[sel]
            expected={'raw_second_over_R':np.average(e*e/rr),
                      'raw_centered_over_R':np.average((e-e.mean())**2/rr)}
            if row['population']=='accepted_supported':
                s=d['slow'][sel,1]
                expected.update(slow_second_over_R=np.average(s*s/rr),
                                slow_centered_over_R=np.average((s-s.mean())**2/rr))
            for name,value in expected.items():
                delta=abs(float(row[name])-value);worst=max(worst,delta)
                assert delta<1e-12
        route_packets=[v for v in packets if v['route']==route]
        assert len(route_packets)==tr['t'].size
        # Independently check arbitrary symmetric kernel windows by scalar double loops.
        p=np.load(cell['online']['path']); ds=p['ds'];dt=p['dt'];gy=p['gy']
        arc=np.r_[0.,np.cumsum(abs(ds[1:]))]
        angle=(gy[1:]-tr['x'][:-1,3]*dt[1:]+np.pi)%(2*np.pi)-np.pi
        yaw=np.r_[0.,np.cumsum(abs(angle))]
        for i in (0,137,tr['t'].size//2,tr['t'].size-1):
            history=[j for j in range(i) if tr['mask'][j] and tr['t'][j]>=tr['t'][i]-10.][-100:]+[i]
            def kernel(a,b):
                return np.exp(-abs(arc[a]-arc[b])-abs(yaw[a]-yaw[b])/np.deg2rad(10.))
            pair_sum=sum(kernel(a,b) for a in history for b in history)
            n_eff=len(history)**2/pair_sum
            n_w=sum(kernel(i,b) for b in history)
            rec=route_packets[i]
            assert abs(float(rec['N_eff'])-n_eff)<1e-10
            assert abs(float(rec['N_w'])-n_w)<1e-10
    out={'status':'PASS','checks':'All summaries from trace; G0 exact D5 parity; independent scalar kernel sums; all input hashes unchanged',
         'summary_rows':len(rows),'packet_rows':len(packets),'max_summary_abs_error':worst,
         'root_contract_sha256':sha(ROOT/'RUN_CONTRACT.json'),'verification_code_sha256':sha(__file__)}
    with (OUT/'VERIFICATION.json').open('x',encoding='utf-8') as f:
        json.dump(out,f,indent=2,ensure_ascii=False);f.write('\n')
    print(json.dumps(out,ensure_ascii=False))


if __name__=='__main__':main()
