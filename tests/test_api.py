"""API 层测试。使用假数据服务，不访问网络。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.deps import get_service
from tests.fakes import FailingService, FakeService


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_service] = lambda: FakeService()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["plugins"]["total"] >= 4
    assert body["plugins"]["unavailable"] == 0


def test_plugins_list(client: TestClient) -> None:
    response = client.get("/api/plugins")
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert "returns.interval" in ids
    assert "attribution.brinson" in ids


def test_fund_detail(client: TestClient) -> None:
    response = client.get("/api/funds/110022")
    assert response.status_code == 200
    assert response.json()["name"] == "测试基金"


def test_fund_code_validation(client: TestClient) -> None:
    response = client.get("/api/funds/abc")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == 400


def test_review_partitions_results_by_plugin(client: TestClient) -> None:
    response = client.post("/api/review", json={"fund_code": "110022", "month": "2026-10"})
    assert response.status_code == 200
    body = response.json()

    assert body["month"] == "2026-10"
    assert len(body["nav_series"]) == 2
    assert body["results"]["returns.interval"]["status"] == "ready"
    assert body["results"]["returns.interval"]["data"]["period_return"] == pytest.approx(0.1)
    attribution = body["results"]["attribution.brinson"]
    assert attribution["status"] == "ready"
    assert attribution["data"]["items"]
    assert attribution["notes"]
    assert body["results"]["example.momentum_summary"]["data"]["up_days"] == 1
    assert body["errors"] == []


def test_review_returns_404_for_empty_month(client: TestClient) -> None:
    response = client.post("/api/review", json={"fund_code": "110022", "month": "1900-01"})
    assert response.status_code == 404
    assert "没有净值数据" in response.json()["error"]["message"]


def test_review_validates_payload(client: TestClient) -> None:
    response = client.post("/api/review", json={"fund_code": "abc", "month": "2026-10"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == 422


def test_review_reports_source_failure_as_503() -> None:
    app = create_app()
    app.dependency_overrides[get_service] = lambda: FailingService()
    with TestClient(app) as test_client:
        response = test_client.post("/api/review", json={"fund_code": "110022", "month": "2026-10"})
    app.dependency_overrides.clear()

    assert response.status_code == 503
    assert "净值数据不可用" in response.json()["error"]["message"]
