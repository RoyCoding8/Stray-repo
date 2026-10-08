import pytest

from rsi import archive, genome, task
from settlement.common import ConflictPayload, SettlementError


def test_parent_weights_reward_score_and_penalize_children():
    assert archive.weight(0.5, 0) == 0.5
    assert archive.weight(0.5, 3) == 0.125
    assert archive.weight(0, 100) > 0
    assert archive.weight(1, 0) > archive.weight(0.5, 0)
    with pytest.raises(ValueError):
        archive.weight(1.1, 0)


def test_archive_keeps_every_node_and_replays_its_original_choice(migrated_db, tmp_path):
    roots = dict(staging_root=tmp_path/'stage', artifacts_root=tmp_path/'art')
    seed = genome.Genome({'AGENTS.md': b'seed'})
    genome.publish(migrated_db, seed, parent=None, origin='test', **roots)
    child = genome.Genome({'AGENTS.md': b'child'})
    genome.publish(migrated_db, child, parent=seed.digest, origin='test', **roots)
    dev = task.Task('simple', 'dev', 'solve', {'solve.py': b'pass'},
                    {'test.py': b'pass'}, {'solve.py': b'pass'}, ('test.py',))
    task.publish(migrated_db, dev, **roots)
    chosen = archive.select_parent(migrated_db, 'round-1', (dev.digest,), draw=0)
    recorded = archive.decision(migrated_db, 'round-1')
    assert recorded['actor'] == 'fixed'
    assert {n['digest'] for n in recorded['data']['nodes']} == {seed.digest, child.digest}
    assert all(n['weight'] > 0 and n['score'] == 0 and n['measured'] == 0
               for n in recorded['data']['nodes'])
    newest = genome.Genome({'AGENTS.md': b'newest'})
    genome.publish(migrated_db, newest, parent=child.digest, origin='test', **roots)
    assert archive.select_parent(migrated_db, 'round-1', (dev.digest,), draw=0.999) == chosen
    assert len(archive.decision(migrated_db, 'round-1')['data']['nodes']) == 2
    anchor = task.Task('held', 'anchor', 'solve', {'solve.py': b'pass'},
                       {'test.py': b'pass'}, {'solve.py': b'pass'}, ('test.py',))
    task.publish(migrated_db, anchor, **roots)
    with pytest.raises(SettlementError, match='dev tasks'):
        archive.select_parent(migrated_db, 'round-2', (anchor.digest,))


def test_decision_attribution_and_immutable_replay(migrated_db):
    data = dict(kind='proposal', actor='ai', subject='genome', data={'rationale': 'observed failure'})
    assert archive.record(migrated_db, 'choice', **data) == data
    assert archive.record(migrated_db, 'choice', **data) == data
    with pytest.raises(ConflictPayload):
        archive.record(migrated_db, 'choice', **dict(data, actor='fixed'))
