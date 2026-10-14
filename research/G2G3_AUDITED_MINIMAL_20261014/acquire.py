"""Audited acquisition of one pinned Actions artifact, no experiment inference.

No credentials are forwarded to redirected object storage or written to logs.
"""
from __future__ import annotations
import hashlib
import json
import os
import urllib.request
import urllib.error
import urllib.parse
import zipfile
import io
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    audit=json.loads((REPO/'outputs/g2g3_minimal/PRE_RUN_acquire.json').read_text())
    if audit['run_decision']!='GO_WITH_CLAIM_LIMITATION':
        raise RuntimeError('HARD_EXECUTION_BLOCK: acquisition audit not GO')
    for path,digest in audit['source_sha256'].items():
        if hashlib.sha256((REPO/path).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('HARD_EXECUTION_BLOCK: changed audited acquisition code')
    C=json.loads((ROOT/'CONTRACT.json').read_text())['source_artifact']
    uri='https://api.github.com/repos/myoungsunk/sionna-resimulation/actions/artifacts/'+str(C['artifact_id'])+'/zip'
    token=os.environ.get('GH_TOKEN')
    if not token:raise RuntimeError('Missing GitHub Actions artifact read token')
    req=urllib.request.Request(uri,headers={'Authorization':'Bearer '+token,
                  'Accept':'application/vnd.github+json','User-Agent':'g2g3-audited-acquisition'})
    try:
        response=urllib.request.build_opener(NoRedirect).open(req,timeout=30)
    except urllib.error.HTTPError as exc:
        if exc.code not in (301,302,303,307,308):
            raise RuntimeError('Artifact API returned status '+str(exc.code)) from None
        url=exc.headers['Location']
        parsed=urllib.parse.urlparse(url)
        if parsed.scheme!='https' or not (parsed.hostname.endswith('.blob.core.windows.net') or
                parsed.hostname.endswith('.githubusercontent.com')):
            raise RuntimeError('Unexpected artifact redirect host')
        response=urllib.request.urlopen(url,timeout=60)  # No authentication header.
    with response:
        data=response.read(100*1024*1024+1)
    if len(data)>100*1024*1024:raise RuntimeError('Artifact size limit exceeded')
    digest=hashlib.sha256(data).hexdigest()
    if digest!=C['zip_sha256']:raise RuntimeError('HARD_EXECUTION_BLOCK: artifact ZIP hash mismatch')
    target=REPO/'inputs/range_audit'
    target.mkdir(parents=True,exist_ok=False)
    hashes={}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sum(i.file_size for i in z.infolist())>500*1024*1024:
            raise RuntimeError('Artifact expansion exceeds audited bound')
        for name in (C['data'],C['unique_rf'],C['receipt']):
            if Path(name).name!=name:raise RuntimeError('Artifact path not a simple basename')
            raw=z.read(name)
            (target/name).write_bytes(raw)
            hashes[name]=hashlib.sha256(raw).hexdigest()
    (target/'ACQUISITION.json').write_text(json.dumps(dict(
        run_id=C['run_id'],artifact_id=C['artifact_id'],zip_sha256=digest,
        file_sha256=hashes,scope='read-only immutable source reuse'),indent=2))
    print('ACQUISITION_PASS',C['artifact_id'],digest,hashes)


if __name__=='__main__':main()
