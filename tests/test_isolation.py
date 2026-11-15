"""故障隔离验收（AC7）。

一个插件在运行期抛异常，必须只影响它自己的结果分区：
其他插件照常返回，接口仍是 200，错误汇总在 errors 里。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.deps import get_service
from engine.runtime import AlgorithmPlugin, PluginContext, PluginResult, registry
from tests.fakes import FakeService

BOOM_ID = "zz.boom"


def _boom(ctx: PluginContext) -> PluginResult:
    raise RuntimeError("故意抛出的故障")


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_service] = lambda: FakeService()
    with TestClient(app) as test_client:
        registry.ensure_loaded()
        registry.register(
            AlgorithmPlugin(
                id=BOOM_ID,
                title="故障插件",
                run=_boom,
                status="ready",
            )
        )
        try:
            yield test_client
        finally:
            registry.unregister(BOOM_ID)
            app.dependency_overrides.clear()


def test_failing_plugin_is_isolated(client: TestClient) -> None:
    response = client.post("/api/review", json={"fund_code": "110022", "month": "2026-10"})

    assert response.status_code == 200
    body = response.json()

    # 故障插件自己进入 error 状态
    assert body["results"][BOOM_ID]["status"] == "error"
    assert "故意抛出的故障" in body["results"][BOOM_ID]["error"]

    # 其他插件不受影响
    assert body["results"]["returns.interval"]["status"] == "ready"
    assert body["results"]["example.momentum_summary"]["status"] == "ready"

    # 错误被汇总，而不是让请求失败
    assert any(BOOM_ID in item for item in body["errors"])


def test_plugin_level_isolation_in_registry() -> None:
    registry.ensure_loaded()
    registry.register(AlgorithmPlugin(id=BOOM_ID, title="故障插件", run=_boom, status="ready"))
    try:
        result, error = registry.execute_safely(BOOM_ID, PluginContext())
        assert result is None
        assert error is not None and "故意抛出的故障" in error

        ok = registry.execute(
            "returns.interval",
            PluginContext(
                data={
                    "nav_series": [
                        {"date": "2026-10-01", "nav": 1.0},
                        {"date": "2026-10-02", "nav": 1.1},
                    ]
                }
            ),
        )
        assert ok.status == "ready"
    finally:
        registry.unregister(BOOM_ID)
