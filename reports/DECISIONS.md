# Decisions

| ID | Requirement | Reason / evidence | Alternative selected | Consequence |
|---|---|---|---|---|
| D-001 | TECHNOLOGY-DECISIONS §2 (PostgreSQL 18) | Build host provides PostgreSQL 16.15; no PG18 available. Constraint logic uses standard SQL portable across both. | Develop and test against local PostgreSQL 16; declare PostgreSQL 18 as the deployment target and re-verify on first deployment. | S0 manifest records both; deployment gate stays open until tested on PG18. |
| D-002 | PRACTICAL-SPECIFICATION §6 (gVisor `runsc`) | No Docker/`runsc` on this host. Spec forbids silent unrestricted fallback. | Ship the `gvisor` execution profile probe-gated (reports explicit incompatible here); add an explicitly labeled `local-process` profile for bounded software-diagnosis work that never claims containment. | Isolation gate unverified on this host; reproducible setup deferred to a Linux/gVisor host. |
