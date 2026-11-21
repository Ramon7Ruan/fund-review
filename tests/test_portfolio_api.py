"""组合收益接口测试。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.deps import get_service
from tests.fakes import FakeService


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_service] = lambda: FakeService()
    with TestClient(app) as test_client:
        yield test_client
        app.dependency_overrides.clear()


def test_portfolio_review_ok(client: TestClient) -> None:
    response = client.post(
        "/api/portfolio/review",
        json={"month": "2026-10", "weights": {"110022": 0.5, "003095": 0.5}},
    )

    assert response.status_code == 200
    body = response.json()

    # FakeService 的复权序列两点：1.0 → 1.1，每只基金收益 10%
    assert body["total_return"] == pytest.approx(0.1, abs=1e-6)
    assert len(body["contributions"]) == 2
    assert body["cash_weight"] == pytest.approx(0.0, abs=1e-6)
    assert body["errors"] == []
    assert body["meta"]["110022"]["dividend_source"] == "fake"


def test_portfolio_empty_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/portfolio/review", json={"month": "2026-10", "weights": {}}
    )
    assert response.status_code == 400


def test_portfolio_weight_sum_over_one_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/portfolio/review",
        json={"month": "2026-10", "weights": {"110022": 0.7, "003095": 0.5}},
    )
    # 权重和 1.2 > 1，应在引擎层报错
    assert response.status_code in (400, 500)


def test_portfolio_with_cash(client: TestClient) -> None:
    response = client.post(
        "/api/portfolio/review",
        json={"month": "2026-10", "weights": {"110022": 0.4}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_return"] == pytest.approx(0.04, abs=1e-6)
    assert body["cash_weight"] == pytest.approx(0.6, abs=1e-6)
