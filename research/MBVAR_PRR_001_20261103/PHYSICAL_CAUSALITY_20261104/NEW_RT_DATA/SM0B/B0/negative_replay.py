import ast, hashlib, json, tarfile
from pathlib import Path
from types import SimpleNamespace
import numpy as np

root = Path(__file__).resolve().parent
with tarfile.open(root / "evidence.tar.gz") as t:
    ledger = (root / "SHA256SUMS.txt").read_text().splitlines()
    for line in ledger:
        sha, name = line.split(None, 1)
        assert hashlib.sha256(t.extractfile(name).read()).hexdigest() == sha, name
    source = ast.parse(t.extractfile("run.py").read())
    for name in ("QA.json", "INPUT_LOCK.json"):
        assert (root/name).read_bytes() == t.extractfile("out/"+name).read()
qa = json.loads((root / "QA.json").read_text())
# Replay the actual post-pool exit predicate without invoking a solver.
terminal = next(n for n in ast.walk(source) if isinstance(n, ast.Call)
                and ast.unparse(n.func) == "sys.exit")
expr = compile(ast.fix_missing_locations(ast.Expression(terminal.args[0])), "run.py", "eval")
def accepted(rows):
    return eval(expr, {"results":rows}) == 0

cases = {
    "baseline":qa, "missing_key":qa[:-1], "duplicate_key":qa[:-1]+[qa[0]],
    "out_of_pose_set":[dict(qa[0],pose=999999), *qa[1:]],
    "route_mixing":[dict(qa[0],route="R5"), *qa[1:]],
}
verdict = {k:accepted(v) for k,v in cases.items()}
assert verdict["baseline"]
report = dict(verified_archive_members=len(ledger),solver_calls=0,
              stage="existing post-pool acceptance predicate",accepted=verdict,
              gate="STOP" if any(v for k,v in verdict.items() if k!="baseline") else "PASS")
(root/"NEGATIVE_QA.json").write_text(json.dumps(report,indent=2)+"\n")
print(report)
