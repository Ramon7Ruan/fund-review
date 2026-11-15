"""异动检测实现。

v0.1 为占位：接口已固定，规则实现由插件接入。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from engine.screening.types import Anomaly, AnomalyRule


def detect_anomalies(
    quotes: Mapping[str, Sequence[Mapping[str, object]]],
    rule: AnomalyRule | None = None,
) -> tuple[Anomaly, ...]:
    """按规则筛选异动。

    参数：
        quotes: 键为标的代码，值为按日期升序的行情记录（至少含 date/close/amount）。
        rule: 阈值，缺省使用 AnomalyRule 默认值。

    说明：
        价格、量能、相对、行业四类规则由接入方实现。
        本函数在 v0.1 只保证接口稳定。
    """
    raise NotImplementedError("异动检测尚未接入，见 engine/screening/_template.py")
