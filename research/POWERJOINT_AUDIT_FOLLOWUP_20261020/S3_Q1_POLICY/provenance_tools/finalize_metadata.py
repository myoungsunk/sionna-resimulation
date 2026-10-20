"""Hash final text outputs without normalizing any prior summary bytes."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[4];HERE=ROOT/'research/POWERJOINT_AUDIT_FOLLOWUP_20261020/S3_Q1_POLICY'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def main():
 receipt=json.loads((HERE/'PUBLICATION_RECEIPT.json').read_text());manifest=json.loads((HERE/'MANIFEST.json').read_text());manifest.update(results_publication_commit=receipt['final_commit'],publication_receipt='PUBLICATION_RECEIPT.json',full_output_index='OUTPUT_INDEX.json',code_sha256={str(p.relative_to(HERE)):sha(p) for p in HERE.rglob('*.py') if '__pycache__' not in p.parts})
 if (HERE/'FINAL_VERIFICATION.json').exists():manifest['final_verification']=json.loads((HERE/'FINAL_VERIFICATION.json').read_text())
 dump(HERE/'MANIFEST.json',manifest)
 outputs={p.relative_to(HERE).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='OUTPUT_INDEX.json' and p.suffix.lower() not in ['.npz','.npy','.zip','.gz','.pkl']}
 assert all(r['bytes']<=20_000_000 for r in outputs.values())
 dump(HERE/'OUTPUT_INDEX.json',dict(outputs=outputs,files=len(outputs),root_summary_sha256=sha(HERE.parent/'00_SUMMARY_KO.md'),exclude='index self, bytecode, large binary traces retained in original Actions and release archives'))
 print('S3_FINAL_INDEX',len(outputs),flush=True)
if __name__=='__main__':main()
