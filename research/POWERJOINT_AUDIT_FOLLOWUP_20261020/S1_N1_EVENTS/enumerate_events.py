"""Enumerate frozen geometric RF visits only; no observation/filter/model execution.

--new-traces accepts preserved T2 seed0 NPZ inputs recursively; alternatively
--new-csv-root accepts exact released */CASES/<case>/RADIO_POSE.csv files.
The CSV alternative uses successful T2 manifest motion_n for timeline end only.
EVENT_LIST contains included events; the receipt retains every candidate.
"""
from pathlib import Path
import argparse,ast,base64,csv,hashlib,io,json,zipfile
import numpy as np

OLD=('R2_aA_m0','R2_aA_m45','R2_aB_m0','R4_aA_m0','R4_aB_m0','R5_aA_m0','R5_aB_m0')
NEW=tuple(f'{r}_{a}_M45_FULL' for r in ('C01','C02','C03','O01','O02','O03') for a in (('A','B') if r.startswith('C') else ('O0',)))

def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def write_csv(path,rows):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def same_file(paths):
    if not paths:raise ValueError('MISSING_RAW_NEW_INPUT')
    hashes={digest(p) for p in paths}
    if len(hashes)!=1:raise ValueError('NONIDENTICAL_DUPLICATE_INPUT')
    return sorted(paths)[0]

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--old-rf-zip',type=Path,required=True)
    group=ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--new-traces',type=Path)
    group.add_argument('--new-csv-root',type=Path)
    ap.add_argument('--t2-manifest',type=Path,default=Path(__file__).resolve().parents[2]/'POWERJOINT_AUDIT_RERUN_20261020/T2_NEW_ROUTE_BASELINE/MANIFEST.json')
    ap.add_argument('--physical-draft',type=Path,default=Path(__file__).with_name('EVENT_PROVENANCE_DRAFT.json'))
    ap.add_argument('--out',type=Path,default=Path(__file__).parent)
    a=ap.parse_args();inputs=[];datasets={}
    with zipfile.ZipFile(a.old_rf_zip) as z:
        for case in OLD:
            member=f'P2_OUT/{case}_full_seed0_ONE_STEP.npz';raw=z.read(member)
            with np.load(io.BytesIO(raw),allow_pickle=False) as d:
                datasets[case]=(d['t_s'].copy(),d['truth_for_offline_scoring_only'][:,:3].copy(),d['pose_id'].copy(),np.arange(len(d['t_s'])),float(d['t_s'][-1]))
            inputs.append(dict(case=case,path=str(a.old_rf_zip),member=member,sha256=hashlib.sha256(raw).hexdigest(),archive_sha256=digest(a.old_rf_zip)))
    t2=json.loads(a.t2_manifest.read_text(encoding='utf-8'));metadata={r['route']:r['inputs'] for r in t2['routes']}
    for case in NEW:
        if a.new_traces:
            p=same_file(list(a.new_traces.rglob(case+'_B0.npz')))
            with np.load(p,allow_pickle=False) as d:
                t=d['t'];radio=np.flatnonzero(d['radio_mask'].astype(bool));truth=d['truth_for_offline_scoring_only'];ids=d['radio_pose_ids']
                assert len(ids)==len(radio)
                datasets[case]=(t[radio].copy(),truth[radio,:3].copy(),ids.copy(),radio,float(t[-1]))
        else:
            p=same_file([p for p in a.new_csv_root.rglob('RADIO_POSE.csv') if p.parent.name==case])
            with p.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
            t=np.array([float(r['t_s']) for r in rows]);truth=np.array([[float(r['x_m']),float(r['y_m']),np.radians(float(r['yaw_body_deg']))] for r in rows]);ids=np.array([int(r['pose_id']) for r in rows])
            motion=np.rint(t/.25).astype(int);assert np.max(abs(motion*.25-t))<1e-9
            end=(metadata[case[:3]]['motion_n']-1)*.25
            datasets[case]=(t,truth,ids,motion,end)
        inputs.append(dict(case=case,path=str(p),sha256=digest(p),bytes=p.stat().st_size))
    draft=json.loads(a.physical_draft.read_text(encoding='utf-8'));references={}
    source=next(s for s in draft['official_sources_raw_bytes'] if s['path'].endswith('online_packet_audit.py'))
    tree=ast.parse(base64.b64decode(source['source_bytes_base64']).decode())
    spec=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SPEC' for t in n.targets))
    for route,anchor,axis,low,high,visit,gain in spec:
        references[(f'{route}_{anchor}_M45_FULL',axis[0],low,high,visit)]=gain
    records=[]
    for case,(t,truth,ids,motion,end) in datasets.items():
        assert np.all(np.diff(t)>0) and len(np.unique(ids))==len(ids)
        old=case in OLD;axis='y' if case.startswith('O') else 'x';column=1 if axis=='y' else 0
        bins=((0,4),(4,8),(8,12)) if axis=='y' else ((1,4),(4,10),(10,16),(16,20 if old else 21))
        for low,high in bins:
            mask=(truth[:,column]>=low)&(truth[:,column]<high)&(t>=0)
            changes=np.diff(np.r_[False,mask,False].astype(int));starts=np.flatnonzero(changes==1);stops=np.flatnonzero(changes==-1)
            for visit,(i0,i1) in enumerate(zip(starts,stops),1):
                if visit>5:break
                n=int(i1-i0);post=bool(float(t[i1-1])+30<=end+1e-9);included=n>=3 and post
                event=f'{case}_{axis}{low}_{high}_V{visit}'
                records.append(dict(event=event,case=case,population='legacy' if old else 'new',axis=axis,low=low,high=high,visit=visit,rf_i0=int(i0),rf_i1_exclusive=int(i1),n=n,first_pose_id=int(ids[i0]),last_pose_id=int(ids[i1-1]),motion_i0=int(motion[i0]),motion_i1_exclusive=int(motion[i1-1]+1),t_start_s=float(t[i0]),t_end_s=float(t[i1-1]),timeline_end_s=end,required_horizon_end_s=float(t[i1-1])+30,full_post30_available=post,included=included,exclusion_reason='' if included else '|'.join(x for x,b in [('N_LT3',n<3),('INCOMPLETE_POST30',not post)] if b)))
                records[-1].update(historical_skip_reference_deg=references.get((case,axis,low,high,visit),''),historical_reference_only=True)
    comp=[]
    for e in draft['physical_61_not_original47']['events']:
        matches=[r for r in records if (r['case'],r['axis'],r['low'],r['high'],r['visit'])==(e['case'],e['axis'],e['low'],e['high'],e['visit'])]
        r=matches[0] if len(matches)==1 else None
        equal=bool(r and all(abs(float(r[k])-float(e[j]))<=1e-9 for k,j in [('rf_i0','i0'),('rf_i1_exclusive','i1'),('n','n'),('t_start_s','t_start_s'),('t_end_s','t_end_s')]))
        comp.append(dict(event=e['event'],case=e['case'],axis=e['axis'],low=e['low'],high=e['high'],visit=e['visit'],source_artifact_id=e['source_artifact_id'],source_i0=e['i0'],source_i1=e['i1'],enumerated_i0=r['rf_i0'] if r else '',enumerated_i1=r['rf_i1_exclusive'] if r else '',membership_equal=equal,included=r['included'] if r else False,exclusion_reason=r['exclusion_reason'] if r else 'MISSING_CANDIDATE'))
    # Membership disagreement is evidence, not silently repaired/filter-selected.
    a.out.mkdir(parents=True,exist_ok=True);write_csv(a.out/'EVENT_LIST.csv',[r for r in records if r['included']]);write_csv(a.out/'PHYSICAL_ROW_COMPARISON.csv',comp)
    receipt=dict(status='ENUMERATED_FROM_FROZEN_GEOMETRY',original_77_status='BLOCKED_SOURCE_UNAVAILABLE',script_sha256=digest(Path(__file__)),input_receipts=inputs,t2_manifest_sha256=digest(a.t2_manifest),membership='Half-open spatial bins,t>=0,maximal contiguous RF runs; visit1..5 assigned before n/horizon filtering; n>=3 and entire event_end+30s available.',counts={group:{'candidates':sum(r['population']==group for r in records),'included':sum(r['population']==group and r['included'] for r in records)} for group in ('legacy','new')},physical61_comparison=dict(rows=len(comp),equal=sum(r['membership_equal'] for r in comp)),outputs={n:dict(sha256=digest(a.out/n),bytes=(a.out/n).stat().st_size) for n in ('EVENT_LIST.csv','PHYSICAL_ROW_COMPARISON.csv')},filter_or_RF_execution=False)
    receipt['all_candidates_before_filtering']=records
    receipt['counts_by_route']={route:dict(candidates=sum(r['case'].startswith(route+'_') for r in records),included=sum(r['case'].startswith(route+'_') and r['included'] for r in records)) for route in ('R2','R4','R5','C01','C02','C03','O01','O02','O03')}
    receipt['checks']=dict(unique_candidate_events=len({r['event'] for r in records})==len(records),physical61_membership_match=all(r['membership_equal'] for r in comp),included_n_and_horizon_pass=all(r['n']>=3 and r['full_post30_available'] for r in records if r['included']))
    receipt['historical_SPEC12_source_sha256']=source['sha256']
    receipt['preserved_release_restore_receipts']=[dict(path=str(p),sha256=digest(p),receipt=json.loads(p.read_text(encoding='utf-8'))) for p in sorted(a.new_traces.rglob('S1_RESTORE_RECEIPT.json'))] if a.new_traces else []
    (a.out/'EVENT_ENUMERATION_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'counts':receipt['counts'],'physical61_comparison':receipt['physical61_comparison']}))

if __name__=='__main__':main()
