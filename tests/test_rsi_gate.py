from dataclasses import replace

import pytest

from rsi import archive, gate, genome, task
from settlement import db
from settlement.common import Command, SettlementError
from settlement import store
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher
from pathlib import Path
import sys


def test_paired_anchor_rule_requires_gain_without_regression():
    yes=gate.paired_verdict((False,)*6,(True,)*6,0.025)
    assert yes == dict(wins=6,losses=0,p_value=0.015625,alpha=0.025,promote=True)
    assert not gate.paired_verdict((False,)*4,(True,)*4,0.025)['promote']
    assert not gate.paired_verdict((True,False),(False,True),0.99)['promote']
    assert not gate.paired_verdict((True,)*6,(True,)*6,0.025)['promote']
    with pytest.raises(ValueError,match='unknown'):
        gate.paired_verdict((None,),(True,),0.025)


def test_frozen_gate_blocks_uncontained_execution_before_model_calls(migrated_db,tmp_path):
    roots=dict(staging_root=tmp_path/'stage',artifacts_root=tmp_path/'art')
    seed=genome.Genome({'AGENTS.md':b'seed'})
    child=genome.Genome({'AGENTS.md':b'child'})
    genome.publish(migrated_db,seed,parent=None,origin='test',**roots)
    genome.publish(migrated_db,child,parent=seed.digest,origin='test',**roots)
    base=task.Task('simple','dev','solve',{'solve.py':b'pass'},
                   {'test.py':b'pass'},{'solve.py':b'pass'},('test.py',))
    tasks=tuple(replace(base,name=split,split=split) for split in ('dev','val','anchor'))
    for t in tasks: task.publish(migrated_db,t,**roots)
    epoch=gate.freeze(migrated_db,tasks,gate.Budget('fixture:free',5000,30000))
    assert gate.freeze(migrated_db,tasks,gate.Budget('fixture:free',5000,30000)) == epoch
    class Uncontained:
        def declaration(self): return {'containment':False,'network':'none'}
    report=gate.run(migrated_db,Uncontained(),Uncontained(),gate_id='one',epoch=epoch,
                    parent=seed.digest,candidate=child.digest,token_allocation='unused',cpu_allocation='unused',**roots)
    assert report['disposition']=='blocked' and report['phases']=={}
    assert archive.decision(migrated_db,'gate:one')['actor']=='fixed'
    with db.connect(migrated_db) as conn:
        assert conn.execute('SELECT count(*) FROM operations').fetchone()[0] == 0
    alpha=gate.reserve_anchor(migrated_db,'one',(tasks[-1],))
    assert alpha==0.025
    assert gate.reserve_anchor(migrated_db,'one',(tasks[-1],))==alpha
    changed=replace(tasks[-1],name='renamed',runtime='another runtime')
    assert gate.anchor_identity(changed)==gate.anchor_identity(tasks[-1])
    task.publish(migrated_db,changed,**roots)
    with db.connect(migrated_db) as conn:
        conn.execute("INSERT INTO rsi_gate_runs (id,epoch,parent,candidate) VALUES ('two',%s,%s,%s)",
                     (epoch,seed.digest,child.digest))
    with pytest.raises(SettlementError,match='already exposed'):
        gate.reserve_anchor(migrated_db,'two',(changed,))


def test_benchmark_runs_real_verifier_and_replays_without_promoting(migrated_db,tmp_path):
    roots=dict(staging_root=tmp_path/'stage',artifacts_root=tmp_path/'art')
    seed=genome.Genome({'AGENTS.md':b'Leave the stub.'})
    child=genome.Genome({'AGENTS.md':b'Implement add.'})
    for g,parent in ((seed,None),(child,seed.digest)):
        genome.publish(migrated_db,g,parent=parent,origin='test',**roots)
    tests=b'import unittest\nfrom calc import add\nclass Test(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2,3),5)\n'
    base=task.Task('dev','dev','Implement add.',{'calc.py':b'def add(a,b): pass\n'},
                   {'test.py':tests},{'calc.py':b'def add(a,b): return a+b\n'},('test.py',))
    tasks=(base,replace(base,name='val',split='val'),*(
        replace(base,name='anchor-'+str(i),split='anchor',instruction='Implement add. Case '+str(i)) for i in range(6)))
    for t in tasks: task.publish(migrated_db,t,**roots)
    for name,domain in (('tokens','tokens'),('cpu','cpu')):
        store.seed_allocation(migrated_db,Command(request_id=name,payload={
            'allocation_id':name,'domain':domain,'authorized':100000}))
    agent=CodexLauncher(tmp_path/'runs',codex_cmd=[sys.executable,
        str(Path(__file__).parent/'fixtures/fake_gate.py')],
        provider=Provider('http://fixture/v1','fixture:free','fixture'),allowed_overrides=genome.HARNESS_KEYS)
    local=LocalLauncher(tmp_path/'verifiers')
    epoch=gate.freeze(migrated_db,tasks,gate.Budget('fixture:free',5000,30000),execution='benchmark')
    kw=dict(gate_id='comparison',epoch=epoch,parent=seed.digest,candidate=child.digest,
            token_allocation='tokens',cpu_allocation='cpu',**roots)
    report=gate.run(migrated_db,agent,local,**kw)
    assert report['scope']=='benchmark'
    assert report['disposition']=='experimental_gain'
    assert report['anchor_comparison']['wins']==6
    assert report['phases']['regression']==[]
    assert [r['passed'] for r in report['phases']['val']]==[False,True]
    before=store.allocation_status(migrated_db,'tokens')['consumed']
    assert gate.run(migrated_db,agent,local,**kw)==report
    assert store.allocation_status(migrated_db,'tokens')['consumed']==before
