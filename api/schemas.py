"""接口的请求与响应模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ReviewRequest(BaseModel):
    fund_code: str = Field(..., pattern=r"^\d{6}$", description="6 位基金代码")
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$", description="YYYY-MM")


class PluginResultPayload(BaseModel):
    status: str
    title: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    error: str | None = None


class ReviewResponse(BaseModel):
    fund: dict[str, Any]
    month: str
    nav_series: list[dict[str, Any]]
    holdings: list[dict[str, Any]]
    results: dict[str, PluginResultPayload]
    plugins: list[dict[str, Any]]
    errors: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class ErrorBody(BaseModel):
    code: int
    message: str
