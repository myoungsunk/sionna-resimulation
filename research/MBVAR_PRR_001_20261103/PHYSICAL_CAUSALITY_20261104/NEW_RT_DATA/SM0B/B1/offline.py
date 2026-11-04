from pathlib import Path
import subprocess, json, tarfile, ast
from gate import registry, keys, verify
here = Path(__file__).resolve().parent
reg = next(p for p in subprocess.check_output(["git","ls-tree","--full-tree","-r","--name-only","HEAD"],text=True).splitlines() if p.endswith("/SM0/references/REGISTERED_POSES.csv"))
(here/"registered.csv").write_bytes(subprocess.check_output(["git","show","HEAD:"+reg]))
expected = keys(registry(here/"registered.csv"))
rows = [dict(route=r,pose=p,mode=m,calls=257,status="PASS_TECHNICAL") for r,p,m in expected]
verify(expected,rows)
cases = dict(missing=rows[1:], duplicate=[rows[1],*rows[1:]], outside=[dict(rows[0],pose=-1),*rows[1:]], route_mix=[dict(rows[0],route="R5"),*rows[1:]])
results = {}
for name, bad in cases.items():
    try:
        verify(expected,bad)
    except ValueError as error:
        assert str(error)=="REGISTERED_KEY_MISMATCH"
        results[name]="REJECTED"
    else:
        raise AssertionError(name)
# Replay committed B0 field fixtures in memory, preserving historic output.
b0=here.parent/"B0"
source=(b0/"negative_replay.py").read_text()
tree=ast.parse(source)
tree.body=[n for n in tree.body if not (isinstance(n,ast.Expr) and "write_text" in ast.unparse(n))]
env={"__file__":str(b0/"negative_replay.py")}
exec(compile(tree,"negative_replay.py","exec"),env)
for name, (ok,corrupt) in env["tests"].items():
    assert ok and not corrupt
    results[name]="REJECTED"
assert len(results)==12
(here/"OFFLINE_QA.json").write_text(json.dumps(dict(solver_calls=0,baseline_keys=len(rows),controls=results),indent=2)+"\n")

