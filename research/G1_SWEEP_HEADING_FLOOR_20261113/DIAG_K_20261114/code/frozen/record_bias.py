"""Record scope and compatible inherited diagnostics for S2′."""
import hashlib
import json
from pathlib import Path
import sys

run = Path(sys.argv[1])
old = run.parent / "RUN3_20261113T085001Z" / "outputs"
manifest = old / "MANIFEST.json"
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert digest(manifest) == "5f9732bf406fde2e0f6bb7f80ad3b04979ec4e84c3d4731ed980e7af7a235ef3"
name = "S1P_BIAS_CHECK.json"
old_record = json.loads(manifest.read_text())
source = old / name
def has_hash(value, target, sha):
    if not isinstance(value, dict):
        return False
    return (any(str(key).endswith(target) and value == sha for key, value in value.items())
            or any(has_hash(child, target, sha) for child in value.values()))
assert has_hash(old_record, name, digest(source))
destination = run / "s2_out" / name
with destination.open("xb") as f:
    f.write(source.read_bytes())

