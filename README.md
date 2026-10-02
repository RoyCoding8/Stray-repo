# Recoverable history archive

Extract `complete-pre-consolidation-99e23b3.bundle` from this branch; then run:

```sh
git bundle verify complete-pre-consolidation-99e23b3.bundle
git clone --bare complete-pre-consolidation-99e23b3.bundle recovered.git
git --git-dir=recovered.git fsck --full
```

Do not merge this archive into the source branch. Its manifest preserves all old refs.
Historical evidence and commits remain available in the recovered repository.

The supplemental stash bundle preserves all saved stash entries, including reflog-only entries. After cloning the main bundle, run:

```sh
git --git-dir=recovered.git bundle unbundle stash-history.bundle
git --git-dir=recovered.git fsck --full
```

`stash_oids` in manifest.json lists the original stash order.
