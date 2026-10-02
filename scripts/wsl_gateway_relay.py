#!/usr/bin/env python3
"""Reach the Windows loopback gateway from inside WSL without opening a Windows port.

WSL2 here runs in NAT mode behind the Hyper-V firewall, whose
``DefaultInboundAction`` is ``Block``. A Windows listener is therefore
unreachable from WSL however it is bound, and adding an allow rule needs
elevation this shell does not have. Two listener shapes were measured and both
failed identically, so no amount of rebinding fixes it.

The WSL interop path can execute a Windows binary, and that binary sees the
Windows loopback. So the gateway is reachable with nothing newly exposed.

This file is both halves of that bridge.

  serve    The relay, run under the WSL (Linux) interpreter. Listens on a WSL
           loopback port, speaks HTTP, and for each request spawns the bridge
           half under the Windows interpreter, which makes the real call with
           ``http.client`` and hands the response back over stdio.

  __bridge The spawned half, run under the Windows interpreter. One request,
           one response, then exit. No carried state, so no session to corrupt.

Start the relay:

    python3 scripts/wsl_gateway_relay.py serve

A caller then states the relay as its endpoint. Nothing is sniffed and nothing
is retried on another endpoint, so a recorded result names the endpoint that
produced it:

    export SETTLEMENT_GATEWAY_ENDPOINT=http://127.0.0.1:4100/v1

With the relay down that URL fails by name, as a connection refused on 4100.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import socketserver
import struct
import subprocess
import sys
from http.server import BaseHTTPRequestHandler

DEFAULT_BIND = "127.0.0.1"
DEFAULT_PORT = 4100
DEFAULT_UPSTREAM = "http://127.0.0.1:4000"
CALL_TIMEOUT_S = 300

# Hop-by-hop headers belong to one connection and must not be forwarded. Host is
# dropped because the upstream needs its own authority, not the relay's.
HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "proxy-connection", "te", "trailer", "transfer-encoding", "upgrade", "host",
})

# Interpreters to try, in order, for the bridge half. This is interpreter
# discovery, which has to adapt to the machine. Endpoint selection never adapts.
_PYTHON_CANDIDATES = (
    ("/mnt/c/Windows/py.exe", ("-3",)),
    ("/mnt/c/Windows/py.exe", ()),
    ("/mnt/c/CLI/cx/.venv/Scripts/python.exe", ()),
)


class RelayError(RuntimeError):
    """A failure that must surface to the caller instead of being retried away."""


# --------------------------------------------------------------------------- #
# stdio framing: a 4-byte little-endian length, a JSON metadata line, then
# exactly body_len raw bytes. Framing the body separately keeps binary payloads
# intact, which the interop pipe has been measured to carry byte-for-byte.
# --------------------------------------------------------------------------- #

def _read_exact(stream, n: int) -> bytes:
    chunks = []
    got = 0
    while got < n:
        chunk = stream.read(n - got)
        if not chunk:
            raise RelayError("bridge closed the pipe after %d of %d bytes" % (got, n))
        chunks.append(chunk)
        got += len(chunk)
    return b"".join(chunks)


def _send_frame(stream, meta: dict, body: bytes) -> None:
    line = json.dumps(meta).encode()
    stream.write(struct.pack("<I", len(line)))
    stream.write(line)
    if body:
        stream.write(body)
    stream.flush()


def _recv_frame(stream) -> tuple[dict, bytes]:
    raw = _read_exact(stream, 4)
    (length,) = struct.unpack("<I", raw)
    meta = json.loads(_read_exact(stream, length))
    return meta, _read_exact(stream, int(meta["body_len"]))


# --------------------------------------------------------------------------- #
# Windows side
# --------------------------------------------------------------------------- #

def _windows_path(wsl_path: str) -> str:
    """Convert a WSL path to the Windows form a spawned process can open."""
    done = subprocess.run(["wslpath", "-w", wsl_path], capture_output=True,
                          text=True, timeout=30)
    if done.returncode != 0:
        raise RelayError("wslpath -w %s failed: %s" % (wsl_path, done.stderr.strip()))
    return done.stdout.strip()


def _windows_interpreter() -> tuple[str, list[str]]:
    """Find a Windows Python. Explicit override wins; the rest is discovery."""
    override = os.environ.get("W0_WINDOWS_PYTHON")
    if override:
        return override, []
    for exe, prefix in _PYTHON_CANDIDATES:
        if not os.path.exists(exe):
            continue
        probe = [exe, *prefix, "-c", "import sys; sys.stdout.write(sys.executable)"]
        try:
            done = subprocess.run(probe, capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            # The Microsoft Store stub opens a window and waits. Not an interpreter.
            continue
        if done.returncode == 0 and done.stdout.strip().lower().endswith(".exe"):
            return exe, list(prefix)
    raise RelayError(
        "no Windows Python interpreter found for the bridge half. Tried %s. "
        "Set W0_WINDOWS_PYTHON to a Windows python.exe path."
        % ", ".join(exe for exe, _ in _PYTHON_CANDIDATES))


def _upstream_target(upstream: str) -> tuple[str, int]:
    """Split an explicit upstream URL. No default, no discovery."""
    from urllib.parse import urlsplit
    parts = urlsplit(upstream)
    if parts.scheme != "http" or not parts.hostname:
        raise RelayError("upstream must be an http:// URL, got %r" % upstream)
    if parts.path.rstrip("/") not in ("", "/v1"):
        raise RelayError("upstream must be the gateway root or its /v1, got %r" % upstream)
    return parts.hostname, parts.port or 80


def serve_bridge(upstream: str) -> int:
    """One framed request in, one framed response out. Runs under Windows Python."""
    if os.name != "nt":
        raise RelayError("the bridge half must run under a Windows interpreter, "
                         "not the WSL one")
    host, port = _upstream_target(upstream)
    import http.client

    meta, body = _recv_frame(sys.stdin.buffer)
    headers = {name: value for name, value in meta["headers"]}
    conn = http.client.HTTPConnection(host, port, timeout=CALL_TIMEOUT_S)
    try:
        conn.request(meta["method"], meta["path"], body=body or None, headers=headers)
        response = conn.getresponse()
        payload = response.read()
        out_headers = [[name, value] for name, value in response.getheaders()]
        _send_frame(sys.stdout.buffer, {
            "status": response.status,
            "reason": response.reason,
            "headers": out_headers,
            "body_len": len(payload),
        }, payload)
    except Exception as exc:
        # Report the failure, never paper over it by trying a different endpoint.
        _send_frame(sys.stdout.buffer, {
            "error": "%s: %s" % (type(exc).__name__, exc),
            "upstream": upstream,
            "body_len": 0,
        }, b"")
    finally:
        conn.close()
    return 0


# --------------------------------------------------------------------------- #
# WSL side
# --------------------------------------------------------------------------- #

class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "w0-relay"
    sys_version = ""

    def log_message(self, fmt, *args):
        sys.stderr.write("[relay] %s - %s\n" % (self.address_string(), fmt % args))

    def _fail(self, status: int, reason: str, detail: str) -> None:
        body = json.dumps({
            "error": reason,
            "detail": detail,
            "relay_upstream": self.server.upstream,
            "note": "this relay serves one named upstream and never falls back",
        }, indent=2).encode() + b"\n"
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._relay()

    def do_POST(self):
        self._relay()

    def _relay(self) -> None:
        # One request per connection keeps every call independently attributable.
        self.close_connection = True

        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            self._fail(411, "chunked request bodies are not supported",
                       "send Content-Length instead")
            return

        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        headers = [[name, value] for name, value in self.headers.items()
                   if name.lower() not in HOP_BY_HOP]

        try:
            status, reason, out_headers, payload = self.server.call_bridge(
                self.command, self.path, headers, body)
        except RelayError as exc:
            self._fail(502, "relay could not reach its Windows bridge half", str(exc))
            return

        self.send_response(status, reason)
        seen = set()
        for name, value in out_headers:
            if name.lower() in HOP_BY_HOP:
                continue
            self.send_header(name, value)
            seen.add(name.lower())
        if "content-length" not in seen:
            self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)


class _Relay(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, addr, upstream: str):
        super().__init__(addr, _Handler)
        self.upstream = upstream
        self.exe, self.prefix = _windows_interpreter()
        self.script = _windows_path(os.path.abspath(__file__))

    def call_bridge(self, method: str, path: str,
                    headers: list, body: bytes) -> tuple[int, str, list, bytes]:
        """Run one request through the Windows half. Raises on any failure."""
        argv = [self.exe, *self.prefix, self.script, "__bridge", "--upstream", self.upstream]
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, bufsize=0)
        try:
            _send_frame(proc.stdin, {
                "method": method, "path": path, "headers": headers, "body_len": len(body),
            }, body)
            proc.stdin.close()
            meta, payload = _recv_frame(proc.stdout)
        except RelayError:
            proc.kill()
            proc.wait(timeout=30)
            detail = (proc.stderr.read() or b"").decode(errors="replace").strip()
            raise RelayError("Windows bridge produced no response" +
                             (": " + detail if detail else ""))
        finally:
            if proc.poll() is None:
                proc.kill()
        if "error" in meta:
            raise RelayError(meta["error"])
        return meta["status"], meta.get("reason", ""), meta["headers"], payload


def serve(bind: str, port: int, upstream: str) -> int:
    server = _Relay((bind, port), upstream)
    host, up_port = _upstream_target(upstream)
    sys.stderr.write(
        "[relay] listening on http://%s:%d/v1  ->  upstream http://%s:%d\n"
        "[relay] bridge interpreter: %s\n"
        "[relay] a caller must name this endpoint; there is no fallback\n"
        % (bind, port, host, up_port, server.exe))
    sys.stderr.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def check(bind: str, port: int, upstream: str, key: str | None, model: str) -> int:
    """Exercise the running relay with real calls and print literal results."""
    import urllib.error
    import urllib.request

    base = "http://%s:%d" % (bind, port)
    headers = {"Authorization": "Bearer " + key} if key else {}

    def call(method: str, path: str, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(base + path, data=data, method=method,
                                     headers=dict(headers))
        try:
            with urllib.request.urlopen(req, timeout=CALL_TIMEOUT_S) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    print("relay   :", base + "/v1")
    print("upstream:", upstream)
    print("key     :", "supplied" if key else "ABSENT (expect 401)")
    print("model   :", model)
    print()

    status, raw = call("GET", "/v1/models")
    print("GET /v1/models ->", status)
    try:
        catalog = json.loads(raw)
        ids = [m.get("id") for m in catalog.get("data", [])]
        print("  object  :", catalog.get("object"))
        print("  models  :", len(ids))
        print("  first   :", ids[:3])
        print("  free    :", [i for i in ids if str(i).endswith(":free")][:3])
    except Exception:
        print("  body    :", raw[:400].decode(errors="replace"))
    print()

    status, raw = call("POST", "/v1/chat/completions", {
        "model": model, "messages": [{"role": "user", "content": "hi"}]})
    print("POST /v1/chat/completions ->", status)
    try:
        body = json.loads(raw)
        if "error" in body:
            print("  gateway error:", body["error"].get("message"))
        else:
            for choice in body.get("choices", []):
                msg = choice.get("message", {})
                print("  model   :", body.get("model"))
                print("  reply   :", (msg.get("content") or "")[:300])
    except Exception:
        print("  body    :", raw[:400].decode(errors="replace"))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("serve", help="run the relay (under the WSL interpreter)")
    run.add_argument("--bind", default=DEFAULT_BIND)
    run.add_argument("--port", type=int, default=DEFAULT_PORT)
    run.add_argument("--upstream", default=DEFAULT_UPSTREAM,
                     help="the one Windows endpoint this relay serves")

    bridge = sub.add_parser("__bridge", help=argparse.SUPPRESS)
    bridge.add_argument("--upstream", default=DEFAULT_UPSTREAM)

    probe = sub.add_parser("check", help="call a running relay and print the results")
    probe.add_argument("--bind", default=DEFAULT_BIND)
    probe.add_argument("--port", type=int, default=DEFAULT_PORT)
    probe.add_argument("--upstream", default=DEFAULT_UPSTREAM)
    probe.add_argument("--key", default=os.environ.get("CX_API_KEY"),
                       help="gateway credential; prefer the CX_API_KEY env var")
    probe.add_argument("--model", default="openrouter/free",
                       help="model named by name for the completion probe")

    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            return serve(args.bind, args.port, args.upstream)
        if args.command == "__bridge":
            return serve_bridge(args.upstream)
        return check(args.bind, args.port, args.upstream, args.key, args.model)
    except RelayError as exc:
        sys.stderr.write("relay error: %s\n" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
