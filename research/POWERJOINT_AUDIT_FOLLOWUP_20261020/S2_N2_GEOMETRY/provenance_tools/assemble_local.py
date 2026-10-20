"""Assemble byte-identical recovered S2 text outputs; aggregate without rerunning filters."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[4];HERE=ROOT/'research/POWERJOINT_AUDIT_FOLLOWUP_20261020/S2_N2_GEOMETRY'
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--recovered',type=Path,required=True);p.add_argument('--selected',type=Path,required=True);p.add_argument('--new-run',type=int,required=True);a=p.parse_args()
 receipt=json.loads((a.recovered/'RECOVERY_RECEIPT.json').read_text());assert receipt['complete'];records=receipt['records'];assert len(records)==29
 for rec in records:
  source=a.recovered/f"run-{rec['actions_run_id']}"/rec['name'];target=HERE/'execution'/rec['name'];shutil.copytree(source,target,dirs_exist_ok=True)
  if rec['actions_run_id'] in [39374960558,a.new_run]:
   for route in ['R2','R4','R5'] if rec['actions_run_id']==39374960558 else ['C01','C02','C03','O01','O02','O03']:
    folder=source/'s2'/route
    if folder.exists():shutil.copytree(folder,a.selected/route,dirs_exist_ok=True)
 for name in ['RECOVERY_RECEIPT.json','PUBLIC_BUNDLE_RECEIPT.json']:
  shutil.copy2(a.recovered/name,HERE/name)
 for name in ['failure_logs']:
  if (a.recovered/name).exists():shutil.copytree(a.recovered/name,HERE/name,dirs_exist_ok=True)
 for path in a.recovered.glob('RUN_*.json'):shutil.copy2(path,HERE/'execution'/path.name)
 for path in a.recovered.glob('JOBS_*.json'):shutil.copy2(path,HERE/'execution'/path.name)
 subprocess.run([sys.executable,'-X','utf8',str(HERE/'aggregate.py'),'--execution',str(a.selected),'--out',str(HERE)],check=True)
 manifest=json.loads((HERE/'MANIFEST.json').read_text());manifest.update(original_artifacts=records,public_summary_bundle=json.loads((HERE/'PUBLIC_BUNDLE_RECEIPT.json').read_text()),protocol_commit='2f1b21b9f984ba0d5d3768f9a84a8f5b7d263683',training_code_commit='791e49671bbf1c45f94a3907002b27764bb56718',models_and_adapter_commit='481c249e04164ffc5deccaaefbcc84c16a5779f3',legacy_execution_commit='94c3255a6a4f016732b25bd4e40257ad74c922b0',new_execution_commit='d57e8960c52d30e8eb1b34ca39a9389cc4beb76b',preserved_S1_commit='5b2f7c509863558e4de1f184d38f2404699d248e',scope='S2 only; no S3',code_sha256={str(p.relative_to(HERE)):sha(p) for p in HERE.rglob('*.py') if '__pycache__' not in p.parts})
 dump(HERE/'MANIFEST.json',manifest)
 print('S2_TEXT_ASSEMBLED',len(records),flush=True)
if __name__=='__main__':main()
