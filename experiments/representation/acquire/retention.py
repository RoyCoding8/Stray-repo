"""Frozen campaign retention and executable constructor contracts.

Retention (``rpr-retention/1``) freezes the A/B/C artifacts selected by
``campaign.run_campaign`` with identities, lineage, applicability,
dependencies, budget and explicit reasons, so evaluation consumes exactly
the acquired bytes or fails loudly. Constructor contracts make each arm
usable: ``rpr-procedure/1`` validates and boundedly executes an acquired
``procedure.py``; lessons text parses to a per-family method directive
against the closed reducer vocabulary with a frozen-selector fallback;
``rpr-core-interface/1`` plus the frozen core bytes teach transfer
constructors the immutable core contract.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from settlement import artifacts
from settlement import representation as R
from settlement.common import SettlementError

RETENTION_FORMAT = "rpr-retention/1"
PROCEDURE_FORMAT = "rpr-procedure/1"
CORE_INTERFACE_VERSION = "rpr-core-interface/1"

METHODS = ("ddmin", "greedy")
FAMILIES = ("software", "graph")
TEXT_ENTRY = {"lessons": "lessons.md", "procedure": "procedure.py"}
STAGE_FAMILIES = {"source": ["software"], "transfer": ["graph"]}
ENTRY_KEYS = ("A-source", "A-transfer", "B-source", "B-transfer", "C-source",
              "C-transfer")

CORE_SOURCE_CAP_CHARS = 16384
PROCEDURE_TIMEOUT_MS = 2000

_FORBIDDEN_CALLS = frozenset([
    "open", "exec", "eval", "compile", "__import__", "input", "breakpoint",
    "exit", "quit", "getattr", "setattr", "delattr", "globals", "locals",
    "vars", "dir", "help", "type", "memoryview"])

CORE_INTERFACE = """rpr-core-interface/1: frozen source core operational contract.

The composition runs profile representation-01/1 as
`python <entry> <request.json> <response.json>`. Action owners: encode
(adapter), start (core), advance (core), decode (adapter).
Adapter encode maps one task to {"encoded_object": {"atoms": [int, ...],
"tunables": {"chunk_frac": int >= 1, "max_proposals": 1..16,
"order": "head" | "tail"}}, "aux": {...},
"applicability": {"supported": bool, "reason": str}}.
Core start reads the encoded atoms and tunables and proposes {"kept": [...]}
index subsets; core advance refines from feedback with halving chunks; both
finish with {"final_object": {"kept": [...]}}. Kept entries are ordered int
indices within the atom range. Adapter decode maps kept indices back to a
candidate written in the task's own vocabulary. Every response echoes
task_id, composition_id, core_digest and adapter_digest, or refuses with a
bounded reason. Unsupported families, over-cap inputs and malformed tasks
are refused, never searched. Preservation is decided by the independent
oracle, never by the core or adapter. The frozen core below is immutable:
never return core.py, it is refused."""


class RetentionError(SettlementError):
    pass


def estimate_input_tokens(text: str) -> int:
    return len(text) // 4 + 1


def transfer_enrichment(core_text: str) -> str:
    return "\n\n".join([
        "Frozen source core (%s), immutable:" % CORE_INTERFACE_VERSION,
        CORE_INTERFACE,
        core_text,
    ])


def enrichment_reserve(num_calls: int) -> int:
    return int(num_calls) * estimate_input_tokens(
        transfer_enrichment("x" * CORE_SOURCE_CAP_CHARS))


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _word_hits(line: str, words: tuple) -> list:
    return [word for word in words
            if re.search(r"\b%s\b" % re.escape(word), line)]


def parse_lessons_directive(body, frozen_selectors: dict) -> tuple:
    text = body if isinstance(body, str) else ""
    directive: dict = {}
    for line in text.lower().splitlines():
        methods = _word_hits(line, METHODS)
        if len(methods) != 1:
            continue
        for family in _word_hits(line, FAMILIES):
            if family not in directive:
                directive[family] = methods[0]
    missing = [family for family in FAMILIES if family not in directive]
    arm_a = (frozen_selectors or {}).get("arm-A", {})
    for family in missing:
        directive[family] = ((arm_a.get(family) or {}).get("method"))
    if not missing:
        return directive, {"source": "acquired",
                           "reason": "per-family method lines present"}
    return directive, {
        "source": "fallback-frozen-selector",
        "reason": "no valid %s method lines; froze arm-A selectors"
                  % ",".join(missing)}


def validate_procedure(body) -> dict:
    if not isinstance(body, str) or not body.strip():
        return {"status": "refused", "reason": "empty-procedure"}
    try:
        tree = ast.parse(body)
    except (SyntaxError, ValueError, RecursionError):
        return {"status": "refused", "reason": "unparseable-python"}
    selects = [node for node in tree.body
               if isinstance(node, ast.FunctionDef) and node.name == "select"]
    if len(selects) != 1:
        return {"status": "refused", "reason": "missing-select-entry"}
    args = selects[0].args
    params = list(args.posonlyargs) + list(args.args)
    if len(params) != 1 or args.vararg is not None \
            or args.kwarg is not None or args.kwonlyargs:
        return {"status": "refused", "reason": "select-arity"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return {"status": "refused", "reason": "imports-forbidden"}
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            return {"status": "refused", "reason": "dunder-access-forbidden"}
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            return {"status": "refused", "reason": "dunder-access-forbidden"}
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in _FORBIDDEN_CALLS:
            return {"status": "refused",
                    "reason": "io-or-reflection-forbidden"}
    return {"status": "valid", "format": PROCEDURE_FORMAT, "entry": "select"}


_DRIVER = ("import importlib.util, sys\n"
           "spec = importlib.util.spec_from_file_location("
           "\"acquired_procedure\", sys.argv[1])\n"
           "module = importlib.util.module_from_spec(spec)\n"
           "spec.loader.exec_module(module)\n"
           "print(module.select(float(sys.argv[2])))\n")


def _probe(body: str, measure: float, timeout_ms: int, workdir: str) -> tuple:
    module_path = str(Path(workdir) / "procedure.py")
    driver_path = str(Path(workdir) / "driver.py")
    Path(module_path).write_text(body, encoding="utf-8")
    Path(driver_path).write_text(_DRIVER, encoding="utf-8")
    wall = time.monotonic()
    try:
        completed = subprocess.run(
            [sys.executable, "-I", driver_path, module_path, repr(measure)],
            capture_output=True, text=True, cwd=workdir,
            timeout=max(1, timeout_ms) / 1000)
    except subprocess.TimeoutExpired:
        return None, time.monotonic() - wall, "timeout"
    elapsed = time.monotonic() - wall
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip().splitlines()
        return None, elapsed, "exit-%d%s" % (
            completed.returncode,
            (": " + detail[-1][:120]) if detail else "")
    return completed.stdout.strip(), elapsed, ""


def execute_procedure(body, measure: float,
                      timeout_ms: int = PROCEDURE_TIMEOUT_MS) -> dict:
    checked = validate_procedure(body)
    if checked["status"] != "valid":
        return {"status": "refused", "reason": checked["reason"],
                "elapsed_ms": 0, "calls": 0}
    if isinstance(measure, bool) or not isinstance(measure, (int, float)):
        return {"status": "error", "reason": "measure-not-numeric",
                "elapsed_ms": 0, "calls": 0}
    with tempfile.TemporaryDirectory(prefix="rpr-proc-") as workdir:
        first, spent, problem = _probe(body, measure, timeout_ms, workdir)
        if problem == "timeout":
            return {"status": "timeout",
                    "reason": "wall-clock-bound-exceeded",
                    "elapsed_ms": int(spent * 1000), "calls": 1}
        if problem:
            return {"status": "error", "reason": problem,
                    "elapsed_ms": int(spent * 1000), "calls": 1}
        second, more, problem = _probe(body, measure, timeout_ms, workdir)
        spent += more
        if problem == "timeout":
            return {"status": "timeout",
                    "reason": "wall-clock-bound-exceeded",
                    "elapsed_ms": int(spent * 1000), "calls": 2}
        if problem:
            return {"status": "error", "reason": problem,
                    "elapsed_ms": int(spent * 1000), "calls": 2}
        if first != second:
            return {"status": "error", "reason": "nondeterministic-select",
                    "elapsed_ms": int(spent * 1000), "calls": 2}
        if first not in METHODS:
            return {"status": "refused",
                    "reason": "method-outside-vocabulary",
                    "elapsed_ms": int(spent * 1000), "calls": 2}
        return {"status": "ok", "method": first,
                "elapsed_ms": int(spent * 1000), "calls": 2}


def _null_identities(kind: str) -> dict:
    if kind in TEXT_ENTRY:
        return {"artifact_digest": None, "file_digest": None}
    return {"composition_id": None, "package_digest": None,
            "core_digest": None, "adapter_digest": None}


def _identities(kind: str, winner: dict | None) -> dict:
    if winner is None:
        return _null_identities(kind)
    if kind in TEXT_ENTRY:
        return {"artifact_digest": winner.get("artifact_digest"),
                "file_digest": winner.get("file_digest")}
    return {"composition_id": winner.get("composition_id"),
            "package_digest": winner.get("package_digest"),
            "core_digest": winner.get("core_digest"),
            "adapter_digest": winner.get("adapter_digest")}


def _lineage(stage: str, kind: str, winner: dict | None, sel: dict,
             selection_tasks: dict) -> dict:
    base = {"selection_task": selection_tasks[stage], "prompt_digest": None,
            "response_digest": None, "verdict": "no-candidate",
            "improvement_u": None, "verified": False}
    if winner is None:
        return base
    base["prompt_digest"] = winner.get("prompt_digest")
    base["response_digest"] = winner.get("response_digest")
    if kind in TEXT_ENTRY:
        base["verdict"] = "stored-unexecuted"
        return base
    execution = winner.get("execution") or {}
    if not execution.get("executed"):
        base["verdict"] = "not-executed: %s" % execution.get(
            "reason", "missing")
        return base
    base["verdict"] = execution.get("disposition", "unknown")
    base["improvement_u"] = execution.get("improvement_u")
    base["verified"] = bool(execution.get("verified"))
    return base


def _contract(kind: str, winner: dict | None, sel: dict,
              selectors: dict) -> tuple:
    if kind == "lessons":
        body = (winner.get("files") or {}).get("lessons.md", "") \
            if winner else ""
        directive, info = parse_lessons_directive(body, selectors)
        return "directive", {"directive": directive,
                             "source": info["source"],
                             "reason": info["reason"]}
    if kind == "procedure":
        if winner is None:
            return "procedure", {"status": "absent",
                                 "format": PROCEDURE_FORMAT,
                                 "reason": sel.get("reason", "")}
        checked = validate_procedure(
            (winner.get("files") or {}).get("procedure.py", ""))
        record = {"status": checked["status"], "format": PROCEDURE_FORMAT}
        if checked["status"] == "valid":
            record["entry"] = checked["entry"]
        else:
            record["reason"] = checked["reason"]
        return "procedure", record
    adapted = bool((winner or {}).get("core_adapted", False))
    return "core", {"core_adapted": adapted,
                    "adaptation": (winner or {}).get("adaptation")}


def _budget(slots: list) -> dict:
    spent = {"model_calls": 0, "input_tokens": 0, "output_tokens": 0,
             "grant_units": 0}
    exposure = 0
    for slot in slots:
        exposure += int(slot.get("exposure", 0) or 0)
        if "dispatch_state" in slot:
            spent["model_calls"] += 1
        for key in ("input_tokens", "output_tokens", "grant_units"):
            spent[key] += int(slot.get(key, 0) or 0)
    return {"exposure": exposure, "spent": spent}


def _freeze_entry(arm: str, stage: str, slots: list, sel: dict,
                  selectors: dict, selection_tasks: dict,
                  frozen_core_digest: str | None) -> dict:
    kind = slots[0]["kind"]
    selected = sel.get("selected")
    winner = None
    if selected is not None:
        winner = next((slot for slot in slots if slot["slot"] == selected),
                      None)
    entry = {"arm": arm, "stage": stage, "kind": kind, "selected": selected,
             "reason": sel.get("reason", ""),
             "identities": _identities(kind, winner),
             "lineage": _lineage(stage, kind, winner, sel, selection_tasks),
             "applicability": {"stage": stage,
                               "families": list(STAGE_FAMILIES[stage])},
             "dependencies": {"frozen_core_digest": frozen_core_digest
                              if stage == "transfer" else None},
             "budget": _budget(slots)}
    name, contract = _contract(kind, winner, sel, selectors)
    entry[name] = contract
    return entry


def freeze_retention(*, tag: str, model: str, reasoning_effort: str,
                     manifest_sha: str,
                     selectors: dict, selection_tasks: dict, slots: list,
                     selection: dict, frozen_core_digest: str | None,
                     spent: dict, budget: dict, equal_opportunity: str,
                     campaign_allocation: str, foundation_allocation: str,
                     transfer_reserve: int) -> dict:
    entries = {}
    for (arm, stage), sel in sorted(selection.items()):
        keyed = [slot for slot in slots
                 if slot["arm"] == arm and slot["stage"] == stage]
        entries["%s-%s" % (arm, stage)] = _freeze_entry(
            arm, stage, keyed, sel, selectors, selection_tasks,
            frozen_core_digest)
    return {"format": RETENTION_FORMAT, "tag": tag, "model": model,
            "reasoning_effort": reasoning_effort,
            "manifest_sha256": manifest_sha, "selectors": selectors,
            "frozen_core_digest": frozen_core_digest, "budget": budget,
            "equal_opportunity": equal_opportunity,
            "transfer_enrichment_reserve": transfer_reserve,
            "campaign_allocation": campaign_allocation,
            "foundation_allocation": foundation_allocation,
            "entries": entries, "spent": spent}


def _package_text(artifacts_root, digest: str, name: str) -> bytes:
    try:
        package = json.loads((Path(artifacts_root) / digest).read_bytes()
                             .decode("utf-8"))
        return bytes.fromhex(package["files"][name])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RetentionError("unreadable-package %s: %s"
                             % (digest[:12], exc))


def _load_text(key: str, entry: dict, dsn: str, artifacts_root) -> None:
    identities = entry.get("identities") or {}
    artifact_digest = identities.get("artifact_digest")
    file_digest = identities.get("file_digest")
    if not isinstance(artifact_digest, str) or not artifact_digest \
            or not isinstance(file_digest, str) or not file_digest:
        raise RetentionError("%s selected without artifact identity" % key)
    checked = artifacts.verify_bytes(dsn, artifacts_root, artifact_digest)
    if not checked.get("ok"):
        raise RetentionError("%s artifact unverifiable: %s"
                             % (key, checked.get("reason", "")))
    raw = _package_text(artifacts_root, artifact_digest,
                        TEXT_ENTRY[entry["kind"]])
    if _digest(raw) != file_digest:
        raise RetentionError("%s file digest mismatch" % key)


def _load_composition(key: str, entry: dict, dsn: str, artifacts_root) -> None:
    identities = entry.get("identities") or {}
    composition_id = identities.get("composition_id")
    if not isinstance(composition_id, str) or not composition_id:
        raise RetentionError("%s selected without composition identity" % key)
    try:
        checked = R.check_composition(dsn, artifacts_root, composition_id)
    except SettlementError as exc:
        raise RetentionError("%s composition unverifiable: %s"
                             % (key, str(exc)[:200]))
    for field in ("package_digest", "core_digest", "adapter_digest"):
        if checked.get(field) != identities.get(field):
            raise RetentionError("%s %s mismatch" % (key, field))


def load_retention(path, dsn: str, artifacts_root) -> dict:
    try:
        doc = json.loads(Path(path).read_bytes().decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise RetentionError("unreadable-retention: %s" % exc)
    if not isinstance(doc, dict) or doc.get("format") != RETENTION_FORMAT:
        raise RetentionError("unknown-format: %s"
                             % (doc.get("format") if isinstance(
                                 doc, dict) else type(doc).__name__))
    entries = doc.get("entries")
    if not isinstance(entries, dict) \
            or sorted(entries) != sorted(ENTRY_KEYS):
        raise RetentionError("retention entries are not the frozen panel")
    try:
        pinned = (ROOT / "experiments" / "representation" / "experiment"
                  / "manifest.sha256").read_text().strip()
    except OSError as exc:
        raise RetentionError("manifest-hash-unreadable: %s" % exc)
    if doc.get("manifest_sha256") != pinned:
        raise RetentionError("manifest-mismatch: retention froze %s" %
                             doc.get("manifest_sha256"))
    for key in ENTRY_KEYS:
        entry = entries[key]
        if not isinstance(entry, dict) or not entry.get("reason"):
            raise RetentionError("%s entry lacks an explicit reason" % key)
        if entry.get("selected") is None:
            continue
        if entry.get("kind") in TEXT_ENTRY:
            _load_text(key, entry, dsn, artifacts_root)
        elif entry.get("kind") in ("core", "adapter"):
            _load_composition(key, entry, dsn, artifacts_root)
        else:
            raise RetentionError("%s entry has an unknown kind" % key)
    return doc
