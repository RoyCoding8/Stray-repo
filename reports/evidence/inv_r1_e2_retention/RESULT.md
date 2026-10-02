# E2, contrast three: retained policy versus cold reacquisition

The handoff's third E2 contrast: *"Retained policy versus a cold
reacquisition control, accounting for construction and use costs separately
and together over a declared number of uses."*

`acquisition_cost_arms` existed and was tested, but like the other
constructors it had never been run to produce a number.

## The contrast

Both arms spend the same on **use**. The only difference is whether the
construction is paid again.

- `retained` — the capability is kept; 0 construction dispatches.
- `cold` — the capability is rebuilt before the use sequence; 1
  construction dispatch.

Declared uses: **5**. Unit price: **3269** reservation units per dispatch,
read from the cap sheet's `unit_allowance.per_request`, not a constant —
the old per-dispatch constant was measured from a 33-character smoke
request while a real construction call is 4880 characters and 2048 output
tokens, so every cost figure built on it understated the headroom a run
needs.

## Result

| arm | construction | use | total units | per use |
|---|---|---|---|---|
| retained | 0 dispatches (0 units) | 5 (16345) | **16345** | 3269.0 |
| cold | 1 dispatch (3269) | 5 (16345) | **19614** | 3922.8 |

**Crossover: 5 uses.** Retention pays for itself exactly at the declared
horizon and not before it: at 4 uses the cold arm is still cheaper, at 5
they are equal in total, and beyond 5 retention is strictly cheaper.

## What this is and is not

It is a **cost** result, and a clean one — the two arms are separated in
only the construction dispatch and the unit price is derived from the real
cap sheet. It answers the handoff's question about how construction and use
costs relate.

It is **not** a claim that retention improves quality. This contrast prices
retention; it does not measure whether the retained policy performs better
than a freshly built one, which is the third bullet's other half and would
need both arms run to a score. The crossover of 5 is also specific to this
budget: it is where one construction call's price equals the per-use price
divided by the number of uses, so a different `model_calls` allowance or a
different use count moves it arithmetically.

Evidence: `costs.json`.
