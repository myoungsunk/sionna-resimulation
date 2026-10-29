"""Effective lock = frozen contract lock overlaid by the FROZEN amendment locks listed in RUN_REQUEST.json (in order).

An amendment lock is the last ```json block under '## AMENDMENT_LOCK' in contracts/<ID>.md, with status FROZEN and
base_contract_sha256 equal to the frozen contract's sha256. Overlay: 'resolved' and 'run_plan' merge per key,
'splits' merge per track, 'code_sha256' is replaced, every other key is replaced.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

EXP = Path(__file__).resolve().parent.parent
CONTRACT = EXP / "contracts" / "EXPERIMENT_CONTRACT_MBVAR-INFO-001.md"
REQ = EXP / "RUN_REQUEST.json"


def _last_json(text: str, heading: str):
    if heading not in text:
        return None
    seg = text.split(heading, 1)[1]
    blocks = re.findall(r"```json\n(.*?)\n```", seg, re.S)
    return json.loads(blocks[-1]) if blocks else None


def base_lock(contract=None):
    return _last_json(Path(contract or CONTRACT).read_text(), "## FROZEN_LOCK")


def amendment_lock(aid: str):
    p = EXP / "contracts" / f"{aid}.md"
    return _last_json(p.read_text(), "## AMENDMENT_LOCK") if p.exists() else None


def effective_lock(amendments=None, contract=None):
    contract = Path(contract or CONTRACT)
    lk = base_lock(contract)
    if lk is None:
        return None
    lk = json.loads(json.dumps(lk))
    if amendments is None:
        amendments = json.loads(REQ.read_text()).get("amendments", []) if REQ.exists() else []
    csha = hashlib.sha256(contract.read_bytes()).hexdigest(); applied = []
    for aid in amendments:
        al = amendment_lock(aid)
        if al is None:
            continue
        if al.get("status") != "FROZEN" or al.get("base_contract_sha256") != csha:
            raise SystemExit(f"ERR_CONTRACT_DRAFT amendment lock {aid} not FROZEN or not on this contract")
        for k, v in al.items():
            if k in ("resolved", "run_plan") and isinstance(v, dict):
                lk.setdefault(k, {}).update(v)
            elif k == "splits" and isinstance(v, dict):
                lk.setdefault("splits", {}).update(v)
            elif k not in ("status", "base_contract_sha256"):
                lk[k] = v
        applied.append(aid)
    lk["applied_amendment_locks"] = applied
    return lk
