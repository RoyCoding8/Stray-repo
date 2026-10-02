# w0-relay: reaching the Windows gateway from WSL

Lane w0-relay. Worktree `wt/w0-relay`, uncommitted. The deliverable is
`scripts/wsl_gateway_relay.py`.

## The premise was wrong, so the relay is not a Windows listener

The task specified the likely shape: a forwarder bound to the WSL-visible
Windows address, proxying to `127.0.0.1:4000`. That shape cannot work on this
machine, and the reason is not the gateway's bind address.

I measured the blocking layer before building anything:

```
Get-NetFirewallHyperVVMSetting
  Enabled                : True
  DefaultInboundAction  : Block          <- governs WSL -> host traffic
```

WSL2 is in NAT mode, so WSL-to-host traffic crosses the Hyper-V firewall, and
that firewall's default inbound action is `Block`. No Windows bind address
escapes it. I built and measured two listener shapes anyway, and both failed
identically:

| Windows listener            | bound and visible in netstat | WSL -> it |
|---|---|---|
| `127.0.0.1:4000` (the existing gateway) | yes | HTTP 000 |
| `172.22.128.1:4000` (the Hyper-V vNIC)  | yes, `0.0.0.0:4100` too | HTTP 000 |

Raw TCP from WSL to `172.22.128.1:4100` gave `TimeoutError`, so the packet is
dropped rather than refused. WSL ping to `172.22.128.1` is 100% loss. The
reverse direction is entirely healthy: Windows reaches a listener inside WSL on
`172.22.141.222:4199` with HTTP 200. So the VM network path works in one
direction only, and the Hyper-V firewall is what closes the other.

Opening it would need an elevated command, which is out of scope:

```
New-NetFirewallHyperVRule -DisplayName probe -Direction Inbound -Action Allow ...
  -> CimException :: Access is denied.
```

The shell is confirmed unelevated (`elevated=False`), and I attempted nothing
further.

## What actually works: the interop path

WSL interop can execute a Windows binary, and that binary sees the Windows
loopback. Measured from inside WSL:

```
/mnt/c/Windows/System32/curl.exe -o /dev/null -w "%{http_code}" http://127.0.0.1:4000/v1/models
  -> 401          (a real application-level response, not a timeout)
```

That is the whole unblock, and it opens **no new network surface**, because the
Windows side never listens. This is the security win: the deliverable does not
expose the loopback service on any interface.

Interop stdio is binary-clean, which the design depends on. 16 random bytes
pushed through the pipe came back byte-identical
(`LEN=16 HEX=bbde80382940255130f34686ce5ef5e5`), and a nonzero exit code
propagates normally.

## Shape

`scripts/wsl_gateway_relay.py` holds both halves of the bridge.

- `serve` runs under the **WSL** interpreter. It listens on a **WSL loopback**
  port, default `127.0.0.1:4100`, and serves HTTP.
- `__bridge` runs under the **Windows** interpreter. It makes the real call
  with `http.client` and hands the response back over stdio.

Each request spawns one bridge process. One request, one response, then exit,
so there is no session or interpreter state to corrupt between calls. Payloads
cross as a 4-byte little-endian length, a JSON metadata line, then the raw body,
so binary bodies survive the pipe.

Windows Python is discovered at start, not assumed: `W0_WINDOWS_PYTHON` if
set, else `py.exe` with and without `-3`, else the cx venv interpreter. On this
machine it resolves to `/mnt/c/Windows/py.exe`. This is interpreter discovery,
which must adapt to the machine.

## Proof from inside WSL

Started with the command in the next section, then:

```
GET /v1/models -> 200
  object  : list
  models  : 255
  first   : ['qwen.qwen3-coder-30b-a3b-instruct', 'puter/gpt-5.6-sol-pro', 'deepseek-v4-flash']
  free    : ['nvidia/nemotron-3-ultra-550b-a55b:free', 'kilo/poolside/laguna-xs-2.1:free', 'poolside/laguna-xs-2.1:free']

POST /v1/chat/completions -> 200
  model   : nvidia/nemotron-3.5-content-safety:free
  reply   : User Safety: safe
```

`GET /health`, which `s09_study_preflight.control_plane_root` depends on, also
returns 200 with `{"status": "ok"}`, so the repo's existing preflight can point
at the relay without modification.

Unauthenticated, the relay returns the gateway's own 401 with
`{"error": {"message": "invalid api key"}}`, which shows the credential is
being forwarded and rejected by the application rather than dropped in transit.

## How a caller states the endpoint, and what happens when the relay is down

The route is explicit. A caller names the relay as its endpoint, and the relay
names its upstream as a startup flag:

```
python3 scripts/wsl_gateway_relay.py serve --port 4100 --upstream http://127.0.0.1:4000
```

```
export SETTLEMENT_GATEWAY_ENDPOINT=http://127.0.0.1:4100/v1
```

`SETTLEMENT_GATEWAY_ENDPOINT` is the variable
`experiments/ad01/s09_study_preflight.py:37` already reads (`ENDPOINT_VAR`),
so no existing caller changes.

There is no sniffing and no fallback anywhere in the design. A request that
cannot reach its named upstream returns 502 naming that upstream, verbatim:

```json
{
  "error": "relay could not reach its Windows bridge half",
  "detail": "ConnectionRefusedError: [WinError 10061] ...",
  "relay_upstream": "http://127.0.0.1:4999",
  "note": "this relay serves one named upstream and never falls back"
}
```

That was measured with a deliberately wrong upstream port on 4101. With the
relay stopped entirely, `curl http://127.0.0.1:4100/v1/models` returns
`http_code=000` and a connection refusal on 4100. In both cases the failure
names the endpoint that was asked for and no other endpoint is contacted, so
every recorded result stays attributable to the route that produced it.

## Operational status

Start it with one command, from WSL, in the foreground:

```
cd /mnt/d/AI/Agent-Society-v2/.worktrees/w0-relay
python3 scripts/wsl_gateway_relay.py serve --port 4100
```

**It must be started manually before a session that needs the gateway. It does
not survive a WSL shutdown, because `wsl --shutdown` stops the distribution
and the relay is a foreground process in it.** It is not a service. I did not
install a service, a startup task, or a scheduled task, since that changes the
user's machine beyond this task's scope.

I did not run the `tests/test_s09_e2_scored.py` file the task mentioned. Whether
the relay makes those 18 Windows failures pass is unproven here. Two things
block a claim. The file is scored live-run, so confirming it needs a budgeted
run, and the child-exec path needs the WSL venv, not the system Python the
bridge half uses. I also did not verify that a caller launched from
`tests/test_s09_e2_scored.py` can reach the relay on `127.0.0.1:4100` from its
own working directory. That is the next check for whoever picks this up.

## Security posture

Stated plainly, because the first design would have been the opposite.

**The delivered relay exposes nothing new.** It binds WSL loopback only, by
default `127.0.0.1:4100`. It is not reachable from Windows or from the network;
`curl http://172.22.141.222:4100/v1/models` from Windows returns HTTP 000. The
gateway on `127.0.0.1:4000` stays bound to loopback, unchanged. No firewall
rule, no listener, and no credential store was added, and nothing was logged
beyond a one-line request log with no auth headers.

The exposure the task warned about is real but belongs to the design I did not
build. A Windows forwarder bound to `172.22.128.1` would have put a
credential-authenticated proxy for the gateway onto a vNIC that was previously
unreachable, and every other machine on that subnet. It would also have
required an elevated firewall change. Neither applies here.

One reviewer note on the part that does hold risk. The relay forwards whatever
credential the caller presents to the Windows gateway, and it holds no secret
of its own. `CX_API_KEY` must be present in the caller's own WSL environment;
the relay neither reads nor stores the Windows user environment. Anyone who can
reach the relay can already reach the gateway, so the relay adds no new
authorization surface. It is a translator, not a new trust boundary.

## Undetermined

- Whether the 18 `test_s09_e2_scored.py` failures on Windows actually clear. Not
  run, for the two reasons above.
- Whether `child_limits` in the scored path needs anything beyond a reachable
  endpoint. The relay is a network fix only, and I did not verify the rest.
- Relayed **streaming** responses. `serve` buffers each response, since the
  bridge reads the upstream to completion before framing it. A streaming
  caller will not stream. I did not test a streamed completion, and a study
  that needs incremental output would need a different transport.
- **Chunked request bodies** are refused with a 411 and a named reason. Send
  `Content-Length`.
- Windows Python is discovered at relay start. If `py.exe` is absent on another
  machine the relay fails at startup with a named error rather than at call
  time. `W0_WINDOWS_PYTHON` overrides the search.
- A caller passing a large request body pays one process spawn per request,
  measured at roughly 0.1 s of interop overhead. Adequate for study dispatch,
  unmeasured under concurrency.
