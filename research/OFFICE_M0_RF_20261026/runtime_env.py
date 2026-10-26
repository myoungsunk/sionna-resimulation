"""Select the actual installed LLVM18 library without shell quoting."""
import json
import os
from pathlib import Path

candidates = sorted(p for p in Path("/usr/lib/x86_64-linux-gnu").glob("libLLVM*.so*")
                    if "18" in p.name and p.is_file())
if not candidates:
    raise RuntimeError("LLVM18_LIBRARY_NOT_FOUND")
library = str(candidates[0].resolve())
with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as stream:
    stream.write("DRJIT_LIBLLVM_PATH=" + library + "\n")
Path("work/RUNTIME_SETUP.json").write_text(json.dumps({"llvm_library": library,
    "status": "LLVM_LOCATED_RF_NOT_RUN"}, indent=2))
print("LLVM library:", library)

