"""Enumerate all Actions references, never inspect numeric result distributions."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
from github_io import session,api,sha

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--base-root',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    artifacts=defaultdict(set);runs=defaultdict(set)
    def record(dst,value,source):
        try:i=int(value)
        except (TypeError,ValueError):return
        if 100_000_000<=i<1_000_000_000_000:dst[i].add(source)
    def text_refs(value,source):
        for x in re.findall(r'(?:actions/artifacts/|artifact[-\s]*)(\d{8,})',value,re.I):record(artifacts,x,source)
        for group in re.findall(r'(?:actions/runs/|run\s*)(\d{8,}(?:\s*,\s*\d{8,})*)',value,re.I):
            for x in re.findall(r'\d{8,}',group):record(runs,x,source)
    def walk(value,source,key='',parent=None):
        if isinstance(value,dict):
            if ('archive_download_url' in value or '/actions/artifacts/' in str(value.get('url',''))) and 'id' in value:
                record(artifacts,value['id'],source)
            for k,v in value.items():
                if k.lower() in ['artifact_id','artifact_ids','combined_artifact']:
                    for x in v if isinstance(v,list) else [v]:record(artifacts,x,source)
                if k.lower() in ['run_id','actions_run_id','t2_run','old_run']:
                    for x in v if isinstance(v,list) else [v]:record(runs,x,source)
                if k=='artifacts' and isinstance(v,list):
                    for item in v:
                        if isinstance(item,dict):record(artifacts,item.get('id'),source)
                if k=='workflow_run' and isinstance(v,dict):record(runs,v.get('id'),source)
                walk(v,source,k,value)
        elif isinstance(value,list):
            for v in value:walk(v,source,key,parent)
        elif isinstance(value,str):text_refs(value,source)
    scanned=[]
    for p in sorted(args.base_root.rglob('*.json')):
        if not ('manifest' in p.name.lower() or 'receipt' in p.name.lower() or p.name=='ACTIONS_ARTIFACT.json'):continue
        rel=p.relative_to(args.base_root).as_posix();scanned.append(dict(path=rel,sha256=sha(p)));walk(json.loads(p.read_text(encoding='utf-8-sig')),rel)
    p=args.base_root/'00_SUMMARY_KO.md';text_refs(p.read_text(encoding='utf-8'),p.name);scanned.append(dict(path=p.name,sha256=sha(p)))
    s=session();metadata={}
    for run in sorted(runs):
        page=1
        while True:
            d=api(s,f'actions/runs/{run}/artifacts?per_page=100&page={page}')
            for a in d['artifacts']:
                metadata[a['id']]=a;artifacts[a['id']].add(f'expanded-run:{run}')
            if len(d['artifacts'])<100:break
            page+=1
    for aid in sorted(artifacts):
        if aid not in metadata:metadata[aid]=api(s,f'actions/artifacts/{aid}')
    rows=[]
    for aid in sorted(artifacts):
        a=metadata[aid]
        rows.append(dict(artifact_id=aid,run_id=a['workflow_run']['id'],source_commit=a['workflow_run']['head_sha'],name=a['name'],bytes=a['size_in_bytes'],original_digest=a.get('digest'),expired=a.get('expired'),expires_at=a.get('expires_at'),reference_sources=sorted(artifacts[aid])))
    result=dict(base_commit='034e57a7209a3bd1bb8857b24fd85c64942e1258',scanned_sources=scanned,referenced_runs={str(k):sorted(v) for k,v in sorted(runs.items())},artifacts=rows,artifact_count=len(rows),total_bytes=sum(x['bytes'] for x in rows),missing_digest_ids=[x['artifact_id'] for x in rows if not x['original_digest']],expired_ids=[x['artifact_id'] for x in rows if x['expired']])
    args.out.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({k:result[k] for k in ['artifact_count','total_bytes','missing_digest_ids','expired_ids']}))

if __name__=='__main__':main()
