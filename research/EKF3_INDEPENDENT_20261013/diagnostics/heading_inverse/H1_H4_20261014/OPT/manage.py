from pathlib import Path
import subprocess,sys,json,uuid
ROOT=Path(__file__).resolve().parent
PY='C:/Users/Myoungsun Kim/AppData/Local/Programs/Python/Python310/python.exe'
MGR='C:/Users/Myoungsun Kim/.codex/skills/managed-processes/scripts/manager.py'
THREAD='01a137c0-9673-7af0-9267-bbaee7060989'
F=ROOT/'OWNERSHIP.json'
if not F.exists():F.write_text(json.dumps(dict(run=str(uuid.uuid4()),thread=THREAD)))
owner=json.loads(F.read_text());action=sys.argv[1];stage=sys.argv[2] if len(sys.argv)>2 else 'CLOSURE'
if action=='start':
 task=[str(ROOT.parent/(stage+'.py'))] if stage in ('aggregate','render') else [str(ROOT/'run_heading.py'),stage]
 cmd=[PY,'-B',MGR,'start','--thread',THREAD,'--run',owner['run'],'--request',stage,'--',PY,'-B',*task]
elif action=='status':cmd=[PY,'-B',MGR,'status','--id',json.loads((ROOT/(stage+'_START.json')).read_text())['processes'][0]['id']]
elif action=='finish':cmd=[PY,'-B',MGR,'finish','--run',owner['run'],'--wait','10']
else:raise ValueError(action)
p=subprocess.run(cmd,capture_output=True);assert p.returncode==0,p.stderr
r=json.loads(p.stdout);(ROOT/(stage+'_'+action.upper()+'.json')).write_text(json.dumps(r,indent=2))
for item in r['processes']:
 print(json.dumps({k:item.get(k) for k in ['id','request_id','state','exit_code','ref_count','actual_process','actual_supervisor','job']}))
 if action=='status':
  for n in ['stdout.log','stderr.log']:
   f=Path(item['log_dir'])/n
   if f.exists():print(n,'\n'.join(f.read_text(encoding='utf-8',errors='replace').splitlines()[-8:]))
