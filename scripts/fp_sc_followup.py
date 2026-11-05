#!/usr/bin/env python3
"""FP-SC follow-up CLI: plan, format export, or explicitly authorized execution."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from qclean_uwb.fp_sc.followup.runner import main
if __name__ == "__main__":
    raise SystemExit(main())
