"""Bounded offline QA of published audit evidence; no RF or policy reruns."""
import ast
import base64
import csv
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
METRICS=['heading_rmse_deg','signed_heading_deg','heading_sigma_rms_deg','heading95',
         'heading_nees','pose_nees','conditional_xy_nees','xy_rmse_m',
         'bias_rmse_dps','bias_mean_dps','bias_final_dps']
TABLES={
    'T1_MEMORY/CANONICAL_RESULTS.csv':576,
    'T2_NEW_ROUTE_BASELINE/BASELINE.csv':108,
    'T4_F1_EVENT/INTERVENTIONS.csv':None,
    'T4_F1_EVENT/SRC_TAP/INTERVENTIONS.csv':None,
    'T5_INITIALIZATION/RESULTS.csv':360,
    'T6_RANGE/RANGE_REPLAY.csv':336,
    'T7_POLICY/POLICY_RESULTS.csv':432,
    'T9_SPEC/RESULTS.csv':72,
}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    failures=[];not_local=[];hash_checks=0;python_count=0;tables=[];stored_elsewhere=[]
    files=[p for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    for p in files:
        if p.stat().st_size>20_000_000:failures.append('FILE_OVER20MB:'+str(p.relative_to(ROOT)))
        if p.suffix.lower() in ('.npz','.npy','.zip','.pkl','.pickle','.tar'):
            failures.append('ARTIFACT_ONLY_BINARY:'+str(p.relative_to(ROOT)))
        if p.suffix=='.py':
            ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p));python_count+=1
    for p in ROOT.rglob('MANIFEST.json'):
        d=json.loads(p.read_text(encoding='utf-8-sig'))
        outputs=d.get('outputs',{})
        if not isinstance(outputs,dict):continue
        for name,want in outputs.items():
            if not isinstance(want,str) or len(want)!=64:continue
            f=p.parent/name
            if f.exists():
                hash_checks+=1
                if sha(f)!=want:failures.append('OUTPUT_SHA:'+str(f.relative_to(ROOT)))
            elif Path(name).suffix in ('.pkl','.pickle'):
                packed=ROOT/'T7_POLICY/TRAINED_MODELS_BASE64.json'
                item=json.loads(packed.read_text())['models'][Path(name).name]
                data=base64.b64decode(item['base64'],validate=True)
                if hashlib.sha256(data).hexdigest()!=want or len(data)!=item['bytes']:
                    failures.append('ENCODED_MODEL_SHA:'+name)
                else:stored_elsewhere.append(dict(manifest=p.relative_to(ROOT).as_posix(),name=name,
                                                 stored=packed.relative_to(ROOT).as_posix(),sha256=want))
            elif Path(name).suffix in ('.npz','.npy'):
                not_local.append(dict(manifest=p.relative_to(ROOT).as_posix(),artifact_only=name,sha256=want))
            else:
                matches=[q for q in files if q.name==Path(name).name and sha(q)==want]
                if matches:
                    stored_elsewhere.append(dict(manifest=p.relative_to(ROOT).as_posix(),name=name,
                                                 stored=matches[0].relative_to(ROOT).as_posix(),sha256=want))
                else:failures.append('MISSING_OUTPUT:'+str(f.relative_to(ROOT)))
    for rel,count in TABLES.items():
        p=ROOT/rel
        if not p.exists():failures.append('MISSING_TABLE:'+rel);continue
        with p.open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
        missing=set(METRICS)-set(fields)
        if missing:failures.append('MISSING_METRICS:'+rel+':'+str(sorted(missing)))
        if count is not None and len(rows)!=count:failures.append('ROW_COUNT:'+rel+':'+str(len(rows)))
        tables.append(dict(file=rel,rows=len(rows),common_metrics=len(set(METRICS)&set(fields))))
    def read(rel):
        with (ROOT/rel).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
    canonical={(x['case'],x['arm']):float(x['heading_rmse_deg']) for x in read('T1_MEMORY/CANONICAL_RESULTS.csv')
               if x['bias']=='B0' and x['dataset']=='old'}
    slide4=read('T3_SOURCEFFD_TABLES/SLIDE4_POWER.csv')
    slide4_delta=max(abs(float(x['heading_rmse_deg'])-canonical[x['case'],x['arm']]) for x in slide4)
    if slide4_delta>1e-9:failures.append('T3_SLIDE4_VS_T1:'+str(slide4_delta))
    result=dict(technical='TECHNICAL_PASS' if not failures else 'FAIL',python_syntax_files=python_count,
                checked_output_hashes=hash_checks,artifact_only_outputs=not_local,duplicate_control_view_outputs=stored_elsewhere,recursive_tables=tables,
                slide4_vs_canonical_max_heading_delta_deg=slide4_delta,
                files=len(files),largest_file_bytes=max(p.stat().st_size for p in files),failures=failures,
                limit='Publication integrity QA only. Original numeric parity/scorer evidence remains in task reports and Actions receipts.')
    (ROOT/'PUBLICATION_QA.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['technical','python_syntax_files','checked_output_hashes','recursive_tables','slide4_vs_canonical_max_heading_delta_deg','largest_file_bytes','failures']},ensure_ascii=False))
    if failures:raise SystemExit(1)

if __name__=='__main__':main()
