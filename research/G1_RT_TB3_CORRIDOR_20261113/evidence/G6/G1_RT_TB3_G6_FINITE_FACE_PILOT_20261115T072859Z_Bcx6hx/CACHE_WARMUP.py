import hashlib
import os
from pathlib import Path
import re
import sys
import tempfile
from datetime import datetime, timezone

dest = Path(sys.argv[1])
for arg in sys.argv[2:]:
    source = Path(arg)
    names = sorted(p.name for p in source.iterdir() if re.fullmatch(r"[0-9a-f]{32}\.llvm\.bin", p.name))
    added = 0
    for name in names:
        target = dest / name
        if target.exists():
            continue
        with tempfile.NamedTemporaryFile(dir=dest) as staged:
            staged.write((source / name).read_bytes())
            staged.flush()
            try:
                os.link(staged.name, target)
            except FileExistsError:
                continue
        added += 1
    print(datetime.now(timezone.utc).isoformat(), source, "keys", len(names), "added", added,
          "sorted_keys_sha256", hashlib.sha256("\n".join(names).encode()).hexdigest(), flush=True)
