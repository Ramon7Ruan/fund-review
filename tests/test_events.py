"""事件陈列：四条准入门槛、空状态、文案约束。"""

from __future__ import annotations

from engine.attribution import DISCLAIMER, EMPTY_TEXT, filter_events, has_advice_language
from engine.plugins.attribution_events.plugin import run as run_events
from engine.runtime import PluginContext


def _event(code: str, title: str, date: str, url: str) -> dict:
    return {
        "code": code,
        "title": title,
        "date": date,
        "url": url,
        "event_type": "stock_notice",
    }


def test_filter_keeps_only_direct_and_traceable():
    events = [
        _event("600519", "持仓公司季报", "2026-10-28", "https://data.eastmoney.com/a.html"),
        _event("110022", "基金分红公告", "2026-10-20", "https://fund.eastmoney.com/b.html"),
        _event("000001", "与持仓无关", "2026-10-28", "https://data.eastmoney.com/c.html"),
        _event("600519", "没有原文链接", "2026-10-28", ""),
        _event("600519", "没有日期", "", "https://data.eastmoney.com/d.html"),
        _event("600519", "持仓公司季报", "2026-10-28", "https://data.eastmoney.com/a.html"),
    ]

    kept, dropped = filter_events(events, "110022", ["600519"], "2026-10")

    assert [item.title for item in kept] == ["持仓公司季报", "基金分红公告"]
    assert kept[0].date > kept[1].date
    assert dropped == 4


def test_filter_requires_month_match():
    events = [
        _event("600519", "上月公告", "2026-09-30", "https://data.eastmoney.com/a.html"),
        _event("600519", "本月公告", "2026-10-08", "https://data.eastmoney.com/a.html"),
    ]
    kept, dropped = filter_events(events, "110022", ["600519"], "2026-10")
    assert [item.title for item in kept] == ["本月公告"]
    assert dropped == 1


def test_source_is_derived_from_url():
    kept, _ = filter_events(
        [
            _event("600519", "个股公告", "2026-10-28", "https://data.eastmoney.com/a.html"),
            _event("110022", "基金公告", "2026-10-28", "https://fund.eastmoney.com/b.html"),
        ],
        "110022",
        ["600519"],
        "2026-10",
    )
    assert {item.source for item in kept} == {"东方财富", "天天基金"}


def test_plugin_empty_state_is_explicit():
    result = run_events(
        PluginContext(
            fund={"code": "110022"},
            month="2026-10",
            data={"events": [], "holdings": []},
        )
    )
    assert result.status == "ready"
    assert result.data["count"] == 0
    assert result.data["items"] == []
    assert EMPTY_TEXT in result.notes
    assert DISCLAIMER in result.notes


def test_plugin_filters_injected_events():
    events = [
        _event("600519", "持仓公司季报", "2026-10-28", "https://data.eastmoney.com/a.html"),
        _event("000001", "与持仓无关", "2026-10-28", "https://data.eastmoney.com/c.html"),
    ]
    result = run_events(
        PluginContext(
            fund={"code": "110022"},
            month="2026-10",
            data={"events": events, "holdings": [{"code": "600519", "weight": 0.1}]},
        )
    )
    assert result.data["count"] == 1
    assert result.data["dropped"] == 1
    assert result.data["items"][0]["related_code"] == "600519"


def test_notes_have_no_causal_or_advice_language():
    result = run_events(
        PluginContext(
            fund={"code": "110022"},
            month="2026-10",
            data={
                "events": [
                    _event("600519", "季报", "2026-10-28", "https://data.eastmoney.com/a.html")
                ],
                "holdings": [{"code": "600519", "weight": 0.1}],
            },
        )
    )
    for note in result.notes:
        if note == DISCLAIMER:
            continue
        assert not has_advice_language(note), note


def test_advice_language_detector():
    assert has_advice_language("该事件导致净值上涨")
    assert has_advice_language("利好消费板块")
    assert not has_advice_language(DISCLAIMER)
