"""Revisioned interpretations over immutable learner-visible experiences."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from psycopg.rows import dict_row

from settlement import db
from settlement.common import SettlementError, StaleRevision

from . import experience

_STATUSES = {"untested", "supported", "challenged", "withdrawn", "superseded"}
_VIEWS = {"structured", "raw-history"}
_MAX_TEXT = 16 * 1024
_MAX_PURPOSE = 1024
_MAX_SCOPE_ITEMS = 16
_MAX_LINKS = 32
_MAX_OBSERVATIONS = 64
_MAX_QUERY_LIMIT = 50
_MAX_QUERY_IDS = 256
_MAX_ROOTS = 256
_MAX_ANCESTRY = 512
_CLAIM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$")
_KIND = re.compile(r"^[a-z][a-z0-9_.-]{0,39}$")
_WORD = re.compile(r"[\w-]{3,}", re.UNICODE)
_STOP_WORDS = {"and", "are", "for", "from", "how", "that", "the", "this", "with"}


def _scope(value: Any, name: str) -> dict[str, str]:
    if not isinstance(value, dict) or len(value) > _MAX_SCOPE_ITEMS:
        raise SettlementError(f"{name} must be an object with at most {_MAX_SCOPE_ITEMS} filters")
    result: dict[str, str] = {}
    for key, item in value.items():
        if (not isinstance(key, str) or not key or len(key) > 64
                or not isinstance(item, str) or not item or len(item) > 256):
            raise SettlementError(f"{name} filters must have bounded non-empty string keys and values")
        result[key] = item
    return result


def _ids(value: Iterable[int], name: str, maximum: int) -> list[int]:
    if isinstance(value, (str, bytes)):
        raise SettlementError(f"{name} must be an array of positive observation IDs")
    try:
        items = list(value)
    except TypeError as exc:
        raise SettlementError(f"{name} must be an array of positive observation IDs") from exc
    if (len(items) > maximum or any(type(item) is not int or item < 1 for item in items)
            or len(set(items)) != len(items)):
        raise SettlementError(f"{name} must contain at most {maximum} distinct positive integers")
    return items


def _pairs(value: Iterable, name: str) -> list[list[Any]]:
    if isinstance(value, (str, bytes)):
        raise SettlementError(f"{name} must contain claim ID and version pairs")
    try:
        items = list(value)
    except TypeError as exc:
        raise SettlementError(f"{name} must contain claim ID and version pairs") from exc
    if len(items) > _MAX_LINKS:
        raise SettlementError(f"{name} exceeds the {_MAX_LINKS}-link limit")
    result: list[list[Any]] = []
    for item in items:
        if (not isinstance(item, (list, tuple)) or len(item) != 2
                or not isinstance(item[0], str) or not _CLAIM_ID.fullmatch(item[0])
                or type(item[1]) is not int or item[1] < 1):
            raise SettlementError(f"{name} entries must be (claim_id, positive_version) pairs")
        pair = [item[0], item[1]]
        if pair in result:
            raise SettlementError(f"{name} entries must be distinct")
        result.append(pair)
    return result


def _claim_id(value: str) -> str:
    if not isinstance(value, str) or not _CLAIM_ID.fullmatch(value):
        raise SettlementError("claim_id must be a bounded identifier")
    return value


def _purpose(value: str) -> str:
    if (not isinstance(value, str) or not value.strip()
            or len(value) > _MAX_PURPOSE or "\x00" in value):
        raise SettlementError("purpose must be non-empty and bounded")
    return value.strip()


def _record(row: dict) -> dict:
    return {
        "claim_id": row["claim_id"],
        "version": int(row["version"]),
        "revision": int(row["revision"]),
        "kind": row["kind"],
        "status": row["status"],
        "text": row["text"],
        "scope": dict(row["scope"] or {}),
        "support": list(row["support"] or []),
        "opposition": list(row["opposition"] or []),
        "derived_from": [list(pair) for pair in (row["derived_from"] or [])],
        "supersedes": [list(pair) for pair in (row["supersedes"] or [])],
    }


def _load_versions(cur, revision: int) -> dict[tuple[str, int], dict]:
    cur.execute(
        "SELECT claim_id, version, revision, kind, status, text, scope, support, opposition,"
        " derived_from, supersedes FROM rsi_memory_claim_versions"
        " WHERE revision <= %s ORDER BY revision, claim_id, version",
        (revision,),
    )
    return {(row["claim_id"], int(row["version"])): _record(row)
            for row in cur.fetchall()}


def _heads(versions: dict[tuple[str, int], dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for row in versions.values():
        if row["claim_id"] not in result or row["version"] > result[row["claim_id"]]["version"]:
            result[row["claim_id"]] = row
    return result


def _captured(cur, revision: int) -> dict[int, dict]:
    cur.execute(
        "SELECT observation_id, revision, scope, visibility FROM rsi_memory_experiences"
        " WHERE revision <= %s ORDER BY revision, observation_id",
        (revision,),
    )
    return {int(row["observation_id"]): {
        "revision": int(row["revision"]),
        "scope": dict(row["scope"] or {}),
        "visibility": row["visibility"],
    } for row in cur.fetchall()}


def _roots(key: tuple[str, int], versions: dict[tuple[str, int], dict],
           captured: dict[int, dict], *, max_nodes: int = _MAX_ANCESTRY):
    """Flatten a small, version-linked ancestry to distinct original IDs."""
    memo: dict[tuple[str, int], tuple[set[int], set[int]] | None] = {}
    visiting: set[tuple[str, int]] = set()
    visited_nodes = 0

    def visit(current: tuple[str, int]):
        nonlocal visited_nodes
        if current in memo:
            return memo[current]
        if current in visiting or visited_nodes >= max_nodes:
            return None
        row = versions.get(current)
        if row is None:
            return None
        visiting.add(current)
        visited_nodes += 1
        support = set(row["support"])
        opposition = set(row["opposition"])
        if any(type(item) is not int or item < 1 or item not in captured
               or captured[item]["visibility"] != "learner"
               for item in support | opposition):
            result = None
        else:
            result = (support, opposition)
            for parent in row["derived_from"]:
                roots = visit((parent[0], int(parent[1])))
                if roots is None:
                    result = None
                    break
                result[0].update(roots[0])
                result[1].update(roots[1])
            if (result is not None and
                    len(result[0]) + len(result[1]) > _MAX_ROOTS):
                result = None
        visiting.remove(current)
        memo[current] = result
        return result

    return visit(key)


def _scope_roots(roots: tuple[set[int], set[int]], scope: dict,
                 captured: dict[int, dict]) -> tuple[set[int], set[int]]:
    """A task-specific interpretation cannot inherit another task's roots."""
    def applies(observation_id: int) -> bool:
        source_scope = captured[observation_id]["scope"]
        return not ("task" in scope and "task" in source_scope
                    and scope["task"] != source_scope["task"])

    return ({item for item in roots[0] if applies(item)},
            {item for item in roots[1] if applies(item)})


def _validate_links(cur, *, claim_id: str, version: int, scope: dict,
                    observations: list[int], links: list[list[Any]],
                    supersedes: list[list[Any]], prior_revision: int):
    ids = set(observations)
    if ids:
        cur.execute(
            "SELECT observation_id, scope, visibility FROM rsi_memory_experiences"
            " WHERE observation_id = ANY(%s) AND revision <= %s",
            (sorted(ids), prior_revision),
        )
        found = {int(row["observation_id"]): row for row in cur.fetchall()}
        if (len(found) != len(ids)
                or any(row["visibility"] != "learner" for row in found.values())):
            raise SettlementError("observation reference is unavailable to learner memory")
        if any("task" in scope and "task" in dict(row["scope"] or {})
               and scope["task"] != dict(row["scope"] or {})["task"]
               for row in found.values()):
            raise SettlementError("observation task scope does not match the claim")
    if any(pair[0] == claim_id for pair in links):
        raise SettlementError("a claim cannot derive from another version of itself")
    if [claim_id, version] in supersedes:
        raise SettlementError("a claim version cannot link to itself")
    if any(pair[0] != claim_id and pair not in links for pair in supersedes):
        raise SettlementError("cross-claim supersession must derive from that version")
    for pair in links + supersedes:
        cur.execute(
            "SELECT scope FROM rsi_memory_claim_versions"
            " WHERE claim_id = %s AND version = %s AND revision <= %s",
            (pair[0], pair[1], prior_revision),
        )
        row = cur.fetchone()
        if row is None:
            raise SettlementError("claim relationship references an unavailable version")
        if pair in links and any(scope.get(key) != value for key, value in row["scope"].items()):
            raise SettlementError("derived claim scope cannot be broader than its source")


def revise(dsn: str, *, claim_id: str, expected_version: int, text: str,
           scope: dict, status: str, support=(), opposition=(), derived_from=(),
           supersedes=(), kind: str = "lesson", artifacts_root) -> dict:
    claim_id = _claim_id(claim_id)
    if type(expected_version) is not int or expected_version < 0:
        raise SettlementError("expected_version must be a non-negative integer")
    if (not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > _MAX_TEXT
            or "\x00" in text):
        raise SettlementError("claim text must be non-empty and at most 16 KiB")
    if not isinstance(status, str) or status not in _STATUSES:
        raise SettlementError("unsupported claim status")
    if not isinstance(kind, str) or not _KIND.fullmatch(kind):
        raise SettlementError("kind must be a bounded lowercase label")
    scope = _scope(scope, "claim scope")
    support = _ids(support, "support", _MAX_OBSERVATIONS)
    opposition = _ids(opposition, "opposition", _MAX_OBSERVATIONS)
    if set(support) & set(opposition):
        raise SettlementError("one observation cannot directly support and oppose the same version")
    derived_from = _pairs(derived_from, "derived_from")
    supersedes = _pairs(supersedes, "supersedes")

    with db.connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        revision = experience._next_revision(cur)
        prior_revision = revision - 1
        cur.execute(
            "SELECT version FROM rsi_memory_claim_versions WHERE claim_id = %s"
            " ORDER BY version DESC LIMIT 1",
            (claim_id,),
        )
        row = cur.fetchone()
        current_version = int(row["version"]) if row is not None else 0
        if current_version != expected_version:
            raise StaleRevision(
                f"expected claim version {expected_version}, current {current_version}")
        version = current_version + 1
        if current_version:
            prior_versions = _load_versions(cur, prior_revision)
            prior_captured = _captured(cur, prior_revision)
            prior = prior_versions[(claim_id, current_version)]
            if any(scope.get(key) != value for key, value in prior["scope"].items()):
                raise SettlementError("claim scope cannot broaden across versions")
            prior_roots = _roots((claim_id, current_version), prior_versions, prior_captured)
            if prior_roots is None:
                raise SettlementError("previous claim ancestry is unavailable")
            prior_roots = _scope_roots(prior_roots, scope, prior_captured)
            carried_opposition = [
                observation_id for observation_id in sorted(prior_roots[1])
            ]
            opposition = list(dict.fromkeys(opposition + carried_opposition))
            if len(opposition) > _MAX_OBSERVATIONS:
                raise SettlementError("inherited opposition exceeds the per-version limit")
        _validate_links(cur, claim_id=claim_id, version=version, scope=scope,
                        observations=support + opposition, links=derived_from,
                        supersedes=supersedes, prior_revision=prior_revision)

        if status == "supported":
            versions = _load_versions(cur, prior_revision)
            captured = _captured(cur, prior_revision)
            support_roots, _ = set(support), set()
            for pair in derived_from:
                parent = versions.get((pair[0], int(pair[1])))
                head = _heads(versions).get(pair[0])
                if parent is None or head is None or head["status"] in {"withdrawn", "superseded"}:
                    raise SettlementError("supported claim cannot inherit a withdrawn source")
                inherited = _roots((pair[0], int(pair[1])), versions, captured)
                if inherited is None:
                    raise SettlementError("claim ancestry is unavailable to learner memory")
                inherited = _scope_roots(inherited, scope, captured)
                support_roots.update(inherited[0])
            if not support_roots:
                raise SettlementError("supported claim needs original checked support")
            resolved = experience.resolve(
                dsn, sorted(support_roots), artifacts_root=artifacts_root,
                revision=prior_revision, visibility="learner")
            checked = {item["observation_id"] for item in resolved["observations"]
                       if type(item.get("observation_id")) is int
                       and isinstance(item.get("content"), dict)
                       and type(item["content"].get("passed")) is bool}
            if not checked:
                raise SettlementError("supported claim needs available checked original evidence")

        cur.execute(
            "INSERT INTO rsi_memory_claim_versions"
            " (claim_id, version, revision, kind, status, text, scope, support, opposition,"
            " derived_from, supersedes)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb,"
            " %s::jsonb, %s::jsonb)",
            (claim_id, version, revision, kind, status, text.strip(),
             json.dumps(scope, sort_keys=True), json.dumps(support),
             json.dumps(opposition), json.dumps(derived_from), json.dumps(supersedes)),
        )
    return {"claim_id": claim_id, "version": version, "revision": revision,
            "kind": kind, "status": status, "text": text.strip(), "scope": scope,
            "support": support, "opposition": opposition,
            "derived_from": derived_from, "supersedes": supersedes}


def _tokens(value: str) -> set[str]:
    return {word.casefold() for word in _WORD.findall(value)
            if word.casefold() not in _STOP_WORDS}


def _matches(text: str, purpose: str) -> tuple[bool, bool]:
    left, right = text.casefold().strip(), purpose.casefold().strip()
    exact = bool(right) and (left == right or right in left)
    if exact:
        return True, True
    return bool(_tokens(left) & _tokens(right)), False


def _as_of(cur, requested: int | None) -> int:
    current = experience._revision(cur)
    selected = current if requested is None else requested
    if type(selected) is not int or selected < 0 or selected > current:
        raise SettlementError("requested memory revision is unavailable")
    return selected


def _investigation_scope(cur, investigation_id: str, scope: dict[str, str]):
    if (not isinstance(investigation_id, str) or not investigation_id
            or len(investigation_id) > 200):
        raise SettlementError("investigation_id must be a bounded identifier")
    cur.execute("SELECT domain, config FROM rsi_investigations WHERE investigation_id = %s",
                (investigation_id,))
    row = cur.fetchone()
    if row is None:
        raise SettlementError("memory query requires an existing investigation")
    if scope.get("domain") != row["domain"]:
        raise SettlementError("query scope domain must match the investigation")
    task = dict(row["config"] or {}).get("task")
    if "task" in scope and task is not None and scope["task"] != task:
        raise SettlementError("query task scope must match the investigation")


def _effective_status(row: dict, support_roots: set[int], opposition_roots: set[int],
                      available: set[int]) -> tuple[str, str | None]:
    recorded = row["status"]
    if recorded == "supported" and not (support_roots & available):
        return ("challenged" if opposition_roots & available else "untested", recorded)
    return recorded, None


def _public_claim(row: dict, roots: tuple[set[int], set[int]],
                  available: set[int]) -> dict:
    support_roots, opposition_roots = roots
    status, recorded = _effective_status(row, support_roots, opposition_roots, available)
    item = {**row, "status": status,
            "support": sorted(support_roots), "opposition": sorted(opposition_roots),
            "direct_support": list(row["support"]),
            "direct_opposition": list(row["opposition"])}
    if recorded is not None:
        item["recorded_status"] = recorded
    return item


def _stale_ancestry(row: dict, heads: dict[str, dict],
                    versions: dict[tuple[str, int], dict],
                    superseded: set[tuple[str, int]],
                    seen: set[tuple[str, int]] | None = None) -> bool:
    seen = set() if seen is None else seen
    for parent, version in row["derived_from"]:
        key = (parent, int(version))
        superseded_by_another = key in superseded and [*key] not in row["supersedes"]
        if key in seen or superseded_by_another:
            return True
        head = heads.get(parent)
        if head is None or head["status"] in {"withdrawn", "superseded"}:
            return True
        ancestor = versions.get(key)
        if ancestor is None:
            return True
        seen.add(key)
        if _stale_ancestry(ancestor, heads, versions, seen):
            return True
        seen.remove(key)
    return False


def _resolve(dsn: str, observation_ids: list[int], artifacts_root,
             revision: int) -> tuple[list[dict], list[dict], set[int], set[int]]:
    if not observation_ids:
        return [], [], set(), set()
    result = experience.resolve(
        dsn, observation_ids, artifacts_root=artifacts_root,
        revision=revision, visibility="learner")
    observations = []
    available: set[int] = set()
    checked: set[int] = set()
    for row in result["observations"]:
        if type(row.get("observation_id")) is not int:
            raise SettlementError("experience resolver returned a malformed observation identity")
        observations.append(dict(row))
        available.add(row["observation_id"])
        content = row.get("content")
        if isinstance(content, dict) and type(content.get("passed")) is bool:
            checked.add(row["observation_id"])
    missing = []
    for item in result["missing_information"]:
        observation_id = item.get("observation_id") if isinstance(item, dict) else None
        if type(observation_id) is int:
            missing.append({"observation_id": observation_id,
                            "reason": "source is unavailable"})
        else:
            missing.append({"reason": "source is unavailable"})
    return observations, missing, checked, available


def _search_experiences(captured: dict[int, dict], scope: dict,
                        excluded: set[int], maximum: int) -> tuple[list[int], bool]:
    candidates = sorted(
        (observation_id for observation_id, item in captured.items()
         if item["visibility"] == "learner" and observation_id not in excluded
         and all(item["scope"].get(key) == value for key, value in scope.items())),
        key=lambda item: (captured[item]["revision"], item), reverse=True)
    selected = candidates[:maximum]
    return selected, len(candidates) > len(selected)


def query(dsn: str, *, purpose: str, investigation_id: str, scope: dict,
          artifacts_root, visibility: str = "learner", revision: int | None = None,
          view: str = "structured", claim_ids=(), observation_ids=(),
          limit: int = 10) -> dict:
    purpose = _purpose(purpose)
    scope = _scope(scope, "query scope")
    if visibility != "learner":
        raise SettlementError("unsupported memory visibility")
    if view not in _VIEWS:
        raise SettlementError("view must be structured or raw-history")
    if type(limit) is not int or limit < 1 or limit > _MAX_QUERY_LIMIT:
        raise SettlementError(f"limit must be between 1 and {_MAX_QUERY_LIMIT}")
    claim_ids = [_claim_id(item) for item in claim_ids]
    if len(claim_ids) > _MAX_LINKS or len(set(claim_ids)) != len(claim_ids):
        raise SettlementError(f"claim_ids must contain at most {_MAX_LINKS} distinct IDs")
    observation_ids = _ids(observation_ids, "observation_ids", _MAX_QUERY_IDS)

    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        selected_revision = _as_of(cur, revision)
        _investigation_scope(cur, investigation_id, scope)
        versions = _load_versions(cur, selected_revision)
        captured = _captured(cur, selected_revision)
        conn.commit()

    missing_information: list[dict] = []
    heads = _heads(versions)
    targets = {(pair[0], int(pair[1])) for row in heads.values()
               if row["scope"] == scope for pair in row["supersedes"]}
    applicable: list[tuple[dict, tuple[set[int], set[int]]]] = []
    hidden_ancestry = False
    for row in heads.values():
        if row["scope"] != scope:
            continue
        if row["status"] in {"withdrawn", "superseded"} and view == "structured":
            continue
        roots = _roots((row["claim_id"], row["version"]), versions, captured)
        if roots is None:
            hidden_ancestry = True
            continue
        roots = _scope_roots(roots, row["scope"], captured)
        if view == "structured" and _stale_ancestry(row, heads, versions, targets):
            continue
        applicable.append((row, roots))

    if view == "raw-history":
        ids = set(observation_ids)
        if claim_ids:
            for requested_id in claim_ids:
                selected = [(row, roots) for row, roots in applicable
                            if row["claim_id"] == requested_id]
                if not selected:
                    missing_information.append({"claim_id": requested_id,
                                                "reason": "claim is unavailable at requested revision"})
                    continue
                for _row, roots in selected:
                    ids.update(roots[0] | roots[1])
        base = [observation_id for observation_id in sorted(ids)
                      if observation_id in captured
                      and captured[observation_id]["revision"] <= selected_revision
                      and captured[observation_id]["visibility"] == "learner"
                      and all(captured[observation_id]["scope"].get(key) == value
                              for key, value in scope.items())]
        if len(base) > _MAX_QUERY_IDS:
            return {"revision": selected_revision, "purpose": purpose, "scope": scope,
                    "view": view, "claims": [], "observations": [],
                    "missing_information": [
                        {"reason": "memory evidence exceeds the bounded query"}]}
        search_ids, search_truncated = ([], False)
        if not claim_ids and not observation_ids:
            search_ids, search_truncated = _search_experiences(
                captured, scope, set(base), _MAX_QUERY_IDS - len(base))
        candidates = base + search_ids
        observations, missing, _checked, _available = _resolve(
            dsn, candidates, artifacts_root, selected_revision)
        missing_information.extend(missing)
        if missing or hidden_ancestry:
            missing_information.append(
                {"reason": "some learner memory was withheld because experience is unavailable"})
        if search_truncated:
            missing_information.append(
                {"reason": "experience search reached its bounded candidate limit"})
        by_id = {item["observation_id"]: item for item in observations}
        selected_ids = list(base)
        if search_ids:
            matches = [observation_id for observation_id in search_ids
                       if observation_id in by_id and
                       _matches(by_id[observation_id]["content"].get("task_instruction", "")[:_MAX_TEXT],
                                purpose)[0]]
            selected_ids.extend(matches[:limit])
        selected = [by_id[item] for item in dict.fromkeys(selected_ids) if item in by_id]
        missing_information.extend(
            {"observation_id": item, "reason": "observation is unavailable at requested revision"}
            for item in observation_ids if item not in base)
        return {"revision": selected_revision, "purpose": purpose, "scope": scope,
                "view": view, "claims": [], "observations": selected,
                "missing_information": missing_information}

    all_root_ids = sorted({item for _row, roots in applicable
                           for group in roots for item in group})
    mandatory_ids = set(all_root_ids) | {
        item for item in observation_ids
        if item in captured and captured[item]["visibility"] == "learner"
        and all(captured[item]["scope"].get(key) == value for key, value in scope.items())
    }
    if len(mandatory_ids) > _MAX_QUERY_IDS:
        return {"revision": selected_revision, "purpose": purpose, "scope": scope,
                "view": view, "claims": [], "observations": [],
                "missing_information": [
                    {"reason": "memory evidence exceeds the bounded query"}]}
    search_ids, search_truncated = ([], False)
    if not claim_ids and not observation_ids:
        search_ids, search_truncated = _search_experiences(
            captured, scope, mandatory_ids, _MAX_QUERY_IDS - len(mandatory_ids))
    to_resolve = sorted(mandatory_ids | set(search_ids))
    resolved, _resolver_missing, available_support, present = _resolve(
        dsn, to_resolve, artifacts_root, selected_revision)
    unavailable_roots = set(all_root_ids) - present
    if unavailable_roots:
        missing_information.append(
            {"reason": "some claims were withheld because referenced experience is unavailable"})
    if hidden_ancestry:
        missing_information.append(
            {"reason": "some learner memory was withheld because experience is unavailable"})
    if search_truncated:
        missing_information.append(
            {"reason": "experience search reached its bounded candidate limit"})
    if any(item.get("observation_id") in set(search_ids)
           for item in _resolver_missing if isinstance(item, dict)):
        missing_information.append(
            {"reason": "some matching experience was withheld because its source is unavailable"})
    eligible: list[tuple[dict, tuple[set[int], set[int]]]] = []
    found_claim_ids = set()
    for row, roots in applicable:
        claim_id_value = row["claim_id"]
        if (roots[0] | roots[1]) - present:
            continue
        if claim_ids and claim_id_value not in claim_ids:
            continue
        if (row["claim_id"], row["version"]) in targets:
            continue
        found_claim_ids.add(claim_id_value)
        root_ids = roots[0] | roots[1]
        if observation_ids and not (root_ids & set(observation_ids)):
            continue
        matched, _exact = _matches(row["text"], purpose)
        if not claim_ids and not observation_ids and not matched:
            continue
        eligible.append((row, roots))
    missing_information.extend(
        {"claim_id": item, "reason": "claim is unavailable at requested revision"}
        for item in claim_ids if item not in found_claim_ids)
    eligible.sort(key=lambda item: (-item[0]["revision"], item[0]["claim_id"]))
    selected_rows = eligible[:limit]
    wanted = {item for _row, roots in selected_rows for group in roots for item in group}
    if observation_ids:
        wanted.update(item for item in observation_ids if item in present)
        missing_information.extend(
            {"observation_id": item,
             "reason": "observation is unavailable at requested revision"}
            for item in observation_ids if item not in present)
    source_by_id = {row["observation_id"]: row for row in resolved}
    if not claim_ids and not observation_ids:
        searchable = set(search_ids) | {
            item for item in mandatory_ids
            if all(captured[item]["scope"].get(key) == value for key, value in scope.items())
        }
        experience_matches = [
            row["observation_id"] for row in resolved
            if row["observation_id"] in searchable
            and _matches(row["content"].get("task_instruction", "")[:_MAX_TEXT], purpose)[0]
        ][:limit]
        wanted.update(experience_matches)
    observations = [source_by_id[item] for item in sorted(wanted) if item in source_by_id]
    claims = [_public_claim(row, roots, available_support) for row, roots in selected_rows]
    return {"revision": selected_revision, "purpose": purpose, "scope": scope,
            "view": view, "claims": claims, "observations": observations,
            "missing_information": missing_information}


def history(dsn: str, claim_id: str, *, artifacts_root,
            visibility: str = "learner") -> list[dict]:
    claim_id = _claim_id(claim_id)
    if visibility != "learner":
        raise SettlementError("unsupported memory visibility")
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        current_revision = experience._revision(cur)
        versions = _load_versions(cur, current_revision)
        captured = _captured(cur, current_revision)
        rows = sorted((row for row in versions.values() if row["claim_id"] == claim_id),
                      key=lambda row: row["version"])
        if not rows or any(_roots((claim_id, row["version"]), versions, captured) is None
                           for row in rows):
            conn.commit()
            return []
        conn.commit()

    result = []
    for row in rows:
        roots = _roots((claim_id, row["version"]), versions, captured)
        assert roots is not None
        roots = _scope_roots(roots, row["scope"], captured)
        root_ids = sorted(roots[0] | roots[1])
        observations, missing, available, present = _resolve(
            dsn, root_ids, artifacts_root, row["revision"])
        if set(root_ids) - present:
            continue
        item = _public_claim(row, roots, available)
        item["observations"] = observations
        item["missing_information"] = missing
        result.append(item)
    return result
