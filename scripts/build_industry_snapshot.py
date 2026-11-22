"""生成申万一级行业映射快照，供接口不可用时兜底。

用法：
    python scripts/build_industry_snapshot.py
    python scripts/build_industry_snapshot.py --out /tmp/sw.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_pipeline.sources.akshare_source import (  # noqa: E402
    fetch_sw_constituents,
    fetch_sw_industries,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default=str(ROOT / "data" / "snapshots" / "sw_industry_map.json"),
        help="输出路径",
    )
    args = parser.parse_args()

    mapping: dict[str, str] = {}
    failures: list[str] = []
    for item in fetch_sw_industries():
        try:
            for member in fetch_sw_constituents(item["sw_code"]):
                mapping.setdefault(member["code"], item["industry"])
        except Exception as exc:  # noqa: BLE001 - 单个行业失败不阻塞整体
            failures.append(f"{item['industry']}（{item['sw_code']}）：{exc}")

    if not mapping:
        print("未获取到任何成分股，快照未生成（接口可能不可用）")
        return 1

    payload = {
        "as_of": date.today().isoformat(),
        "source": "akshare.sw",
        "map": dict(sorted(mapping.items())),
        "failures": failures,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {out}：{len(mapping)} 只股票，{len(failures)} 个行业失败")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
