"""Verifiers a store can reach, for proofs it is otherwise unable to check.

A never-sent proof returns held units to free allocation, and the fields a
caller can read off the operation row are enough to spell one: the subject is
the operation id, the generation is in the payload, and for the bundled
launcher the provenance is the public class constant. ``store._never_sent_proof``
holding a proof to the operation's own launcher narrows the forgery but does not
exclude it, because that launcher id is a name rather than a secret.

What excludes it is a capability the caller cannot derive. ``LocalLauncher``
mints one per dispatch from a secret drawn at construction and never written
anywhere durable, so a proof carrying a valid capability could only have come
from asking that launcher. The store cannot check that on its own: it holds no
secret, and holding one would make the capability forgeable by anything that
can read the store.

So the launcher installs its verifier here at construction, and the store looks
it up by the id the operation was admitted to. The store ends up holding a
reference to an authority rather than a string that names one.

Several launchers can share one id in a process: the id is a class constant,
and a test that builds a launcher per run directory builds several. So an id
accumulates verifiers rather than keeping the first, and a capability is
accepted when any of them vouches for it. That stays sound, because each holds
a secret drawn at its own construction: a capability the caller wrote is
compared against every one of them and matches none.

Registration is what a launcher does by existing, and it is per-process. A
launcher that never registers cannot be held to a capability, and its proofs
stay attribution-only. That is the honest limit of the guarantee: it binds every
launcher that can attest, and a deployment that substitutes its own launcher can
substitute one that declines to. Substituting code is a different threat from
supplying a payload, and closing that one is not this layer's job.
"""

from __future__ import annotations

from typing import Any, Callable

Verifier = Callable[[str, int, str], bool]

_VERIFIERS: dict[str, list[Verifier]] = {}


def register(launcher_id: str, verify: Verifier) -> None:
    """Let a store reach ``launcher_id``'s capability check."""
    key = str(launcher_id or "")
    if not key:
        raise ValueError("a verifier needs a launcher id to be reachable by")
    if not callable(verify):
        raise TypeError("verifier for %r is not callable" % (key,))
    held = _VERIFIERS.setdefault(key, [])
    if verify not in held:
        held.append(verify)


def verifier_for(launcher_id: str | None) -> list[Verifier]:
    """Every check registered for this launcher id."""
    if not launcher_id:
        return []
    return list(_VERIFIERS.get(str(launcher_id), ()))


def attests(launcher_id: str | None) -> bool:
    """Whether this launcher can be held to a capability at all.

    The store needs this before it makes a capability mandatory, because
    requiring one nothing can mint would strand every operation the launcher
    owns. Refusing to hold a proof is different from being unable to check one.
    """
    return bool(verifier_for(launcher_id))


def _reset_for_tests() -> None:
    _VERIFIERS.clear()


def check(launcher_id: str | None, operation_id: str,
          generation: int, capability: Any) -> bool:
    """Whether a launcher of this id minted this exact capability."""
    for verify in verifier_for(launcher_id):
        try:
            if verify(operation_id, int(generation), capability):
                return True
        except Exception:
            continue
    return False
