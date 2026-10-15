# P10 bounded campaign pilot

This pilot exercises one campaign development turn and one frozen final
assessment. It measures the campaign path, not autonomous acquisition, transfer,
learning, or improvement of the learner. The parent and candidate genomes are
human-authored. The candidate adds only generic process advice.

The campaign development task and the assessment epoch's development, validation,
and anchor tasks have four distinct ground-truth contents. The epoch development
task is frozen and authorized, but this gate does not execute it before the
comparison. The final gate admits two validation runs, one candidate regression
run on already-solved validation work, and two anchor runs. The development turn
plus those five assessment admissions use at most six model admissions.

`scenario.json` pins task content and all caps. `driver.py prepare` publishes the
four tasks and both genomes, freezes the epoch, seeds the named allocation roots
and grant, writes a freeze record, starts the campaign, and suspends it before any
model action. The next invocation runs in a new process, inspects and resumes the
same campaign, performs one development wake, and suspends again. A third process
inspects and resumes that campaign for the due final assessment. Assessment
exports use `campaign.export` and `campaign.recompute`.

The freeze records the source manifest and SHA-256, scenario, protocol, caps,
actual task/genome/epoch/grant/root identities, and a credential-free route
identity computed as SHA-256 of the configured base URL with trailing slashes
removed. It never records the route URL or key. Each phase checks that the source,
scenario, protocol, and caps still match. A changed freeze stops the run before
the next campaign action.

The finite bounds are 400,000 admitted tokens per action, 90,000 ms per action,
2,400,000 token units and 3,000,000 CPU units across the campaign, one turn, five
wakes per public run, with a 120-second development phase and a 480-second
assessment phase inside a 600-second total wall envelope measured from freeze.
The driver refuses to start a phase unless its declared minimum window remains.
Token ceilings bound admission charging; they do not physically preempt provider
work. The campaign wall check runs at a wake boundary, so it does not interrupt
a gate already in progress. A timeout or unknown effect remains incomplete with
its original operation identity. `unfinished_campaigns` names a campaign that
still needs assessment or reconciliation; `unresolved_operations` contains only
IDs derived from exported durable operations. The driver does not retry an
operation under a new campaign id.

The epoch uses the existing native `benchmark` execution mode. Local worker and
verifier children are uncontained. Fixture mode uses a cooperative deterministic
worker to qualify the public path; it does not test hostile-code containment.
The same limitation must be considered when interpreting a live run.

Fixture qualification runs only against an isolated test database and makes no
provider call. Its scratch data belongs under the test's temporary directory,
separate from completed live runs.

```powershell
$env:PYTHONPATH = "src;tests;."
$env:PYTHONUNBUFFERED = "1"
$campaignId = "p10-live-$([guid]::NewGuid().ToString('N').Substring(0, 12))"
$python = "D:\AI\Agent-Society-v2\.venv\Scripts\python.exe"
& $python experiments\campaign10\driver.py prepare --mode live --id $campaignId
& $python experiments\campaign10\driver.py development --mode live --id $campaignId
& $python experiments\campaign10\driver.py assessment --mode live --id $campaignId
```

Set `S09ISO_ADMIN_DSN` to the separately provisioned pilot database before
running. The live route file and Codex executable use the paths assigned for this
pilot. Use one id for all three commands. If a phase reports incomplete, inspect
and export that same campaign; do not start a replacement identity.
