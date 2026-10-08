"""Fixture solver; the gate still runs the actual task verifier."""
import runpy
import sys
from pathlib import Path

if sys.argv[1]=='exec':
    ws=Path(sys.argv[sys.argv.index('-C')+1])
    if (ws/'AGENTS.md').read_bytes()==b'Implement add.':
        (ws/'calc.py').write_bytes(b'def add(a,b): return a+b\n')
sys.argv.insert(1,'ok')
runpy.run_path(str(Path(__file__).with_name('fake_codex.py')),run_name='__main__')
