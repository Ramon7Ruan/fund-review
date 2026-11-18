"""Issue #1：时点持仓、净值导入与重复数据防护。"""

from __future__ import annotations

import pytest

from data_pipeline.fund_store import FundDataStore

HOLDINGS = """fund_code,as_of,stock_code,stock_name,weight
110022,2026-09-30,600519,贵州茅台,0.40
110022,2026-09-30,000333,美的集团,0.30
110022,2026-10-30,600519,贵州茅台,0.35
110022,2026-10-30,000333,美的集团,0.34
"""

NAV = """fund_code,date,unit_nav,dividend_per_share
110022,2026-09-30,1.00,0
110022,2026-10-15,0.90,0.20
110022,2026-10-30,0.99,0
"""


def test_monthly_snapshots_are_dated_and_reimport_is_idempotent(tmp_path) -> None:
    store = FundDataStore(tmp_path / "fund.db")
    assert store.import_holdings_csv(HOLDINGS.encode("utf-8-sig")) == {
        "imported": 2,
        "unchanged": 0,
    }
    assert store.import_holdings_csv(HOLDINGS) == {"imported": 0, "unchanged": 2}
    month = store.month_snapshots("110022", "2026-10")
    assert month["start"]["as_of"] == "2026-09-30"
    assert month["end"]["as_of"] == "2026-10-30"
    assert month["start"]["positions"][0]["weight"] == 0.4
    assert month["end"]["positions"][0]["weight"] == 0.35
    assert store.month_snapshots("110022", "2026-11")["end"] is None
    store.close()


def test_conflicting_snapshot_rolls_back_whole_import(tmp_path) -> None:
    store = FundDataStore(tmp_path / "fund.db")
    store.import_holdings_csv(HOLDINGS)
    conflict = """fund_code,as_of,stock_code,stock_name,weight
110022,2026-11-30,600519,贵州茅台,0.20
110022,2026-10-30,600519,贵州茅台,0.50
"""
    with pytest.raises(ValueError, match="拒绝覆盖"):
        store.import_holdings_csv(conflict)
    assert store.snapshot("110022", "2026-11-30") is None
    store.close()


def test_nav_import_is_idempotent_and_conflicts_are_rejected(tmp_path) -> None:
    store = FundDataStore(tmp_path / "fund.db")
    assert store.import_nav_csv(NAV) == {"imported": 3, "unchanged": 0}
    assert store.import_nav_csv(NAV) == {"imported": 0, "unchanged": 3}
    assert store.nav_series("110022")[1]["dividend_per_share"] == 0.2
    with pytest.raises(ValueError, match="拒绝覆盖"):
        store.import_nav_csv(NAV.replace("0.90,0.20", "0.90,0.10"))
    store.close()


def test_invalid_weight_and_duplicate_stock_are_rejected(tmp_path) -> None:
    store = FundDataStore(tmp_path / "fund.db")
    with pytest.raises(ValueError, match="0 到 1"):
        store.import_holdings_csv(HOLDINGS.replace("0.40", "40"))
    with pytest.raises(ValueError, match="重复"):
        store.import_holdings_csv(HOLDINGS + "110022,2026-09-30,600519,贵州茅台,0.20\n")
    assert store.snapshot("110022", "2026-09-30") is None
    store.close()


def test_nav_import_requires_explicit_dividend_column(tmp_path) -> None:
    store = FundDataStore(tmp_path / "fund.db")
    with pytest.raises(ValueError, match="dividend_per_share"):
        store.import_nav_csv("fund_code,date,unit_nav\n110022,2026-10-30,1.0\n")
    store.close()
