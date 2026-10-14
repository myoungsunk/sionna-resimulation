import os,sys,json,shutil,subprocess,hashlib
from pathlib import Path
import pandas as pd

HERE=Path(__file__).resolve().parent
REPO=HERE.parent/'PUBLISH_20261014/repo'
BRANCH='research/ekf3-independent-p0-20261013'
REL='research/EKF3_INDEPENDENT_20261013/diagnostics/heading_inverse/H4_POSTERIOR_STATE_CHECK_20261014'
ENV=os.environ.copy();ENV['GIT_INDEX_FILE']=str(HERE/'addendum.index')
def git(*args):
    p=subprocess.run(['git','-C',str(REPO),*args],env=ENV,capture_output=True,text=True,encoding='utf-8')
    if p.returncode:raise RuntimeError(p.stderr)
    return p.stdout.strip()
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def main():
    r=json.loads((HERE/'FULL/RECEIPT.json').read_text());sm=json.loads((HERE/'SMOKE/RECEIPT.json').read_text())
    assert sm['status']=='PASS'
    g=pd.read_csv(HERE/'FULL/GROUP_PARITY.csv')
    lines=['# H4 사후 상태 독립 검산 추가 결과', '',f"판정: **{r['status']}**. {r['rows']:,}개 업데이트, {r['groups']:,}개 그룹. 허용치 1e-8 유지, scientific_PASS=false.", '',
    '이전 H1–H4 결과의 NIS·gate·공분산 검산에 저장된 사후 상태 검산을 추가했다. 기존 결과 파일·필터·관측·임계값은 수정하지 않았다.', '',
    '| 모델 | 최대 x 오차 (m) | 최대 y 오차 (m) | 최대 Heading 오차 (rad) | 실패 시점 |', '|---|---:|---:|---:|---:|']
    for name,a in g.groupby('model'):
        lines.append(f"| {name} | {a.posterior_x_max_m.max():.9g} | {a.posterior_y_max_m.max():.9g} | {a.posterior_psi_max_rad.max():.9g} | {a.posterior_fail_rows.sum()} |")
    lines += ['',f"수용 {r['accepted']:,}개, 거부 {r['rejected']:,}개. 실제 보정에서 ±π 경계 통과 {r['wrap_crossings']:,}개. 양방향 wrap 및 잘못된 상태 주입 검사는 합성 검사에서도 수행했다.",'',
    '## 방법 및 주장 범위','',
    '- 이전 저장 posterior와 동결 motion으로 prior를 독립 계산했다. 현재 posterior 또는 정답 상태를 prior 생성에 사용하지 않았다.',
    '- 동일 prior에서 H, innovation, NIS, gate, gain 및 Joseph covariance를 재계산했다. 수용 시 x_prior + K innovation을, 거부 시 prior 그대로를 저장된 x/y/psi와 비교했다. Heading 차이는 wrap 후 라디안 단위로 비교했다.',
    '- 강건 모델은 저장된 최종 RF 가중치로 R_effective를 구성했다. 최적화 상태 보정량과 해당 gain 보정량의 일치성을 검산한 것이며, 강건 가중치 최적화를 독립 재실행한 검사는 아니다.',
    '- 각 그룹의 첫 저장 시점은 직전 posterior가 없어 제외했다. 기존 H4와 동일한 전체 평가 집합이다. 새로운 재귀 주행 실행 또는 독립 과학적 확증으로 표현하지 않는다.',
    '- 8개 합성 검사와 단일 조건 smoke 후 전체 H4 검산을 수행했다. 원본 source/input/trace 해시를 확인했다.', '',
    '[전체 증빙](FULL/RECEIPT.json) · [그룹별 검산](FULL/GROUP_PARITY.csv) · [시점별 상태와 잔차](FULL/STATE_RESIDUALS.csv.gz) · [기존 H1–H4](../H1_H4_20261014/SUMMARY_KO.md)', '',
    '## 재실행','',
    'check_posterior.py는 실제 실행된 Windows source snapshot이다. 원래 실험 폴더 아래에서 실행했으며 ../OPT/run_heading.py 및 원본 동결 입력 경로를 사용한다. 다른 환경에서는 기존 H1_H4_20261014의 OPT를 해당 위치로 매핑하고 입력 경로를 준비해야 한다. python -B check_posterior.py --smoke 후 python -B check_posterior.py 순서로 실행한다. 이미 존재하는 출력은 덮어쓰지 않는다.']
    (HERE/'SUMMARY_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    git('fetch','--depth=1','--filter=blob:none','origin',BRANCH)
    base=git('rev-parse','FETCH_HEAD');git('read-tree',base)
    target=REPO/REL;target.mkdir(parents=True,exist_ok=False)
    selected=[HERE/'check_posterior.py',HERE/'publish_addendum.py',HERE/'SUMMARY_KO.md',HERE/'EXECUTION_RECEIPT.json']
    selected+=list((HERE/'LOGS').glob('*'))
    selected+=list((HERE/'SMOKE').glob('*'))+list((HERE/'FULL').glob('*'))
    manifest={}
    for p in selected:
        relative=p.relative_to(HERE);dest=target/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
        assert sha(dest)==sha(p);manifest[relative.as_posix()]={'sha256':sha(p),'bytes':p.stat().st_size}
    (target/'PUBLICATION_MANIFEST.json').write_text(json.dumps(dict(base_commit=base,scope='ADDITIVE_ONLY',files=manifest),indent=2),encoding='utf-8')
    git('add','--',REL)
    changes=git('diff','--cached','--name-status').splitlines();assert all(x.startswith('A\t'+REL+'/') for x in changes)
    git('-c','core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol','diff','--cached','--check')
    tree=git('write-tree','--missing-ok');commit=git('commit-tree',tree,'-p',base,'-m','Add independent H4 posterior state and heading wrap verification')
    print('PREPARED',commit,len(changes),flush=True)
    git('push','origin',commit+':refs/heads/'+BRANCH)
    remote=git('ls-remote','origin','refs/heads/'+BRANCH).split()[0];assert remote==commit
    for p,info in manifest.items():
        expected=git('hash-object',str(target/p));actual=git('rev-parse',commit+':'+REL+'/'+p);assert expected==actual
    receipt=dict(status='PASS',commit=commit,base=base,remote_head=remote,files=len(changes),path=REL,result_status=r['status'])
    (HERE/'PUBLISHED.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt),flush=True)

if __name__=='__main__':main()
