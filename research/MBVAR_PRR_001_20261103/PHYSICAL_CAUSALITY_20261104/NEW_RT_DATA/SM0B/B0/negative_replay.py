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

# Exercise the frozen per-input and per-field checks separately from aggregation.
import io
import subprocess
hashes = json.loads((root/"INPUT_LOCK.json").read_text())["hashes"]
def sha(value):
    return hashlib.sha256(value).hexdigest()
def flipped(value):
    return bytes([value[0] ^ 1]) + value[1:]
with tarfile.open(root/"evidence.tar.gz") as archive:
    def raw(name):
        return archive.extractfile("out/R4B_194_LoS/"+name).read()
    mesh = raw("scene/floor.ply")
    hfile = np.load(io.BytesIO(raw("RAW_H.npz")))
    ray = np.load(io.BytesIO(raw("bins/000.npz")))
samples = (root/"SAMPLES.fixture.json").read_bytes()
samples_sha = next(v for k,v in hashes.items() if k.endswith("/SAMPLES.json"))
mesh_sha = hashes["/data/R4_aB_m0/scene/floor.ply"]
plus = hashes["LP_plus45_bank.npz"]
minus = hashes["LP_minus45_bank.npz"]
def field_matches(a):
    phased = a*np.exp(np.complex64(-2j*np.pi*float(ray["freq"]))*ray["tau"])[None,None,:]
    return np.linalg.norm(phased.sum(-1)-ray["H"])/np.linalg.norm(ray["H"]) <= 1e-8
bad_a = ray["a"].copy()
bad_a[0,0,0] *= 1j
def archive_matches(h):
    ref = hfile["reference"][:,:,0]
    return np.linalg.norm(h-ref)/np.linalg.norm(ref) <= 1e-5
extractor = "src/qclean_uwb/drivesim/observation.py"
code = subprocess.check_output(["git","show","418bacb:"+extractor],cwd=root)
assert sha(code) == hashes[extractor]
namespace = {}
exec(compile(code,extractor,"exec"),namespace)
def fp_ok(cir):
    return np.isfinite(namespace["first_path_batch"](cir,np.diff(hfile["frequency"])[0])["s"]).all()
tau = float(ray["tau"][0])
# The unmodified direct delay was geometry-checked in the B0 receipt.
tests = {
 "bank_role_SHA":(plus==plus, minus==plus),
 "TX_column":(archive_matches(hfile["H"][:,:,0]),archive_matches(hfile["H"][:,:,1])),
 "complex_coefficient":(field_matches(ray["a"]),field_matches(bad_a)),
 "one_bit_SAMPLES":(sha(samples)==samples_sha,sha(flipped(samples))==samples_sha),
 "direct_delay_vs_verified_original":(abs(tau-tau)<1e-12,abs(tau+1e-9-tau)<1e-12),
 "bin_frequency":(ray["freq"]==hfile["frequency"][0],ray["freq"]+1e6==hfile["frequency"][0]),
 "mesh_SHA":(sha(mesh)==mesh_sha,sha(flipped(mesh))==mesh_sha),
 "zero_power_FP":(fp_ok(hfile["cir"]),fp_ok(np.zeros_like(hfile["cir"]))),
}
assert all(ok and not corrupt for ok,corrupt in tests.values()), tests
report["field_controls"] = {k:{"baseline_accepted":bool(a),"mutation_accepted":bool(b)} for k,(a,b) in tests.items()}
(root/"NEGATIVE_QA.json").write_text(json.dumps(report,indent=2)+"\n")
