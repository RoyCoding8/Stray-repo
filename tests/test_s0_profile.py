from __future__ import annotations

import pytest

from settlement.common import IncompatibleVersion, ResultCode, SettlementError


def test_gvisor_probe_reports_explicit_incompatible_on_this_host():
    from settlement import exec_profile

    probe = exec_profile.probe_gvisor()
    assert probe.available is False
    assert probe.code == ResultCode.INCOMPATIBLE_VERSION
    assert "runsc" in probe.reason or "docker" in probe.reason


def test_gvisor_probe_missing_binaries_never_raises():
    from settlement import exec_profile

    probe = exec_profile.probe_gvisor(runsc_path="/nonexistent/runsc", docker_path="/nonexistent/dkr")
    assert probe.available is False
    assert probe.code == ResultCode.INCOMPATIBLE_VERSION


def test_gvisor_dispatch_refuses_without_fallback():
    from settlement import exec_profile

    with pytest.raises(IncompatibleVersion):
        exec_profile.dispatch("gvisor", ["/bin/true"])


def test_unknown_profile_is_invalid_input():
    from settlement import exec_profile

    with pytest.raises(SettlementError) as excinfo:
        exec_profile.dispatch("no-such-profile", ["/bin/true"])
    assert excinfo.value.code == ResultCode.INVALID_INPUT


def test_local_process_runs_bounded_command():
    from settlement import exec_profile

    result = exec_profile.dispatch(
        "local-process", ["/bin/echo", "hello"], timeout_ms=5_000, max_output_bytes=1024
    )
    assert result.returncode == 0
    assert result.stdout == "hello\n"
    assert result.containment is False
    assert result.simulated is False
    assert result.timed_out is False


def test_local_process_timeout_kills_command():
    from settlement import exec_profile

    result = exec_profile.dispatch(
        "local-process", ["/bin/sleep", "30"], timeout_ms=500, max_output_bytes=1024
    )
    assert result.timed_out is True
    assert result.containment is False


def test_local_process_carries_no_credentials():
    from settlement import exec_profile

    result = exec_profile.dispatch(
        "local-process",
        ["/usr/bin/env"],
        timeout_ms=5_000,
        max_output_bytes=65536,
        extra_env={
            "SETTLEMENT_GATEWAY_KEY": "s3cr3t",
            "MY_TOKEN": "tok",
            "KEEP_ME": "visible",
        },
    )
    assert result.returncode == 0
    assert "s3cr3t" not in result.stdout
    assert "tok=" not in result.stdout
    assert "KEEP_ME=visible" in result.stdout


def test_local_process_caps_output():
    from settlement import exec_profile

    result = exec_profile.dispatch(
        "local-process",
        ["/bin/sh", "-c", "yes | head -c 100000"],
        timeout_ms=5_000,
        max_output_bytes=100,
    )
    assert len(result.stdout.encode()) <= 100
    assert result.truncated is True
    assert result.containment is False


def test_local_process_cpu_limit_kills_spinner():
    from settlement import exec_profile

    result = exec_profile.dispatch(
        "local-process",
        ["/bin/sh", "-c", "while true; do :; done"],
        timeout_ms=10_000,
        max_output_bytes=1024,
        cpu_seconds=1,
    )
    assert result.returncode != 0
    assert result.timed_out is False


def test_simulated_profile_returns_labeled_canned_result():
    from settlement import exec_profile

    result = exec_profile.dispatch("simulated", ["/nonexistent-binary"])
    assert result.simulated is True
    assert result.containment is False
    assert result.returncode == 0
