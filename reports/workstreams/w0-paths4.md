# w0-paths4 — host-independent paths in the remaining four sites

Base `ccd3df3` (the sibling fix, "Name repository-relative paths with forward
slashes everywhere"). Branch `wt/w0-paths4`. Four changes, one token each.

## The defect

`str(path.relative_to(root))` renders with the host separator. On Windows that
is a backslash. The committed data in this repo is forward-slash throughout, so
a build on this host names a file differently from the same build on Linux.
The per-file digests stay correct either way, which is what makes the defect
quiet: the manifest describing the files is simply a different byte string on
each operating system, and no digest check sees it.

## Per-site evidence that the string is host-dependent

All four reproduced on this host (`os.sep == '\\'`), before any change.

| Site | What it feeds | Kind | Changed | Why |
|---|---|---|---|---|
| `experiments/representation/splits.py:319` | `manifest.json` `files[].path`, inside the bytes hashed into `manifest.sha256` | digest-bearing manifest | yes | A rebuild on Windows cannot reproduce the committed `manifest.sha256` |
| `experiments/representation/acquire/contexts.py:74` | `path` of every task in `source_context.json` / `transfer_context.json`; read back at `acquire/run.py:817` as `ROOT / entry["path"]` | digest-pinned document, and a lookup | yes | Not a pure lookup key. `experiment/freeze.py:145` digests the whole document, so the separator changes the document digest |
| `scripts/checkpoint.py:135` | `manifest.json` `artifacts[].path`, consumed by `restore.py:267` | digest-bearing manifest | yes | Pairs with site 4 |
| `scripts/restore.py:275` | `sorted(...)` compared against `sorted(e["path"] for e in manifest["artifacts"])` | string comparison in a verification | yes | The recovery path rejecting an intact backup |

### Site 1 — splits.py

```
first 3 : ['controls\\ctrl-gr-bipartite.json', 'controls\\ctrl-gr-triangle.json', ...]
backslash entries: 44 of 44
committed first 3: ['controls/ctrl-gr-bipartite.json', 'controls/ctrl-gr-triangle.json', ...]
REBUILD EQUALS COMMITTED: False
```

44 of 44 entries carry a backslash. The committed manifest has zero.

### Site 2 — contexts.py

The question posed for this site was whether the string is a comparison, a
manifest, or only a lookup key. It is all three, and the manifest role is what
makes it a defect.

```
returned:  'software\\development\\sw-dev-00.json'
committed: 'software/development/sw-dev-00.json'
```

`experiment/freeze.py:145` computes `_digest(committed) != _digest(rebuilt)`
over the whole document and raises `committed source_context.json drifted from
its generator`. With 10 task paths in the document, the separator alone moves
the digest:

```
committed digest: 3929da0e1d29b79cd46441ec1f439ded43e76d9ecfaa177c5944e21e02209698
rebuilt   digest: ecdd706053ad392fdf8c2e0169b3d06029c99279cabb6c4799d4f06f96db6672
differing bytes: 21927 of 28336
```

It is also a real lookup: `acquire/run.py:817` does
`(ROOT / entry["path"]).read_bytes()`. A backslash is a legal filename
character on Windows, so that read succeeds locally and resolves to nothing on
the host that consumes the context. The defect is quiet in both directions.

### Site 3 and 4 — checkpoint.py and restore.py

```
manifest paths  : ['world-0\\dev\\ad01-w0-dev-gr-00.json', 'world-0\\top.txt']
tar member names: ['world-0/dev/ad01-w0-dev-gr-00.json', 'world-0/top.txt']

SAME-HOST  hashed == expected: True
CROSS-HOST hashed != expected: False
           -> restore would record: artifact tar contents differ from manifest
```

A useful detail fell out of this. The tar was always portable:
`tarfile.TarFile.gettarinfo` applies `arcname.replace(os.sep, "/")`
(stdlib source, line 22 of that method). Its members read `world-0/dev/...`
on this host while the manifest said `world-0\dev\...`. So the two halves of
the comparison were never agreeing on this host in the first place; they were
only agreeing with each other, and only because both were wrong the same way.

## The fix

Converged on `path.relative_to(root).as_posix()`, the form
`experiments/ad01/worlds.py:86` and nine other sites already use. No helper, no
normalizer, no shim. `scripts/restore.py:275` is the only line that got
shorter (99 chars, was 101).

## Deliberately left alone

`scripts/checkpoint.py:146` — `arcname=str(path.relative_to(root))` in
`_write_tar`. It is in my owned file and it is the fifth `str(...relative_to())`
in the repo, but it is not the same defect. `gettarinfo` normalizes the
arcname before storing it, which the reproduction above shows directly: the tar
members were forward-slash while the manifest was not. Changing it would be a
cosmetic edit to a value the stdlib already makes host-independent, and the
test `test_the_artifact_tar_member_names_are_forward_slash_already` now guards
the pairing so a future stdlib change would be caught here rather than in a
restore.

Two other findings outside my scope, recorded not edited:

- `.gitattributes` covers `experiments/representation/fixtures/**` and
  `experiments/representation/experiment/**` with `text eol=lf`, but not
  `experiments/representation/acquire/**`. With `core.autocrlf=true` the
  committed contexts check out as CRLF, so `freeze.py:145` fails on a correct
  checkout. That is the sole remaining cause of the four pre-existing failures
  listed below. It is a second host-dependency in the same freeze, and the
  fix is a two-line `.gitattributes` addition, which is not mine to make.
- `experiments/team01/freeze.py:39` and
  `experiments/coord02/corpus/generate.py:832` sort manifest entries by
  `path`. With backslash-separated paths the sort order differs from the
  forward-slash order, so a host could emit a differently *ordered* manifest
  even where every path is spelled the same. I did not confirm a committed
  freeze is affected.

## Checkpoint and restore round trip

No PostgreSQL and no Docker on this host: no `pg_dump` on PATH, no server
listening, `find` for `pg_dump.exe` returns nothing. The database halves of
`run_checkpoint` and `run_restore` (`pg_dump`, `pg_restore`, `checkpoint_barrier`,
`restore_fence`) cannot execute here and I did not run them. I say so rather
than claim a pass I did not observe.

The artifact half, which is the half these four lines govern, runs for real
over a real tar written by the real `_write_tar` and read by the real
`run_restore`. `run_restore` is driven as an operator drives it, with only its
database calls substituted at seams it already has.

```
checkpoint._artifact_manifest from: D:\...\w0-paths4\scripts\checkpoint.py
restore module from:              D:\...\w0-paths4\scripts\restore.py

1. CHECKPOINT manifest artifacts:
     path= world-0/dev/ad01-w0-dev-gr-00.json  sha256= d18b57997e0c7cfd...
     path= world-0/top.txt                    sha256= f7de2947c64cb643...
   tar members          : ['world-0/dev/ad01-w0-dev-gr-00.json', 'world-0/top.txt']

2. RESTORE verifies:
     report["mismatches"] == []      (was ['artifact tar contents differ from manifest'])
     report["ok"] is True
     restored tree     : world-0/dev/ad01-w0-dev-gr-00.json, world-0/top.txt
```

Manifest and tar now name the same files with the same spelling. The restored
tree lands under the path the manifest gives it.

## Red, then green

New tests, each asserting a literal forward-slash path or a literal committed
digest, so each fails if the code returns the host-native form.

- `tests/test_posix_paths_representation_freeze.py` (7 tests, sites 1 and 2)
- `tests/test_posix_paths_checkpoint_restore.py` (5 tests, sites 3 and 4)

Red, before the fixes:

```
FAILED test_a_built_fixture_manifest_names_its_files_with_forward_slashes
FAILED test_a_built_fixture_manifest_is_byte_identical_to_the_committed_one
FAILED test_a_built_context_names_its_tasks_with_forward_slashes
FAILED test_a_built_context_digests_to_the_committed_bytes
FAILED test_the_checkpoint_manifest_names_its_artifacts_with_forward_slashes
FAILED test_a_recovery_set_restored_onto_another_host_verifies
6 failed, 6 passed
```

with the separator visible in the diff:

```
E  - controls/ctrl-gr-bipartite.json
E  + controls\ctrl-gr-bipartite.json
E  AssertionError: source_context.json drifted from its generator on this host
E  assert '3929da0e1d29...4e21e02209698' == 'ecdd706053ad...4f06f96db6672'
E  assert 'artifact tar contents differ from manifest' not in ['artifact tar contents differ from manifest']
```

Green, after:

```
12 passed in 0.88s
```

Red again with the four source files reverted and the tests kept, which is the
check that the tests observe the defect and not something else:

```
git stash push -- <the four sources>
6 failed, 6 passed
git stash pop
```

Both rebuilt contexts now digest to the committed blobs exactly:

```
source_context.json   5e94e611466a06b668400ce9f6949dcca9a6b0c390b3bee3af4c481c327a896a  MATCHES
transfer_context.json 6fd3e9c9a7bdf31a2e3be976f56f9436b5071162fa1c386a45c3301c0ccec1d9  MATCHES
```

## Counts, for the files I touched only

Two runs of the same eight-file set, at `ccd3df3` with the four fixes stashed,
and with them applied:

```
BASELINE   4 failed, 45 passed, 20 skipped in 69.44s
WITH FIXES 4 failed, 45 passed, 20 skipped in 65.39s
```

Identical. The four failures were already failing before my change, for a
reason my change does not reach:

- `tests/test_rpr04_freeze.py::test_freeze_verifies_clean`
- `tests/test_rpr04_freeze.py::test_both_freezes_verify_independently`
- `tests/test_rpr11_heldout.py::test_freeze_clean_and_rule_text`
- `tests/test_rpr03_acquire.py::test_contexts_deterministic`

All four reduce to `committed source_context.json drifted from its generator`,
all four are the CRLF checkout described above, and all four compare against
the working-tree file rather than the committed blob. Simulating that
comparison directly:

```
rebuilt vs on-disk(CRLF) : False
rebuilt vs on-disk(LF)   : True
```

So my fix closed the separator half of this and the line-ending half remains.
Before the fix the same rebuild produced `ecdd7060...`; after, `5e94e611...`,
which is the committed blob digest. The path is now correct; the checkout is
still CRLF.

I did not run a full suite. One orchestrator run was in flight and concurrent
runs had already starved this host.

## Unresolved

- The four pre-existing failures above. The fix is a `.gitattributes` entry for
  `experiments/representation/acquire/**`, outside my owned scope.
- The database half of the checkpoint and restore round trip, unproven on this
  host for lack of PostgreSQL. The artifact half is proven.
- Two other `files.sort(key=... "path")` sites that could order a manifest
  differently by host, listed above, neither confirmed against a committed
  freeze.
