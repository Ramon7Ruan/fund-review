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
            [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "weight": 0.1,
                    "industry": "",
                    "quarter": quarter,
                }
            ],
            {"source": "fake", "cached": False, "quarter": quarter, "count": 1, "attempts": []},
        )

    def get_quotes(self, codes, month: str) -> tuple[dict[str, list[dict]], dict]:
        rows = {
            str(code): [
                {"date": f"{month}-01", "close": 10.0},
                {"date": f"{month}-28", "close": 10.5},
            ]
            for code in codes
        }
        return rows, {
            "source": "fake",
            "adjust": "none",
            "requested": len(rows),
            "count": len(rows),
            "cached": False,
            "missing": [],
        }

    def get_industry_map(self, codes) -> tuple[dict[str, str], dict]:
        mapping = {str(code): "食品饮料" for code in codes}
        return mapping, {
            "source": "fake",
            "requested": len(mapping),
            "mapped": len(mapping),
            "unmapped": [],
            "attempts": [],
        }

    def get_industry_returns(self, month: str, industries=None) -> tuple[dict[str, float], dict]:
        names = list(industries) if industries is not None else ["食品饮料"]
        return {name: 0.02 for name in names}, {
            "source": "fake",
            "count": len(names),
            "missing": [],
            "adjust": "none",
        }

    def get_events(self, fund_code, holding_codes, month: str) -> tuple[list[dict], dict]:
        return (
            [
                {
                    "code": "600519",
                    "title": "贵州茅台:2026年第三季度报告",
                    "date": f"{month}-28",
                    "url": "https://data.eastmoney.com/notices/detail/600519/x.html",
                    "event_type": "stock_notice",
                },
                {
                    "code": "000001",
                    "title": "与持仓无关的公告",
                    "date": f"{month}-28",
                    "url": "https://data.eastmoney.com/notices/detail/000001/y.html",
                    "event_type": "stock_notice",
                },
                {
                    "code": "600519",
                    "title": "缺少原文链接的公告",
                    "date": f"{month}-28",
                    "url": "",
                    "event_type": "stock_notice",
                },
            ],
            {"source": "fake", "cached": False, "count": 3, "missing": []},
        )


class FailingService(FakeService):
    def get_nav(self, code: str, month: str | None = None) -> tuple[list[dict], dict]:
        raise SourceUnavailable("akshare 未安装")
