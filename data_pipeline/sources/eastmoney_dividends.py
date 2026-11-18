"""东方财富基金分红页：核对基金身份并只读取指定分红表。"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

import httpx

from data_pipeline.sources.akshare_source import SourceUnavailable


class _DividendTable(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_title = False
        self.title = ""
        self.in_table = False
        self.in_cell = False
        self.cell = ""
        self.row: list[str] = []
        self.rows: list[list[str]] = []
        self.table_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self.in_title = True
        elif tag == "table" and "cfxq" in dict(attrs).get("class", "").split():
            self.in_table = True
            self.table_count += 1
        elif self.in_table and tag == "tr":
            self.row = []
        elif self.in_table and tag in {"th", "td"}:
            self.in_cell = True
            self.cell = ""

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title += data
        if self.in_cell:
            self.cell += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        elif self.in_table and tag in {"th", "td"}:
            self.row.append(self.cell.strip())
            self.in_cell = False
        elif self.in_table and tag == "tr" and self.row:
            self.rows.append(self.row)
        elif self.in_table and tag == "table":
            self.in_table = False


def fetch_fund_dividends(code: str) -> list[dict[str, Any]]:
    """按除息日返回每份现金红利；接口异常不能当作零分红。"""
    try:
        response = httpx.get(f"https://fundf10.eastmoney.com/fhsp_{code}.html", timeout=12)
        response.raise_for_status()
        table = _DividendTable()
        table.feed(response.text)
        if not re.search(rf"\({re.escape(code)}\)基金分红送配", table.title):
            raise ValueError("分红页面基金代码或页面类型不匹配")
        if table.table_count != 1 or not table.rows:
            raise ValueError("分红表缺失或重复")
        if table.rows[0] != ["年份", "权益登记日", "除息日", "每10份分红", "分红发放日"]:
            raise ValueError("分红表字段已变化")
        if len(table.rows) < 2:
            raise ValueError("分红表未返回数据状态")
        if len(table.rows) == 2 and table.rows[1] == ["暂无分红信息!"]:
            return []
        amounts: dict[str, float] = {}
        for row in table.rows[1:]:
            if len(row) != 5:
                raise ValueError("分红表数据列数异常")
            day = row[2]
            match = re.fullmatch(r"每10份派现金\s*(\d+(?:\.\d+)?)\s*元", row[3])
            if match is None:
                raise ValueError(f"无法识别每10份分红：{row[3]}")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                raise ValueError(f"无效除息日期：{day}")
            amounts[day] = round(amounts.get(day, 0.0) + float(match[1]) / 10, 8)
        return [
            {"date": day, "dividend_per_share": amount} for day, amount in sorted(amounts.items())
        ]
    except Exception as exc:  # noqa: BLE001 - 不把接口失败误认为无分红
        raise SourceUnavailable(f"基金 {code} 分红信息不可用：{type(exc).__name__}: {exc}") from exc
