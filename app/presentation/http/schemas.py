"""Request bodies accepted by the HTTP API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateRun(BaseModel):
    scenario_id: str = Field(max_length=100)


class Approve(BaseModel):
    args: dict[str, Any] | None = Field(default=None)


class Reject(BaseModel):
    feedback: str = Field(default="", max_length=2000)


class Message(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
