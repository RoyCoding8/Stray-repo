# Settlement: technology decisions

2026-09-09. R6 of this isolated design pass. Implements the obligations of [the conceptual architecture](REFINED-ARCHITECTURE.md) and [selected representations](REPRESENTATION-DESIGN.md). These are target decisions, not changes to the concurrent repository implementation. Primary documentation was checked during this pass; no software was installed or exercised.

## 1. Operating envelope

Select one Linux runtime host, initially a dedicated Linux VM accessible from the user's Windows machine. Put state and artifacts on the guest's native filesystem. The browser is the operator interface. This does not assume that a suitable VM or sandbox already exists on the current machine; provisioning and compatibility are build prerequisites, not facts established by this research.

The initial system has external model inference, finite local CPU/RAM/storage, no model training, and multiple concurrent bounded investigations. It supports generated Python and ordinary Linux command-line tools. Other languages can arrive in versioned execution images. Specialized kernel features, nested container engines, and GPU access are outside the first compatibility envelope.

The declared fault model includes process death, host restart with durable storage intact, lost or delayed network responses, duplicate delivery, expired ownership, and application revision. It excludes a compromised host administrator, exploitable flaws in the trusted stack, and simultaneous loss of all durable copies from its correctness guarantees. Backups address a separately declared recovery point; they do not erase actions performed after that point.

The single host is an intentional availability limit. It may stop when that host stops. Recovery and accounting must be correct when it returns; automatic multi-host failover is not required to demonstrate learning.

## 2. Selected stack

| Layer | Selection | Job and boundary |
|---|---|---|
| Trusted application | Python 3.12, Pydantic 2, asyncio | Typed commands, transition logic, bounded coordination. Generated code never imports into this process. |
| Durable state | PostgreSQL 18, psycopg 3, explicit SQL migrations | Domain records, constraints, resource accounting, journal, admission and work ownership. |
| Durable orchestration | DBOS Python | Recovery of bounded trusted orchestration; domain state remains explicit. |
| Artifact storage | Immutable files on the Linux host with SHA-256 manifests; metadata in PostgreSQL | Programs, images, data, proofs and transcripts; publish and retention protocol in R7. |
| Generated execution | OCI images, Docker Engine with gVisor `runsc`, using `systrap` in the VM | Isolated, resource-constrained worker processes; mediated effects and separate attempt workspaces. |
| Model transport | HTTPX in the trusted broker, talking to the user-supplied gateway | Bounded requests, response/usage attribution, cancellation and error reporting. Provider adaptation stays at the gateway boundary. |
| Retrieval | PostgreSQL full-text search plus dependency traversal; bounded query expansion as a capability | Search across retained material, with provenance and access filtering. |
| Operator interface | FastAPI, Jinja2, HTMX, small controlled SVG views | Server-owned run state, commands, live inspection, evidence and comparison views. |
| Verification | pytest and Hypothesis; real Postgres/sandbox integration fixtures | Transition properties, generated failure sequences, recovery and isolation checks. |

This preserves the repository's Python/Postgres/DBOS direction where it serves the new semantics. PostgreSQL 18 is selected for a new isolated deployment, not as an instruction to upgrade the concurrent database. Version 18 is currently supported; exact patch versions and the dependency lock must be recorded and tested when the implementation environment is assembled. Do not carry old pins into a new compatibility claim without checking them. [PostgreSQL version policy](https://www.postgresql.org/support/versioning/)

No agent framework owns the investigation loop. The stable interpreter executes the selected composition semantics; candidate programs and compositions are data and isolated artifacts. This separation is the reason cognitive self-change need not redeploy the trusted application.

## 3. PostgreSQL owns coherent domain state

Use relational tables for distinct semantic entities and explicit grouped-premise tables for evidence. JSONB is appropriate for versioned domain-specific content, not for hiding ownership, budget, version, or state-transition constraints from the database.

Admission and resource changes use short SERIALIZABLE transactions, with whole-transaction retry on serialization failure. No model call, container execution, or external write occurs inside a retried transaction. Read-only browsing can use weaker isolation because it does not authorize effects. PostgreSQL documents both serializable behavior and the need to retry failed transactions. [Transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html)

Work acquisition uses row ownership and a generation check. `SKIP LOCKED` may improve queue acquisition throughput, but it is not used to determine that no relevant counterevidence exists or that a resource pool has capacity. PostgreSQL explicitly distinguishes its usefulness for queue consumers from its inconsistent general view. [SELECT locking clauses](https://www.postgresql.org/docs/current/sql-select.html)

Use an outbox committed with the domain transition. Its dispatcher starts deterministic workflow identities; duplicate dispatch must be harmless. PostgreSQL notifications can reduce latency, but periodic durable scans establish recovery. Listener setup has a documented initial race, so notifications are hints rather than the only record of work. [LISTEN](https://www.postgresql.org/docs/current/sql-listen.html)

Use one database with separated domain and DBOS namespaces and database privileges. No generated worker receives a database credential. Hidden evaluation content also has an access boundary; a table name alone is not isolation.

## 4. DBOS recovers orchestration, not external reality

Retain DBOS because durable scheduling and recovery already have a concrete role here. Each bounded attempt or experiment uses a stable trusted workflow; an investigation can outlive many such workflows. A centuries-long, self-rewriting workflow is not the unit of persistence.

DBOS requires deterministic workflow structure relative to recorded step results. It also states that an interrupted step may be retried. Therefore nondeterministic choices are recorded through steps, and effects pass through the operation broker with durable identities. These product guarantees do not imply exactly-once external actions. [DBOS workflows](https://docs.dbos.dev/python/tutorials/workflow-tutorial)

The trusted interpreter reads an immutable composition version and advances through recorded continuations. A model proposing a new branch produces a recorded step result. Domain writes within steps have command idempotency keys, so a crash between a domain commit and a DBOS checkpoint does not duplicate them. A broker call repeated by DBOS refers to the existing operation, including its unresolved status, rather than automatically issuing another external request.

Keep DBOS execution progress and domain truth distinct: a successful workflow is not a fulfilled investigation, and a failed workflow does not cancel a pending external action. A domain outbox repairs a crash between admission and workflow enqueue without depending on a cross-system transaction.

Trusted interpreter upgrades use explicit application versions and retain old executors until their workflows drain or undergo a tested migration. DBOS documents version-matched recovery and this deployment pattern. Ordinary capability revisions use artifact versions and scoped release, not application upgrades. [Upgrading workflow code](https://docs.dbos.dev/python/tutorials/upgrading-workflows)

Reject Temporal as an additional dependency for this initial host: the design presently needs no second orchestration system. Reconsider orchestration technology if measured multi-host operations or version migration requirements exceed this arrangement. This is a choice about operational scope, not a claim that Temporal lacks the required capabilities.

## 5. Execution and effects

Select gVisor `runsc` through Docker's OCI runtime integration. The documented integration supports running container images through `runsc`; trusted runtime configuration and host inspection establish what was actually launched, not text printed by the candidate. [Docker integration](https://gvisor.dev/docs/user_guide/quick_start/docker/)

Use `systrap` inside the Linux VM. gVisor's platform guidance identifies it as the default and discusses its suitability inside VMs without requiring nested KVM. The actual image/tool compatibility and performance still need measurement on the chosen host. [Platform guidance](https://gvisor.dev/docs/user_guide/platforms/)

The selected worker profile has no network, no credentials, no Docker socket, read-only declared inputs, a bounded writable scratch area, and bounded output. Model requests and other effects are framed proposals over a controlled pipe to the broker. The broker authorizes each request; a worker cannot choose an arbitrary host URL or import an enforcing function to authorize itself.

gVisor reduces exposure to the host system API; it does not independently enforce the application's network policy, authority model, or all resource limits. Its security model explicitly relies on host resource controls. Apply CPU, memory, process and wall-time limits, plus separate scratch/output quotas and admission capacity. [gVisor security model](https://gvisor.dev/docs/architecture_guide/security/), [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/)

An invocation requiring an unsupported syscall or tool profile returns an explicit compatibility failure. It does not silently fall back to an unrestricted local subprocess. A different executor profile requires a separate admitted capability and authority scope. Candidate evaluation uses the same restriction; the evaluator's hidden answers must not be mounted into the candidate's container.

Dependency construction is a separate bounded operation. Pin wheels, source archives, and image digests before execution; builds run in isolation. Acquiring a package may require a brokered network operation, but package installation does not gain host credentials. The first learned capabilities can use the declared base image without solving arbitrary package installation.

## 6. Gateway contract, not provider policy

Use HTTPX directly for the narrow gateway connection. The user already intends to implement the endpoint; adding LiteLLM Router inside Settlement would duplicate retry and routing ownership for that contract. Existing LiteLLM code is not removed by this decision.

The broker accepts model-operation requests with a model reference, structured message/tool content, explicit output limits, deadline, and operation identity. The gateway adapter returns actual model metadata when available, usage/charge evidence, completion status, and a typed error. Keep raw attributable protocol material where needed by the retention policy.

Choose one wire adapter for the user's first endpoint. Another protocol adds an adapter, not another agent architecture. No model name or provider is fixed here. Discovery, authentication, inference, streaming, usage reporting, and cancellation are separate compatibility checks.

HTTPX exposes connect, read, write, and pool timeouts. The broker also enforces a total attempt deadline; a sequence of non-expiring read intervals must not keep a stream alive forever. [HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/)

Retry authority belongs to the broker. Gateway-side retries must either share an enforceable exposure bound and visible semantics, or the broker cannot promise a hard monetary ceiling. A disconnected stream does not establish that billing stopped. Cancellation requests and confirmed cancellation are different outcomes.

## 7. Retrieval and context

Start with indexed full-text search, explicit dependency traversal, identity lookup, and bounded model-assisted query expansion. PostgreSQL supplies the text-search representations and indexing; the learned context capability decides how to use the resulting material. [PostgreSQL text search](https://www.postgresql.org/docs/current/textsearch-intro.html)

This is the selected initial retrieval policy, not a claim that lexical retrieval is sufficient for all knowledge. Build the first context evaluation around cold counterexamples, terminology changes, resumed investigations, and irrelevant but persuasive material. Its failure can justify a different retriever through E4.

Select pgvector as the extension if an embedding service and measured semantic-retrieval advantage justify that revision. No GPU or embedding endpoint is assumed in the initial envelope. An approximate index changes retrieval recall; pgvector documents both exact search and the recall/speed trade-off of approximate indexes. Do not confuse semantic retrieval with a complete evidence-admissibility check. [pgvector](https://github.com/pgvector/pgvector)

Do not add Neo4j, a separate vector service, or Redis for these initial responsibilities. Explicit relations and derived views already express the semantics; another service must earn its coordination and recovery cost.

## 8. Operator interface and visibility

Choose a browser control surface served by FastAPI with Jinja2 templates and HTMX interactions. FastAPI documents template integration, and HTMX supports HTML fragment updates. This is a selected UI approach, not an assertion that those tools supply domain correctness. [FastAPI templates](https://fastapi.tiangolo.com/advanced/templates/), [HTMX documentation](https://htmx.org/docs/)

Server state is authoritative. Bounded polling with revision cursors is sufficient initially; missed browser updates cannot lose commands or work. Commands carry idempotency keys and expected revisions. Display accepted, applied, refused, and outcome-unknown states separately. The UI must remain usable when every model endpoint is down.

Required views are investigations and their dependency diagram, active attempts and steps, the capability portfolio, candidate/reference trials, evidence with support and opposition, resources with unresolved exposure, and authoritative activity history. Required controls are admission, pause/resume, cancellation, quarantine, explicit allocation changes, and inspection of recovery issues.

Render generated content as inert text by default. Graph labels come from escaped structured data. Executable or HTML artifacts are inspected or downloaded through an isolated presentation path, not inserted into the control page as active content. Do not expose an arbitrary trusted shell through the management UI.

## 9. Verification, deployment, and retention

Use pytest for deterministic acceptance and integration checks and Hypothesis for sequences of stateful actions. Hypothesis provides state-machine testing facilities; the actual properties and failure injection are the project's responsibility. [Stateful testing](https://hypothesis.readthedocs.io/en/latest/stateful.html)

Use real PostgreSQL and `runsc` in their relevant integration gates. Mocked repositories and fake sandboxes cannot establish concurrency or containment. Deterministic fault injection covers the boundary between durable intent, launch, external response, receipt commit, and workflow checkpoint.

Use operating-system service supervision for controller, broker, and database availability. Keep the control API and privileged sandbox launcher separate in authority even if deployed on one host. The worker never inherits their credentials. Runtime privilege and resource profiles are frozen in the deployment manifest until explicitly revised.

Back up database and retained artifacts as a coherent recovery set. PostgreSQL supports dumps, filesystem-level backups, and continuous archiving; the selected first operational procedure is a quiesced checkpoint with verified artifact closure, copied to a different failure domain before claiming recovery from host loss. [Backup and restore](https://www.postgresql.org/docs/current/backup.html)

The first deployment has no zero-loss host-destruction claim. Recovery from an older checkpoint enters reconciliation mode before new external writes. More stringent availability or recovery-point requirements reopen the deployment choice; they are not supplied by adding the word durable.

## 10. Remaining build-time inputs

No further user input is needed to finish this design. Running it later requires a chosen Linux host, a gateway configuration, authorized resource envelopes, and a seeded charter. These are explicit configuration inputs, not missing architectural mechanisms.

The build must record a tested compatibility manifest: Python and package locks, Postgres patch, image digests, `runsc` version/platform, host kernel, limits, gateway contract, and restoration procedure. Version numbers in the concurrent repository are historical evidence, not substitutes for that manifest. [PRACTICAL-SPECIFICATION.md](PRACTICAL-SPECIFICATION.md) defines the implementation obligations and experimental sequence.
