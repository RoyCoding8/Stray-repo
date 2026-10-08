"""Launcher for the ``agent-run`` effect: one Codex CLI run over a staged workspace.

Codex is a component, not part of the kernel's trust base: it runs inside its
own OS sandbox (``workspace-write``) with a per-operation ``CODEX_HOME``, and
the kernel owns everything that decides budget and comparability: model,
provider, sandbox mode, approvals, context limits and which skills exist.

Isolation is checked, not assumed. Before anything is sent, ``codex debug
prompt-input`` renders the model-visible input without a model call, and the
launch is refused if any skill catalog from outside the workspace appears.

Send-once comes from a durable claim file written before the spawn: a claim
present means "may have been sent", absent with the run dir present proves
nothing was.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import child_limits
from .broker import BrokerOp, LaunchOutcome, ReceiptProposal
from .common import SettlementError, fsync_dir

_INFRA_MARKERS = ("503", "502", "504", "429", "service unavailable", "overloaded",
                  "rate limit", "connection refused", "error sending request",
                  "stream disconnected", "auth_unavailable")
_FEATURES_OFF = ("memories", "apps", "plugins", "remote_plugin", "image_generation",
                 "multi_agent", "goals")


@dataclass(frozen=True)
class Provider:
    base_url: str
    model: str
    api_key: str
    context_window: int = 1_000_000
    auto_compact_tokens: int = 200_000
    # Free routes return 503 bursts mid-run; Codex's defaults (4 / 5) give up early.
    request_retries: int = 10
    stream_retries: int = 10
    # Codex has no metadata for models outside its bundled catalog and falls
    # back to defaults. The launcher derives an entry for `model` from this
    # bundled template (gpt-5.4: plain tool mode, 1M max context).
    catalog_template: str = "gpt-5.4"


class CodexLauncher:
    launcher_id = "codex"
    profile = "codex"
    idempotent_resend = False

    def __init__(self, run_dir: str | Path, *, codex_cmd: list[str], provider: Provider,
                 allowed_overrides: frozenset[str]) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.codex_cmd = [str(a) for a in codex_cmd]
        self.provider = provider
        self.allowed_overrides = allowed_overrides
        self._live: set[str] = set()
        self._catalog: bytes | None = None

    def model_catalog(self) -> bytes:
        """A one-model catalog for the kernel's model, derived from Codex's bundled one."""
        if self._catalog is None:
            # A private, empty CODEX_HOME: the operator's ~/.codex may hold a
            # remotely refreshed catalog, which would make runs depend on it.
            home = self.run_dir / ".catalog-home"
            home.mkdir(exist_ok=True)
            env = {k: os.environ[k] for k in ("SYSTEMROOT", "PATH") if k in os.environ}
            proc = subprocess.run([*self.codex_cmd, "debug", "models"], capture_output=True,
                                  stdin=subprocess.DEVNULL, timeout=60,
                                  env=dict(env, CODEX_HOME=str(home)))
            try:
                models = json.loads(proc.stdout.decode("utf-8-sig"))["models"]
            except (ValueError, KeyError) as exc:
                raise SettlementError(f"codex debug models gave no catalog: {exc}") from exc
            p = self.provider
            template = next((m for m in models if m.get("slug") == p.catalog_template), None)
            if template is None:
                raise SettlementError(f"bundled catalog has no {p.catalog_template!r}")
            entry = dict(template, slug=p.model, display_name=p.model,
                         description="kernel route model", visibility="list",
                         context_window=int(p.context_window),
                         max_context_window=int(p.context_window),
                         include_skills_usage_instructions=False,
                         include_plugin_usage_instructions=False,
                         include_apps_usage_instructions=False,
                         upgrade=None, availability_nux=None, service_tiers=[],
                         additional_speed_tiers=[])
            self._catalog = json.dumps({"models": [entry]}).encode("utf-8")
        return self._catalog

    # -- paths ---------------------------------------------------------------
    def _dir(self, operation_id: str) -> Path:
        if not operation_id or any(c in operation_id for c in '/\\:*?"<>|') \
                or operation_id in (".", ".."):
            raise SettlementError(f"operation id {operation_id!r} is not a safe directory name")
        return self.run_dir / operation_id

    def exec_dirs(self, operation_id: str, execution_version: str = "") -> tuple[str, str]:
        d = self._dir(operation_id)
        return str(d / "workspace"), str(d)

    def stage_input(self, operation_id: str, execution_version: str,
                    relpath: str, data: bytes) -> Path:
        d = self._dir(operation_id)
        if (d / "claim").exists():
            raise SettlementError(f"{operation_id} already dispatched; its inputs are fixed")
        from .artifacts import _check_relpath, _contained
        _check_relpath(relpath)
        (d / "workspace").mkdir(parents=True, exist_ok=True)
        target = _contained(d / "workspace", relpath)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def staged_python(self) -> str:
        return sys.executable

    def read_output(self, operation_id: str, execution_version: str, relpath: str) -> bytes:
        from .artifacts import _contained
        return _contained(self._dir(operation_id), relpath).read_bytes()

    # -- send-once evidence ----------------------------------------------------
    def prior_send(self, operation_id: str) -> bool:
        return (self._dir(operation_id) / "claim").exists()

    def prove_never_sent(self, operation_id: str, dispatch_generation: int | None = None) -> bool:
        d = self._dir(operation_id)
        return d.is_dir() and not (d / "claim").exists()

    def read_result(self, operation_id: str) -> dict[str, Any] | None:
        path = self._dir(operation_id) / "result.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def live_ids(self) -> list[str]:
        return sorted(self._live)

    def is_live(self, operation_id: str) -> bool:
        return operation_id in self._live

    def stop(self, operation_id: str) -> bool:
        return operation_id not in self._live  # runs are bounded by timeout_ms

    # -- the run ---------------------------------------------------------------
    def config_toml(self, codex_home: Path) -> str:
        p = self.provider
        return "\n".join([
            f"model = {json.dumps(p.model)}",
            'model_provider = "kernel"',
            'approval_policy = "never"',
            'sandbox_mode = "workspace-write"',
            f"model_context_window = {int(p.context_window)}",
            f"model_auto_compact_token_limit = {int(p.auto_compact_tokens)}",
            f"sqlite_home = {json.dumps(codex_home.as_posix())}",
            f"model_catalog_json = {json.dumps((codex_home / 'catalog.json').as_posix())}",
            "",
            "[model_providers.kernel]",
            'name = "kernel route"',
            f"base_url = {json.dumps(p.base_url)}",
            'env_key = "KERNEL_MODEL_KEY"',
            'wire_api = "responses"',
            f"request_max_retries = {int(p.request_retries)}",
            f"stream_max_retries = {int(p.stream_retries)}",
            "",
            "[skills]",
            "include_instructions = false",
            "",
            "[shell_environment_policy]",
            'inherit = "core"',
            "ignore_default_excludes = false",
            "",
            "[windows]",
            'sandbox = "unelevated"',
            "",
        ])

    def _env(self, d: Path) -> dict[str, str]:
        env = {k: os.environ[k] for k in ("SYSTEMROOT", "PATH", "PATHEXT", "COMSPEC",
                                          "WINDIR", "NUMBER_OF_PROCESSORS")
               if k in os.environ}
        tmp = d / "tmp"
        tmp.mkdir(exist_ok=True)
        env.update(CODEX_HOME=str(d / "codex-home"), KERNEL_MODEL_KEY=self.provider.api_key,
                   TEMP=str(tmp), TMP=str(tmp), PYTHONDONTWRITEBYTECODE="1")
        return env

    def _argv(self, sub: list[str], config: dict[str, Any]) -> list[str]:
        argv = [*self.codex_cmd, *sub]
        for feature in _FEATURES_OFF:
            argv += ["--disable", feature]
        for key, value in sorted(config.items()):
            argv += ["-c", f"{key}={json.dumps(value)}"]
        return argv

    def isolation_problem(self, d: Path, config: dict[str, Any]) -> str | None:
        """Render the model-visible input (no model call) and look for leaks."""
        proc = subprocess.run(self._argv(["debug", "prompt-input"], config) + ["probe"],
                              cwd=d / "workspace", env=self._env(d), capture_output=True,
                              stdin=subprocess.DEVNULL, timeout=120)
        text = proc.stdout.decode("utf-8", "replace")
        if proc.returncode != 0:
            return f"prompt-input exited {proc.returncode}: {proc.stderr.decode('utf-8', 'replace')[-300:]}"
        if "Skill roots" in text or "Available skills" in text:
            return "a harness skill catalog reached the prompt"
        home = str(Path.home()).replace("\\", "\\\\")
        if home in text or str(Path.home()).replace("\\", "/") in text:
            return "the operator's home directory appears in the prompt"
        return None

    def dispatch(self, op: BrokerOp) -> LaunchOutcome:
        d = self._dir(op.operation_id)
        if (d / "result.json").exists() or (d / "claim").exists():
            return LaunchOutcome(sent=False, refused_reason="prior-send-recorded")
        p = op.payload
        config = dict(p.get("config") or {})
        extra = set(config) - self.allowed_overrides
        if extra:
            return LaunchOutcome(sent=False,
                                 refused_reason=f"config sets kernel-owned keys {sorted(extra)}")
        (d / "workspace").mkdir(parents=True, exist_ok=True)
        (d / "codex-home").mkdir(exist_ok=True)
        (d / "codex-home" / "config.toml").write_text(self.config_toml(d / "codex-home"),
                                                      encoding="utf-8")
        try:
            (d / "codex-home" / "catalog.json").write_bytes(self.model_catalog())
        except (OSError, subprocess.TimeoutExpired, SettlementError) as exc:
            return LaunchOutcome(sent=False, refused_reason=f"model catalog: {exc}")
        try:
            problem = self.isolation_problem(d, config)
        except (OSError, subprocess.TimeoutExpired) as exc:
            problem = f"isolation check failed to run: {exc}"
        if problem is not None:
            return LaunchOutcome(sent=False, refused_reason=f"isolation: {problem}")
        with open(d / "claim", "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"generation": op.dispatch_generation, "at": time.time()}))
            handle.flush()
            os.fsync(handle.fileno())
        fsync_dir(d)
        self._live.add(op.operation_id)
        try:
            result = self._run(d, p, config)
        finally:
            self._live.discard(op.operation_id)
        tmp = d / "result.json.tmp"
        tmp.write_text(json.dumps(result), encoding="utf-8")
        os.replace(tmp, d / "result.json")
        tokens = result["tokens"]
        total = None if tokens is None else tokens["input_tokens"] + tokens["output_tokens"]
        charge = total if total is not None and total <= int(p["token_ceiling"]) else None
        return LaunchOutcome(sent=True, receipt=ReceiptProposal(
            receipt_identity=f"codex:{op.operation_id}:g{op.dispatch_generation}",
            content=dict(result, operation_id=op.operation_id,
                         response_digest=result["trajectory_digest"]),
            outcome="success" if result["status"] == "completed" else "failure",
            provenance=self.launcher_id, actual_cost=charge))

    def _run(self, d: Path, p: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        argv = self._argv(["exec", "--json", "--skip-git-repo-check", "--ephemeral",
                           "-C", str(d / "workspace")], config) + [p["instruction"]]
        started = time.monotonic()
        timeout_s = int(p["timeout_ms"]) / 1000
        with open(d / "events.jsonl", "wb") as out, open(d / "stderr.txt", "wb") as err:
            if child_limits.current_execution_host().mechanism == "job-object":
                from . import winjob
                with winjob.Job() as job:
                    proc = job.spawn(argv, cwd=d / "workspace", env=self._env(d),
                                     stdin=subprocess.DEVNULL, stdout=out, stderr=err)
                    timed_out = job.wait(proc, timeout_s)
            else:
                proc = subprocess.Popen(argv, cwd=d / "workspace", env=self._env(d),
                                        stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                        start_new_session=True)
                try:
                    proc.wait(timeout=timeout_s)
                    timed_out = False
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, 9)
                    proc.wait()
                    timed_out = True
        raw = (d / "events.jsonl").read_bytes()
        summary = summarize_events(raw)
        status = summary["status"]
        if timed_out:
            status = "timeout"
        elif status == "completed" and summary["tokens"] is not None:
            total = summary["tokens"]["input_tokens"] + summary["tokens"]["output_tokens"]
            if total > int(p["token_ceiling"]):
                status = "over_budget"
        return {"status": status, "exit_code": proc.returncode,
                "seconds": round(time.monotonic() - started, 1),
                "tokens": summary["tokens"], "infra_reason": summary["infra_reason"],
                "commands": summary["commands"],
                "final_message": summary["final_message"],
                "trajectory_digest": hashlib.sha256(raw).hexdigest(),
                "trajectory_bytes": len(raw)}


def summarize_events(raw: bytes) -> dict[str, Any]:
    """Status, usage and infra classification from `codex exec --json` output."""
    status, tokens, infra, final, commands = "failed", None, "", "", 0
    errors: list[str] = []
    for line in raw.decode("utf-8", "replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get("type")
        item = event.get("item") or {}
        if kind == "turn.completed":
            status = "completed"
            usage = event.get("usage") or {}
            tokens = {k: int(usage.get(k) or 0) for k in
                      ("input_tokens", "cached_input_tokens", "output_tokens",
                       "reasoning_output_tokens")}
        elif kind == "turn.failed":
            status = "failed"
            errors.append(str((event.get("error") or {}).get("message", "")))
        elif kind == "error":
            errors.append(str(event.get("message", "")))
        elif kind == "item.completed" and item.get("type") == "agent_message":
            final = str(item.get("text", ""))
        elif kind == "item.completed" and item.get("type") == "command_execution":
            commands += 1
    if status != "completed" and errors:
        last = errors[-1].lower()
        if any(m in last for m in _INFRA_MARKERS):
            status, infra = "infra_failed", errors[-1][:500]
    return {"status": status, "tokens": tokens, "infra_reason": infra,
            "final_message": final[:4000], "commands": commands}
