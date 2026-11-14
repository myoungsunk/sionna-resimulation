"""Apply the S0 exact B0 reference check as frozen replay emits scenarios."""
import json
from pathlib import Path
import subprocess
import sys


destination = Path(sys.argv[1])
command = sys.argv[2:]
with destination.open("w", encoding="utf-8") as log:
    with subprocess.Popen(command, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT) as run:
        for line in run.stdout:
            log.write(line)
            log.flush()
            print(line, end="", flush=True)
            if not line.startswith("R2_BIAS_CASE "):
                continue
            row = json.loads(line.removeprefix("R2_BIAS_CASE "))
            if row["level"] == "B0" and row["B0_archived_DR_prior_parity"] != [0.0, 0.0]:
                run.terminate()
                run.wait(timeout=10)
                print("S0_FAIL_B0_EXACT", row["case"], row["channel"], row["B0_archived_DR_prior_parity"])
                sys.exit(30)
        sys.exit(run.wait())