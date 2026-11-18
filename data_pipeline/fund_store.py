"""用户导入的基金持仓快照与净值序列，独立于抓取缓存。"""

from __future__ import annotations

import calendar
import csv
import hashlib
import io
import json
import math
import re
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


def _day(value: str) -> str:
    return date.fromisoformat(value.strip()).isoformat()


def _code(value: str) -> str:
    code = value.strip()
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError(f"代码必须是六位数字：{value!r}")
    return code


def _number(value: str, *, positive: bool = False) -> float:
    try:
        number = Decimal(value.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"无效数值：{value!r}") from exc
    if not number.is_finite() or number < 0 or (positive and number == 0):
        raise ValueError(f"数值必须有限且非负：{value!r}")
    result = float(number)
    if not math.isfinite(result):
        raise ValueError(f"数值超出可用范围：{value!r}")
    return result


def _csv_rows(content: str | bytes, required: set[str]) -> list[dict[str, str]]:
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError(
            f"CSV 缺少列：{', '.join(sorted(required - set(reader.fieldnames or [])))}"
        )
    rows = list(reader)
    if not rows:
        raise ValueError("CSV 没有数据行")
    return rows


class FundDataStore:
    """按基金与实际日期存档；重复导入跳过，冲突导入整批回滚。"""

    def __init__(self, path: str | Path = "data/cache/fund_review.db") -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(target)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS holding_snapshot (
                fund_code TEXT NOT NULL, as_of TEXT NOT NULL, fingerprint TEXT NOT NULL,
                PRIMARY KEY (fund_code, as_of)
            );
            CREATE TABLE IF NOT EXISTS holding_position (
                fund_code TEXT NOT NULL, as_of TEXT NOT NULL, stock_code TEXT NOT NULL,
                stock_name TEXT NOT NULL, weight REAL NOT NULL,
                PRIMARY KEY (fund_code, as_of, stock_code),
                FOREIGN KEY (fund_code, as_of) REFERENCES holding_snapshot(fund_code, as_of)
            );
            CREATE TABLE IF NOT EXISTS fund_nav_point (
                fund_code TEXT NOT NULL, date TEXT NOT NULL, unit_nav REAL NOT NULL,
                dividend_per_share REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (fund_code, date)
            );
        """)

    def import_holdings_csv(self, content: str | bytes) -> dict[str, int]:
        groups: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
        for line, row in enumerate(
            _csv_rows(content, {"fund_code", "as_of", "stock_code", "stock_name", "weight"}),
            start=2,
        ):
            try:
                fund, as_of, stock = (
                    _code(row["fund_code"]),
                    _day(row["as_of"]),
                    _code(row["stock_code"]),
                )
                weight = _number(row["weight"], positive=True)
                if weight > 1:
                    raise ValueError("weight 必须是 0 到 1 的小数，不是百分数")
                name = row["stock_name"].strip()
                if not name or stock in groups[(fund, as_of)]:
                    raise ValueError("股票名称为空或同一快照股票代码重复")
                groups[(fund, as_of)][stock] = {"code": stock, "name": name, "weight": weight}
            except (ValueError, AttributeError, TypeError) as exc:
                raise ValueError(f"持仓 CSV 第 {line} 行：{exc}") from exc
        imported = unchanged = 0
        with self.conn:
            for (fund, as_of), positions in groups.items():
                if sum(item["weight"] for item in positions.values()) > 1.000001:
                    raise ValueError(f"{fund} {as_of} 持仓权重合计超过 1")
                normalized = sorted(positions.values(), key=lambda item: item["code"])
                fingerprint = hashlib.sha256(
                    json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode()
                ).hexdigest()
                existing = self.conn.execute(
                    "SELECT fingerprint FROM holding_snapshot WHERE fund_code=? AND as_of=?",
                    (fund, as_of),
                ).fetchone()
                if existing:
                    if existing["fingerprint"] != fingerprint:
                        raise ValueError(f"{fund} {as_of} 已有不同持仓，拒绝覆盖")
                    unchanged += 1
                    continue
                self.conn.execute(
                    "INSERT INTO holding_snapshot VALUES (?,?,?)", (fund, as_of, fingerprint)
                )
                self.conn.executemany(
                    "INSERT INTO holding_position VALUES (?,?,?,?,?)",
                    [
                        (fund, as_of, item["code"], item["name"], item["weight"])
                        for item in normalized
                    ],
                )
                imported += 1
        return {"imported": imported, "unchanged": unchanged}

    def snapshot(self, fund_code: str, as_of: str) -> dict[str, Any] | None:
        rows = self.conn.execute(
            "SELECT stock_code AS code, stock_name AS name, weight FROM holding_position "
            "WHERE fund_code=? AND as_of=? ORDER BY weight DESC, stock_code",
            (_code(fund_code), _day(as_of)),
        ).fetchall()
        return (
            {"fund_code": fund_code, "as_of": as_of, "positions": [dict(row) for row in rows]}
            if rows
            else None
        )

    def month_snapshots(self, fund_code: str, month: str) -> dict[str, Any]:
        year, number = (int(part) for part in month.split("-"))
        start_cutoff = (date(year, number, 1) - timedelta(days=1)).isoformat()
        end_cutoff = date(year, number, calendar.monthrange(year, number)[1]).isoformat()

        def latest(cutoff: str, after: str = "0000-01-01") -> dict[str, Any] | None:
            row = self.conn.execute(
                "SELECT as_of FROM holding_snapshot WHERE fund_code=? AND as_of>? AND as_of<=? "
                "ORDER BY as_of DESC LIMIT 1",
                (_code(fund_code), after, cutoff),
            ).fetchone()
            return self.snapshot(fund_code, row["as_of"]) if row else None

        return {"start": latest(start_cutoff), "end": latest(end_cutoff, start_cutoff)}

    def import_nav_csv(self, content: str | bytes) -> dict[str, int]:
        rows = _csv_rows(content, {"fund_code", "date", "unit_nav", "dividend_per_share"})
        points: dict[tuple[str, str], tuple[float, float]] = {}
        for line, row in enumerate(rows, start=2):
            try:
                key = (_code(row["fund_code"]), _day(row["date"]))
                nav = _number(row["unit_nav"], positive=True)
                dividend = _number(row.get("dividend_per_share") or "0")
                value = (nav, dividend)
                if key in points and points[key] != value:
                    raise ValueError("同一日期有冲突的净值")
                points[key] = value
            except (ValueError, AttributeError, TypeError) as exc:
                raise ValueError(f"净值 CSV 第 {line} 行：{exc}") from exc
        imported = unchanged = 0
        with self.conn:
            for (fund, day), value in points.items():
                existing = self.conn.execute(
                    "SELECT unit_nav, dividend_per_share FROM fund_nav_point "
                    "WHERE fund_code=? AND date=?",
                    (fund, day),
                ).fetchone()
                if existing:
                    if tuple(existing) != value:
                        raise ValueError(f"{fund} {day} 已有不同净值或分红，拒绝覆盖")
                    unchanged += 1
                    continue
                self.conn.execute(
                    "INSERT INTO fund_nav_point VALUES (?,?,?,?)", (fund, day, *value)
                )
                imported += 1
        return {"imported": imported, "unchanged": unchanged}

    def nav_series(self, fund_code: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT date, unit_nav AS nav FROM fund_nav_point WHERE fund_code=? ORDER BY date",
            (_code(fund_code),),
        ).fetchall()
        return [dict(row) for row in rows]

    def nav_points(self, fund_code: str) -> list[dict[str, Any]]:
        """Internal points retain dividends for total-return calculation."""
        rows = self.conn.execute(
            "SELECT date, unit_nav, dividend_per_share FROM fund_nav_point "
            "WHERE fund_code=? ORDER BY date",
            (_code(fund_code),),
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self.conn.close()
