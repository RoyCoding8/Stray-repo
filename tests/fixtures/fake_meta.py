"""Fixture proposal output. It exercises plumbing, not AI improvement."""
from pathlib import Path
import runpy
import sys

mode, args = sys.argv[1], sys.argv[2:]
if args[0] == 'exec' and mode in ('change', 'invalid'):
    workspace = Path(args[args.index('-C')+1])
    if mode == 'change':
        (workspace/'genome/AGENTS.md').write_bytes(b'Use literal examples and test boundary cases.\n')
        (workspace/'genome/meta/IMPROVE.md').write_bytes(b'Compare errors before changing instructions.\n')
    else:
        (workspace/'genome/README.md').write_text('outside genome layout')
sys.argv[1] = 'infra' if mode == 'infra' else 'ok'
runpy.run_path(str(Path(__file__).with_name('fake_codex.py')), run_name='__main__')
