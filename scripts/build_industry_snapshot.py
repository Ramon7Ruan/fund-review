"""生成申万一级行业映射和最近六个完整月份的指数日线快照。

用法：
    python scripts/build_industry_snapshot.py
    python scripts/build_industry_snapshot.py --out /tmp/sw.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_pipeline.sources.akshare_source import (  # noqa: E402
    SourceUnavailable,
    fetch_sw_constituents,
    fetch_sw_index_bars,
    fetch_sw_industries,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default=str(ROOT / "data" / "snapshots" / "sw_industry_map.json"),
        help="输出路径",
    )
    parser.add_argument(
        "--index-out",
        default=str(ROOT / "data" / "snapshots" / "sw_industry_bars.json"),
        help="指数日线快照输出路径",
    )
    args = parser.parse_args()

    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    end = today.replace(day=1) - timedelta(days=1)
    month_number = today.year * 12 + today.month - 1 - 6
    year, month = divmod(month_number, 12)
    start = f"{year:04d}-{month + 1:02d}-01"
    mapping: dict[str, str] = {}
    indices = {}
    map_failures: list[str] = []
    bar_failures: list[str] = []
    for item in fetch_sw_industries():
        name, code = item["industry"], item["sw_code"]
        try:
            for member in fetch_sw_constituents(code):
                mapping.setdefault(member["code"], name)
        except SourceUnavailable as exc:
            map_failures.append(f"{name}（{code}）：{exc}")
        try:
            bars = fetch_sw_index_bars(code, start, end.isoformat())
            indices[name] = {"sw_code": code, "bars": bars}
        except SourceUnavailable as exc:
            bar_failures.append(f"{name}（{code}）：{exc}")

    if not mapping or not indices:
        print("缺少成分股或指数日线，保留已有快照")
        return 1

    provenance = {"as_of": today.isoformat(), "source": "akshare.sw"}
    for filename, payload in (
        (args.out, {**provenance, "map": dict(sorted(mapping.items())), "failures": map_failures}),
        (
            args.index_out,
            {
                **provenance,
                "window_start": start,
                "window_end": end.isoformat(),
                "indices": dict(sorted(indices.items())),
                "failures": bar_failures,
            },
        ),
    ):
        out = Path(filename)
        out.parent.mkdir(parents=True, exist_ok=True)
        temporary = out.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        temporary.replace(out)
    print(
        f"股票 {len(mapping)} 只，映射失败行业 {len(map_failures)} 个；"
        f"指数 {len(indices)} 个，日线失败行业 {len(bar_failures)} 个；区间 {start} 至 {end}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
