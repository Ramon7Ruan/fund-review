"""数据源：akshare 适配器。

设计要点：
1. akshare 为可选依赖（体积大、依赖多），在函数内部延迟导入。CI 不安装也能跑测试。
2. 所有返回都转成普通 dict/list，脱离 pandas，避免上层与 pandas 耦合。
3. 每个函数只负责一件事：抓取 + 字段标准化。不做缓存、不做计算。
"""

from __future__ import annotations

import re
from typing import Any

import httpx

# 个股公告接口在 1.20.65 才改成 symbol/indicator/start_date/end_date 签名；
# 更早版本是 security/symbol/begin_date/end_date，直接调用会 TypeError。
MIN_AKSHARE_VERSION = "1.20.65"


class SourceUnavailable(RuntimeError):
    """数据源不可用（未安装依赖、接口变更、网络失败）。"""


def _akshare():
    try:
        import akshare as ak  # noqa: PLC0415 - 延迟导入是刻意设计
    except ImportError as exc:  # pragma: no cover - 取决运行环境
        raise SourceUnavailable("未安装 akshare，无法抓取真实数据") from exc
    return ak


def _version_tuple(text: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", str(text))
    return tuple(int(item) for item in numbers[:3])


def _ensure_akshare_version() -> None:
    """公告接口有明确的版本下限，旧版本直接给出可执行的提示。"""
    ak = _akshare()
    version = str(getattr(ak, "__version__", "0"))
    if _version_tuple(version) < _version_tuple(MIN_AKSHARE_VERSION):
        raise SourceUnavailable(
            f"个股公告接口需要 akshare>={MIN_AKSHARE_VERSION}，当前为 {version}；"
            f"请执行 pip install -U 'akshare>={MIN_AKSHARE_VERSION}'"
        )


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


# ---------- 归因所需：个股行情、申万行业 ----------


def market_symbol(code: str) -> str:
    """把 6 位代码补成新浪/腾讯需要的带市场前缀形式。"""
    code = str(code).zfill(6)
    if code.startswith(("60", "68", "9")):
        return f"sh{code}"
    return f"sz{code}"


def fetch_stock_bars(code: str, start_date: str, end_date: str) -> tuple[list[dict[str, Any]], str]:
    """抓取个股日线（不复权），新浪为主、腾讯为备。

    不复权是刻意的：样本与口径都以数据源原始收盘价为准，
    除权除息的影响由归因残差吸收，并在 meta.adjust 里明确标注 none。
    返回 (bars, source)。
    """
    ak = _akshare()
    symbol = market_symbol(code)
    df = None
    source = "sina"
    try:
        fetch_sina = getattr(ak, "stock_zh_a_hist_sina", None) or ak.stock_zh_a_daily
        df = fetch_sina(
            symbol=symbol,
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        )
        if df is None or df.empty:
            raise SourceUnavailable(f"{code} 新浪无个股行情")
    except Exception:  # noqa: BLE001 - 主源失败转备源
        try:
            df = ak.stock_zh_a_hist_tx(symbol=symbol, start_date=start_date, end_date=end_date)
            source = "tencent"
        except Exception as exc:  # noqa: BLE001
            raise SourceUnavailable(f"{code} 个股行情抓取失败：{type(exc).__name__}") from exc

    if df is None or df.empty:
        raise SourceUnavailable(f"{code} 无个股行情")

    bars: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        bars.append(
            {
                "date": str(row["date"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
                "amount": float(row["amount"]),
            }
        )
    bars.sort(key=lambda x: x["date"])
    return bars, source


def fetch_sw_industries() -> list[dict[str, Any]]:
    """申万一级行业列表：[{industry, sw_code}]。"""
    ak = _akshare()
    try:
        df = ak.sw_index_first_info()
    except Exception as exc:  # noqa: BLE001
        raise SourceUnavailable(f"申万行业列表抓取失败：{type(exc).__name__}") from exc
    if df is None or df.empty:
        raise SourceUnavailable("申万行业列表为空")
    return [
        {"industry": str(row["行业名称"]), "sw_code": str(row["行业代码"]).split(".")[0]}
        for _, row in df.iterrows()
    ]


def fetch_sw_constituents(sw_code: str) -> list[dict[str, Any]]:
    """某个申万一级行业的成分股：[{code, name}]。"""
    ak = _akshare()
    try:
        df = ak.index_component_sw(symbol=sw_code)
    except Exception as exc:  # noqa: BLE001
        raise SourceUnavailable(f"申万 {sw_code} 成分股抓取失败：{type(exc).__name__}") from exc
    if df is None or df.empty:
        raise SourceUnavailable(f"申万 {sw_code} 成分股为空")
    return [
        {"code": str(row["证券代码"]).zfill(6), "name": str(row["证券名称"])}
        for _, row in df.iterrows()
    ]


def fetch_sw_index_bars(sw_code: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    """申万一级行业指数日线（只取收盘价，用于算区间收益）。"""
    ak = _akshare()
    try:
        df = ak.index_hist_sw(symbol=sw_code, period="day")
    except Exception as exc:  # noqa: BLE001
        raise SourceUnavailable(f"申万 {sw_code} 指数抓取失败：{type(exc).__name__}") from exc
    if df is None or df.empty:
        raise SourceUnavailable(f"申万 {sw_code} 指数为空")

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        day = str(row["日期"])
        if start_date <= day <= end_date:
            rows.append({"date": day, "close": float(row["收盘"])})
    rows.sort(key=lambda x: x["date"])
    if not rows:
        raise SourceUnavailable(f"申万 {sw_code} 在 {start_date}~{end_date} 无数据")
    return rows


def fetch_announcements(day: str) -> list[dict[str, Any]]:
    """按日抓取全市场公告（巨潮/东财），字段含原文链接，供事件陈列过滤。

    day 为 YYYYMMDD。返回 [{code, name, title, event_type, date, url}]。
    """
    ak = _akshare()
    try:
        df = ak.stock_notice_report(symbol="全部", date=day)
    except Exception as exc:  # noqa: BLE001
        raise SourceUnavailable(f"公告抓取失败：{type(exc).__name__}") from exc
    if df is None or df.empty:
        return []

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        rows.append(
            {
                "code": str(row["代码"]).zfill(6),
                "name": str(row["名称"]),
                "title": str(row["公告标题"]),
                "event_type": "stock_notice",
                "date": str(row["公告日期"]),
                "url": str(row["网址"]),
            }
        )
    return rows


def _stock_announcements_confirm_empty(code: str, start_date: str, end_date: str) -> bool:
    """AKShare 处理零条公告时会抛 KeyError，向东财核实是否确实为空。"""
    try:
        response = httpx.get(
            "https://np-anotice-stock.eastmoney.com/api/security/ann",
            params={
                "sr": -1,
                "page_size": 1,
                "page_index": 1,
                "ann_type": "A",
                "client_source": "web",
                "f_node": 0,
                "s_node": 0,
                "stock_list": code,
                "begin_time": start_date,
                "end_time": end_date,
            },
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return False
    if not isinstance(payload, dict) or payload.get("success") != 1:
        return False
    data = payload.get("data")
    return isinstance(data, dict) and data.get("total_hits") == 0 and data.get("list") == []


def fetch_stock_announcements(code: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    """按个股抓取公告，日期为 YYYY-MM-DD。要求 akshare>=1.20.65。"""
    _ensure_akshare_version()
    ak = _akshare()
    try:
        df = ak.stock_individual_notice_report(
            symbol=code, indicator="全部", start_date=start_date, end_date=end_date
        )
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, KeyError) and exc.args == ("代码",):
            if _stock_announcements_confirm_empty(code, start_date, end_date):
                return []
        raise SourceUnavailable(f"{code} 公告抓取失败：{type(exc).__name__}") from exc
    if df is None or df.empty:
        return []

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        rows.append(
            {
                "code": str(row["代码"]).zfill(6),
                "name": str(row["名称"]),
                "title": str(row["公告标题"]),
                "event_type": "stock_notice",
                "date": str(row["公告日期"]),
                "url": str(row["网址"]),
            }
        )
    return rows


def fetch_fund_announcements(code: str) -> list[dict[str, Any]]:
    """基金自身公告。东财只给报告 ID，原文链接按固定格式拼接（已验证可达）。"""
    ak = _akshare()
    try:
        df = ak.fund_announcement_report_em(symbol=code)
    except Exception as exc:  # noqa: BLE001
        raise SourceUnavailable(f"{code} 基金公告抓取失败：{type(exc).__name__}") from exc
    if df is None or df.empty:
        return []

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        report_id = str(row["报告ID"])
        rows.append(
            {
                "code": code,
                "name": str(row.get("基金名称", code)),
                "title": str(row["公告标题"]),
                "event_type": "fund_notice",
                "date": str(row["公告日期"]),
                "url": f"https://fund.eastmoney.com/gonggao/{code},{report_id}.html",
            }
        )
    return rows
