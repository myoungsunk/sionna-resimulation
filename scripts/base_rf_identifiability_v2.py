#!/usr/bin/env python3
"""Implementation-only audit by default. RF replay is explicit and separately authorized."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.cli import main
from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.common import BlockedError,ContractError
if __name__=='__main__':
    try:raise SystemExit(main())
    except (BlockedError,ContractError) as exc:
        print(f'{type(exc).__name__}: {exc}',file=sys.stderr);raise SystemExit(2)
