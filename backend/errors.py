from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict


class ApiErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    provider: str | None = None
    retryable: bool = False
    details: dict[str, Any] | None = None


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ApiErrorPayload


@dataclass(slots=True)
class ServiceError(Exception):
    status_code: int
    code: str
    message: str
    provider: str | None = None
    retryable: bool = False
    details: dict[str, Any] | None = None

    def to_envelope(self) -> ErrorEnvelope:
        return ErrorEnvelope(
            error=ApiErrorPayload(
                code=self.code,
                message=self.message,
                provider=self.provider,
                retryable=self.retryable,
                details=self.details,
            )
        )
