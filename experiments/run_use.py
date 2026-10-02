"""Subsequent-use assignment (D02-004/CTX-08): run AFTER disposition.

A fresh process obtains the released-or-incumbent behavior through ordinary
selection, invokes it on one unseen task, grades the new task and records
outcome/cost. The caller (experiments/run_dev_episode.py) spawns this file
in a separate process; phase completion derives from the receipts recorded
here, never from routing/pinning metadata.

Deterministic default uses the composite fixture adapter (labeled
simulated). Live mode reuses the episode's gateway/launcher selection and
refuses without supplied access, allocation and profile.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
EXPERIMENTS = HERE.parent
WORKTREE = EXPERIMENTS.parent
for _anchor in (str(EXPERIMENTS), str(WORKTREE / "src")):
    if _anchor not in sys.path:
        sys.path.insert(0, _anchor)

from settlement import development, experiment  # noqa: E402


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--artifacts-root", required=True)
    parser.add_argument("--allocation", required=True)
    parser.add_argument("--investigation", required=True)
    parser.add_argument("--episode", required=True)
    parser.add_argument("--use-task", required=True)
    parser.add_argument("--prior-exposure", default="")
    parser.add_argument("--protocol-prefix", default="dev02use")
    parser.add_argument("--disposition-json", default="",
                        help="post-comparison disposition document:"
                        " {released: {family: version_id},"
                        " router_policies: {family: policy}, trial: bool}")
    parser.add_argument("--model", default=os.environ.get("SETTLEMENT_MODEL", ""))
    parser.add_argument("--gateway", default="fixture",
                        choices=("fixture", "live"))
    parser.add_argument("--launcher", default="local",
                        choices=("runsc", "local"))
    parser.add_argument("--allow-uncontained", action="store_true")
    parser.add_argument("--runsc-image",
                        default=os.environ.get("SETTLEMENT_RUNSC_IMAGE", ""))
    parser.add_argument("--runsc-python",
                        default=os.environ.get("SETTLEMENT_RUNSC_PYTHON", ""))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    from run_dev_episode import _fixture_double, _live_adapter
    from run_live_abc import _effective_config, _source_fingerprint

    args = _parse(argv)
    from fault_tasks import BY_ID

    if args.use_task not in BY_ID:
        print(f"subsequent use refused: unknown task {args.use_task}")
        return 2
    if args.disposition_json:
        try:
            disposition = json.loads(args.disposition_json)
        except ValueError:
            print("subsequent use refused: --disposition-json is not JSON")
            return 2
        if not isinstance(disposition, dict):
            print("subsequent use refused: --disposition-json needs an object")
            return 2
    else:
        disposition = None
    if args.gateway == "fixture":
        adapter, _, _, _ = _fixture_double()
        from settlement.launcher_local import LocalLauncher

        launcher = LocalLauncher(tempfile.mkdtemp(prefix="devuse-runs-"))
        model = "scripted"
    else:
        live, blocker, code = _live_adapter(args)
        if live is None:
            print(blocker)
            return code
        adapter, launcher, model = (live["adapter"], live["launcher"],
                                    args.model)
    try:
        episode = development.get_episode(args.dsn, args.episode)
    except Exception as exc:
        print(f"subsequent use refused: {exc}")
        return 3
    if episode is None:
        print(f"subsequent use refused: unknown episode {args.episode}")
        return 2
    task = BY_ID[args.use_task]
    try:
        use = experiment.run_subsequent_use(
            args.dsn, artifacts_root=args.artifacts_root, launcher=launcher,
            adapter=adapter, model=model, allocation_id=args.allocation,
            investigation_id=args.investigation, episode_id=args.episode,
            bindings=episode.get("bindings") or {},
            use_task={"id": task["id"], "family": task["family"],
                      "broken": task["broken"], "cases": task["cases"]},
            grader_path=str(EXPERIMENTS / "run_tests.py"),
            protocol_prefix=args.protocol_prefix,
            prior_exposure=args.prior_exposure, disposition=disposition)
    except Exception as exc:
        print(f"subsequent use refused: {exc}")
        return 3
    use["launcher"] = launcher.profile
    use["model"] = model
    use["source"] = _source_fingerprint()
    use["effective_config"] = _effective_config(
        adapter=adapter, launcher=launcher, model=model, grant_units=None,
        run_allocation=args.allocation, args=args)
    print(json.dumps(use, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
