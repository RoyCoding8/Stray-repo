import worktree_checkouts


def test_native_registry_paths_include_only_this_repositories_siblings(tmp_path, monkeypatch):
    canonical = tmp_path / "repository"
    admin = canonical / ".git" / "worktrees"
    admin.mkdir(parents=True)
    own, sibling, foreign = (tmp_path / name for name in ("own", "sibling", "foreign"))
    for lane in (own, sibling, foreign):
        lane.mkdir()
    for lane in (own, sibling):
        (lane / ".git").write_text("gitdir: " + (admin / lane.name).as_posix())
    (foreign / ".git").write_text("gitdir: " + (tmp_path / "other" / ".git" / "worktrees" / "foreign").as_posix())
    output = "\n".join("worktree " + lane.as_posix() for lane in (canonical, own, sibling, foreign))
    monkeypatch.setattr(worktree_checkouts, "_run", lambda args, cwd: output)
    assert worktree_checkouts.sibling_checkouts(canonical, own) == [sibling]
