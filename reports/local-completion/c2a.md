# C2A action checkpoint

The shared campaign driver now executes a selected retained method through the existing bounded child and broker. It checks family and source digest, refuses unavailable methods without constructing a replacement, and conservatively consumes the query allowance when failed execution leaves actual usage unknown. Successful use does not acquire or retain a duplicate method.

Operational feedback now creates a durable policy revision proposal, constructs `entry=STEP` bytes through the existing broker constructor, and freezes those bytes with parent lineage. Missing feedback refuses durably. A constructed policy remains `assessment_status=pending`; it is not inserted into the method repertoire or promoted. Connecting sealed policy assessment, policy binding and subsequent policy execution is the next architectural milestone, not a completed part of this checkpoint.

## Observed verification

The first three public-path tests failed before implementation: retained use called construction twice, an unknown method triggered construction, and a revision request silently stopped. After implementation, `tests/test_s09c2a_actions.py` gives **5 passed in 10.44s** on WSL Ubuntu, PostgreSQL 18.6, Python 3.14 and real child processes. The provider is a recording double. The five cases cover retained use, failure query accounting, unavailable use, feedback refusal, and proposal/construction/freeze without premature release.

Run from this checkout in WSL with its absolute root and `src` on `PYTHONPATH`:

```sh
/home/ubuntu/.venvs/as9/bin/python -m pytest tests/test_s09c2a_actions.py -q -p no:cacheprovider
```

The fixture creates and removes only `s09_local_actions`. `actions-red.log` and `actions-checkpoint.log` preserve observed output. An earlier combined adjacent-test run was interrupted; its four progress dots do not establish a passing suite. There were no study live inference calls.

Jev reviewed the bounded diff and evidence. It favored connecting policy assessment next, did not support full stage closure, and returned uncertain execution risk (0.53). These are review signals, not verification. The retained-use failure accounting check was added afterward. The next worker must validate the complete public cycle rather than manually supplying missing lifecycle transitions in tests.
