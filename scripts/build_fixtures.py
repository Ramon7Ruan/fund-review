"""生成 tests/fixtures/ 下的真实数据样本。

用途：给全组提供一份统一、真实、可复现的验收数据。
所有数据来自公开数据源（akshare），不使用任何编造值。

用法：
    python scripts/build_fixtures.py            # 全量重建
    python scripts/build_fixtures.py --month 2026-10

注意：
- 需要安装 akshare：.venv/bin/python -m pip install akshare
- 只抓取，不修改任何计算逻辑
- 失败项会记录在 manifest.json 的 failures 里，不会静默跳过
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT))

# 三只基金，覆盖三个申万一级行业，模拟一个基金投资用户的持仓结构
FUNDS = [
    {"code": "110022", "label": "易方达消费行业", "theme": "食品饮料"},
    {"code": "003095", "label": "中欧医疗健康混合", "theme": "医药生物"},
    {"code": "519674", "label": "银河创新成长混合", "theme": "电子"},
]

# 申万一级行业代码（用于行业指数与基准收益）
SW_INDUSTRIES = {
    "食品饮料": "801120",
    "医药生物": "801150",
    "电子": "801080",
}

TOP_N = 10  # 每只基金只保留前十大持仓，控制样本体积
PAUSE = 0.25  # 限速，避免触发数据源风控


def log(msg: str) -> None:
    print(msg, flush=True)


def symbol_with_market(code: str) -> str:
    """把 6 位代码补成新浪/腾讯需要的带市场前缀形式。"""
    code = str(code).zfill(6)
    if code.startswith(("60", "68", "9")):
        return f"sh{code}"
    return f"sz{code}"


def month_filter(rows: list[dict], month: str) -> list[dict]:
    return [r for r in rows if str(r.get("date", "")).startswith(month)]


def build(month: str) -> None:
    import akshare as ak  # 延迟导入，无 akshare 时其它脚本不受影响

    year = month[:4]
    OUT.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    stats: dict[str, object] = {"funds": {}, "quotes": 0, "industries": []}
    funds_payload: dict[str, dict] = {}
    quotes_payload: dict[str, dict] = {}

    # ---------- 1. 基金净值与持仓 ----------
    all_quotes: dict[str, dict] = {}
    for fund in FUNDS:
        code = fund["code"]
        log(f"== {code} {fund['label']} ==")

        try:
            nav_df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
            nav_all = [
                {"date": str(r["净值日期"]), "nav": float(r["单位净值"])}
                for _, r in nav_df.iterrows()
            ]
            nav_month = sorted(month_filter(nav_all, month), key=lambda x: x["date"])
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{code} 净值抓取失败：{type(exc).__name__}: {exc}")
            nav_month = []
        time.sleep(PAUSE)

        try:
            hold_df = ak.fund_portfolio_hold_em(symbol=code, date=year)
            if hold_df is None or hold_df.empty:
                # 持仓披露可能滞后，退到前一年
                hold_df = ak.fund_portfolio_hold_em(symbol=code, date=str(int(year) - 1))
            quarter = str(hold_df["季度"].iloc[0])
            latest = hold_df[hold_df["季度"] == quarter].copy()
            latest = latest.sort_values("占净值比例", ascending=False).head(TOP_N)
            holdings = [
                {
                    "code": str(r["股票代码"]).zfill(6),
                    "name": str(r["股票名称"]),
                    "weight": round(float(r["占净值比例"]) / 100.0, 8),
                    "industry": "",
                    "quarter": quarter,
                }
                for _, r in latest.iterrows()
            ]
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{code} 持仓抓取失败：{type(exc).__name__}: {exc}")
            quarter, holdings = "", []
        time.sleep(PAUSE)

        funds_payload[code] = {
            "fund": {"code": code, "name": fund["label"], "theme": fund["theme"]},
            "month": month,
            "nav_series": nav_month,
            "holdings": holdings,
            "disclosure_quarter": quarter,
        }
        stats["funds"][code] = {
            "nav_points": len(nav_month),
            "holdings": len(holdings),
            "quarter": quarter,
            "weight_sum": round(sum(h["weight"] for h in holdings), 6),
        }
        log(f"   净值 {len(nav_month)} 点，持仓 {len(holdings)} 只，披露期 {quarter}")

        for h in holdings:
            all_quotes.setdefault(h["code"], {"code": h["code"], "name": h["name"]})

    # ---------- 2. 个股当月行情（真实来源：新浪，失败转腾讯） ----------
    log(f"\n== 个股行情，共 {len(all_quotes)} 只 ==")
    for code, meta in sorted(all_quotes.items()):
        symbol = symbol_with_market(code)
        bars: list[dict] = []
        source = ""
        try:
            df = ak.stock_zh_a_daily(symbol=symbol, start_date=f"{month}-01", end_date=f"{month}-31")
            source = "sina"
            for _, r in df.iterrows():
                bars.append(
                    {
                        "date": str(r["date"]),
                        "open": float(r["open"]),
                        "high": float(r["high"]),
                        "low": float(r["low"]),
                        "close": float(r["close"]),
                        "volume": float(r["volume"]),
                        "amount": float(r["amount"]),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{code} 新浪行情失败：{type(exc).__name__}")
            try:
                df = ak.stock_zh_a_hist_tx(symbol=symbol, start_date=f"{month}-01", end_date=f"{month}-31")
                source = "tencent"
                for _, r in df.iterrows():
                    bars.append(
                        {
                            "date": str(r["date"]),
                            "open": float(r["open"]),
                            "high": float(r["high"]),
                            "low": float(r["low"]),
                            "close": float(r["close"]),
                            "volume": float(r["volume"]),
                            "amount": float(r["amount"]),
                        }
                    )
            except Exception as exc2:  # noqa: BLE001
                failures.append(f"{code} 腾讯行情也失败：{type(exc2).__name__}")

        bars = sorted(month_filter(bars, month), key=lambda x: x["date"])
        if bars:
            quotes_payload[code] = {
                "code": code,
                "name": meta["name"],
                "month": month,
                "source": source,
                "bars": bars,
            }
            stats["quotes"] = int(stats["quotes"]) + 1
        time.sleep(PAUSE)
    log(f"   成功 {stats['quotes']} / {len(all_quotes)} 只")

    # ---------- 3. 申万一级行业指数 ----------
    log("\n== 申万一级行业指数 ==")
    industry_payload = []
    for name, sw_code in SW_INDUSTRIES.items():
        try:
            df = ak.index_hist_sw(symbol=sw_code, period="day")
            rows = [
                {"date": str(r["日期"]), "close": float(r["收盘"]), "amount": float(r["成交额"])}
                for _, r in df.iterrows()
            ]
            rows = sorted(month_filter(rows, month), key=lambda x: x["date"])
            if rows:
                industry_payload.append({"industry": name, "sw_code": sw_code, "bars": rows})
                stats["industries"].append(name)
                log(f"   {name}（{sw_code}）：{len(rows)} 个交易日")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"行业指数 {name} 失败：{type(exc).__name__}: {exc}")
        time.sleep(PAUSE)

    (OUT / "industries.json").write_text(
        json.dumps(industry_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ---------- 4. 已知答案（验收基准） ----------
    expected = {}
    for fund in FUNDS:
        code = fund["code"]
        data = funds_payload[code]
        series = data["nav_series"]
        if len(series) < 2:
            continue
        start, end = series[0], series[-1]
        peak = series[0]["nav"]
        max_dd = 0.0
        for p in series:
            peak = max(peak, p["nav"])
            max_dd = min(max_dd, p["nav"] / peak - 1.0)
        expected[code] = {
            "name": data["fund"]["name"],
            "start_date": start["date"],
            "end_date": end["date"],
            "period_return": round(end["nav"] / start["nav"] - 1.0, 8),
            "max_drawdown": round(max_dd, 8),
            "points": len(series),
            "weight_sum_top10": round(sum(h["weight"] for h in data["holdings"]), 8),
        }
    (OUT / "expected.json").write_text(
        json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "funds.json").write_text(
        json.dumps(funds_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "quotes.json").write_text(
        json.dumps(quotes_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ---------- 5. 元信息 ----------
    manifest = {
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "month": month,
        "source": "akshare（东方财富 / 新浪财经 / 腾讯财经 / 申万宏源研究）",
        "funds": [f["code"] for f in FUNDS],
        "top_n_holdings": TOP_N,
        "stats": stats,
        "failures": failures,
        "notes": [
            "净值为单位净值，未做分红复权",
            "持仓为各基金最近一期披露的前十大，披露期可能不一致",
            "样本仅用于验收，不构成任何投资建议",
        ],
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    log("\n== 完成 ==")
    log(json.dumps(stats, ensure_ascii=False, indent=2))
    if failures:
        log(f"\n失败 {len(failures)} 项：")
        for f in failures:
            log("  - " + f)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", default="2026-10")
    args = parser.parse_args()
    build(args.month)
