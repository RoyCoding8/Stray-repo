"""E2: does relevant experience beat a size-matched irrelevant control?

Expansion question 2: *does accumulated experience improve acquisition and
action choice, and does relevant experience beat irrelevant or shuffled
experience?*

The apparatus was here and had never been driven. `learner.matched_experience_arms`
builds the relevant-vs-irrelevant pair with `equal_length_experience_pair`
enforcing that the two arms carry the same number of characters, so context
volume cannot be what any difference is attributed to. But nothing had ever
called it and then scored a difference: the test suite exercised
`acquisition_cost_arms`, which is the *cost* side, not the relevance
contrast.

This module is the scored contrast. It renders the exact construction prompt
each arm would spend a live call on, dispatches both through the real
`learner.model_propose` path, and reports whether the two acquisitions
differ. Two things it deliberately does not do:

- It does not attribute a score difference to relevance unless the two
  rendered prompts are the same length. The enforcement lives in the pair
  constructor; this re-asserts it before dispatch so a caller that reached
  past it cannot smuggle an unequal control into a scored claim.
- It does not treat a tie as a win. A tie is `tie`.

The two arms' prompts differ in exactly one place — the trailing
`Prior observations:` line — so a difference in what the model writes back
is attributable to the experience content, not to the surrounding contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from . import learner


@dataclass(frozen=True)
class ArmAcquisition:
    arm: str
    prompt: str
    prompt_chars: int
    response: str
    method: str
    digest: str
    operation_id: str
    error: str = ""

    def as_dict(self) -> dict:
        return {"arm": self.arm, "prompt_chars": self.prompt_chars,
                "method": self.method, "digest": self.digest,
                "operation_id": self.operation_id, "error": self.error}


@dataclass(frozen=True)
class ScoredContrast:
    condition: str
    target_task_id: str
    relevant: ArmAcquisition
    irrelevant: ArmAcquisition
    relevant_chars: int
    irrelevant_chars: int
    outcome: str
    detail: Mapping[str, Any] = field(default_factory=dict)

    @property
    def differs(self) -> bool:
        if self.outcome == "unscored":
            return False
        return self.relevant.digest != self.irrelevant.digest

    def as_dict(self) -> dict:
        return {
            "condition": self.condition,
            "target_task_id": self.target_task_id,
            "outcome": self.outcome,
            "relevant": self.relevant.as_dict(),
            "irrelevant": self.irrelevant.as_dict(),
            "relevant_chars": self.relevant_chars,
            "irrelevant_chars": self.irrelevant_chars,
            "differs": self.differs,
            "detail": dict(self.detail),
        }


def _extract_method(response: str) -> str:
    """The chosen `method=` from a construction, or '' if unparseable.

    This is the same observable the method-menu study recorded: what the
    model actually reached for. It is parsed, never defaulted, so an
    acquisition that named nothing reads as `none` and is not silently
    credited with a method it did not choose.
    """
    import re
    match = re.search(r"method\s*=\s*[\"']([a-z_]+)[\"']", response or "")
    return match.group(1) if match else "none"


def build_scored_contrast(target_task: dict, source_task_ids: list,
                          filler_task_ids: list, visible: list,
                          *, budget: dict | None = None) -> dict:
    """The size-matched pair, re-asserting equal length before anything runs."""
    pair = learner.matched_experience_arms(
        target_task, source_task_ids, visible, task_ids=filler_task_ids,
        budget=budget)
    learner.equal_length_experience_pair(pair["relevant"], pair["irrelevant"])
    return pair


def render_prompts(pair: dict) -> dict:
    """The two exact construction prompts, keyed by arm name."""
    return {
        "relevant": learner.treatment_prompt(
            pair["relevant"], pair["relevant"]["task"],
            pair["relevant"]),
        "irrelevant": learner.treatment_prompt(
            pair["irrelevant"], pair["irrelevant"]["task"],
            pair["irrelevant"]),
    }


def score_from_proposals(relevant: dict, irrelevant: dict, *,
                         target_task_id: str,
                         relevant_chars: int,
                         irrelevant_chars: int) -> ScoredContrast:
    """Compare two already-settled acquisitions, no dispatch."""
    import hashlib
    def _arm(name, proposal):
        text = proposal.get("source", "") if isinstance(proposal, dict) else ""
        return ArmAcquisition(
            arm=name, prompt="", prompt_chars=0, response=text,
            method=_extract_method(text),
            digest=hashlib.sha256(text.encode()).hexdigest(),
            operation_id=(proposal or {}).get("operation_id", ""),
            error=(proposal or {}).get("error", ""))
    rel = _arm("relevant", relevant)
    irr = _arm("irrelevant", irrelevant)
    if rel.error or irr.error:
        outcome = "unscored"
    elif rel.digest == irr.digest:
        outcome = "tie"
    else:
        outcome = "differs"
    return ScoredContrast(
        condition="relevant-versus-shuffled",
        target_task_id=target_task_id, relevant=rel, irrelevant=irr,
        relevant_chars=relevant_chars, irrelevant_chars=irrelevant_chars,
        outcome=outcome,
        detail={"relevant_method": rel.method, "irrelevant_method": irr.method})


def live_scored_contrast(dsn: str, *, target_task: dict,
                         source_task_ids: list, filler_task_ids: list,
                         visible: list, gateway: Any, model: str,
                         charter: dict, world: int, arm: str,
                         allocation_id: str,
                         budget: dict | None = None) -> ScoredContrast:
    """Dispatch both arms through the real learner path and score the pair.

    Each arm gets its own campaign id, so the two construction calls are
    two operations and neither is served from the other's settled receipt.
    """
    pair = build_scored_contrast(target_task, source_task_ids,
                                 filler_task_ids, visible, budget=budget)
    results = {}
    for name in ("relevant", "irrelevant"):
        cid = "%s-e2-%s" % (target_task.get("task_id", "t"), name)
        prop = learner.propose_from_model(
            dsn, cid=cid, gateway=gateway, model=model, charter=charter,
            world=world, arm=arm, allocation_id=allocation_id)
        try:
            proposal = prop(pair[name], {})
            results[name] = {"source": proposal.get("source", ""),
                             "operation_id": cid}
        except Exception as exc:
            results[name] = {"source": "",
                             "error": "%s: %s" % (type(exc).__name__, exc),
                             "operation_id": cid}
    scored = score_from_proposals(
        results["relevant"], results["irrelevant"],
        target_task_id=target_task.get("task_id", ""),
        relevant_chars=pair["relevant_chars"],
        irrelevant_chars=pair["irrelevant_chars"])
    return scored
