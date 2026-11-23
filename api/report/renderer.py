"""月度回顾报告渲染。

纯函数：输入 ``/api/review`` 返回的 ReviewResponse 快照，输出自包含 HTML 字符串。

为什么不用模板引擎：``requirements-lock.txt`` 里没有 jinja2，引入它要改锁定文件与 CI，
而报告结构固定、区块少，用标准库字符串拼接加 ``html.escape`` 足够。

为什么在这里做而不是前端：打印样式（``@page`` 分页、表头重复）写在服务端模板里，
前端只负责调起打印，后续加 Word 等出口时改这一处即可。

约束：
- 不读文件、不访问网络、不依赖第三方库。
- 输出必须自包含：CSS 内联、SVG 内联，不引用任何外部资源，断网也能打开。
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any

from engine.attribution import DISCLAIMER as EVENT_DISCLAIMER

# 涨跌配色沿用 A 股习惯：涨红跌绿，与工作台页面保持一致。
UP_COLOR = "#C62828"
DOWN_COLOR = "#1B7F3B"
FLAT_COLOR = "#5F5E5A"

_PLUGIN_INTERVAL = "returns.interval"
_PLUGIN_BRINSON = "attribution.brinson"
_PLUGIN_EVENTS = "attribution.events"


def render(snapshot: dict[str, Any], generated_at: datetime | None = None) -> str:
    """把一次回顾快照渲染成完整 HTML 文档。"""
    fund = _dict(snapshot.get("fund"))
    month = str(snapshot.get("month") or "")
    results = _dict(snapshot.get("results"))
    nav_series = _list(snapshot.get("nav_series"))

    interval = _payload(results, _PLUGIN_INTERVAL)
    brinson = _payload(results, _PLUGIN_BRINSON)
    events = _payload(results, _PLUGIN_EVENTS)

    name = fund.get("name") or fund.get("code") or "基金"
    title = f"{name} {month} 月度回顾"
    stamp = (generated_at or datetime.now()).strftime("%Y-%m-%d %H:%M")

    body = "".join(
        [
            _header(fund, month),
            _summary_section(interval, nav_series),
            _holdings_section(_list(snapshot.get("holdings_changes"))),
            _brinson_section(brinson),
            _events_section(events),
            _errors_section(_list(snapshot.get("errors"))),
        ]
    )

    return _document(title=title, body=body, stamp=stamp, month=month)


def _document(*, title: str, body: str, stamp: str, month: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<main class="page">
{body}
<footer class="foot">
  <p>本报告由 fund-review 生成，数据来源为公开披露信息，仅供个人复盘使用，不构成投资建议。</p>
  <p class="muted">生成时间 {_esc(stamp)} · 回顾月份 {_esc(month)}</p>
</footer>
</main>
</body>
</html>
"""


def _header(fund: dict[str, Any], month: str) -> str:
    name = fund.get("name") or "未命名基金"
    code = str(fund.get("code") or "")
    meta_bits = [str(fund.get(key) or "") for key in ("type", "company")]
    meta_text = " · ".join(bit for bit in meta_bits if bit)
    return f"""<header class="head">
  <h1>{_esc(str(name))}</h1>
  <div class="head-meta">
    <span class="code">{_esc(code)}</span>
    <span>{_esc(meta_text)}</span>
    <span class="tag">{_esc(month)}</span>
  </div>
</header>
"""


def _summary_section(interval: dict[str, Any], nav_series: list[dict[str, Any]]) -> str:
    if not interval:
        empty = '<p class="empty">本期区间收益数据不可用，暂无法给出收益概况。</p>'
        return _section("收益概况", empty)

    period_return = _float(interval.get("period_return"))
    drawdown = _float(interval.get("max_drawdown"))
    start_date = _esc(str(interval.get("start_date") or ""))
    end_date = _esc(str(interval.get("end_date") or ""))
    points = interval.get("points")
    point_text = _esc(str(points)) if points else "—"

    cards = "".join(
        [
            _metric("区间收益", _pct(period_return), color=_return_color(period_return)),
            _metric("最大回撤", _pct(drawdown), color=_return_color(drawdown)),
            _metric("区间", f"{start_date} → {end_date}", small=True),
            _metric("净值点", point_text, small=True),
        ]
    )
    metrics = f'<div class="metrics">{cards}</div>'
    chart = _svg_chart(nav_series, period_return)
    return _section("收益概况", metrics + chart)


def _svg_chart(series: list[dict[str, Any]], period_return: float | None) -> str:
    """内联 SVG 净值走势。不引图表库，保证报告单文件可离线打开。"""
    values: list[float] = []
    labels: list[str] = []
    for row in series:
        nav = _float(_dict(row).get("nav"))
        if nav is None:
            continue
        values.append(nav)
        labels.append(str(_dict(row).get("date") or ""))

    if len(values) < 2:
        return '<p class="empty">净值点数不足，无法绘制走势。</p>'

    width, height, pad_x, pad_y = 640.0, 132.0, 10.0, 20.0
    low, high = min(values), max(values)
    span = (high - low) or 1.0
    step = (width - 2 * pad_x) / (len(values) - 1)
    coords: list[str] = []
    for index, nav in enumerate(values):
        x = pad_x + step * index
        y = pad_y + (height - 2 * pad_y) * (1 - (nav - low) / span)
        coords.append(f"{x:.1f},{y:.1f}")

    stroke = _return_color(period_return)
    first_label = _esc(labels[0] if labels else "")
    last_label = _esc(labels[-1] if labels else "")
    middle = f"区间净值 {_num(low, 4)} → {_num(high, 4)}"
    base_y = height - pad_y
    points_attr = " ".join(coords)

    return f"""<figure class="chart">
<svg viewBox="0 0 {width:.0f} {height:.0f}" preserveAspectRatio="none" role="img">
  <title>净值走势</title>
  <line x1="{pad_x}" y1="{base_y}" x2="{width - pad_x}" y2="{base_y}"
        stroke="#E5E1D8" stroke-width="1"/>
  <polyline fill="none" stroke="{stroke}" stroke-width="2" points="{points_attr}"/>
</svg>
<figcaption>
  <span>{first_label}</span>
  <span>{middle}</span>
  <span>{last_label}</span>
</figcaption>
</figure>
"""


def _holdings_section(changes: list[dict[str, Any]]) -> str:
    if not changes:
        return _section("持仓变动", '<p class="empty">未取得跨期持仓对比数据。</p>')

    rows: list[str] = []
    for item in changes[:10]:
        row = _dict(item)
        delta = _float(row.get("delta"))
        name = _esc(str(row.get("name") or ""))
        code = _esc(str(row.get("code") or ""))
        industry = _esc(str(row.get("industry") or "—"))
        previous = _pct(_float(row.get("previous_weight")), signed=False)
        current = _pct(_float(row.get("current_weight")), signed=False)
        rows.append(
            "<tr>"
            f"<td>{name}</td>"
            f'<td class="mono">{code}</td>'
            f"<td>{industry}</td>"
            f'<td class="num">{previous}</td>'
            f'<td class="num">{current}</td>'
            f'<td class="num" style="color:{_return_color(delta)}">{_pct(delta)}</td>'
            "</tr>"
        )

    table = (
        "<table><thead><tr>"
        "<th>名称</th><th>代码</th><th>行业</th>"
        '<th class="num">上期权重</th><th class="num">本期权重</th><th class="num">变动</th>'
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )
    return _section("持仓变动（前十大口径）", table)


def _brinson_section(brinson: dict[str, Any]) -> str:
    if not brinson:
        empty = '<p class="empty">本期归因数据未生成（可能缺少持仓或行情数据）。</p>'
        return _section("收益归因", empty)

    residual = _float(brinson.get("residual_return"))
    coverage = _float(brinson.get("coverage"))
    method = str(brinson.get("method") or "")

    cards = "".join(
        [
            _metric("未被解释收益", _pct(residual), small=True),
            _metric("持仓覆盖度", _pct(coverage, signed=False), small=True),
        ]
    )
    body = f'<div class="metrics">{cards}</div>'
    body += _industry_table(_list(brinson.get("industries")))
    body += _stock_table(_list(brinson.get("items")))
    if method:
        body += f'<p class="note">归因方法：{_esc(method)}</p>'
    return _section("收益归因", body)


def _industry_table(industries: list[Any]) -> str:
    if not industries:
        return ""
    rows: list[str] = []
    for item in industries[:8]:
        row = _dict(item)
        contribution = _float(row.get("contribution"))
        weight = _pct(_float(row.get("weight")), signed=False)
        industry = _esc(str(row.get("industry") or "未分类"))
        rows.append(
            "<tr>"
            f"<td>{industry}</td>"
            f'<td class="num">{weight}</td>'
            f'<td class="num" style="color:{_return_color(contribution)}">{_pct(contribution)}</td>'
            "</tr>"
        )
    return (
        "<h3>行业贡献</h3><table><thead><tr>"
        '<th>行业</th><th class="num">权重</th><th class="num">贡献</th>'
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _stock_table(items: list[Any]) -> str:
    if not items:
        return ""

    def magnitude(item: Any) -> float:
        return abs(_float(_dict(item).get("contribution")) or 0.0)

    rows: list[str] = []
    for item in sorted(items, key=magnitude, reverse=True)[:5]:
        row = _dict(item)
        contribution = _float(row.get("contribution"))
        period_return = _pct(_float(row.get("period_return")))
        name = _esc(str(row.get("name") or ""))
        industry = _esc(str(row.get("industry") or "—"))
        rows.append(
            "<tr>"
            f"<td>{name}</td>"
            f"<td>{industry}</td>"
            f'<td class="num">{period_return}</td>'
            f'<td class="num" style="color:{_return_color(contribution)}">{_pct(contribution)}</td>'
            "</tr>"
        )
    return (
        "<h3>个股贡献（绝对值前五）</h3><table><thead><tr>"
        '<th>名称</th><th>行业</th><th class="num">区间涨跌</th><th class="num">贡献</th>'
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _events_section(events: dict[str, Any]) -> str:
    items = _list(events.get("items"))
    if not items:
        return _section("相关事件", f'<p class="empty">{_esc(EVENT_DISCLAIMER)}</p>')

    rows: list[str] = []
    for item in items[:12]:
        row = _dict(item)
        url = str(row.get("url") or "")
        title = _esc(str(row.get("title") or ""))
        date_text = _esc(str(row.get("date") or ""))
        related = _esc(str(row.get("related_code") or "—"))
        linked = f'<a href="{_esc(url)}">{title}</a>' if url else title
        rows.append(
            f'<tr><td class="nowrap">{date_text}</td><td>{linked}</td><td>{related}</td></tr>'
        )
    table = (
        "<table><thead><tr>"
        '<th style="width:88px">日期</th><th>公告</th><th style="width:76px">相关代码</th>'
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )
    return _section("相关事件", table + f'<p class="note">{_esc(EVENT_DISCLAIMER)}</p>')


def _errors_section(errors: list[Any]) -> str:
    if not errors:
        return ""
    items = "".join(f"<li>{_esc(str(item))}</li>" for item in errors)
    return _section("数据说明", f'<ul class="issues">{items}</ul>')


def _metric(label: str, value_html: str, *, small: bool = False, color: str | None = None) -> str:
    classes = "metric-value small" if small else "metric-value"
    style = f' style="color:{color}"' if color else ""
    return (
        '<div class="metric">'
        f'<div class="metric-label">{_esc(label)}</div>'
        f'<div class="{classes}"{style}>{value_html}</div>'
        "</div>"
    )


def _section(title: str, body: str) -> str:
    return f'<section class="block"><h2>{_esc(title)}</h2>{body}</section>\n'


def _payload(results: dict[str, Any], plugin_id: str) -> dict[str, Any]:
    item = _dict(results.get(plugin_id))
    if item.get("status") != "ready":
        return {}
    return _dict(item.get("data"))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _pct(value: float | None, *, digits: int = 2, signed: bool = True) -> str:
    if value is None:
        return "—"
    text = f"{value * 100:.{digits}f}%"
    return f"+{text}" if signed and value > 0 else text


def _num(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _return_color(value: float | None) -> str:
    if value is None or value == 0:
        return FLAT_COLOR
    return UP_COLOR if value > 0 else DOWN_COLOR


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
  margin: 0; padding: 0; background: #fff; color: #2C2C2A;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB",
    "Microsoft YaHei", "Source Han Sans SC", "Noto Sans CJK SC", sans-serif;
  font-size: 12px; line-height: 1.6;
}
.page { max-width: 760px; margin: 0 auto; padding: 20px 22px 26px; }
.head { border-bottom: 2px solid #2C2C2A; padding-bottom: 10px; margin-bottom: 14px; }
h1 { margin: 0 0 6px; font-size: 20px; font-weight: 600; letter-spacing: 0.2px; }
.head-meta {
  display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
  color: #5F5E5A; font-size: 11px;
}
.code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #2C2C2A; }
.tag { border: 1px solid #B4B2A9; border-radius: 3px; padding: 1px 6px; }
.block { margin: 0 0 15px; page-break-inside: avoid; }
h2 {
  font-size: 13px; font-weight: 600; margin: 0 0 10px;
  padding-left: 8px; border-left: 3px solid #2C2C2A;
}
h3 { font-size: 12px; font-weight: 600; margin: 14px 0 6px; color: #444441; }
.metrics { display: flex; flex-wrap: wrap; gap: 24px; margin-bottom: 12px; }
.metric-label { font-size: 11px; color: #888780; }
.metric-value {
  font-size: 19px; font-weight: 600;
  font-family: ui-monospace, Menlo, monospace;
}
.metric-value.small { font-size: 13px; font-weight: 500; }
table { width: 100%; border-collapse: collapse; font-size: 11px; }
th, td {
  border-bottom: 1px solid #E5E1D8; padding: 6px 8px;
  text-align: left; vertical-align: top;
}
th { background: #F1EFE8; font-weight: 600; color: #444441; white-space: nowrap; }
.num {
  text-align: right; white-space: nowrap;
  font-family: ui-monospace, Menlo, monospace;
}
.mono { font-family: ui-monospace, Menlo, monospace; }
.nowrap { white-space: nowrap; }
.chart { margin: 10px 0 0; }
.chart svg { width: 100%; height: 132px; display: block; }
.chart figcaption {
  display: flex; justify-content: space-between;
  font-size: 10px; color: #888780; margin-top: 4px;
}
.empty { color: #888780; margin: 0; }
.note { font-size: 10px; color: #888780; margin: 8px 0 0; line-height: 1.5; }
.issues { margin: 0; padding-left: 18px; font-size: 11px; color: #854F0B; }
a { color: #185FA5; text-decoration: none; }
.foot {
  border-top: 1px solid #E5E1D8; margin-top: 14px; padding-top: 8px;
  font-size: 10px; color: #5F5E5A;
}
.foot p { margin: 2px 0; }
.muted { color: #888780; }
@page { size: A4; margin: 16mm 14mm; }
@media print {
  body { font-size: 11.5px; }
  .page { max-width: none; padding: 0; }
  thead { display: table-header-group; }
  tr, .block, .metrics { page-break-inside: avoid; }
  a { color: #2C2C2A; }
}
"""
