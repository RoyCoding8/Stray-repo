"""M3 finite Boolean-rule discovery instrument.

Four input bits, four output bits. Each output bit comes from the public
restricted hypothesis class: an affine expression over the four inputs,
optionally XORed with one pairwise input product. Deduplicated by sixteen
bit truth table. A hidden target selects four such functions. The learner
may ask at most eight queries, then commits an executable predictor built
only from legal class members. Private scoring covers all sixteen inputs
with queried and unqueried subsets reported separately.

Views exposed to the learner (public, model input, child) carry only the
task identity, the hypothesis class descriptor, the observed query pairs
and the remaining budget. Target tables and unqueried outputs never enter
them. Deterministic, no network, no database.
"""

from __future__ import annotations

import hashlib
import hmac
import random

N_INPUTS = 4
N_OUTPUTS = 4
N_STATES = 16
MAX_QUERIES = 8
SPLITS = ("dev", "qual", "audit")
INSTRUMENT_ID = "boolean-rule-v1"

PAIRS = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
NO_PAIR = -1


class RuleRefused(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _parity(word: int) -> int:
    return bin(word).count("1") & 1


def eval_spec(const: int, mask: int, pair: int, x: int) -> int:
    bit = const ^ _parity(mask & x)
    if pair != NO_PAIR:
        i, j = PAIRS[pair]
        bit ^= ((x >> i) & 1) & ((x >> j) & 1)
    return bit


def spec_table(const: int, mask: int, pair: int) -> int:
    table = 0
    for x in range(N_STATES):
        table |= eval_spec(const, mask, pair, x) << x
    return table


def _build_class() -> tuple:
    seen: dict = {}
    for const in (0, 1):
        for mask in range(16):
            for pair in (NO_PAIR, 0, 1, 2, 3, 4, 5):
                table = spec_table(const, mask, pair)
                if table not in seen:
                    pair_repr = None if pair == NO_PAIR else list(PAIRS[pair])
                    seen[table] = {"const": const, "mask": mask,
                                   "pair": pair_repr}
    return tuple(sorted(seen)), seen


CLASS_TABLES, _TABLE_TO_SPEC = _build_class()
CLASS_INDEX = {table: pos for pos, table in enumerate(CLASS_TABLES)}


def class_digest() -> str:
    raw = ",".join(str(t) for t in CLASS_TABLES).encode()
    return hashlib.sha256(raw).hexdigest()[:12]


def spec_for_table(table: int) -> dict:
    return dict(_TABLE_TO_SPEC[table])


def _validate_spec(spec: object) -> int:
    if not isinstance(spec, dict):
        raise RuleRefused("illegal-hypothesis")
    const, mask, pair = spec.get("const"), spec.get("mask"), spec.get("pair")
    if const not in (0, 1) or not isinstance(mask, int):
        raise RuleRefused("illegal-hypothesis")
    if not 0 <= mask <= 15:
        raise RuleRefused("illegal-hypothesis")
    if pair is None:
        pair_idx = NO_PAIR
    elif (isinstance(pair, (list, tuple)) and len(pair) == 2
            and tuple(pair) in PAIRS):
        pair_idx = PAIRS.index(tuple(pair))
    else:
        raise RuleRefused("illegal-hypothesis")
    table = spec_table(const, mask, pair_idx)
    if table not in CLASS_INDEX:
        raise RuleRefused("illegal-hypothesis")
    return table


def execute_predictor(predictor: dict, x: int) -> tuple:
    if not isinstance(x, int) or not 0 <= x < N_STATES:
        raise RuleRefused("illegal-input")
    specs = predictor.get("specs") if isinstance(predictor, dict) else None
    if (not isinstance(specs, (list, tuple)) or len(specs) != N_OUTPUTS):
        raise RuleRefused("illegal-hypothesis")
    tables = [_validate_spec(spec) for spec in specs]
    return tuple((table >> x) & 1 for table in tables)


def execute_all(predictor: dict) -> tuple:
    return tuple(execute_predictor(predictor, x) for x in range(N_STATES))


def _check_split(split: str) -> None:
    if split not in SPLITS:
        raise RuleRefused("unknown-split")


# Bound from frozen world state rather than hardcoded here, so the two
# instruments cannot drift apart and the key has one home. Read at call
# time so a caller that swaps it (the tests do) sees the swap.
from experiments.ad01 import worlds as _worlds  # noqa: E402
_ID_KEY = _worlds.TASK_ID_KEY


def key_id(key: str) -> str:
    """A task id suffix a policy holding only the view cannot invert.

    N-01 made this a plain sha256 of `(instrument, split, seed)`, which
    stopped the id naming the seed but not a policy recovering it: the
    digest is unsalted over a 0..9999 seed space, so enumerating the
    space reproduces any id. Measured in `make_task("dev", 4)`: the id
    comes back at seed 4 after a thousand hashes.

    The HMAC key is frozen world state (`worlds.TASK_ID_KEY`) rather than
    a per-campaign secret, because `offline_recompute` re-derives ids in
    another process to verify frozen evidence. It lives in the repository
    and is therefore not a secret from an adversary who reads the source;
    what it prevents is a policy that holds the view alone from inverting
    the id.
    """
    return hmac.new(_ID_KEY, key.encode(), hashlib.sha256).hexdigest()[:12]


def make_task(split: str, seed: int) -> dict:
    _check_split(split)
    if not isinstance(seed, int) or seed < 0:
        raise RuleRefused("illegal-seed")
    key = "%s/%s/%d" % (INSTRUMENT_ID, split, seed)
    rng = random.Random(int(hashlib.sha256(key.encode()).hexdigest(), 16))
    tables = tuple(rng.sample(CLASS_TABLES, N_OUTPUTS))
    # `rule-dev-0004` names the seed, and the seed is the recipe. A policy
    # reading the public id regenerates the hidden tables and scores full
    # marks unqueried. The seed stays on the task for the grader alone.
    return {"task_id": "rule-%s-%s" % (split, key_id(key)), "split": split,
            "seed": seed, "tables": tables,
            "instrument": INSTRUMENT_ID}


def task_signature(task: dict) -> tuple:
    return tuple(task["tables"])


def find_cross_split_duplicates(split_tasks: dict) -> list:
    seen: dict = {}
    problems = []
    for split in sorted(split_tasks):
        for task in split_tasks[split]:
            signature = task_signature(task)
            if signature in seen:
                problems.append("duplicate-truth-table %s %s" % (
                    seen[signature], task["task_id"]))
            else:
                seen[signature] = task["task_id"]
    return problems


def instrument_spec(split: str) -> dict:
    _check_split(split)
    return {"instrument": INSTRUMENT_ID, "n_inputs": N_INPUTS,
            "n_outputs": N_OUTPUTS, "max_queries": MAX_QUERIES,
            "class_digest": class_digest(), "class_size": len(CLASS_TABLES),
            "form": ("affine over four inputs, optionally XORed with "
                     "one pairwise input product")}


PUBLIC_VIEW_KEYS = frozenset({
    "instrument", "task_id", "split", "max_queries", "remaining",
    "observed", "hypothesis_class", "instruction", "committed"})


class RuleSession:
    def __init__(self, task: dict):
        self._task = task
        self._queried: dict = {}
        self._committed = None

    @property
    def queried(self) -> dict:
        return dict(self._queried)

    @property
    def remaining(self) -> int:
        return MAX_QUERIES - len(self._queried)

    def query(self, x: int) -> tuple:
        if not isinstance(x, int) or not 0 <= x < N_STATES:
            raise RuleRefused("illegal-input")
        if x in self._queried:
            return self._queried[x]
        if len(self._queried) >= MAX_QUERIES:
            raise RuleRefused("query-budget-exhausted")
        tables = self._task["tables"]
        y = tuple((table >> x) & 1 for table in tables)
        self._queried[x] = y
        return y

    def _observed(self) -> list:
        return [{"x": x, "y": list(self._queried[x])}
                for x in sorted(self._queried)]

    def _class_descriptor(self) -> dict:
        return {"form": instrument_spec(
            self._task["split"])["form"],
            "n_inputs": N_INPUTS, "n_outputs": N_OUTPUTS,
            "class_digest": class_digest(),
            "class_size": len(CLASS_TABLES)}

    def public_view(self) -> dict:
        return {"instrument": INSTRUMENT_ID,
                "task_id": self._task["task_id"],
                "split": self._task["split"],
                "max_queries": MAX_QUERIES, "remaining": self.remaining,
                "observed": self._observed(),
                "hypothesis_class": self._class_descriptor()}

    def model_input(self) -> dict:
        view = self.public_view()
        view["instruction"] = (
            "Choose an unqueried four-bit input to probe, or commit an "
            "executable predictor built only from the public hypothesis "
            "class. At most %d queries." % MAX_QUERIES)
        return view

    def output_model_input(self) -> dict:
        """The same public fields, with an instruction that matches the reply.

        `model_input` tells the reader it may probe *or* commit. The output
        study embeds this view in a prompt whose only legal reply is the
        commit, so the probe half is an instruction the reader can follow
        and cannot: by the time the prompt is rendered the session has spent
        all eight queries and `remaining` is 0. Asked to choose between
        probe and commit with nothing left to probe, the model narrated its
        reasoning instead of emitting the JSON, and every one of the eight
        dispatches was rejected `too-long` against a 512-character cap.

        The fields stay identical so the prompt still describes the same
        task, and so the frozen digest check still has a single shape to
        compare. Only the instruction changes.
        """
        view = self.public_view()
        view["instruction"] = (
            "Commit one executable predictor built only from the public "
            "hypothesis class. The query budget is spent; no further probes "
            "are available.")
        return view

    def child_view(self) -> dict:
        view = self.public_view()
        view["committed"] = self._committed is not None
        return view

    def commit_predictor(self, predictor: dict) -> dict:
        specs = predictor.get("specs") if isinstance(predictor, dict) else None
        if (not isinstance(specs, (list, tuple))
                or len(specs) != N_OUTPUTS):
            raise RuleRefused("illegal-hypothesis")
        tables = tuple(_validate_spec(spec) for spec in specs)
        committed = {"specs": tuple(dict(s) for s in specs),
                     "tables": tables}
        self._committed = committed
        return committed

    def score(self, predictor: dict) -> dict:
        if predictor != self._committed:
            raise RuleRefused("prediction-not-committed")
        tables = self._task["tables"]
        pred = self._committed["tables"]
        hits = [all(((pred[b] >> x) & 1) == ((tables[b] >> x) & 1)
                    for b in range(N_OUTPUTS))
                for x in range(N_STATES)]
        queried_hits = [hits[x] for x in self._queried]
        unqueried_hits = [hits[x] for x in range(N_STATES)
                          if x not in self._queried]
        n_queried = len(self._queried)
        n_unqueried = N_STATES - n_queried
        return {
            "overall": sum(hits) / N_STATES,
            "queried": (sum(queried_hits) / n_queried if n_queried else 0.0),
            "unqueried": (sum(unqueried_hits) / n_unqueried
                          if n_unqueried else 0.0),
            "n_queried": n_queried}
