# data/snapshots

本地降级快照。数据来自 AKShare 接入的申万一级行业数据。快照记录生成日期、来源和失败列表。

## sw_industry_map.json

```json
{
  "as_of": "2026-11-21",
  "source": "akshare.sw",
  "map": {"600519": "食品饮料", "000333": "家用电器"},
  "failures": []
}
```

- 用途：申万成分股接口不可用时兜底个股 → 申万一级行业映射。
- 溯源：`meta.industry_map.source` 会带 `snapshot:` 前缀，并给出 `as_of`；不得当作当日实时映射。
- 缓存：快照只缓存 10 分钟，接口恢复后会重新尝试实时抓取。
- 实时映射缺少个别股票时，仅对缺失股票使用快照，`meta.industry_map.snapshot_codes` 列出受影响的股票。
- 映射反映抓取日分类，不能用来证明某只股票在历史月份的行业归属。

## sw_industry_bars.json

- 保存申万一级指数代码、日线日期和收盘价，运行时仍按当月首末收盘比值计算区间收益。
- 优先使用缓存和在线日线。行业列表不可用时用备份中的指数代码；日线不可用时仅查目标月份。
- `meta.benchmark_returns.sources` 标出每个指数的来源；使用快照时提供生成日期 `as_of`。
- 未覆盖的月份继续标明缺失。此次快照生成于 2026-11-25，日线覆盖 2026 年 5 至 10 月。

## 更新

```bash
python scripts/build_industry_snapshot.py
```

脚本抓取最近六个完整自然月。更新后检查两个文件的 `failures` 字段及覆盖范围，再提交审查。
