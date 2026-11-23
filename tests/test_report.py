"""报告导出测试。

重点覆盖 Issue #5 的三条验收标准：
1. 能生成包含收益概况与归因结论的报告；
2. 报告里的数字与页面（/api/review 响应）完全一致；
3. 导出文件可离线打开（自包含，不引用任何外部资源）。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.deps import get_service
from api.report import render
from tests.fakes import FakeService


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_service] = lambda: FakeService()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def snapshot(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/review", json={"fund_code": "110022", "month": "2026-10"})
    assert response.status_code == 200
    return response.json()


def _percent(value: float) -> str:
    """与渲染器相同的百分比格式（不带正负号），用于断言数字一致性。"""
    return f"{value * 100:.2f}%"


def test_report_returns_html(client: TestClient, snapshot: dict[str, Any]) -> None:
    response = client.post("/api/report", json=snapshot)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert body.startswith("<!DOCTYPE html>")
    assert "<title>" in body


def test_report_contains_required_sections(client: TestClient, snapshot: dict[str, Any]) -> None:
    body = client.post("/api/report", json=snapshot).text

    assert snapshot["fund"]["name"] in body
    for section in (
        "基金信息",
        "净值表现",
        "涨跌统计",
        "持仓明细",
        "持仓变动",
        "收益归因",
        "相关事件",
        "数据来源与口径",
    ):
        assert section in body, f"缺少章节：{section}"


def test_report_numbers_match_review(client: TestClient, snapshot: dict[str, Any]) -> None:
    """报告数字必须与 /api/review 完全一致：同一份快照，不做二次计算。"""
    body = client.post("/api/report", json=snapshot).text

    interval = snapshot["results"]["returns.interval"]["data"]
    assert _percent(interval["period_return"]) in body
    assert _percent(interval["max_drawdown"]) in body

    brinson = snapshot["results"]["attribution.brinson"]["data"]
    assert _percent(brinson["residual_return"]) in body
    assert _percent(brinson["coverage"]) in body

    momentum = snapshot["results"]["example.momentum_summary"]["data"]
    assert str(momentum["up_days"]) in body
    assert _percent(momentum["up_ratio"]) in body


def test_report_includes_attribution_reconcile(
    client: TestClient, snapshot: dict[str, Any]
) -> None:
    """归因对账：持仓贡献合计与未被解释收益之和应等于基金区间收益。"""
    brinson = snapshot["results"]["attribution.brinson"]["data"]
    total = brinson["total_contribution"] + brinson["residual_return"]
    assert abs(total - brinson["fund_return"]) < 1e-6

    body = client.post("/api/report", json=snapshot).text
    assert "持仓贡献合计" in body
    assert "未被解释收益" in body
    assert "持仓覆盖度" in body


def test_report_lists_holdings(client: TestClient, snapshot: dict[str, Any]) -> None:
    body = client.post("/api/report", json=snapshot).text

    for row in snapshot["holdings"]:
        assert row["name"] in body
        assert str(row["code"]) in body
    assert "前十大合计权重" in body


def test_report_is_self_contained(client: TestClient, snapshot: dict[str, Any]) -> None:
    """离线可打开：不允许引用任何外部样式、脚本或字体。"""
    body = client.post("/api/report", json=snapshot).text

    forbidden = (
        '<link rel="stylesheet"',
        "<script src=",
        "url(http",
        "@import",
    )
    for token in forbidden:
        assert token not in body

    assert "<style>" in body


def test_report_escapes_user_content(client: TestClient, snapshot: dict[str, Any]) -> None:
    """基金名称等外部文本必须转义，避免生成的报告被注入脚本。"""
    snapshot["fund"]["name"] = "<script>alert(1)</script>"
    body = client.post("/api/report", json=snapshot).text

    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


def test_report_degrades_when_plugin_stub(snapshot: dict[str, Any]) -> None:
    """插件不可用时报告仍然可生成，并且不隐瞒缺失。"""
    snapshot["results"]["attribution.brinson"] = {
        "status": "stub",
        "title": "收益拆解",
        "data": {},
        "notes": [],
        "error": None,
    }
    document = render(snapshot)

    assert "收益归因" in document
    assert "未生成" in document


def test_report_lists_errors(snapshot: dict[str, Any]) -> None:
    snapshot["errors"] = ["持仓数据不可用：akshare 未安装"]
    document = render(snapshot)

    assert "数据处理说明" in document
    assert "持仓数据不可用" in document


def test_report_handles_empty_nav(snapshot: dict[str, Any]) -> None:
    """净值点数不足时不画图，也不抛异常。"""
    snapshot["nav_series"] = []
    document = render(snapshot)

    assert "无法绘制走势" in document
