from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ValidationFinding(BaseModel):
    severity: Literal["error", "warn"]
    code: str
    message: str
    path: str | None = None


class ValidationReport(BaseModel):
    ok: bool
    findings: list[ValidationFinding]
