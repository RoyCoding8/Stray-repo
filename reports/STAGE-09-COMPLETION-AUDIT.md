# Stage 9 completion audit

Read-only adversarial pass over the three handover documents at `d8436f0`. No file
was edited. Every number below was recomputed; the command is given so a reader can
re-run it.

`ISSUES`

## 1. Stale or false claims, worst first

**1.1 The completion matrix says E4 never ran. It ran, and the artifact is committed.**
`reports/STAGE-09-COMPLETION-MATRIX.md:36` claims `inv_r1_e4/` holds "**two files, no
other artifact**". `reports/STAGE-09-COMPLETION-MATRIX.md:166` claims "E4: the live
campaign | **not run**". Both are false. The directory holds 5 files plus `run/`
(13 files). `result.json` (24403 B) was committed at `111ec3a` on 2026-09-28 01:44,
**before** the matrix's own last commit `46cedf8` at 03:09 — the matrix was written
after the artifact existed and still denies it.
```
ls -la reports/evidence/inv_r1_e4/ reports/evidence/inv_r1_e4/run/
git log -1 --format='%h %ci' -- reports/evidence/inv_r1_e4/result.json
```
`result.json` is a real result: `verdicts.acquisition = "no-eligible-revision-acquired"`,
`live_claim.dispatches = 6`, six per-dispatch records each refused as
`delegates-to-unchanged-reducer`. A receiving agent reading line 166 will decline a
completed experiment as not started.

**1.2 `TASKS.md` row A8 is OPEN, but its own commit closed it only partially.**
`0f4f8c7` says "A8, partially closed, and the remainder is not mine to close." A7 is
genuinely closed (both ceiling loops, `store.py:1297`). A8 is not, and `TASKS.md:21`
does not say so. Stale as written; wrong in the other direction from the coordinator's
two examples.

**1.3 `TASKS.md` rows C1 and C4 are OPEN; the commits closed them.**
`C1` (N-410, the 5 MB matrix) is closed by `5e368eb` ("90.6% smaller, 10.6x",
5,163,201 B → 487,348 B). `C2` (N-413) is closed by `4df45b2`. `TASKS.md:41` still
lists N-413 as live. `TASKS.md:40` still lists N-410 as live.

**1.4 `TASKS.md` B6 is OPEN and the file it asks for is absent.**
`TASKS.md:32` wants `RETRACTED.md` in the E3 ladder directory.
```
find reports/evidence -name 'RETRACTED.md'
```
Four exist: `inv_r1_e2_noexp`, `inv_r1_e2_relevance`, `inv_r1_e2_transfer`,
`inv_r1_e3_selection`. `inv_r1_e3_ladder/` has none. Still genuinely open — but the
B5 row is DISPATCHED and the B6 row does not point at the sibling that did land.

**1.5 The coordinator report's stash description is wrong on both file and date.**
`reports/STAGE-09-COORDINATOR-REPORT.md:183` says `stash@{0}` is
`experiments/ad01/offline_recompute.py`, dated 2026-09-26.
```
git stash show --name-only 'stash@{0}'   # -> src/settlement/store.py
git log -1 --format='%ci' 'stash@{0}'    # -> 2026-09-28 04:39:34 +0000
```
`stash@{0}` is a `src/settlement/store.py` diff dated 2026-09-28, on `src/`. A later
cleanup told to leave this alone would leave the wrong thing, and the real
`experiments/ad01/offline_recompute.py` (2026-09-26) is described by a line that does
not describe it. There is also a second stash, `stash@{1}: selfdigest`, never mentioned.
The stash does still exist.

**1.6 `reports/evidence/` holds 46 directories, not 44.**
`reports/STAGE-09-COORDINATOR-REPORT.md:209`. `ls -1 reports/evidence | wc -l` → `46`.

**1.7 The handoff fetch is marked done against a ref that does not exist locally.**
`reports/STAGE-09-COORDINATOR-REPORT.md:196` cites
`refs/heads/codex/stage09-expanded-study-handoff = 7ebbb22`. That is false: there is no
such local branch. `git show-ref | grep handoff` finds only
`refs/remotes/origin/codex/stage09-expanded-study-handoff` = `7ebbb22`. The tree
equality at `:197` does reproduce — `git rev-parse '7ebbb22^{tree}' 'dd504e1^{tree}'`
both give `2492b7f4a0247201b9cb3efb9b46498c7641b35c` — so the substance holds and only
the ref name is wrong.

**1.8 The findings ledger's own row count does not close, in three directions.**
`reviews/STAGE-09-FINDINGS.md:8` claims "**91 rows in this file, in two tables.** The
main ledger holds 90". `:26` claims "**main table total 67**", `:30` claims "**file
total 68**". Measured by parsing the `## The ledger` section (lines 90-177) for
`^\|\s*\*{0,2}(N|CS)-\d+`:

| claim | line | measured |
|---|---|---|
| main ledger holds 90 | `:9` | **68** |
| main table total 67 | `:26` | **68** |
| file total 68 | `:30` | **113 id-rows** (68 main + N-65 + 44 post-ledger rows) |
| 91 rows in this file | `:8` | **113** |

The status rows also do not sum to 67: REPAIRED 34 + OPEN 14 + PARTIAL 5 + CONFIRMED 4
+ RESOLVED 4 + UNRESOLVED 2 + SUPERSEDED 2 + CLOSED 1 + RETRACTED 1 = **67**, which
happens to close — but that 67 is stated at `:26` as the *main* table total while the
main table holds 68. Reproduce:
```
python3 -c "
import re
L=open('reviews/STAGE-09-FINDINGS.md').read().split('\n')
s=[i for i,l in enumerate(L) if l.startswith('## The ledger')][0]
e=[i for i,l in enumerate(L) if i>s and l.startswith('## ')][0]
print(sum(1 for l in L[s:e] if re.match(r'^\|\s*\*{0,2}(N|CS)-\d+',l)))"
```

**1.9 N-415 says 101 test files use `migrated_db`; 102 do.**
`reviews/STAGE-09-FINDINGS.md:369`. `grep -rl 'migrated_db' tests/test_*.py | wc -l`
→ `102`. Minor, but it is a count a receiving agent may re-derive and find wrong.

**1.10 `TASKS.md` E3 cites a `.git` size that no longer holds.**
`TASKS.md:60` says `git gc --aggressive` took `.git` 28.1 MB → 7.9 MB. Measured now:
`du -sb .git` = 9,062,565 B (8.6 MiB / 9.1 MB), pack 6,918,377 B. Later commits grew
it. The decision ("leave the evidence alone") is unaffected; the number is stale.

**1.11 `TASKS.md` section D header contradicts the milestone table it points at.**
`TASKS.md:50` says "0 BLOCKED". The matrix records E3's post-fix ladder and E4's live
campaign as "**not run**" (`STAGE-09-COMPLETION-MATRIX.md:165`, `:166`) — the same
category the D header counts as zero. Only E4's entry is actually false (1.1); E3's
matches the artifact. The header is at best unmeasured, and it is stated with the same
confidence as the 2/7/0 figures that do reproduce.

## 2. Internal contradictions

**2.1 The ledger contradicts itself on how many rows it has, in adjacent lines.**
`reviews/STAGE-09-FINDINGS.md:8` "91 rows in this file" vs `:30` "file total 68". These
are 23 rows apart and both are presented as the same parse. Measured 113.

**2.2 The coordinator report contradicts the completion matrix on E4.**
`reports/STAGE-09-COORDINATOR-REPORT.md:211-212` "E4 has none — a generator with no
output" vs `reports/STAGE-09-COMPLETION-MATRIX.md:36` "two files, no other artifact" vs
the on-disk 5 files plus `run/`. All three are wrong in the same direction; the
coordinator report at least has a SCOPE CORRECTION dating the error, the matrix does not.

**2.3 The ledger's N-65 row says 18688 is in "three markdown files"; the same file's
section 513 says four, and the measurement gives nine.**
`reviews/STAGE-09-FINDINGS.md:525` "three markdown files" vs `:529` "it appears in four
documents rather than three". `TASKS.md:67` and the coordinator report `:127` both
repeat "three".
```
grep -rln '18688' --include='*.md' --include='*.json' . | wc -l   # -> 9
```
Nine files: `TASKS.md`, `reviews/STAGE-09-FINDINGS.md`, `reviews/STAGE-09-OPEN-DECISIONS.md`,
`reports/PROJECT-LEDGER.md`, `reports/STAGE-09-COMPLETION-MATRIX.md`,
`reports/STAGE-09-CONNECTED-STATUS.md`, `reports/STAGE-09-COORDINATOR-REPORT.md`,
`reports/STAGE-09-DECISION-TABLE.md`, `reports/STAGE-09-ROADMAP.md`. Five of the nine
are documents about the *finding* rather than statements of the figure, so the honest
count of documents asserting 18688 as settled is smaller than 9 — but "three" and
"four" are both wrong, and the correction the ledger itself made was itself wrong.
Zero artifacts is confirmed.

**RESOLVED 2026-09-29 at `94443a7`.** "Zero artifacts is confirmed" is where this
audit's own method went wrong, and the correction is worth recording next to it: the
artifact was sought as a JSON file and is a **test**. `f3af21a` introduced 18688 in
assertions that carry the per-prompt character counts and the per-request prices, and
`broker.exposure_schedule` recomputes the total from them. **18688 = 4 × 2294 + 4 × 2378.**
The "three versus four versus nine" count above is now moot for a different reason: the
figure is a pre-flight campaign sizing, not a liability, and every document restating it
as held exposure has been corrected to say so. `reviews/STAGE-09-N36-N65.md` has the
derivation and the list.

**2.4 N-415's status conflicts with the ledger's own REPAIRED bucket.**
`reviews/STAGE-09-FINDINGS.md:369` marks N-415 "(unrechecked — recorded, not repaired)"
and the recheck is absent, yet `tests/conftest.py:17-21` still calls `pytest.skip` when
`SETTLEMENT_TEST_DSN` is unset. The row is honest about itself. The conflict is with
`TASKS.md`, which has no row for N-415 at all — the single highest-severity open
finding in the ledger has no task. Same for N-200/N-201/N-202, which do appear (A1-A3),
so this is an omission, not a policy.

## 3. Claims of verification with no evidence behind them

**3.1 The headline test tally has no artifact.** `reports/STAGE-09-COORDINATOR-REPORT.md:31-32`
— "135 failed, 3701 passed, 14 skipped, 57 deselected, 2 xfailed, 5 errors / 3857 tests ·
3:06:28". No run log is on disk; `find . -name '*.log' -size +10k -newermt 2026-09-20`
returns nothing. The same string is repeated at
`reports/STAGE-09-COMPLETION-MATRIX.md:229-230` and in
`reviews/STAGE-09-OPEN-DECISIONS.md:110`, so three documents cite each other rather
than a run. The report does attach three honest conditions, and they are the right
ones — but a receiving agent cannot re-derive or falsify the number. It also predates
six later commits, including the two that closed A7/A8 and N-410.

**3.2 "536 of 537 results (99.8%)" has no artifact either.** `:53`. Same absence.

**3.3 "49 of 54 failing files were reached by the redirect hook and 5 were pinned"**
(`:44`) has no command or file behind it. The seam tally at `:64-65` *does* reproduce
exactly:
```
python3 -c "
import sys,pathlib;sys.path.insert(0,'tests');import conftest_isolation as c
s=c.scan(pathlib.Path('tests'))
print(len(s), sum(1 for x in s if x.redirectable), sum(1 for x in s if x.mode==c.PINNED))"
# -> 22 20 2
```
Blocked seams are `EC02_ADTR_DSN`/`ec02test_adtr` and `P3E_DSN`/`ec02test_p3e_entry`,
matching `:68`. That claim is clean. The 49/54 split above it is not.

**3.4 `TASKS.md` E1 "DONE" is the one DONE row with a measurement, and it does not
reproduce as stated.** `:58` claims "12,507 dirs older than today cleared; 58 MB
reclaimed... Corrected figure: 60.9 MB, not 641 MB" and "7 of today's preserved".
Measured: `.ad01-runs` now holds **17** entries totalling **1.9 MB**
(`du -sh .ad01-runs; ls -1 .ad01-runs | wc -l`). 17 is not 7. The reclaim figure is not
independently checkable now that the directories are gone, but the surviving count
contradicts the "7 of today's preserved" claim as written.

## 4. Verdict

**Not safe to hand over as-is.** Six claims are outright false (E4's result, the stash
description, the local ref, the evidence directory count, two TASKS rows already
closed, the `.git` size), the findings ledger's own row count is wrong by 22 in one
place and 45 in another, and the headline test number has no artifact anywhere. The
SCOPE CORRECTION block at `reports/STAGE-09-COORDINATOR-REPORT.md:5-20` is accurate and
visible, and still the strongest thing in the three documents; it does not cover the
E4 error, which post-dates it. Safe with items 1.1-1.8 and 2.1-2.3 corrected; the
headline tally (3.1) needs either a run log committed or an explicit "unverifiable"
label before handover.

## Appendix — commands, all re-runnable

```
ls -la reports/evidence/inv_r1_e4/ reports/evidence/inv_r1_e4/run/
git log -1 --format='%h %ci %s' -- reports/evidence/inv_r1_e4/result.json
git log -1 --format='%h %ci %s' -- reports/STAGE-09-COMPLETION-MATRIX.md
git show --stat 0f4f8c7 ; git show --stat 5e368eb ; git show --stat 4df45b2
git stash show --name-only 'stash@{0}' ; git stash list
git log -1 --format='%ci' 'stash@{0}' ; ls -la experiments/ad01/offline_recompute.py
ls -1 reports/evidence | wc -l
git show-ref | grep -i handoff
git rev-parse '7ebbb22^{tree}' 'dd504e1^{tree}'
grep -rl 'migrated_db' tests/test_*.py | wc -l
find reports/evidence -name 'RETRACTED.md'
grep -rln '18688' --include='*.md' --include='*.json' . | sort
du -sb .git ; du -sh .ad01-runs ; ls -1 .ad01-runs | wc -l
find . -name '*.log' -not -path './.git/*' -size +10k -newermt 2026-09-20
```
