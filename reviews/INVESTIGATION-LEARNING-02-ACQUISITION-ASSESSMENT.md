# Investigation Learning 02: acquisition assessment

Reviewed `e03b78c` from source and committed live records. This is a causal review, not a test rerun or a new live study.

## Blocking finding: retained is reported as bound

`scripts/invl02_live.py` runs the second improvement round under the already active control-derived package, then calls the model and retains its response. It never adopts or executes the model package. `run_e0` and `run_e12` nevertheless turn `acquisition.status == "retained"` into `revision.disposition == "bound"`.

The archived E0 state makes the mismatch concrete: `reports/evidence/invl02-r123/frontier-live.json` has active package digest `26e14402dae6317d5cefca0745328e983ed787972fd32253b79f010baefc860c`; `reports/evidence/invl02-r123/e0-run.json` reports bound digest `2af6f802758e1681a4c7e0714e5b7d8757e9a4080aead4eb64b4526e1e28128`. The latter is only retained. Its improvement `STEP` returns no action. The archived resumed round precedes model construction and uses the active package's digest. Thus E0 proves live model bytes reached retention, not that a model-acquired improvement was bound, inherited or useful.

Correct the disposition at the source of the projection and the completion/roadmap language. A later prospective study may call a revision bound only after the durable active digest equals the model package digest and an independently checked post-restart child invocation cites that same executable digest. A no-op candidate can be rejected honestly; do not force a bind to satisfy the study.

## Blocking finding: authored strategy is labeled acquired

`experiments/ad01/improve_channel.py::leaf_construct` copies executable source from the fixed `_STRATEGY_SOURCE` menu but assigns `origin: "acquired"`. The E0 treatment archive includes that control-derived package. This obscures whether the behavior was model-generated. Preserve the fixed-menu source and system-selected strategy as separate provenance facts. A claim of *model-acquired executable behavior* needs executable bytes traced to a model response, checks, and selection through the durable binding path. Check that authored-source packages cannot be counted as model-written packages under a new name.

## Next bounded experiment

The JSON rerun is an honest incomplete comparison: P0 is available; P1 and P2 are unavailable after their 1024-output-token responses terminate at `length` before valid JSON. Run one frozen output-shaping experiment with concise response instructions and a larger explicit output allowance on the authorized free route; keep parse failures and usage. If usable predictor programs emerge, assess them against P0 under the existing held-out protocol. This Boolean path currently lets the authored `VersionSpaceLearner` choose queries and asks the model for predictors, so even a positive result would establish acquired predictor utility, not autonomous experiment choice or recursive self-improvement.

Stop if the route still cannot emit a valid program within the frozen budget. Report the availability limit; do not manufacture missing arms or turn transport/schema repair into an open-ended prompt search. After the binding and provenance correction, run a separate inherited-improver comparison only if an eligible model revision exists.
