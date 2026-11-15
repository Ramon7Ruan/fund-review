"""数据源：akshare 适配器。

设计要点：
1. akshare 为可选依赖（体积大、依赖多），在函数内部延迟导入。CI 不安装也能跑测试。
2. 所有返回都转成普通 dict/list，脱离 pandas，避免上层与 pandas 耦合。
3. 每个函数只负责一件事：抓取 + 字段标准化。不做缓存、不做计算。
"""

from __future__ import annotations

from typing import Any


class SourceUnavailable(RuntimeError):
    """数据源不可用（未安装依赖、接口变更、网络失败）。"""


def _akshare():
    try:
        import akshare as ak  # noqa: PLC0415 - 延迟导入是刻意设计
    except ImportError as exc:  # pragma: no cover - 取决运行环境
        raise SourceUnavailable("未安装 akshare，无法抓取真实数据") from exc
    return ak


def fetch_fund_nav(code: str, indicator: str = "单位净值走势") -> list[dict[str, Any]]:
    """抓取基金单位净值序列，返回按日期升序的 [{date, nav}]。"""
    ak = _akshare()
    try:
        df = ak.fund_open_fund_info_em(symbol=code, indicator=indicator)
    except Exception as exc:  # noqa: BLE001 - 第三方异常类型不稳定
        raise SourceUnavailable(f"净值抓取失败：{type(exc).__name__}: {exc}") from exc

    if df is None or df.empty:
        raise SourceUnavailable(f"基金 {code} 无净值数据")

    points: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        points.append({"date": str(row["净值日期"]), "nav": float(row["单位净值"])})
    points.sort(key=lambda x: x["date"])
    return points


def fetch_fund_holdings(code: str, year: str) -> list[dict[str, Any]]:
    """抓取基金某年披露的持仓，返回 [{code, name, weight, quarter}]。

    weight 为占净值比例，转成小数（9.74 -> 0.0974）。
    """
    ak = _akshare()
    try:
        df = ak.fund_portfolio_hold_em(symbol=code, date=year)
    except Exception as exc:  # noqa: BLE001
        raise SourceUnavailable(f"持仓抓取失败：{type(exc).__name__}: {exc}") from exc

    if df is None or df.empty:
        raise SourceUnavailable(f"基金 {code} 在 {year} 年无持仓披露")

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        rows.append(
            {
                "code": str(row["股票代码"]),
                "name": str(row["股票名称"]),
                "weight": round(float(row["占净值比例"]) / 100.0, 8),
                "quarter": str(row["季度"]),
            }
        )
    return rows


def fetch_fund_basic(code: str) -> dict[str, Any]:
    """抓取基金基本信息。失败时返回最小信息，不阻塞主流程。"""
    try:
        ak = _akshare()
        df = ak.fund_individual_basic_info_xq(symbol=code)
        info = dict(zip(df["item"], df["value"], strict=False))
        return {
            "code": code,
            "name": str(info.get("基金名称", code)),
            "type": str(info.get("基金类型", "")),
            "company": str(info.get("基金公司", "")),
        }
    except Exception:  # noqa: BLE001 - 基本信息属于可选增强
        return {"code": code, "name": code, "type": "", "company": ""}
