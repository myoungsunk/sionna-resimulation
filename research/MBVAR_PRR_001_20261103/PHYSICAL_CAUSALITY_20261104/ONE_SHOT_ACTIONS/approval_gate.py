"""No execution on routine pushes; a separate explicit approval commit is required."""
import json,os,subprocess
from pathlib import Path
def authorized(event,attempt,execute,confirmation,approval,parent):
    if attempt!="1": return False
    if event=="workflow_dispatch":
        return execute=="true" and confirmation=="APPROVE_PR36_79156_16_WORKERS"
    return (event=="push" and approval.get("approved") is True
        and approval.get("implementation_commit")==parent
        and approval.get("total_calls")==79156 and approval.get("runners")==4
        and approval.get("workers")==16 and approval.get("retries")==0)
if __name__=="__main__":
    a=json.loads(Path(__file__).with_name("EXECUTION_APPROVAL.json").read_text())
    parent=subprocess.check_output(["git","rev-parse","HEAD^"],text=True).strip()
    ok=authorized(os.getenv("GITHUB_EVENT_NAME"),os.getenv("GITHUB_RUN_ATTEMPT"),
        os.getenv("EXECUTE"),os.getenv("CONFIRMATION"),a,parent)
    print("true" if ok else "false")
