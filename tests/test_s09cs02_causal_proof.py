"""Did a policy's decision cause an operation, or was its digest copied onto it.

Finding S09R-02. A live study dispatched three operations, got three
`failure` receipts with empty text, and exited 0. The bundle's use records
carried a policy digest on every one of them. A prior campaign read those
records and scored them as evidence the policy governed the use. It had not
been invoked.

Two questions were fused into one, and the fusion hid both.

    launch qualification   Can this apparatus produce a causal chain at
                           all? Answered before launch, from reviewer
                           authored policies in a namespace of their own,
                           deterministically, with no store.
    post-effect join       Did a policy's decision cause this operation?
                           Answered after the fact, from the persisted
                           chain alone, re-verifiable offline by a third
                           party who never had our process.

The chain they ask for is one where every link is read off bytes rather
than asserted by the writer:

    policy source -> sha256 -> the decision the bytes returned for this
    view -> the action that decision admitted -> the operation the
    action authorized -> the receipt that operation produced

A record that names a policy but cannot produce its decision for the
specific admitted action is `unproven`. It is never a pass, and it is never
a fail either, because the live run is not ours to re-judge.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import s09_causal_proof as causal

STUDY_ROOT = "s09cs02-root"
ACCOUNT_ID = "s09cs02-alloc"
OPERATION_ID = "ad01-s09cs02-w0-I-90-use-ad01-w1-within-sw-00-acquired-sw"

POLICY_SOURCE = (
    "def STEP(view, state):\n"
    "    task = view['task_content']\n"
    "    action = {'kind': 'use_method', 'target': task['task_id'],\n"
    "              'inputs': {'method_id': 'acquired-sw-1',\n"
    "                         'max_queries': 4},\n"
    "              'evidence_refs': [],\n"
    "              'requested_resources': {'queries': 4}}\n"
    "    return {'action': action, 'state': {'used': True}}\n")

METHOD_SOURCE = (
    "def ENTRY(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method='greedy',\n"
    "                                    max_queries=max_queries)\n")

POLICY_DIGEST = hashlib.sha256(POLICY_SOURCE.encode("utf-8")).hexdigest()
METHOD_DIGEST = hashlib.sha256(METHOD_SOURCE.encode("utf-8")).hexdigest()

VIEW = {
    "task_content": {"task_id": "ad01-w1-within-sw-00", "family": "software"},
    "observations": [], "open_questions": [],
    "last_result": None, "eligible_methods": ["acquired-sw-1"],
    "remaining": {"steps": 6, "queries": 8},
    "contract_versions": {"policy_step": "ad01-policy-step-v1",
                          "child": "ad01-child/1", "packet": "ad01-packet/1"},
}

ACTION = {
    "kind": "use_method", "target": "ad01-w1-within-sw-00",
    "inputs": {"method_id": "acquired-sw-1", "max_queries": 4},
    "evidence_refs": [], "requested_resources": {"queries": 4},
}

RECEIPT = {
    "receipt_identity": "gw:%s" % OPERATION_ID,
    "operation_id": OPERATION_ID,
    "outcome": "success",
    "usage": {"input_tokens": 11, "output_tokens": 7, "charge_units": 0,
              "billed": False},
}


def decision(*, seq: int = 0, action: dict | None = None,
             view: dict | None = None) -> dict:
    return {
        "seq": seq,
        "source_digest": POLICY_DIGEST,
        "view_digest": causal.view_digest(view if view is not None else VIEW),
        "action": dict(action if action is not None else ACTION),
    }


def governed_store(**overrides) -> dict:
    """A store whose chain every link of which can be recomputed."""
    store = {
        "study_root": STUDY_ROOT,
        "decision": decision(),
        "view": dict(VIEW),
        "policy_source": POLICY_SOURCE,
        "operations": {OPERATION_ID: {
            "operation_id": OPERATION_ID, "effect": "model-inference",
            "method_digest": METHOD_DIGEST, "study_root": STUDY_ROOT}},
        "receipts": [dict(RECEIPT)],
        "use_records": [governed_use_record()],
    }
    store.update(overrides)
    return store


def governed_use_record(**overrides) -> dict:
    record = {
        "record_id": "use-1", "task_id": "ad01-w1-within-sw-00",
        "executed": "acquired-sw-1", "selected": "acquired-sw-1",
        "policy_digest": POLICY_DIGEST,
        "executed_source": METHOD_SOURCE,
        "executed_source_digest": METHOD_DIGEST,
        "operation_ids": [OPERATION_ID],
        "policy_actions": [dict(ACTION)],
    }
    record.update(overrides)
    return record


# 1. The live failure. A digest copied from the freeze, with no decision.


def test_a_copied_digest_with_no_decision_is_unproven():
    """What the live run persisted, reproduced exactly.

    `scripts/s09_pilot.py` writes `policy_digest` from the freeze when
    nothing executed. A record carrying that string claims nothing was
    invoked, so the chain cannot be walked and the claim is unproven.
    """
    backfilled = {
        "use_records": [{
            "record_id": "use-1", "executed": "policy",
            "policy_digest": POLICY_DIGEST,
            "executed_policy_digests": [POLICY_DIGEST],
            "executed_policy_digest": POLICY_DIGEST,
            "executed_source_digest": METHOD_DIGEST,
            "executed_source": METHOD_SOURCE,
            "operation_ids": [OPERATION_ID],
        }],
    }

    verdict = causal.join_post_effect(backfilled)

    assert verdict.status == causal.UNPROVEN
    assert verdict.reasons == ("no-policy-decision",)
    assert verdict.chains == ()


# 2. The false rejection. One retained policy, one digest, many tasks.


def test_one_retained_policy_admitting_one_digest_proves():
    """One policy governing many tasks is the ordinary case, not a fault.

    A single retained policy returns one digest on every task, so any check
    that scores digest diversity as evidence rejects a correct artifact.
    """
    verdict = causal.join_post_effect(governed_store())

    assert verdict.status == causal.PROVEN
    assert verdict.reasons == ()
    assert len(verdict.chains) == 1
    chain = verdict.chains[0]
    assert chain.policy_digest == POLICY_DIGEST
    assert chain.method_digest == METHOD_DIGEST
    assert chain.operation_id == OPERATION_ID
    assert chain.receipt_identity == RECEIPT["receipt_identity"]
    assert chain.task_id == "ad01-w1-within-sw-00"


# 3. Two artifacts, two digests, and only one of them is the policy.


def test_a_policy_digest_on_a_record_with_no_decision_is_unproven():
    """The policy and the method may differ. Only the chain is the test.

    The reviewer correction is explicit that a policy STEP and a task
    method ENTRY are distinct artifacts whose digests need not agree, so
    this record's two digests being different is legal and not the defect.
    The defect is that no decision was ever produced for the action.
    """
    decided = governed_store()
    record = governed_use_record(
        policy_digest=POLICY_DIGEST, executed_source_digest=METHOD_DIGEST)

    assert record["policy_digest"] != record["executed_source_digest"]
    verdict = causal.join_post_effect({**decided, "use_records": [record]})
    assert verdict.status == causal.PROVEN

    without = {**decided, "decision": None}
    verdict = causal.join_post_effect({**without, "use_records": [record]})
    assert verdict.status == causal.UNPROVEN
    assert verdict.reasons == ("no-policy-decision",)


# 4. Unrelated records cannot jointly satisfy the predicate.


def test_two_records_that_each_hold_half_the_evidence_are_unproven():
    """Record A has digests, record B has actions, neither has both.

    The preflight's old probe collected digest-bearing records and
    action-bearing records into separate lists, so a set of unrelated
    records satisfied a predicate none of them satisfied alone. The chain
    is per use record, so a record that lacks any link cannot borrow it.
    """
    record_a = governed_use_record(
        record_id="use-a", policy_actions=[dict(ACTION)])
    store = governed_store(
        use_records=[record_a, governed_use_record(
            record_id="use-b", executed_policy_digests=[POLICY_DIGEST])],
        decision=None, operations={OPERATION_ID: {
            "operation_id": OPERATION_ID, "effect": "model-inference",
            "method_digest": METHOD_DIGEST, "study_root": STUDY_ROOT}})

    verdict = causal.join_post_effect(store)

    assert verdict.status == causal.UNPROVEN
    assert set(verdict.reasons) == {"no-policy-decision"}
    assert verdict.chains == ()
    assert record_a["policy_actions"] == [ACTION]


# 5. Each link is load bearing.


@pytest.mark.parametrize("removed", [
    "decision", "action", "view", "operation", "receipt", "method_bytes",
    "policy_bytes", "receipt_identity",
])
def test_removing_any_one_link_turns_a_proven_chain_unproven(removed: str):
    """Walk the chain and cut it once, at each link, in turn."""
    store = governed_store()
    if removed == "decision":
        store["decision"] = None
    elif removed == "action":
        store["decision"] = {**store["decision"],
                             "action": {"kind": "stop",
                                        "target": store["decision"]["action"]["target"],
                                        "inputs": {"reason": "changed"},
                                        "evidence_refs": [],
                                        "requested_resources": {}}}
    elif removed == "view":
        store["view"] = {**store["view"], "remaining": {"steps": 1,
                                                       "queries": 8}}
    elif removed == "operation":
        store["use_records"][0]["operation_ids"] = []
    elif removed == "receipt":
        store["receipts"] = []
    elif removed == "method_bytes":
        store["use_records"][0]["executed_source"] = "def ENTRY(task):\n    return 0\n"
    elif removed == "policy_bytes":
        store["policy_source"] = POLICY_SOURCE + "\n# edited\n"
    elif removed == "receipt_identity":
        store["receipts"] = [{**RECEIPT,
                              "receipt_identity": "inline:%s" % OPERATION_ID}]

    verdict = causal.join_post_effect(store)

    assert verdict.status == causal.UNPROVEN, removed
    assert verdict.reasons, removed
    assert verdict.chains == (), removed


# 6. A doubled receipt in a live lineage.


def test_a_doubled_receipt_in_a_live_lineage_is_detected():
    """A double's receipt shape inside a live namespace is a different fact.

    Identity is where this lives. A live lineage carries its own study
    root, and a receipt whose content names a foreign root, or a gateway
    receipt whose identity is not the `gw:<operation>:<class>` the broker
    mints, is not this lineage's receipt.
    """
    live = governed_store()
    doubled = {
        **live,
        "receipts": [{
            "receipt_identity": "gw:%s" % OPERATION_ID,
            "operation_id": OPERATION_ID,
            "outcome": "success",
            "content": {"study_root": "s09cs02-doubles-root", "text": ""},
            "usage": {"input_tokens": 5, "output_tokens": 5,
                      "charge_units": 0, "billed": False},
        }],
    }

    assert causal.join_post_effect(live).status == causal.PROVEN

    verdict = causal.join_post_effect(doubled)
    assert verdict.status == causal.UNPROVEN
    assert "foreign-study-root" in verdict.reasons
    assert verdict.chains == ()


def test_a_receipt_whose_identity_is_not_the_brokers_shape_is_refused():
    """A hand-written receipt identity is not an operation's receipt."""
    store = governed_store()
    store["receipts"] = [{**RECEIPT,
                          "receipt_identity": "inline:%s" % OPERATION_ID}]

    verdict = causal.join_post_effect(store)

    assert verdict.status == causal.UNPROVEN
    assert verdict.reasons == ("receipt-identity-mismatch",)


# 7. The two checks cannot be confused for one another.


def test_a_post_effect_record_set_does_not_pass_the_pre_launch_check():
    """Post-effect evidence is not a launch qualification.

    The bundle the study is about to write cannot witness the study. The
    launch check admits a policy, replays it, and asks the apparatus to
    operate; it never reads a use record, and a record set alone has no
    policy, no view and no store to replay against. An operation the caller
    names is something it did and can be asked about later, so the two
    checks separate where they overlap and the post-effect check refuses
    where the record set is the only thing offered.
    """
    store = governed_store()
    records = store["use_records"]

    assert causal.join_post_effect(store).status == causal.PROVEN
    assert causal.qualify_pre_launch(policies=(), operations=[]).status \
        == causal.UNPROVEN
    assert records[0]["record_id"] == "use-1"
    assert causal.qualify_pre_launch(
        policies=(), operations=[store["operations"][OPERATION_ID]]
    ).status == causal.UNPROVEN
    assert causal.join_post_effect({"use_records": records}).reasons \
        == ("no-policy-decision",)


def test_a_digest_copied_onto_a_record_never_qualifies_launch_either():
    """A copied string is inert. The launch check has no digest path."""
    run = causal.PolicyRun(policy_source=POLICY_SOURCE, view=dict(VIEW),
                           operations=(OPERATION_ID,))

    launch = causal.qualify_pre_launch(
        policies=(run,),
        operations=[{"operation_id": OPERATION_ID,
                     "effect": "model-inference",
                     "method_digest": METHOD_DIGEST,
                     "study_root": STUDY_ROOT}])

    assert launch.status == causal.PROVEN
    assert [link.persisted for link in launch.links] == [False, False]
    assert all(chain.persisted is False for chain in launch.chains)
    after = causal.join_post_effect(governed_store())
    assert all(link.persisted for link in after.links)
    assert all(chain.persisted is True for chain in after.chains)
    assert causal.PolicyRun(
        policy_source=POLICY_SOURCE, view=dict(VIEW),
        operations=(OPERATION_ID,)).source_digest == POLICY_DIGEST
    assert "policy_digest" not in run.__dataclass_fields__
