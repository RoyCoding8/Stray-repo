#!/bin/sh
# Exercises the hook against a throwaway repo that clones this repo's
# core.hooksPath, so the run cannot disturb a real commit.
set -eu

root=$(git rev-parse --show-toplevel)
pass=0
fail=0

report() {
    if [ "$1" = ok ]; then
        pass=$((pass + 1))
        printf 'PASS %s\n' "$2"
    else
        fail=$((fail + 1))
        printf 'FAIL %s: %s\n' "$2" "$3"
    fi
}

# writes the new repo's path to $REPO, because a function's return value is its
# last command's stdout and set -e drops out of the function when that last
# command succeeds
fixture() {
    REPO=$(mktemp -d)
    t=$REPO
    git -C "$t" init -q
    git -C "$t" config user.email lane@example.invalid
    git -C "$t" config user.name lane
    printf 'one\n' >"$t/mine"
    printf 'one\n' >"$t/foreign"
    git -C "$t" add mine foreign
    git -C "$t" commit -q -m 'base'
    # armed only after the base commit: --no-verify does not skip
    # prepare-commit-msg, so the fixture cannot use it to stand up
    git -C "$t" config core.hooksPath "$root/githooks"
}

# same, plus a path holding a space and one holding a glob character, both
# created with -- so git never sees the shell split them. Its own base commit
# has to be armed-safe already, and it cannot name the spaced path, so it
# commits them under the escape hatch
fixture_odd() {
    REPO=$(mktemp -d)
    t=$REPO
    git -C "$t" init -q
    git -C "$t" config user.email lane@example.invalid
    git -C "$t" config user.name lane
    for f in 'a*b' 'my file.txt'; do
        printf 'one\n' >"$t/$f"
        git -C "$t" add -- "$f"
    done
    git -C "$t" commit -q -m 'base
Scope: ALL'
    git -C "$t" config core.hooksPath "$root/githooks"
}

# commit <repo> <message> ; echoes 0 or 1, plus the hook's stderr
commit() {
    d=$1
    m=$2
    if err=$(git -C "$d" commit -m "$m" 2>&1); then
        printf '0\n'
    else
        printf '1\n%s\n' "$err"
    fi
}

# 1. my file staged and a foreign file also staged, message names only mine:
#    this is the 97c7416 shape, and it must be refused
fixture
printf 'two\n' >"$t/mine"
printf 'two\n' >"$t/foreign"
git -C "$t" add mine foreign
out=$(commit "$t" 'lane X2: my work only
Scope: mine')
case "$out" in
0*) report no "refuses foreign-staged" "commit went through with foreign staged" ;;
*) report ok "refuses foreign-staged" ;;
esac
printf '%s\n' "$out" | tail -n +2 | sed 's/^/    | /'
rm -rf "$t"

# 2. the same commit with the foreign file unstaged, and the message naming
#    its own file, must be permitted
fixture
printf 'two\n' >"$t/mine"
git -C "$t" add mine
out=$(commit "$t" 'lane X2: my work only
Scope: mine')
case "$out" in
0*) report ok "permits intended" ;;
*) report no "permits intended" "$out" ;;
esac
rm -rf "$t"

# 3. a deliberate large commit states the whole scope
fixture
for f in a b c d e f g h i j k l m n o p q r s t; do
    printf 'one\n' >"$t/$f"
done
git -C "$t" add a b c d e f g h i j k l m n o p q r s t
out=$(commit "$t" 'mechanical: rename twenty helpers
Scope: ALL')
case "$out" in
0*) report ok "permits Scope: ALL" ;;
*) report no "permits Scope: ALL" "$out" ;;
esac
rm -rf "$t"

# 4. a message that names nothing must be refused
fixture
printf 'two\n' >"$t/mine"
git -C "$t" add mine
out=$(commit "$t" 'lane X2: my work only')
case "$out" in
0*) report no "refuses missing Scope" "committed with no Scope trailer" ;;
*) report ok "refuses missing Scope" ;;
esac
printf '%s\n' "$out" | tail -n +2 | sed 's/^/    | /'
rm -rf "$t"

# 5. a Scope naming a path that is not staged must be refused
fixture
printf 'two\n' >"$t/mine"
git -C "$t" add mine
out=$(commit "$t" 'lane X2: my work only
Scope: mine ghost')
case "$out" in
0*) report no "refuses unbacked Scope path" "committed naming a path that is not staged" ;;
*) report ok "refuses unbacked Scope path" ;;
esac
rm -rf "$t"

# 6. two paths named, two paths staged: the documented example, and the shape
#    every case above avoided
fixture
printf 'two\n' >"$t/mine"
printf 'two\n' >"$t/foreign"
git -C "$t" add mine foreign
out=$(commit "$t" 'lane Y3: both files
Scope: mine foreign')
case "$out" in
0*) report ok "permits two-path Scope" ;;
*) report no "permits two-path Scope" "$out" ;;
esac
rm -rf "$t"

# 7. two paths named, a third staged: the unnamed path must still be caught
fixture
printf 'two\n' >"$t/mine"
printf 'two\n' >"$t/foreign"
git -C "$t" add mine foreign
printf 'two\n' >"$t/smuggled"
git -C "$t" add smuggled
out=$(commit "$t" 'lane Y3: two of three
Scope: mine foreign')
case "$out" in
0*) report no "refuses unbacked path in two-path Scope" "smuggled.txt committed" ;;
*) report ok "refuses unbacked path in two-path Scope" ;;
esac
printf '%s\n' "$out" | tail -n +2 | sed 's/^/    | /'
rm -rf "$t"

# 8. two paths named, only one staged
fixture
printf 'two\n' >"$t/mine"
git -C "$t" add mine
out=$(commit "$t" 'lane Y3: named a second path
Scope: mine ghost')
case "$out" in
0*) report no "refuses unstaged path in two-path Scope" "committed naming an unstaged path" ;;
*) report ok "refuses unstaged path in two-path Scope" ;;
esac
rm -rf "$t"

# 9. a glob character in a staged path: the word must not expand, which it
#    would if any file in the working directory matched it
fixture_odd
printf 'two\n' >"$t/a*b"
git -C "$t" add -- 'a*b'
# created after staging, so it is in the working directory and not the index.
# Had the hook expanded the word, this is the file it would have found
: >"$t/aXb"
out=$(commit "$t" 'lane Y3: glob path
Scope: a*b')
case "$out" in
0*) report ok "permits glob char in path" ;;
*) report no "permits glob char in path" "$out" ;;
esac
rm -rf "$t"

# 10. a space in a path: the Scope grammar is space-separated, so such a path
#     is not nameable and the honest answer is Scope: ALL
fixture_odd
printf 'two\n' >"$t/my file.txt"
git -C "$t" add -- 'my file.txt'
out=$(commit "$t" 'lane Y3: spaced path, split
Scope: my file.txt')
case "$out" in
0*) report no "refuses a Scope naming a spaced path whole" "the split words were read as two paths" ;;
*) report ok "refuses a Scope naming a spaced path whole" ;;
esac
out=$(commit "$t" 'lane Y3: spaced path, escape hatch
Scope: ALL')
case "$out" in
0*) report ok "permits ALL over a spaced path" ;;
*) report no "permits ALL over a spaced path" "$out" ;;
esac
rm -rf "$t"

printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
