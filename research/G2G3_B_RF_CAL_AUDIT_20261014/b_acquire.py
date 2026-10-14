#!/usr/bin/env python3
"""Download the pinned validated RF/DR artifact without leaking GitHub credentials."""
from __future__ import annotations
import hashlib,json,os,urllib.request,urllib.error,urllib.parse
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OUT=REPO/"outputs"/"B_RF_SIGNED"
INPUT=REPO/"inputs"/"B_RF_SIGNED"

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def main():
    audit=json.loads((OUT/"PRE_RUN_acquire.json").read_text())
    if audit["run_decision"]!="GO_WITH_CLAIM_LIMITATION" or not audit["audited_code_matches_execution_sha"]:
        raise RuntimeError("HARD_EXECUTION_BLOCK: no source-bound acquisition audit")
    c=json.loads((ROOT/"CONTRACT.json").read_text())["source"]
    uri=f"https://api.github.com/repos/myoungsunk/sionna-resimulation/actions/artifacts/{c['artifact_id']}/zip"
    token=os.environ.get("GH_TOKEN")
    if not token:raise RuntimeError("Missing GitHub Actions read-only token")
    req=urllib.request.Request(uri,headers={"Authorization":"Bearer "+token,
        "Accept":"application/vnd.github+json","User-Agent":"g2g3-B-signed-audit"})
    try:
        response=urllib.request.build_opener(NoRedirect).open(req,timeout=30)
    except urllib.error.HTTPError as e:
        if e.code not in (301,302,303,307,308):
            raise RuntimeError("Artifact fetch failed HTTP "+str(e.code)) from None
        url=e.headers.get("Location","")
        host=urllib.parse.urlparse(url)
        if host.scheme!="https" or not (host.hostname or "").endswith(
            (".blob.core.windows.net",".githubusercontent.com")):
            raise RuntimeError("HARD_EXECUTION_BLOCK: untrusted redirected artifact host")
        response=urllib.request.urlopen(url,timeout=60) # No auth header forwarded.
    with response:
        data=response.read(100*1024*1024+1)
    if len(data)>100*1024*1024:
        raise RuntimeError("HARD_EXECUTION_BLOCK: downloaded artifact size overflow")
    digest=hashlib.sha256(data).hexdigest()
    if digest!=c["zip_sha256"]:
        raise RuntimeError("HARD_EXECUTION_BLOCK: input artifact SHA mismatch")
    INPUT.mkdir(parents=True,exist_ok=False)
    (INPUT/"frozen_source.zip").write_bytes(data)
    print("B_ACQUIRE_PINNED_PASS",c["artifact_id"],digest,flush=True)

if __name__=="__main__":main()
