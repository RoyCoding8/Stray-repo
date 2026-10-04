# Windows environment for this repo

**Use the repo's own venv, not whatever `python` resolves to on PATH.**

```bash
cd /d/AI/Agent-Society-v2
.venv/Scripts/python.exe   # correct: D:\AI\Agent-Society-v2\.venv\Scripts\python.exe
```

`C:\CLI\cx\.venv\Scripts\python.exe` is **first on PATH** on this host and shadows
the repo environment. It is the Claude Code router's own environment — leave it
alone, do not modify or delete it — but do not run this project's code with it.

The two differ in installed packages: `psycopg` 3.3.6 in the router environment
against 3.3.5 in the repo's. The project declares `psycopg[binary]>=3.1`, so both
satisfy the pin today, and both are Python 3.13. That makes an accidental import
the only symptom, which is exactly the kind of error that passes review. Anything
that imports a project dependency must use the explicit path above.

For a script rather than an inline check:

```bash
.venv/Scripts/python.exe -c "import ast; ast.parse(open('path.py', encoding='utf-8').read())"
```

`.venv/` is gitignored (`.gitignore:5`), so using it never commits anything.

## Still forbidden

CI carries PostgreSQL and POSIX. Never run `pytest` and never run WSL from this
host, whatever the venv. `ast.parse`, `python -c` and pure-stdlib checks are the
only local execution intended here.