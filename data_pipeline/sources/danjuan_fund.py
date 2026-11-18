"""蛋卷基金历史单位净值，作为东方财富净值接口的独立备份。"""

from __future__ import annotations

from math import isfinite
from typing import Any

import httpx

from data_pipeline.sources.akshare_source import SourceUnavailable


def fetch_fund_nav(code: str) -> list[dict[str, Any]]:
    try:
        response = httpx.get(
            f"https://danjuanapp.com/djapi/fund/nav/history/{code}",
            params={"size": 10000, "page": 1},
            headers={"User-Agent": "Mozilla/5.0"},
            follow_redirects=True,
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload["data"]
        items = data["items"]
        if payload.get("result_code") != 0 or len(items) != int(data["total_items"]):
            raise ValueError("接口未返回完整历史净值")
        rows = [{"date": str(item["date"]), "nav": float(item["nav"])} for item in items]
        if not rows or any(not isfinite(item["nav"]) or item["nav"] <= 0 for item in rows):
            raise ValueError("单位净值缺失或无效")
        rows.sort(key=lambda item: item["date"])
        return rows
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        raise SourceUnavailable(f"蛋卷净值抓取失败：{type(exc).__name__}: {exc}") from exc
