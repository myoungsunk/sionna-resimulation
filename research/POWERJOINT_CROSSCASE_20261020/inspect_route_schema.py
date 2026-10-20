#!/usr/bin/env python3
"""Discover new route physical raw case layout on previously uploaded GH artifact.
No model or inference, saves CSV/JSON schema and sample values (bounded).
"""
import pathlib,sys,json,csv
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
route=sys.argv[3]
files=list(root.rglob("*"))
candidates=[]
for p in files:
 if not p.is_file():continue
 if p.suffix.lower() not in {".csv",".json"}:continue
 if p.stat().st_size>1_500_000:continue
 if p.suffix==".csv":
  try:
   with p.open(encoding="utf-8",newline="") as f:
    r=csv.reader(f);head=next(r,[]);sample=next(r,[])
   kind="csv"; keys=head;sample=sample[:25]
  except Exception as e:continue
 else:
  try:
   j=json.loads(p.read_text())
   keys=list(j)[:40] if isinstance(j,dict) else ["array","count",str(len(j))]
   sample=str(j)[:500]
   kind="json"
  except Exception:continue
 candidates.append({"path":str(p.relative_to(root)),"size":p.stat().st_size,"type":kind,"head":keys[:50],"example":sample})
selected=[c for c in candidates if any(x in c["path"].lower() for x in ["pose","route","manifest","scene_metadata","source_manifest","first_path","qa"])][:200]
report={"route":route,"files_total":len(files),"source_csv_json":len(candidates),"relevant":selected}
(out/f"{route}_SCHEMAS.json").write_text(json.dumps(report,indent=2,ensure_ascii=False))
for c in selected[:45]:print("SCHEMA",route,c["path"],c["head"][:25],str(c["example"])[:180])
