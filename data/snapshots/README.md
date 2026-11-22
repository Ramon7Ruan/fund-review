# data/snapshots

本地降级快照。接口不可用时由数据服务读取，避免页面卡在重试上。

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
- 生成：接口可用时运行

  ```bash
  python scripts/build_industry_snapshot.py
  ```

  文件较大（全市场约 5000 条），是否入库由组长决定；不入库时放在本目录即可被自动读取。
