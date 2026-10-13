# P07. Executable learner revision

Make the procedure producing future capabilities an inherited object. Depends on [P02](02-MEMORY.md), [P03](03-CONTEXT.md), [P04](04-CAPABILITIES.md) and [P05](05-AGENDA.md). [P06](06-SEARCH-AND-REPLAY.md) can supply additional evidence. The [master plan](MASTER-PLAN.md) owns common rules.

## Learning-policy contract

A versioned learning policy selects development evidence, diagnoses a limitation, proposes an intervention, allocates checks and recommends retention. It runs through bounded child execution and requests permitted effects. It cannot modify accounting, authority or protected assessment.

Its inputs identify starting capabilities, visible experience and allocation. Its outputs identify development decisions and successor artifacts. Begin with an executable policy matching the current development procedure. Instructions remain editable data, but the policy also controls real evidence selection and construction decisions.

Revision may affect diagnosis, construction strategy, repair allocation, applicability testing or consolidation. Change one consequential decision family first so the effect can be interpreted. Inheritance means a later learning round loads and executes the new learner version.

Assess mechanism and effectiveness separately. A learner's task-solving score is not its successor-production score. Compare learner variants from common initial capabilities and experience, with equivalent available models and full construction costs. Preserve task and lineage independence in the assessment.

## Delivery slices

1. **P07-1. Expose the existing development decisions.** Implement the seed learner through the explicit policy interface. Route construction and checking to P04 without another lifecycle owner.
2. **P07-2. Revise and inherit.** Use prior development evidence to construct a changed learner. Load it in a fresh later round and capture its actual decisions and successor artifacts.
3. **P07-3. Compare descendants.** Run seed and revised learners from common starting points, then assess their successors on later tasks. Include acquisition costs and unavailable outcomes.

## Acceptance scenarios

- **P07-A.** A changed learner selects a different diagnostic or construction action, and that action actually executes.
- **P07-B.** Restart before the next development round. The intended learner digest governs that round rather than a default implementation.
- **P07-C.** Substitute a learner with unchanged behavior. The system cannot claim improvement merely because its bytes differ.
- **P07-D.** A learner proposes modifying protected assessment or spending authority. The proposal cannot acquire that authority.
- **P07-E.** The learner produces a strong direct solution but no useful successor. Report task success separately from learner benefit.

Use a live learner-revision and successor-generation path for inheritance evidence. Continue comparison across several development rounds for effectiveness. A null descendant comparison is a valid outcome and does not erase the inheritance result.

## Working checkpoint

The system can develop a learner version and use it to develop a later capability. This is bounded structural recursion. Effective recursive improvement remains an empirical claim. Do not add unbounded nested meta-agents or let the learner replace its own final judge. See the older [learner design](../design/LEARNER-REVISION.md) for additional hypotheses.
