from __future__ import annotations

import os

from pydantic import BaseModel, Field


class GatewayConfig(BaseModel):
    endpoint: str = ""
    api_key_env: str = "SETTLEMENT_GATEWAY_KEY"
    timeout_connect_ms: int = 5_000
    timeout_read_ms: int = 60_000
    timeout_total_ms: int = 300_000
    model_config = {"extra": "forbid"}


class ResourceConfig(BaseModel):
    max_concurrent_attempts: int = 4
    max_concurrent_operations: int = 16
    attempt_deadline_ms: int = 600_000
    operation_deadline_ms: int = 300_000
    scratch_bytes: int = 100 * 1024 * 1024
    output_bytes: int = 10 * 1024 * 1024
    model_config = {"extra": "forbid"}


class Settings(BaseModel):
    dsn: str = ""
    artifact_root: str = "var/artifacts"
    staging_root: str = "var/staging"
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    resources: ResourceConfig = Field(default_factory=ResourceConfig)
    model_config = {"extra": "forbid"}

    @classmethod
    def from_env(cls) -> "Settings":
        dsn = os.environ.get("SETTLEMENT_DSN", "")
        artifact_root = os.environ.get("SETTLEMENT_ARTIFACT_ROOT", "var/artifacts")
        staging_root = os.environ.get("SETTLEMENT_STAGING_ROOT", "var/staging")
        endpoint = os.environ.get("SETTLEMENT_GATEWAY_ENDPOINT", "")
        return cls(
            dsn=dsn,
            artifact_root=artifact_root,
            staging_root=staging_root,
            gateway=GatewayConfig(endpoint=endpoint),
        )


SETTLEMENT_DSN_TEMPLATE = "postgresql://ubuntu@/DBNAME?host=/var/run/postgresql"
