"""S1 input audit only. No RF extraction, simulation, fitting, or filter execution."""
from pathlib import Path
import argparse,base64,collections,csv,datetime,hashlib,json,sys

def digest(data):return hashlib.sha256(data).hexdigest()
def write_json(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);a=p.parse_args()
 out=Path(__file__).resolve().parent;source=a.source.resolve()
 sys.path.insert(0,str(out.parent/'S0_CORRECTIONS'))
 from github_io import api,session
 s=session();branch='research/powerjoint-audit-followup-20261020'
 head=api(s,'git/ref/heads/'+branch)['object']['sha']
 engine_path='research/POWERJOINT_AUDIT_RERUN_20261020/canonical_engine.py'
 engine_commit='034e57a7209a3bd1bb8857b24fd85c64942e1258'
 remote=api(s,'contents/'+engine_path,params={'ref':engine_commit})
 remote_bytes=base64.b64decode(remote['content']);local=(source/engine_path).read_bytes()
 assert local==remote_bytes,'ENGINE_BYTE_IDENTITY_FAIL'
 sensor_path='research/POWERJOINT_AUDIT_RERUN_20261020/T2_NEW_ROUTE_BASELINE/PROTOCOL_LOCK.json'
 sensor_sha=digest((source/sensor_path).read_bytes())
 assert sensor_sha=='b05e7ead6cf658d20a4830094cec56332ffcc839e7dccf04fd4ce3a1f86ccef0','SENSOR_LOCK_SHA_FAIL'
 draft_path=out/'EVENT_PROVENANCE_DRAFT.json';draft=json.loads(draft_path.read_text(encoding='utf-8'))
 source_checks=[]
 for row in draft['official_sources_raw_bytes']:
  raw=base64.b64decode(row['source_bytes_base64']);assert digest(raw)==row['sha256']
  assert len(raw)==row['bytes']
  blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
  assert blob==row['blob_sha']
  source_checks.append({k:row[k] for k in ['commit','path','blob_sha','sha256','bytes']})
 events=draft['physical_61_not_original47']['events']
 assert len(events)==61 and len({x['event'] for x in events})==61
 counts=dict(sorted(collections.Counter(x['case'].split('_')[0] for x in events).items()))
 assert counts=={'C01':14,'C02':14,'C03':18,'O01':1,'O02':5,'O03':9}
 assert draft['requested_roster']['certified_event_rows']==0 and not draft['locked']
 fields=['event','case','axis','low','high','visit','i0','i1','n','t_start_s','t_end_s','source_artifact_id','source_member','T2_motion_clock_last_time_s','T2_full_post30_horizon_available']
 with (out/'PHYSICAL_61_CANDIDATES_NOT_S1_ROSTER.csv').open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(events)
 receipt={'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'task':'S1_N1_EVENTS','technical':'BLOCKED_INPUT','scientific_verdict':'NOT_ESTABLISHED','input_audit_checks':'PASS','base_head_observed':head,'engine':{'commit':engine_commit,'path':engine_path,'blob_sha':remote['sha'],'sha256':digest(local),'local_equals_pinned_remote_bytes':True},'sensor_lock':{'path':sensor_path,'sha256':sensor_sha},'provenance_draft_sha256':digest(draft_path.read_bytes()),'embedded_source_checks':source_checks,'requested_roster_count':77,'certified_original_roster_count':0,'physical_candidate_count':61,'physical_candidate_counts_by_route':counts,'physical_candidates_are_replacement_roster':False,'legacy_los_exists':'NOT_ESTABLISHED_ACTUAL_SOURCE_FLAGS','new_pairing_scope':draft['new_pairing']['status'],'PROTOCOL_LOCK_written':False,'recursive_executions':0,'new_Actions_runs':[],'new_artifacts':[],'numerical_claims_unchanged':True}
 write_json(out/'INPUT_AUDIT.json',receipt)
 print(json.dumps({k:receipt[k] for k in ['technical','input_audit_checks','base_head_observed','requested_roster_count','certified_original_roster_count','physical_candidate_count','recursive_executions']},ensure_ascii=False))
if __name__=='__main__':main()
