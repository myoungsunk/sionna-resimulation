"""Finalize S2 publication references and a full text-output hash index."""
from pathlib import Path
import hashlib,json
import pandas as pd
ROOT=Path(__file__).resolve().parents[4];HERE=ROOT/'research/POWERJOINT_AUDIT_FOLLOWUP_20261020/S2_N2_GEOMETRY'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def main():
 receipt=json.loads((HERE/'PUBLICATION_RECEIPT.json').read_text());head=receipt['final_commit'];parity=pd.read_csv(HERE/'T2_METRIC_PARITY.csv');assert len(parity)==180 and parity.max_abs_difference.max()<=1e-9
 checks=pd.read_csv(HERE/'CHECKS.csv');checks=checks[checks.check!='T2_SAME_SEED_ALL11_METRICS'];pd.concat([checks,parity],ignore_index=True).to_csv(HERE/'CHECKS.csv',index=False)
 report=HERE/'RESULTS_KO.md';text=report.read_text(encoding='utf-8');marker='\n## 최종 게시 영수증\n'
 if marker in text:text=text.split(marker)[0]
 text+=f'''{marker}

결과/원본 요약 498개 파일(101,231,274 bytes)은 18개 분할 커밋으로 게시했고 마지막 결과 커밋은 `{head}`다. 최종 metadata/검증 커밋은 이 결과 커밋의 후속이다. 전체 파일 hash는 OUTPUT_INDEX.json, 게시 내역은 PUBLICATION_RECEIPT.json이다.

신규 Q 180셀의 T2 **공통 11지표 전체**를 같은 seed/bias/motion scope로 다시 대조했으며 최대 차이는 {parity.max_abs_difference.max():.17g}다(T2_METRIC_PARITY.csv). 역사적 gate는 seed 0에 한해 확인했고 seed 1–4는 명시된 재생성 reference다. 증거 보존 성공 run39376022836은 29개 원본 archive의 SHA/CRC 및 release 전체 readback을 확인했다. 최종 독립 검증은 provenance_tools/verify_local.py로 재현한다.
'''
 verification=None
 if (HERE/'FINAL_VERIFICATION.json').exists():
  verification=json.loads((HERE/'FINAL_VERIFICATION.json').read_text())
  text+=f"\n최종 검증 영수증(FINAL_VERIFICATION.json): 게시 파일 {verification['remote_S2_files_byte_identical']}개 byte 일치, S0/S1/기존 감사 tree와 S1 요약 prefix 보존. 추론 특징 {verification['inference_feature_rows']:,}행을 저장된 prior 좌표로 독립 재계산한 최대 차이는 {verification['inference_feature_max_abs']:.17g}, μ/C 재계산 최대 차이는 {verification['inference_prediction_max_abs']:.17g}다. 최초 root summary 개행 정규화 오류는 정확한 pinned 원문 bytes 복구 후 재검증했고 ERRORS.json에 보존했다.\n"
 report.write_text(text,encoding='utf-8')
 summary=HERE.parent/'00_SUMMARY_KO.md';s=summary.read_bytes()
 if 'S2 결과 게시 커밋:'.encode('utf-8') not in s:summary.write_bytes(s+f'\nS2 결과 게시 커밋: `{head}` (18개 분할 커밋, 101,231,274 bytes). 원본29개 archive와 공개 release 전체 readback은 S2 MANIFEST/PUBLIC_BUNDLE_RECEIPT에 보존했다.\n'.encode('utf-8'))
 manifest=json.loads((HERE/'MANIFEST.json').read_text());manifest.update(results_publication_commit=head,publication_receipt='PUBLICATION_RECEIPT.json',full_output_index='OUTPUT_INDEX.json',T2_same_seed_common11_parity=dict(cells=180,max_abs_difference=float(parity.max_abs_difference.max()),historical_gate_seeds=[0],regenerated_reference_seeds=[1,2,3,4]),code_sha256={str(p.relative_to(HERE)):sha(p) for p in HERE.rglob('*.py') if '__pycache__' not in p.parts})
 if verification:manifest['final_verification']=verification
 manifest['outputs']={p.name:sha(p) for p in HERE.iterdir() if p.is_file() and p.name not in ['MANIFEST.json','OUTPUT_INDEX.json','FINAL_VERIFICATION.json']};dump(HERE/'MANIFEST.json',manifest)
 outputs={str(p.relative_to(HERE)).replace('\\','/'):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='OUTPUT_INDEX.json' and p.suffix.lower() not in ['.npz','.npy','.zip','.gz']}
 assert all(r['bytes']<=20_000_000 for r in outputs.values());dump(HERE/'OUTPUT_INDEX.json',dict(outputs=outputs,files=len(outputs),root_summary_sha256=sha(summary),exclude='index self and Python bytecode; NPZ kept only in verified original release archives'))
 print('S2_FINAL_INDEX',len(outputs),flush=True)
if __name__=='__main__':main()
