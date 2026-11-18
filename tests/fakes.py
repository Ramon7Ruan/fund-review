"""测试共用的假数据服务。不访问网络。"""

from __future__ import annotations

from typing import Any

from data_pipeline.sources.akshare_source import SourceUnavailable


class FakeService:
    def get_fund(self, code: str) -> dict[str, Any]:
        return {
            "code": code,
            "name": "测试基金",
            "type": "混合型",
            "company": "测试公司",
            "cached": False,
        }

    def get_nav(self, code: str, month: str | None = None) -> tuple[list[dict], dict]:
        meta = {
            "source": "fake",
            "cached": False,
            "total_points": 2,
            "month_points": 2,
            "attempts": [],
        }
        if month == "1900-01":
            return [], {**meta, "total_points": 0, "month_points": 0}
        return (
            [
                {"date": f"{month}-01", "nav": 1.0},
                {"date": f"{month}-28", "nav": 1.1},
            ],
            meta,
        )

    def get_nav_adjusted(self, code: str, month: str | None = None) -> tuple[list[dict], dict]:
        rows, meta = self.get_nav(code, month)
        return (
            [{"date": p["date"], "total_return_index": p["nav"]} for p in rows],
            {**meta, "dividend_source": "fake", "warnings": []},
        )

    def get_holdings(
        self, code: str, year: str, month: str | None = None
    ) -> tuple[list[dict], dict]:
        quarter = f"{year}年1季度股票投资明细"
        return (
            [{"code": "600519", "name": "贵州茅台", "weight": 0.1, "quarter": quarter}],
            {"source": "fake", "cached": False, "quarter": quarter, "count": 1, "attempts": []},
        )


class FailingService(FakeService):
    def get_nav(self, code: str, month: str | None = None) -> tuple[list[dict], dict]:
        raise SourceUnavailable("akshare 未安装")
