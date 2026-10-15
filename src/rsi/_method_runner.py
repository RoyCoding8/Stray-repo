"""Trusted child adapter for one genome-embedded Python method."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import math
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath


class _Capture(io.TextIOBase):
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.parts: list[str] = []
        self.size = 0
        self.truncated = False

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        if not isinstance(text, str):
            raise TypeError("write() argument must be str")
        remaining = max(self.limit - self.size, 0)
        encoded = text.encode("utf-8")
        if len(encoded) <= remaining:
            kept = text
            self.parts.append(kept)
            self.size += len(encoded)
        elif remaining:
            kept = encoded[:remaining].decode("utf-8", "ignore")
            self.parts.append(kept)
            self.size += len(kept.encode("utf-8"))
            self.truncated = True
        if len(encoded) > remaining:
            self.truncated = True
        return len(text)

    def getvalue(self) -> str:
        return "".join(self.parts)


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _json(raw: bytes):
    return json.loads(raw.decode("utf-8"), parse_constant=lambda value:
                      (_ for _ in ()).throw(ValueError(value)))


def _safe_relative(value: str) -> bool:
    path = PurePosixPath(value)
    return (bool(value) and "\\" not in value and not path.is_absolute()
            and not PureWindowsPath(value).drive
            and all(part not in ("", ".", "..") for part in value.split("/")))


def _finite_json(value) -> bool:
    if value is None or type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_finite_json(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _finite_json(item)
                   for key, item in value.items())
    return False


def _manifest(directory: Path, entries: list[dict]) -> bool:
    declared = set()
    for entry in entries:
        path = entry.get("path")
        if not isinstance(path, str) or not _safe_relative(path):
            return False
        declared.add(path)
        try:
            target = directory / path
            if target.is_symlink() or not target.is_file():
                return False
            raw = target.read_bytes()
        except OSError:
            return False
        if len(raw) != entry.get("size") or hashlib.sha256(raw).hexdigest() != entry.get("sha256"):
            return False
    actual = set()
    try:
        for path in directory.rglob("*"):
            if path.is_symlink():
                return False
            if path.is_file():
                actual.add(path.relative_to(directory).as_posix())
    except OSError:
        return False
    return actual == declared


def _run(meta_path: Path) -> dict:
    raw_meta = meta_path.read_bytes()
    meta = _json(raw_meta)
    if sys.version != meta["python_version"] or sys.executable != meta["python_executable"]:
        raise RuntimeError("python runtime identity changed")
    base = meta_path.parent
    if hashlib.sha256((base / "trusted_runner.py").read_bytes()).hexdigest() != meta["runner_digest"]:
        raise RuntimeError("trusted runner bytes changed")
    request_raw = (base / "request.json").read_bytes()
    if hashlib.sha256(request_raw).hexdigest() != meta["request_digest"]:
        raise RuntimeError("request bytes changed after pinning")
    request = _json(request_raw)
    if (not isinstance(request, dict)
            or set(request) != {"interface", "value", "files", "context"}
            or request["interface"] != meta["interface"]
            or not isinstance(request["files"], dict)
            or sorted(request["files"]) != meta["input_slots"]
            or not _finite_json(request)):
        raise RuntimeError("request does not match the pinned interface")
    method_dir = base / "method"
    method_manifest = [item for item in meta["files"] if item["path"].startswith("method/")]
    relative_manifest = [dict(item, path=item["path"][len("method/"):])
                         for item in method_manifest]
    if not _manifest(method_dir, relative_manifest):
        raise RuntimeError("method bytes changed after pinning")
    if set(request["files"]) - {
            item for item in request["files"] if isinstance(item, str) and _safe_relative(item)}:
        raise RuntimeError("request contains an unsafe solution slot")
    for slot, text in request["files"].items():
        if not isinstance(text, str) or not _safe_relative(slot):
            raise RuntimeError("request files are not safe UTF-8 solution slots")

    source = meta["entrypoint"]
    if not _safe_relative(source) or source not in {
            item["path"][len("method/"):] for item in method_manifest}:
        raise RuntimeError("entrypoint is outside the pinned method closure")
    source_path = method_dir / source
    sys.path.insert(0, str(source_path.parent))
    capture = _Capture(min(int(meta["max_output_bytes"]), 16_384))
    error_capture = _Capture(4_096)
    try:
        with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(error_capture):
            spec = importlib.util.spec_from_file_location("_rsi_candidate", source_path)
            if spec is None or spec.loader is None:
                raise RuntimeError("method entrypoint cannot be loaded")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            function = getattr(module, meta["function"])
            if not callable(function):
                raise TypeError("method entrypoint is not callable")
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "data": {"kind": "candidate-error",
                                                "detail": f"{type(exc).__name__}: {exc}"}}

    try:
        with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(error_capture):
            output = function(request)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "data": {"kind": "candidate-error",
                                                "detail": f"{type(exc).__name__}: {exc}",
                                                "candidate_stdout": capture.getvalue()}}
    if (not isinstance(output, dict) or set(output) != {"value", "files"}
            or not _finite_json(output) or not isinstance(output["files"], dict)):
        return {"status": "error", "data": {"kind": "candidate-error",
                                                "detail": "return must have exactly finite JSON value and files",
                                                "candidate_stdout": capture.getvalue()}}
    files = output["files"]
    if any(not isinstance(path, str) or not _safe_relative(path)
           or path not in request["files"] or not isinstance(text, str)
           for path, text in files.items()):
        return {"status": "error", "data": {"kind": "candidate-error",
                                                "detail": "returned files must use declared solution slots",
                                                "candidate_stdout": capture.getvalue()}}
    try:
        if len(_canonical(output)) > int(meta["max_output_bytes"]):
            return {"status": "error", "data": {"kind": "candidate-error",
                                                    "detail": "method output exceeds its declared byte limit",
                                                    "candidate_stdout": capture.getvalue()}}
    except (TypeError, ValueError, UnicodeError):
        return {"status": "error", "data": {"kind": "candidate-error",
                                                "detail": "method output is not canonical JSON",
                                                "candidate_stdout": capture.getvalue()}}
    return {"status": "ok", "data": {"kind": "capability-result",
                                       "output": output,
                                       "input_slots": sorted(request["files"]),
                                       "candidate_stdout": capture.getvalue(),
                                       "candidate_stdout_truncated": capture.truncated,
                                       "candidate_stderr": error_capture.getvalue()}}


def main() -> None:
    try:
        result = _run(Path(sys.argv[1]))
    except Exception as exc:  # noqa: BLE001
        result = {"status": "error", "data": {"kind": "infra-error",
                                                "detail": f"{type(exc).__name__}: {exc}"}}
    try:
        encoded = _canonical(result)
    except Exception as exc:  # noqa: BLE001
        encoded = _canonical({"status": "error", "data": {"kind": "infra-error",
                                                              "detail": f"runner encode failure: {exc}"}})
    if len(encoded) > 1_048_576:
        encoded = _canonical({"status": "error", "data": {"kind": "candidate-error",
                                                              "detail": "worker output exceeds its global byte limit"}})
    sys.__stdout__.buffer.write(encoded)
    sys.__stdout__.buffer.flush()


if __name__ == "__main__":
    main()
