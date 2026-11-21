"""事件陈列：只保留可溯源、直接相关、时间可确认的公开事件。

四条准入门槛（见 docs/归因口径.md）：
  1. 有 http(s) 原文链接与来源
  2. related_code 是本基金或本基金披露持仓
  3. 日期可解析且落在回顾月份内
  4. 同一事件只出现一次

不排序重要程度、不标注正负面、不参与任何收益计算。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

DISCLAIMER = "事件与涨跌同时出现只代表时间上的相关性，不代表因果关系，不构成投资建议。"
EMPTY_TEXT = "本期未检索到与持仓直接相关且可核验的公开事件"

# 只用于扫描我们自己写的说明文案，不用于过滤公告原文标题
ADVICE_TERMS = (
    "导致",
    "因此",
    "所以",
    "利好",
    "利空",
    "建议买",
    "建议卖",
    "建议持有",
    "预计上涨",
    "预计下跌",
    "有望",
    "大概率",
    "主力",
    "抄底",
    "跑赢",
    "看好",
)


@dataclass(frozen=True)
class EventItem:
    """一条通过准入的事件。字段与契约登记的 events 键一致。"""

    date: str
    title: str
    url: str
    source: str
    related_code: str
    event_type: str = "stock_notice"


def has_advice_language(text: str) -> bool:
    """是否出现因果断言、涨跌定性或操作建议。"""
    return any(term in text for term in ADVICE_TERMS)


def _is_http(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def _source_of(url: str) -> str:
    if "fund.eastmoney.com" in url:
        return "天天基金"
    if "eastmoney.com" in url:
        return "东方财富"
    return "公开来源"


def filter_events(
    events: Sequence[dict[str, Any]],
    fund_code: str,
    holding_codes: Sequence[str],
    month: str,
) -> tuple[list[EventItem], int]:
    """按四条门槛过滤并去重。返回 (保留事件, 丢弃条数)。

    丢弃条数必须展示给用户，让“少展示”本身可被检查。
    """
    allowed = {str(fund_code).zfill(6)} | {str(c).zfill(6) for c in holding_codes}
    seen: set[tuple[str, str, str]] = set()
    kept: list[EventItem] = []
    dropped = 0

    for raw in events:
        title = str(raw.get("title") or "").strip()
        url = str(raw.get("url") or "").strip()
        code = str(raw.get("related_code") or raw.get("code") or "").zfill(6)
        date = str(raw.get("date") or "").strip()

        if not title or not _is_http(url) or not date.startswith(month) or code not in allowed:
            dropped += 1
            continue

        key = (date, title, url)
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        kept.append(
            EventItem(
                date=date,
                title=title,
                url=url,
                source=_source_of(url),
                related_code=code,
                event_type=str(raw.get("event_type") or "stock_notice"),
            )
        )

    kept.sort(key=lambda item: (item.date, item.title), reverse=True)
    return kept, dropped
