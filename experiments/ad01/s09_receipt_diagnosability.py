"""Show which causal hypotheses a model-inference receipt can separate.

Two very different things leave the same trace. A request the gateway
refused before it ever left the client, and a request that was dispatched
and whose response was lost in flight, both settle as `outcome: "unknown"`
with entirely null usage. The persisted receipt cannot tell them apart, so
a study whose gateway refused everything reads as a study whose responses
all vanished, and neither reading is a capability result.

This module makes that statement computable rather than asserted. A
hypothesis is a member of an enum, a channel is a member of an enum, and
every hypothesis declares which values of which channels it is able to
produce. Two hypotheses are separated by a channel when their admissible
values are disjoint, and a set of channels is diagnostic for a pair when
at least one of them separates it. Everything reported here is derived
that way, from the committed bytes of an evidence bundle.

The table is a model of what the receipt system emits, not a wish list.
`OUTCOME` admits both `unknown` and `failure` for a pre-dispatch refusal
because both were emitted: the broker at 7e87d73 wrote `unknown` for every
non-`ModelResponse`, and the broker at HEAD writes `failure` for a route
refusal. A field whose value moves between those two across the system's
own history separates nothing, and the table says so.

The proposed shape at the bottom is a design, not an implementation. It is
data. Nothing in `src/settlement/` is modified by this module.
"""

from __future__ import annotations

import json
from enum import Enum
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REPO = Path(__file__).resolve().parents[2]

MODEL_EFFECT = "model-inference"
UNKNOWN = "UNKNOWN"

REFUSAL = "pre-dispatch-refusal"
LOST = "dispatched-response-lost"

# The exporter projects the durable receipt onto these four keys and drops
# the rest of the row, including the content that carries the distinction.
EXPORTED_RECEIPT_KEYS = ("operation_id", "outcome", "receipt_identity", "usage")

# An unconstrained channel admits every observation. The receipt identity
# is one: nothing in the export contract ties a suffix to a cause, so two
# hypotheses that differ only in suffix are not separated by it.
ANY = object()


class Hypothesis(str, Enum):
    PRE_DISPATCH_REFUSAL = REFUSAL
    DISPATCHED_RESPONSE_LOST = LOST
    PROVIDER_FAILURE_OBSERVED = "provider-failure-observed"
    RESPONSE_RECEIVED = "response-received"


class Channel(str, Enum):
    OUTCOME = "outcome"
    USAGE_OBSERVED = "usage_observed"
    RECEIPT_IDENTITY = "receipt_identity"
    DISPATCH_ATTEMPTED = "dispatch_attempted"
    RESPONSE_RECEIVED = "response_received"
    RESPONSE_DIGEST = "response_digest"
    RESPONSE_STATUS = "response_status"
    ERROR_CLASS = "error_class"
    SETTLE_WINDOW = "settle_window"


PREDICTIONS: Mapping[Hypothesis, Mapping[Channel, Any]] = {
    Hypothesis.PRE_DISPATCH_REFUSAL: {
        Channel.OUTCOME: frozenset({"unknown", "failure"}),
        Channel.USAGE_OBSERVED: frozenset({False}),
        Channel.RECEIPT_IDENTITY: ANY,
        Channel.DISPATCH_ATTEMPTED: frozenset({False}),
        Channel.RESPONSE_RECEIVED: frozenset({False}),
        Channel.RESPONSE_DIGEST: frozenset({None}),
        Channel.RESPONSE_STATUS: frozenset({None}),
        Channel.ERROR_CLASS: frozenset({"route"}),
        Channel.SETTLE_WINDOW: frozenset({None}),
    },
    Hypothesis.DISPATCHED_RESPONSE_LOST: {
        Channel.OUTCOME: frozenset({"unknown"}),
        Channel.USAGE_OBSERVED: frozenset({False}),
        Channel.RECEIPT_IDENTITY: ANY,
        Channel.DISPATCH_ATTEMPTED: frozenset({True}),
        Channel.RESPONSE_RECEIVED: frozenset({False}),
        Channel.RESPONSE_DIGEST: frozenset({None}),
        Channel.RESPONSE_STATUS: frozenset({None}),
        Channel.ERROR_CLASS: frozenset(
            {"transport", "timeout", "protocol", "billing_unknown", "cancelled"}),
        Channel.SETTLE_WINDOW: frozenset({"open"}),
    },
    Hypothesis.PROVIDER_FAILURE_OBSERVED: {
        Channel.OUTCOME: frozenset({"unknown", "failure"}),
        Channel.USAGE_OBSERVED: frozenset({False, True}),
        Channel.RECEIPT_IDENTITY: ANY,
        Channel.DISPATCH_ATTEMPTED: frozenset({True}),
        Channel.RESPONSE_RECEIVED: frozenset({True}),
        Channel.RESPONSE_DIGEST: frozenset({"present"}),
        Channel.RESPONSE_STATUS: frozenset({401, 403, 429, 500, 503}),
        Channel.ERROR_CLASS: frozenset({"auth", "rate_limit", "provider_status"}),
        Channel.SETTLE_WINDOW: frozenset({"closed"}),
    },
    Hypothesis.RESPONSE_RECEIVED: {
        Channel.OUTCOME: frozenset({"success"}),
        Channel.USAGE_OBSERVED: frozenset({True}),
        Channel.RECEIPT_IDENTITY: ANY,
        Channel.DISPATCH_ATTEMPTED: frozenset({True}),
        Channel.RESPONSE_RECEIVED: frozenset({True}),
        Channel.RESPONSE_DIGEST: frozenset({"present"}),
        Channel.RESPONSE_STATUS: frozenset({200}),
        Channel.ERROR_CLASS: frozenset({None}),
        Channel.SETTLE_WINDOW: frozenset({"closed"}),
    },
}

FIELD_EVIDENCE: Mapping[Channel, str] = {
    Channel.OUTCOME: "src/settlement/broker.py#L721 and L791",
    Channel.USAGE_OBSERVED: "src/settlement/broker.py#L536",
    Channel.RECEIPT_IDENTITY: "scripts/s09_pilot.py#L680",
    Channel.DISPATCH_ATTEMPTED: "src/settlement/broker.py#L169",
    Channel.RESPONSE_RECEIVED: "src/settlement/broker.py#L562",
    Channel.RESPONSE_DIGEST: "src/settlement/gateway_http.py#L58",
    Channel.RESPONSE_STATUS: "src/settlement/gateway_http.py#L45",
    Channel.ERROR_CLASS: "src/settlement/gateway.py#L19",
    Channel.SETTLE_WINDOW: "src/settlement/store.py#L1412",
}

_ALL_HYPOTHESES = tuple(Hypothesis)
_ALL_CHANNELS = tuple(Channel)
ALL_PAIRS = tuple(
    (a, b) for i, a in enumerate(_ALL_HYPOTHESES) for b in _ALL_HYPOTHESES[i + 1:])


class BundleMissing(Exception):
    """Raised when an evidence directory carries no operations map."""


def _pointer(operation_id: str, index: int, *rest: str) -> str:
    tail = "".join("/%s" % part for part in rest)
    return "/%s/receipts/%d%s" % (operation_id, index, tail)


def _admissible(predicted: Any, observed: Any) -> bool:
    if predicted is ANY:
        return True
    return observed in predicted


def separates(channel: Channel, left: Hypothesis, right: Hypothesis) -> bool:
    """Whether `channel` gives the two hypotheses disjoint values."""
    a = PREDICTIONS[left][channel]
    b = PREDICTIONS[right][channel]
    if a is ANY or b is ANY:
        return False
    return a.isdisjoint(b)


def separated_pairs(channels: Iterable[Channel]) -> frozenset:
    """Every pair some channel in `channels` tells apart."""
    return frozenset(
        pair for pair in ALL_PAIRS
        if any(separates(c, pair[0], pair[1]) for c in channels))


def _label(pair) -> str:
    return "%s vs %s" % (pair[0].value, pair[1].value)


def minimal_separator(pair, channels: Iterable[Channel]) -> list:
    """Smallest subset of `channels` that separates `pair`, by search.

    Returned in Channel order so the answer is a fact about the table
    rather than an artefact of set iteration.
    """
    pool = [c for c in _ALL_CHANNELS if c in set(channels)]
    for size in range(1, len(pool) + 1):
        for subset in combinations(pool, size):
            if all(separates(c, pair[0], pair[1]) for c in subset):
                return list(subset)
    return []


def minimal_full_separator(channels: Iterable[Channel]) -> list:
    """Smallest subset of `channels` separating every pair."""
    pool = [c for c in _ALL_CHANNELS if c in set(channels)]
    for size in range(1, len(pool) + 1):
        for subset in combinations(pool, size):
            if all(separates(c, a, b) for c in subset for a, b in ALL_PAIRS):
                return list(subset)
    return []


def _present(receipt: Mapping[str, Any]) -> bool:
    return "usage" in receipt


def _observed_usage(receipt: Mapping[str, Any]) -> Any:
    usage = receipt.get("usage")
    if not isinstance(usage, Mapping):
        return None
    return any(value is not None for value in usage.values())


def _window(receipt: Mapping[str, Any]) -> Any:
    if receipt.get("received_at"):
        return "closed"
    return "open" if receipt.get("attempted_at") else None


def _has_window(receipt: Mapping[str, Any]) -> bool:
    return "attempted_at" in receipt or "received_at" in receipt


def _plain(key: str):
    return lambda receipt: receipt.get(key)


def _has(key: str):
    return lambda receipt: key in receipt


def _digest(receipt: Mapping[str, Any]) -> Any:
    return "present" if receipt.get("response_digest") else None


# One place decides how a channel is read off a receipt. Without it the
# same five special cases would have to be kept in step across two
# functions, and a channel that gained a rule in one would be read
# differently by the other.
CHANNEL_READERS = {
    Channel.OUTCOME: (_has("outcome"), _plain("outcome")),
    Channel.USAGE_OBSERVED: (_present, _observed_usage),
    Channel.RECEIPT_IDENTITY: (_has("receipt_identity"),
                               _plain("receipt_identity")),
    Channel.RESPONSE_DIGEST: (_has("response_digest"), _digest),
    Channel.SETTLE_WINDOW: (_has_window, _window),
    Channel.DISPATCH_ATTEMPTED: (_has("dispatch_attempted"),
                                 _plain("dispatch_attempted")),
    Channel.RESPONSE_RECEIVED: (_has("response_received"),
                                _plain("response_received")),
    Channel.RESPONSE_STATUS: (_has("response_status"),
                              _plain("response_status")),
    Channel.ERROR_CLASS: (_has("error_class"), _plain("error_class")),
}


def _carries(receipt: Mapping[str, Any], channel: Channel) -> bool:
    return CHANNEL_READERS[channel][0](receipt)


def observe(receipt: Mapping[str, Any], channel: Channel) -> Any:
    return CHANNEL_READERS[channel][1](receipt)


def available_channels(receipts: Sequence[Mapping[str, Any]]) -> tuple:
    """The channels these bytes actually carry, derived not declared."""
    return tuple(c for c in _ALL_CHANNELS
                 if any(_carries(r, c) for r in receipts))


def live_hypotheses(receipt: Mapping[str, Any],
                    channels: Iterable[Channel]) -> tuple:
    """Hypotheses this receipt's observed values do not rule out."""
    return tuple(
        h for h in _ALL_HYPOTHESES
        if all(_admissible(PREDICTIONS[h][c], observe(receipt, c))
               for c in channels))


def load_receipts(bundle) -> list:
    """Model-inference receipts from an evidence directory or a raw map."""
    if isinstance(bundle, Mapping):
        operations = bundle
    else:
        path = Path(bundle)
        target = path if path.is_dir() else path.parent
        operations_file = target / "operations.json"
        if not operations_file.exists():
            raise BundleMissing("no operations.json under %s" % target)
        operations = json.loads(operations_file.read_text())
    if not isinstance(operations, Mapping):
        raise BundleMissing("operations map is not an object")
    rows = []
    for operation_id in sorted(operations):
        record = operations[operation_id]
        if not isinstance(record, Mapping):
            continue
        if record.get("effect") != MODEL_EFFECT:
            continue
        for index, receipt in enumerate(record.get("receipts") or []):
            if isinstance(receipt, Mapping):
                rows.append((operation_id, index, receipt))
    return rows


def bundle_name(bundle) -> str:
    path = Path(bundle) if not isinstance(bundle, Mapping) else Path(".")
    target = path if path.is_dir() else path.parent
    return target.name


def current_diagnosability(evidence_dir) -> dict:
    """Per receipt, which hypotheses the persisted evidence leaves live."""
    rows = load_receipts(evidence_dir)
    if not rows:
        raise BundleMissing("no model-inference receipts in %s"
                            % evidence_dir)
    channels = available_channels([r for _, _, r in rows])
    per_receipt = []
    for operation_id, index, receipt in rows:
        live = live_hypotheses(receipt, channels)
        per_receipt.append({
            "operation_id": operation_id,
            "outcome": receipt.get("outcome"),
            "usage_observed": observe(receipt, Channel.USAGE_OBSERVED),
            "identity_suffix": _suffix(str(receipt.get("receipt_identity", "")),
                                       operation_id),
            "live_hypotheses": [h.value for h in live],
            "evidence": "%s#%s" % (bundle_name(evidence_dir),
                                   _pointer(operation_id, index, "outcome")),
        })
    conflicted = [r for r in per_receipt
                  if REFUSAL in r["live_hypotheses"]
                  and LOST in r["live_hypotheses"]]
    return {
        "bundle": bundle_name(evidence_dir),
        "receipt_count": len(per_receipt),
        "channels_available": [c.value for c in channels],
        "channels_missing": [c.value for c in _ALL_CHANNELS
                             if c not in channels],
        "receipt_fields": sorted({key for _, _, r in rows for key in r}),
        "unseparated_pairs": [
            _label(p) for p in ALL_PAIRS if p not in separated_pairs(channels)],
        "refusal_lost_separated":
            _separated(channels, Hypothesis.PRE_DISPATCH_REFUSAL,
                       Hypothesis.DISPATCHED_RESPONSE_LOST),
        "receipts_leaving_both_live": len(conflicted),
        "receipts": per_receipt,
    }


def _suffix(identity: str, operation_id: str) -> str:
    prefix = "gw:%s:" % operation_id
    return identity[len(prefix):] if identity.startswith(prefix) else UNKNOWN


def _separated(channels: Iterable[Channel], left: Hypothesis,
               right: Hypothesis) -> bool:
    return any(separates(c, left, right) for c in channels)


def distinguishability_report(bundle) -> dict:
    """Can this bundle tell a pre-dispatch refusal from a lost response?

    The verdict is about the schema, so it is computed from the channels
    the bytes carry rather than from any particular receipt's values. A
    bundle that happens not to contain a conflicting receipt is still
    unable to resolve one, and the report says both things.
    """
    rows = load_receipts(bundle)
    channels = available_channels([r for _, _, r in rows])
    pair = (Hypothesis.PRE_DISPATCH_REFUSAL,
            Hypothesis.DISPATCHED_RESPONSE_LOST)
    witnesses = [c for c in channels if separates(c, pair[0], pair[1])]
    non_success = [(op, i, r) for op, i, r in rows
                   if r.get("outcome") != "success"]
    both_live = [op for op, i, r in non_success
                 if {h.value for h in live_hypotheses(r, channels)}
                 >= {REFUSAL, LOST}]
    return {
        "bundle": bundle_name(bundle),
        "distinguishable": bool(witnesses),
        "verdict": "DISTINGUISHABLE" if witnesses else "INDISTINGUISHABLE",
        "pair": _label(pair),
        "separating_channels": [c.value for c in witnesses],
        "channels_available": [c.value for c in channels],
        "receipt_count": len(rows),
        "non_success_receipts": len(non_success),
        "receipts_leaving_both_live": len(both_live),
        "live_on_both_live_receipts": sorted(both_live),
        "evidence": ("%s#/operations.json" % bundle_name(bundle)
                     if not isinstance(bundle, Mapping) else UNKNOWN),
    }


def required_fields() -> dict:
    """The fields that would separate the pairs, and which each one serves.

    Every field carries the pairs it separates, computed from the table,
    and a field that separates nothing is not recommended. The minimum is
    a search result, not a preference.
    """
    pair = (Hypothesis.PRE_DISPATCH_REFUSAL,
            Hypothesis.DISPATCHED_RESPONSE_LOST)
    suffix = identity_is_informative(BUNDLES["opus"])
    rows = []
    for channel in _ALL_CHANNELS:
        pairs = sorted(_label(p) for p in ALL_PAIRS
                       if separates(channel, p[0], p[1]))
        row = {
            "field": channel.value,
            "separates": pairs,
            "justified": bool(pairs),
            "recommended": bool(pairs),
            "evidence": FIELD_EVIDENCE[channel],
        }
        if channel is Channel.RECEIPT_IDENTITY:
            row["justified"] = suffix["suffix_varies_within_pooled_set"]
            row["recommended"] = row["justified"]
            row["refuted_by"] = suffix["pooled_by_suffix"]
        rows.append(row)
    justified = [row for row in rows if row["justified"]]
    return {
        "pair": _label(pair),
        "fields": rows,
        "justified_fields": [row["field"] for row in justified],
        "unjustified_fields": [row["field"] for row in rows
                               if not row["justified"]],
        "minimal_for_pair": [c.value for c in minimal_separator(pair,
                                                                _ALL_CHANNELS)],
        "minimal_for_all_pairs": [c.value for c in minimal_full_separator(
            _ALL_CHANNELS)],
    }


def proposed_receipt_shape() -> dict:
    """A receipt shape that makes the answer yes. A design, not a port.

    `dispatch_attempted` is the load-bearing field: it is the only channel
    that separates a pre-dispatch refusal from a lost response on its own,
    and it is the one the two receipts can differ on while every exported
    field stays byte-identical.
    """
    pair = (Hypothesis.PRE_DISPATCH_REFUSAL,
            Hypothesis.DISPATCHED_RESPONSE_LOST)
    return {
        "kind": "design-only",
        "installs_into_src_settlement": False,
        "load_bearing": [c.value for c in minimal_separator(pair,
                                                           _ALL_CHANNELS)],
        "fields": [
            {"name": "operation_id", "type": "str", "required": True,
             "invariant": "names the operation this receipt settles"},
            {"name": "outcome", "type": "str", "required": True,
             "invariant": "one of success, failure, unknown"},
            {"name": "dispatch_attempted", "type": "bool", "required": True,
             "invariant": "false when the request never left the client",
             "separates": [_label(pair)]},
            {"name": "response_received", "type": "bool", "required": True,
             "invariant": "true only when response bytes were read",
             "separates": sorted(_label(p) for p in ALL_PAIRS
                                 if separates(Channel.RESPONSE_RECEIVED,
                                              p[0], p[1]))},
            {"name": "response_digest", "type": "str | None", "required": True,
             "invariant": "non-null exactly when response_received",
             "separates": sorted(_label(p) for p in ALL_PAIRS
                                 if separates(Channel.RESPONSE_DIGEST,
                                              p[0], p[1]))},
            {"name": "response_status", "type": "int | None", "required": True,
             "invariant": "the HTTP status, null when no response arrived",
             "separates": sorted(_label(p) for p in ALL_PAIRS
                                 if separates(Channel.RESPONSE_STATUS,
                                              p[0], p[1]))},
            {"name": "error_class", "type": "str | None", "required": True,
             "invariant": "the terminal cause, null on success",
             "separates": sorted(_label(p) for p in ALL_PAIRS
                                 if separates(Channel.ERROR_CLASS,
                                              p[0], p[1]))},
            {"name": "attempted_at", "type": "str | None", "required": True,
             "invariant": "absent when dispatch_attempted is false"},
            {"name": "received_at", "type": "str | None", "required": True,
             "invariant": "present exactly when response_received",
             "separates": sorted(_label(p) for p in ALL_PAIRS
                                 if separates(Channel.SETTLE_WINDOW,
                                              p[0], p[1]))},
            {"name": "usage", "type": "dict", "required": True,
             "invariant": "all null when no usage was measured"},
        ],
        "why": (
            "A pre-dispatch refusal and a lost response agree on outcome, on "
            "null usage, and on the receipt identity the exporter assigns. They "
            "can only be told apart by a field that records whether the "
            "request left the client, which is why the proposed shape leads "
            "with dispatch_attempted and treats the rest as corroboration."),
    }


def identity_is_informative(evidence_dir) -> dict:
    """Whether the identity suffix varies inside the conflated set.

    A suffix could only separate two hypotheses that share every other
    observed value if it were to take different values on such a pair.
    So the question is whether it varies at all among the receipts that
    outcome already pools together, which is computed here rather than
    assumed.
    """
    rows = load_receipts(evidence_dir)
    pooled: dict = {}
    for operation_id, _, receipt in rows:
        if receipt.get("outcome") == "success":
            continue
        pooled.setdefault(_suffix(str(receipt.get("receipt_identity", "")),
                                  operation_id), []).append(operation_id)
    return {
        "bundle": bundle_name(evidence_dir),
        "non_success_receipts": sum(len(v) for v in pooled.values()),
        "distinct_suffixes": sorted(pooled),
        "suffix_varies_within_pooled_set": len(pooled) > 1,
        "pooled_by_suffix": {k: sorted(v) for k, v in sorted(pooled.items())},
        "conclusion": (
            "the suffix is constant across every non-success receipt, so it "
            "partitions the conflated set no further than outcome already "
            "does" if len(pooled) <= 1 else
            "the suffix takes more than one value here"),
    }


def fallback_usage_sentinel(evidence_dir) -> dict:
    """Success receipts whose usage is the recorded adapter's fallback.

    `RecordingGatewayAdapter` answers every unscripted call with a fixed
    `Usage(input_tokens=5, output_tokens=5)`. A bundle whose success
    receipts all carry exactly that pair ran against the recorded adapter,
    whatever its freeze claims. This does not settle which adapter ran; it
    reports the coincidence so a reader does not take it for live usage.
    """
    rows = load_receipts(evidence_dir)
    sentinel, other = [], 0
    for operation_id, index, receipt in rows:
        if receipt.get("outcome") != "success":
            continue
        usage = receipt.get("usage") or {}
        if (usage.get("input_tokens"), usage.get("output_tokens")) == (5, 5):
            sentinel.append(operation_id)
        else:
            other += 1
    return {
        "bundle": bundle_name(evidence_dir),
        "success_receipts": len(sentinel) + other,
        "sentinel_5_5": len(sentinel),
        "other_success_receipts": other,
        "all_success_are_sentinel": bool(sentinel) and other == 0,
        "sentinel_source": "experiments/ad01/learner.py#L56",
        "adapter_conclusion": UNKNOWN,
        "evidence": "%s#/operations.json" % bundle_name(evidence_dir),
    }


BUNDLES = {
    "opus": REPO / "evidence_s09_live_opus",
    "m3": REPO / "evidence_s09_m3_live",
}


def main(argv=None) -> int:
    print(json.dumps({
        "diagnosability": {name: current_diagnosability(path)
                           for name, path in BUNDLES.items()},
        "reports": {name: distinguishability_report(path)
                    for name, path in BUNDLES.items()},
        "required_fields": required_fields(),
        "proposed_receipt_shape": proposed_receipt_shape(),
    }, indent=2, sort_keys=True, default=list))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
