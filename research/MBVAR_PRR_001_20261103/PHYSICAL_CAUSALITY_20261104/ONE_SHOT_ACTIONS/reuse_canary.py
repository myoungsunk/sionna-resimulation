"""Verify and stage the successful prior canary; never invokes a solver."""
import json,sys,urllib.request
from pathlib import Path
from orchestrate import sha,dump,safe_extract,ledger
def verify(work):
    import numpy as np
    lock=json.loads(Path(__file__).with_name("CANARY_REUSE.json").read_text())
    archive=work/"shard_canary.tar.gz"
    if not archive.exists():urllib.request.urlretrieve(lock["url"],archive)
    assert sha(archive)==lock["sha256"],"CANARY_ARCHIVE_SHA"
    safe_extract(archive,work/"canary_verified")
    d=work/"canary_verified/output_canary"
    hashes=json.loads((d/"OUTPUT_SHA256.json").read_text())
    actual={f.relative_to(d).as_posix() for f in d.rglob("*") if f.is_file() and f.name!="OUTPUT_SHA256.json"}
    assert set(hashes)==actual
    for name,h in hashes.items():assert sha(d/name)==h,name
    statuses=json.loads((d/"STATUS.json").read_text())
    expected={r["task_id"] for r in ledger() if r["route"]=="R4_B" and r["pose_id"] in ("194","234") and r["source_track"]=="ORIGINAL_6_WALL_CORRIDOR"}
    assert len(statuses)==4 and {r["task_id"] for r in statuses}==expected
    assert not (d/"STOP").exists() and json.loads((d/"CONTROL_PLANE_ERRORS.json").read_text())==[]
    for row in statuses:
        assert row["status"]=="PASS_TECHNICAL" and row["calls"]==row["saved_bins"]==257
        folder=d/row["task_id"]
        receipt=json.loads((folder/"result.json").read_text())
        assert receipt["archive_rel_L2"] <= (1e-3 if receipt["mode"]=="Full" else 1e-5)
        assert receipt["reassembly_rel_L2"]<=1e-8 and receipt["reassembly_max_normalized"]<=1e-8
        assert receipt["tap"]==receipt["reference_tap"]
        bins,=folder.glob("*/bins")
        assert {f.name for f in bins.glob("*.npz")}=={f"{i:03d}.npz" for i in range(257)}
        assert (bins.parent/"FIRST_PATH.npz").is_file()
        for f in bins.glob("*.npz"):
            with np.load(f) as z:
                h=(z["a"]*np.exp(np.complex64(-2j*np.pi*float(z["freq"]))*z["tau"])[None,None,:]).sum(-1)
                assert np.linalg.norm(h-z["H"])/np.linalg.norm(z["H"])<=1e-8
    dump(Path(str(archive)+".sha256.json"),dict(sha256=sha(archive),bytes=archive.stat().st_size))
    dump(work/"CANARY_REUSE_VERIFIED.json",dict(status="PASS_REUSED_CANARY",**lock))
    return lock
if __name__=="__main__":
    work=Path(sys.argv[1]);work.mkdir(parents=True,exist_ok=True);verify(work)
