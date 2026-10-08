import json
from pathlib import Path
import sys
from dataclasses import replace

import pytest

from rsi import archive, episode, genome, improve, task
from settlement import store
from settlement.common import Command
from settlement.launcher_codex import CodexLauncher, Provider


@pytest.mark.parametrize('mode,status', [('change','completed'),('invalid','invalid'),('infra','infra_failed'),('unchanged','invalid')])
def test_proposal_records_output_and_replays_without_another_send(migrated_db, tmp_path, mode, status):
    roots = dict(staging_root=tmp_path/'stage', artifacts_root=tmp_path/'art')
    seed = genome.Genome({'AGENTS.md':b'initial rules', 'meta/IMPROVE.md':b'Read dev failures.'})
    genome.publish(migrated_db, seed, parent=None, origin='test', **roots)
    store.seed_allocation(migrated_db, Command(request_id='tokens',payload={
        'allocation_id':'tokens','domain':'tokens','authorized':100000}))
    launcher = CodexLauncher(tmp_path/'runs',codex_cmd=[sys.executable,
        str(Path(__file__).parent/'fixtures/fake_meta.py'),mode],
        provider=Provider('http://fixture/v1','fixture:free','fixture'),allowed_overrides=genome.HARNESS_KEYS)
    kw=dict(operation_id='proposal',allocation_id='tokens',token_ceiling=5000,timeout_ms=30000,**roots)
    first = improve.propose(migrated_db,launcher,seed.digest,**kw)
    assert first.status == status
    if status == 'completed':
        child = genome.load(migrated_db,roots['artifacts_root'],first.child)
        assert child.files['AGENTS.md'] == b'Use literal examples and test boundary cases.\n'
        assert child.files['meta/IMPROVE.md'] == b'Compare errors before changing instructions.\n'
    else:
        assert first.child is None
    assert improve.propose(migrated_db,launcher,seed.digest,**kw) == first
    assert (tmp_path/'runs/proposal/fake-calls.txt').read_text().count('\n') == 1
    assert archive.decision(migrated_db,'proposal:proposal')['actor'] == 'ai'
    assert json.loads(improve.evidence_bundle(migrated_db,roots['artifacts_root'],seed.digest)) == {
        'parent':seed.digest,'failed_siblings':[],'dev_episodes':[]}


def test_genome_bytes_cannot_change_after_identity_is_computed():
    seed=genome.Genome({'AGENTS.md':b'rules'})
    with pytest.raises(TypeError):
        seed.files['AGENTS.md']=b'changed'
    with pytest.raises(genome.GenomeError,match='collide'):
        genome.Genome({'AGENTS.md':b'a','agents.md':b'b'})


def test_meta_evidence_excludes_validation_and_anchor_episodes(migrated_db, tmp_path):
    roots=dict(staging_root=tmp_path/'stage',artifacts_root=tmp_path/'art')
    seed=genome.Genome({'AGENTS.md':b'initial','meta/IMPROVE.md':b'Improve from dev.'})
    genome.publish(migrated_db,seed,parent=None,origin='test',**roots)
    store.seed_allocation(migrated_db,Command(request_id='budget',payload={
        'allocation_id':'tokens','domain':'tokens','authorized':100000}))
    launcher=CodexLauncher(tmp_path/'runs',codex_cmd=[sys.executable,
        str(Path(__file__).parent/'fixtures/fake_codex.py'),'ok'],
        provider=Provider('http://fixture/v1','fixture:free','fixture'),allowed_overrides=genome.HARNESS_KEYS)
    base=task.Task('visible-dev','dev','Implement solve.',{'solve.py':b'pass'},
                   {'test.py':b'pass'},{'solve.py':b'pass'},('test.py',))
    for split in ('dev','val','anchor'):
        item=replace(base,name='visible-dev' if split=='dev' else 'secret-'+split,split=split)
        task.publish(migrated_db,item,**roots)
        episode.run_episode(migrated_db,launcher,seed,operation_id='episode-'+split,task=item,
                            allocation_id='tokens',attempt_id=None,token_ceiling=5000,timeout_ms=30000,**roots)
    data=json.loads(improve.evidence_bundle(migrated_db,roots['artifacts_root'],seed.digest))
    assert [(e['name'],e['operation_id']) for e in data['dev_episodes']] == [('visible-dev','episode-dev')]
    assert 'secret-anchor' not in json.dumps(data)
    assert 'secret-val' not in json.dumps(data)
