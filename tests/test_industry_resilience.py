"""行业映射的降级与退避：失败不拖慢后续请求，快照可兜底。"""

from __future__ import annotations

import json

import pytest

import data_pipeline.service as service_module
from data_pipeline.cache.store import MemoryCache
from data_pipeline.service import DataService
from data_pipeline.sources import akshare_source
from data_pipeline.sources.akshare_source import SourceUnavailable


@pytest.fixture
def service():
    svc = DataService(cache=MemoryCache())
    yield svc
    svc.close()


def _offline():
    raise SourceUnavailable("down")


def test_backoff_after_full_failure(service, monkeypatch, tmp_path):
    monkeypatch.setattr(service_module, "INDUSTRY_SNAPSHOT_PATH", tmp_path / "missing.json")
    calls: list[int] = []

    def fail():
        calls.append(1)
        raise SourceUnavailable("down")

    monkeypatch.setattr(akshare_source, "fetch_sw_industries", fail)

    with pytest.raises(SourceUnavailable):
        service.get_industry_map(["600519"])
    with pytest.raises(SourceUnavailable, match="退避"):
        service.get_industry_map(["600519"])

    assert len(calls) == 1, "退避窗口内不应再次遍历行业"


def test_snapshot_fallback_is_traceable(service, monkeypatch, tmp_path):
    snapshot = tmp_path / "sw.json"
    snapshot.write_text(
        json.dumps(
            {"as_of": "2026-11-21", "source": "akshare.sw", "map": {"600519": "食品饮料"}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(service_module, "INDUSTRY_SNAPSHOT_PATH", snapshot)
    monkeypatch.setattr(akshare_source, "fetch_sw_industries", _offline)

    mapping, meta = service.get_industry_map(["600519"])

    assert mapping == {"600519": "食品饮料"}
    assert meta["source"].startswith("snapshot:")
    assert meta["as_of"] == "2026-11-21"
    assert "快照" in meta["attempts"][0]


def test_snapshot_is_not_cached_as_fresh_map(service, monkeypatch, tmp_path):
    """快照只做短缓存，接口恢复后应重新尝试实时抓取。"""
    snapshot = tmp_path / "sw.json"
    snapshot.write_text(
        json.dumps({"as_of": "2026-11-21", "source": "akshare.sw", "map": {"600519": "food"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(service_module, "INDUSTRY_SNAPSHOT_PATH", snapshot)
    monkeypatch.setattr(akshare_source, "fetch_sw_industries", _offline)

    service.get_industry_map(["600519"])
    second_mapping, second_meta = service.get_industry_map(["600519"])

    assert second_mapping == {"600519": "food"}
    # 第二次直接命中快照缓存，不再走抓取，但来源仍标 snapshot
    assert second_meta["source"].startswith("snapshot:")


def test_snapshot_file_with_bad_shape_is_ignored(service, monkeypatch, tmp_path):
    snapshot = tmp_path / "sw.json"
    snapshot.write_text('{"as_of": "2026-11-21", "map": {}}', encoding="utf-8")
    monkeypatch.setattr(service_module, "INDUSTRY_SNAPSHOT_PATH", snapshot)
    monkeypatch.setattr(akshare_source, "fetch_sw_industries", _offline)

    with pytest.raises(SourceUnavailable):
        service.get_industry_map(["600519"])


def test_legacy_cache_key_does_not_break_upgrade(service, monkeypatch, tmp_path):
    """v1 缓存是裸 map；升级后不能被当成新结构读取，否则线上会 KeyError。"""
    monkeypatch.setattr(service_module, "INDUSTRY_SNAPSHOT_PATH", tmp_path / "missing.json")
    service.cache.set("industry:map:v1", {"600519": "旧行业"})
    monkeypatch.setattr(
        akshare_source,
        "fetch_sw_industries",
        lambda: [{"industry": "食品饮料", "sw_code": "801120"}],
    )
    monkeypatch.setattr(
        akshare_source,
        "fetch_sw_constituents",
        lambda sw: [{"code": "600519", "name": "贵州茅台"}],
    )

    mapping, meta = service.get_industry_map(["600519"])

    assert mapping == {"600519": "食品饮料"}
    assert meta["source"] == "akshare.sw"


def test_installed_akshare_adapter_uses_current_function(monkeypatch):
    from types import SimpleNamespace

    frame = SimpleNamespace(
        empty=False, iterrows=lambda: iter([(0, {"行业名称": "食品饮料", "行业代码": "801120.SI"})])
    )
    monkeypatch.setattr(
        akshare_source, "_akshare", lambda: SimpleNamespace(index_first_info_sw=lambda: frame)
    )
    assert akshare_source.fetch_sw_industries() == [{"industry": "食品饮料", "sw_code": "801120"}]


def test_bundled_snapshots_work_when_all_sw_calls_fail(service, monkeypatch):
    monkeypatch.setattr(akshare_source, "fetch_sw_industries", _offline)
    monkeypatch.setattr(akshare_source, "fetch_sw_index_bars", lambda *_: _offline())
    mapping, map_meta = service.get_industry_map(["600519", "000333"])
    snapshot = json.loads(service_module.INDUSTRY_BARS_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    month = snapshot["window_end"][:7]
    industry_returns, meta = service.get_industry_returns(month, sorted(set(mapping.values())))

    assert mapping == {"600519": "食品饮料", "000333": "家用电器"}
    assert map_meta["source"].startswith("snapshot:")
    assert set(industry_returns) == set(mapping.values())
    assert meta["source"].startswith("snapshot:")
    assert meta["as_of"] and not meta["missing"]
    assert meta["sources"]["食品饮料"] == meta["source"]

    old_returns, old_meta = service.get_industry_returns("2020-10", ["食品饮料"])
    assert old_returns == {}
    assert "没有同月备份" in old_meta["missing"][0]


def test_live_values_take_priority_over_snapshots(service, monkeypatch):
    monkeypatch.setattr(
        akshare_source,
        "fetch_sw_industries",
        lambda: [{"industry": "食品饮料", "sw_code": "801120"}],
    )
    monkeypatch.setattr(akshare_source, "fetch_sw_constituents", lambda _: [{"code": "600519"}])
    mapping, meta = service.get_industry_map(["600519", "000333"])
    assert mapping == {"600519": "食品饮料", "000333": "家用电器"}
    assert meta["snapshot_codes"] == ["000333"]

    snapshot = json.loads(service_module.INDUSTRY_BARS_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    end = snapshot["window_end"]
    month = end[:7]

    def fetch_bars(code, first, last):
        assert (first, last) == (f"{month}-01", end)
        if code != "801120":
            raise SourceUnavailable("live bars unavailable")
        return [{"date": first, "close": 100}, {"date": last, "close": 125}]

    monkeypatch.setattr(akshare_source, "fetch_sw_index_bars", fetch_bars)
    values, meta = service.get_industry_returns(month, ["食品饮料", "家用电器"])
    assert values["食品饮料"] == 0.25
    assert set(values) == {"食品饮料", "家用电器"}
    assert meta["source"] == "mixed"
    assert meta["sources"]["食品饮料"] == "akshare.sw"
    assert meta["sources"]["家用电器"].startswith("snapshot:")
