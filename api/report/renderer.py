"""月度回顾报告渲染。

纯函数：输入 ``/api/review`` 返回的 ReviewResponse 快照，输出自包含 HTML 字符串。

为什么不用模板引擎：``requirements-lock.txt`` 里没有 jinja2，引入它要改锁定文件与 CI，
而报告结构固定、区块少，用标准库字符串拼接加 ``html.escape`` 足够。

为什么在这里做而不是前端：打印样式（``@page`` 分页、表头重复）写在服务端模板里，
前端只负责调起打印，后续加 Word 等出口时改这一处即可。

数字一致性：所有已由插件算出的指标（区间收益、最大回撤、归因、涨跌天数）都直接取自
``results``，本模块**不重新计算**这些数；只有持仓合计权重这类就地汇总会标明口径。

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
_PLUGIN_MOMENTUM = "example.momentum_summary"

_SOURCE_LABELS = {
    "nav": "基金净值",
    "holdings": "持仓明细",
    "quotes": "个股行情",
    "industry_map": "行业映射",
    "benchmark_returns": "行业指数",
    "events": "公开公告",
}


def render(snapshot: dict[str, Any], generated_at: datetime | None = None) -> str:
    """把一次回顾快照渲染成完整 HTML 文档。"""
    fund = _dict(snapshot.get("fund"))
    month = str(snapshot.get("month") or "")
    results = _dict(snapshot.get("results"))
    nav_series = _list(snapshot.get("nav_series"))
    holdings = _list(snapshot.get("holdings"))
    errors = _list(snapshot.get("errors"))
    meta = _dict(snapshot.get("meta"))

    interval = _payload(results, _PLUGIN_INTERVAL)
    brinson = _payload(results, _PLUGIN_BRINSON)
    events = _payload(results, _PLUGIN_EVENTS)
    momentum = _payload(results, _PLUGIN_MOMENTUM)

    name = fund.get("name") or fund.get("code") or "基金"
    title = f"{name} {month} 月度回顾"
    stamp = (generated_at or datetime.now()).strftime("%Y-%m-%d %H:%M")

    body = "".join(
        [
            _header(fund, month),
            _lede_section(interval, momentum, nav_series),
            _profile_section(fund, month, interval, meta),
            _nav_section(interval, nav_series),
            _momentum_section(momentum),
            _holdings_section(holdings, _dict(snapshot.get("holdings_compare"))),
            _changes_section(_list(snapshot.get("holdings_changes"))),
            _brinson_section(brinson),
            _events_section(events),
            _source_section(meta, results),
            _errors_section(errors),
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
  <p>本报告由 fund-review 生成，数据取自公开披露信息，仅供个人复盘使用，不构成投资建议。</p>
  <p class="muted">生成时间 {_esc(stamp)} · 回顾月份 {_esc(month)} · 指标与工作台页面同源</p>
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
  <div class="head-top">
    <h1>{_esc(str(name))}</h1>
    <span class="tag">{_esc(month)}</span>
  </div>
  <div class="head-meta">
    <span class="code">{_esc(code)}</span>
    <span>{_esc(meta_text)}</span>
    <span>月度投资回顾</span>
  </div>
</header>
"""


def _lede_section(
    interval: dict[str, Any], momentum: dict[str, Any], nav_series: list[dict[str, Any]]
) -> str:
    """开篇摘要：用事实陈述说清本月最重要的几个数，不做判断、不给建议。"""
    if not interval:
        lead = "本期净值数据不可用，报告仅呈现可获得的持仓与事件信息。"
        return f'<p class="lede">{_esc(lead)}</p>'

    period_return = _float(interval.get("period_return"))
    drawdown = _float(interval.get("max_drawdown"))
    start_date = str(interval.get("start_date") or "")
    end_date = str(interval.get("end_date") or "")
    start_nav = _num(_float(interval.get("start_nav")), 4)
    end_nav = _num(_float(interval.get("end_nav")), 4)

    parts = [
        f"报告期内（{start_date} 至 {end_date}）单位净值由 {start_nav} 变为 {end_nav}",
        f"区间收益 {_pct(period_return)}",
        f"最大回撤 {_pct(drawdown)}",
    ]
    up = momentum.get("up_days")
    down = momentum.get("down_days")
    if up is not None and down is not None:
        parts.append(f"上涨 {up} 天、下跌 {down} 天")

    lead = "，".join(parts) + "。"
    chips = "".join(
        [
            _chip("区间收益", _pct(period_return), _return_color(period_return)),
            _chip("最大回撤", _pct(drawdown), _return_color(drawdown)),
            _chip("净值", f"{start_nav} → {end_nav}", FLAT_COLOR),
            _chip("净值点", str(len(nav_series)), FLAT_COLOR),
        ]
    )
    return f'<p class="lede">{_esc(lead)}</p><div class="chips">{chips}</div>'


def _profile_section(
    fund: dict[str, Any], month: str, interval: dict[str, Any], meta: dict[str, Any]
) -> str:
    nav_meta = _dict(meta.get("nav"))
    nav_start = str(interval.get("start_date") or "—")
    nav_end = str(interval.get("end_date") or "—")
    points = nav_meta.get("month_points") or interval.get("points") or "—"
    cached = "本地缓存" if nav_meta.get("cached") else "本次抓取"
    rows = [
        ("基金名称", str(fund.get("name") or "—")),
        ("基金代码", str(fund.get("code") or "—")),
        ("基金类型", str(fund.get("type") or "—")),
        ("管理公司", str(fund.get("company") or "—")),
        ("回顾月份", month or "—"),
        ("净值区间", f"{nav_start} 至 {nav_end}"),
        ("净值点数", str(points)),
        ("数据状态", cached),
    ]
    return _section("基金信息", _kv_table(rows))


def _nav_section(interval: dict[str, Any], nav_series: list[dict[str, Any]]) -> str:
    if not interval:
        return _section("净值表现", '<p class="empty">本期区间收益数据不可用。</p>')

    period_return = _float(interval.get("period_return"))
    drawdown = _float(interval.get("max_drawdown"))
    cards = "".join(
        [
            _metric("区间收益", _pct(period_return), color=_return_color(period_return)),
            _metric("最大回撤", _pct(drawdown), color=_return_color(drawdown)),
            _metric("期初净值", _num(_float(interval.get("start_nav")), 4), small=True),
            _metric("期末净值", _num(_float(interval.get("end_nav")), 4), small=True),
        ]
    )
    body = f'<div class="metrics">{cards}</div>'
    body += _svg_chart(nav_series, period_return)
    body += '<p class="note">走势按报告期内每个披露日绘制，缺口为节假日与非披露日。</p>'
    return _section("净值表现", body)


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

    width, height, pad_x, pad_y = 640.0, 150.0, 10.0, 18.0
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


def _momentum_section(momentum: dict[str, Any]) -> str:
    if not momentum:
        return _section("涨跌统计", '<p class="empty">本期涨跌天数统计未生成。</p>')

    up = _int(momentum.get("up_days"))
    down = _int(momentum.get("down_days"))
    flat = _int(momentum.get("flat_days"))
    total = _int(momentum.get("trading_days"))
    ratio = _float(momentum.get("up_ratio"))
    best = _float(momentum.get("best_day"))
    worst = _float(momentum.get("worst_day"))

    cards = "".join(
        [
            _metric("上涨天数", str(up), color=UP_COLOR),
            _metric("下跌天数", str(down), color=DOWN_COLOR),
            _metric("平盘天数", str(flat), color=FLAT_COLOR),
            _metric("上涨占比", _pct(ratio, signed=False), small=True),
            _metric("单日最佳", _pct(best), small=True, color=_return_color(best)),
            _metric("单日最差", _pct(worst), small=True, color=_return_color(worst)),
        ]
    )
    note = f'<p class="note">按相邻披露日净值变动统计，共 {total} 个变动区间。</p>'
    return _section("涨跌统计", f'<div class="metrics">{cards}</div>' + note)


def _holdings_section(holdings: list[Any], compare: dict[str, Any]) -> str:
    if not holdings:
        return _section("持仓明细", '<p class="empty">本期未取得持仓数据。</p>')

    rows: list[str] = []
    total_weight = 0.0
    for index, item in enumerate(holdings[:10], start=1):
        row = _dict(item)
        weight = _float(row.get("weight")) or 0.0
        total_weight += weight
        name = _esc(str(row.get("name") or ""))
        code = _esc(str(row.get("code") or ""))
        industry = _esc(str(row.get("industry") or "未分类"))
        rows.append(
            "<tr>"
            f'<td class="idx">{index}</td>'
            f"<td>{name}</td>"
            f'<td class="mono">{code}</td>'
            f"<td>{industry}</td>"
            f'<td class="num">{_pct(weight, signed=False)}</td>'
            "</tr>"
        )

    table = (
        "<table><thead><tr>"
        '<th style="width:36px">#</th><th>名称</th><th>代码</th><th>行业</th>'
        '<th class="num">权重</th>'
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )

    bits = [f"前十大合计权重 {_pct(total_weight, signed=False)}"]
    if len(holdings) > 10:
        bits.append(f"页面披露 {len(holdings)} 条，此处按前十大取 10 条")
    quarter = compare.get("current_quarter")
    if quarter:
        bits.append(f"披露期次 {quarter}")
    body = table + f'<p class="note">{" · ".join(_esc(x) for x in bits)}</p>'
    note = compare.get("note")
    if note:
        body += f'<p class="note">{_esc(str(note))}</p>'
    return _section("持仓明细（前十大）", body)


def _changes_section(changes: list[dict[str, Any]]) -> str:
    if not changes:
        return _section("持仓变动", '<p class="empty">未取得跨期持仓对比数据。</p>')

    rows: list[str] = []
    for item in changes:
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
    return _section("持仓变动（前十大同口径）", table)


def _brinson_section(brinson: dict[str, Any]) -> str:
    if not brinson:
        empty = '<p class="empty">本期归因数据未生成（可能缺少持仓或行情数据）。</p>'
        return _section("收益归因", empty)

    fund_return = _float(brinson.get("fund_return"))
    contribution = _float(brinson.get("total_contribution"))
    residual = _float(brinson.get("residual_return"))
    coverage = _float(brinson.get("coverage"))
    method = str(brinson.get("method") or "")

    cards = "".join(
        [
            _metric("基金区间收益", _pct(fund_return), color=_return_color(fund_return)),
            _metric("持仓贡献合计", _pct(contribution), color=_return_color(contribution)),
            _metric("未被解释收益", _pct(residual), small=True),
            _metric("持仓覆盖度", _pct(coverage, signed=False), small=True),
        ]
    )

    body = f'<div class="metrics">{cards}</div>'
    body += _industry_table(_list(brinson.get("industries")))
    body += _stock_table(_list(brinson.get("items")))
    check = (
        " + ".join([_pct(contribution, signed=False), _pct(residual, signed=False)])
        + " = "
        + _pct(fund_return, signed=False)
    )
    tail = "归因方法 " + method + "。持仓贡献合计与未被解释收益之和等于基金区间收益："
    body += f'<p class="note">{_esc(tail + check)}，可自行对账。</p>'
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

    total = len(items)
    shown = items[:12]
    rows: list[str] = []
    for item in shown:
        row = _dict(item)
        url = _safe_url(str(row.get("url") or ""))
        title = _esc(str(row.get("title") or ""))
        date_text = _esc(str(row.get("date") or ""))
        related = _esc(str(row.get("related_code") or "—"))
        source = _esc(str(row.get("source") or ""))
        linked = (
            f'<a href="{_esc(url)}" target="_blank" rel="noopener noreferrer">{title}</a>'
            if url
            else title
        )
        rows.append(
            "<tr>"
            f'<td class="nowrap">{date_text}</td>'
            f"<td>{linked}</td>"
            f'<td class="mono">{related}</td>'
            f"<td>{source}</td>"
            "</tr>"
        )

    table = (
        "<table><thead><tr>"
        '<th style="width:78px">日期</th><th>公告标题</th>'
        '<th style="width:76px">相关代码</th><th style="width:70px">来源</th>'
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )
    parts = [EVENT_DISCLAIMER]
    dropped = events.get("dropped")
    if dropped:
        parts.append(f"另有 {dropped} 条未通过可核验筛选，未展示。")
    if total > len(shown):
        parts.append(f"共 {total} 条可展示事件，此处列出最近 {len(shown)} 条。")
    body = table + f'<p class="note">{_esc(" ".join(parts))}</p>'
    return _section("相关事件", body)


def _source_section(meta: dict[str, Any], results: dict[str, Any]) -> str:
    rows: list[tuple[str, str, str]] = []
    for key, label in _SOURCE_LABELS.items():
        info = _dict(meta.get(key))
        if not info:
            continue
        source = str(info.get("source") or "—")
        cached = "缓存" if info.get("cached") else "实时"
        count = info.get("count")
        total_points = info.get("total_points")
        missing = _list(info.get("missing"))
        extra: list[str] = []
        if count is not None:
            extra.append(f"{count} 条")
        if total_points is not None:
            extra.append(f"{total_points} 点")
        if missing:
            extra.append(f"缺失 {len(missing)} 项")
        detail = "，".join(extra) if extra else "—"
        rows.append((label, f"{source}（{cached}）", detail))

    if not rows:
        return ""

    body_rows = "".join(
        f"<tr><td>{_esc(a)}</td><td>{_esc(b)}</td><td>{_esc(c)}</td></tr>" for a, b, c in rows
    )
    table = (
        "<table><thead><tr>"
        '<th style="width:84px">数据项</th><th style="width:170px">来源</th><th>明细</th>'
        "</tr></thead><tbody>" + body_rows + "</tbody></table>"
    )

    skipped: list[str] = []
    for plugin_id, payload in results.items():
        item = _dict(payload)
        status = str(item.get("status") or "")
        if status == "ready":
            continue
        label = str(item.get("title") or plugin_id)
        reason = str(item.get("error") or "")
        skipped.append(label + "（" + status + ("：" + reason if reason else "") + "）")

    body = table
    if skipped:
        joined = "；".join(skipped)
        body += f'<p class="note">本次未能生成的功能：{_esc(joined)}</p>'
    return _section("数据来源与口径", body)


def _errors_section(errors: list[Any]) -> str:
    if not errors:
        return ""
    items = "".join(f"<li>{_esc(str(item))}</li>" for item in errors)
    return _section("数据处理说明", f'<ul class="issues">{items}</ul>')


def _kv_table(rows: list[tuple[str, str]]) -> str:
    body = "".join(
        f'<tr><th class="kv">{_esc(label)}</th><td>{_esc(value)}</td></tr>' for label, value in rows
    )
    return f'<table class="kv-table"><tbody>{body}</tbody></table>'


def _chip(label: str, value: str, color: str) -> str:
    return (
        '<div class="chip">'
        f'<span class="chip-label">{_esc(label)}</span>'
        f'<span class="chip-value" style="color:{color}">{_esc(value)}</span>'
        "</div>"
    )


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


def _int(value: Any) -> int:
    number = _float(value)
    return int(number) if number is not None else 0


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


def _safe_url(value: str) -> str:
    """只允许 http/https 链接；其他协议返回空串，按纯文本渲染。"""
    url = value.strip()
    return url if url.startswith(("http://", "https://")) else ""


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
  margin: 0; padding: 0; background: #fff; color: #2C2C2A;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB",
    "Microsoft YaHei", "Source Han Sans SC", "Noto Sans CJK SC", sans-serif;
  font-size: 12px; line-height: 1.62;
}
.page { max-width: 760px; margin: 0 auto; padding: 18px 22px 24px; }
.head { border-bottom: 2px solid #2C2C2A; padding-bottom: 9px; margin-bottom: 12px; }
.head-top { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
h1 { margin: 0; font-size: 19px; font-weight: 600; letter-spacing: 0.2px; }
.head-meta {
  display: flex; flex-wrap: wrap; gap: 9px; align-items: center;
  color: #5F5E5A; font-size: 11px; margin-top: 4px;
}
.code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #2C2C2A; }
.tag { border: 1px solid #B4B2A9; border-radius: 3px; padding: 1px 6px; font-size: 10.5px; }
.lede {
  margin: 0 0 9px; font-size: 12.5px; line-height: 1.7;
  padding: 9px 12px; background: #F7F5F0; border-left: 3px solid #B4B2A9;
}
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 15px; }
.chip {
  display: flex; align-items: baseline; gap: 6px;
  border: 1px solid #E5E1D8; border-radius: 4px; padding: 4px 9px;
}
.chip-label { font-size: 10.5px; color: #888780; }
.chip-value { font-size: 12.5px; font-weight: 600; font-family: ui-monospace, Menlo, monospace; }
.block { margin: 0 0 14px; page-break-inside: avoid; }
h2 {
  font-size: 12.5px; font-weight: 600; margin: 0 0 7px;
  padding-left: 8px; border-left: 3px solid #2C2C2A;
}
h3 { font-size: 11.5px; font-weight: 600; margin: 11px 0 5px; color: #444441; }
.metrics { display: flex; flex-wrap: wrap; gap: 20px; margin-bottom: 7px; }
.metric-label { font-size: 10.5px; color: #888780; }
.metric-value {
  font-size: 17px; font-weight: 600;
  font-family: ui-monospace, Menlo, monospace; line-height: 1.3;
}
.metric-value.small { font-size: 12.5px; font-weight: 500; }
table { width: 100%; border-collapse: collapse; font-size: 11px; }
th, td {
  border-bottom: 1px solid #E5E1D8; padding: 4px 7px;
  text-align: left; vertical-align: top;
}
th { background: #F1EFE8; font-weight: 600; color: #444441; white-space: nowrap; }
.kv-table th.kv { width: 84px; background: #F7F5F0; font-weight: 500; color: #5F5E5A; }
.num {
  text-align: right; white-space: nowrap;
  font-family: ui-monospace, Menlo, monospace;
}
.idx { color: #888780; font-family: ui-monospace, Menlo, monospace; }
.mono { font-family: ui-monospace, Menlo, monospace; }
.nowrap { white-space: nowrap; }
.chart { margin: 7px 0 0; }
.chart svg { width: 100%; height: 150px; display: block; }
.chart figcaption {
  display: flex; justify-content: space-between;
  font-size: 10px; color: #888780; margin-top: 3px;
}
.empty { color: #888780; margin: 0; }
.note { font-size: 10px; color: #888780; margin: 6px 0 0; line-height: 1.55; }
.issues { margin: 0; padding-left: 18px; font-size: 11px; color: #854F0B; }
a { color: #185FA5; text-decoration: none; }
.foot {
  border-top: 1px solid #E5E1D8; margin-top: 12px; padding-top: 8px;
  font-size: 9.5px; color: #5F5E5A;
}
.foot p { margin: 2px 0; }
.muted { color: #888780; }
@page { size: A4; margin: 13mm 12mm; }
@media print {
  body { font-size: 11px; }
  .page { max-width: none; padding: 0; }
  thead { display: table-header-group; }
  tr, .block, .metrics, .chips { page-break-inside: avoid; }
  h2, h3 { page-break-after: avoid; }
  a { color: #2C2C2A; }
}
"""
