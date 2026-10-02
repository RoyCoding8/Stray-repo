# Commit scope

Every commit here ends with a `Scope:` trailer naming each path it touches.

```
lane X2: refuse a commit carrying foreign work

Scope: githooks/prepare-commit-msg githooks/install docs/COMMIT-SCOPE.md
```

## Why

Three commits captured another lane's uncommitted files. The content was right
and only the message was wrong, but the message is what a reviewer reads. A
`git add -a`, or a `git commit -- <paths>` that left the index dirty, put three
lanes under one line of history.

Lane briefs already say "git add only your own files". That is advice. This is
a hook.

## Install

```
sh githooks/install
```

It sets `core.hooksPath=githooks` in the repo's own config and then reads the
value back, exiting 1 if it did not take. The hook itself is committed, so a
fresh clone needs only that one command.

## Use

- `Scope: a.py b.py` names exactly what you staged. Every staged path must be
  named and every named path must be staged, or the commit is refused.
- `Scope: ALL` is the deliberate escape hatch. Use it for a mechanical
  refactor, a rename sweep, or any commit where listing twenty paths in the
  message is noise. It is one word that says "yes, this is many files, and I
  mean it".

Paths are separated by spaces, so a path containing a space cannot be named.
There are none in this repo, and `git diff --name-only` would quote one anyway.
If you ever add one, its commit takes `Scope: ALL`. A glob character in a
path is fine and is matched literally.

## Limits

Git records no identity for a staged path, so the hook cannot tell who staged
what. It can only force the committer to state their intent and check that
statement against the index, which is why the message carries the intent
rather than a file list passed on the command line.

`--no-verify` does not skip this hook. It skips `pre-commit` and `commit-msg`
only. A committer who wants to lie instead of guessing can pass `--no-verify` to
neither, and can edit `.git/config`; nothing in the working tree can stop that.
What this removes is the accident, which is what happened three times.

## Test

```
sh tools/test_pre_commit_scope.sh
```

Eleven cases against throwaway repos that share this repo's hook path. The
runner's own commits are not under test.
