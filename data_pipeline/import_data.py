"""运行：python -m data_pipeline.import_data <holdings|nav|month> ..."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_pipeline.fund_store import FundDataStore


def main() -> None:
    parser = argparse.ArgumentParser(description="导入基金持仓快照或基金净值")
    parser.add_argument("--db", default="data/cache/fund_review.db", help="SQLite 文件路径")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("holdings").add_argument("csv_file", type=Path)
    commands.add_parser("nav").add_argument("csv_file", type=Path)
    month = commands.add_parser("month")
    month.add_argument("fund_code")
    month.add_argument("month")
    args = parser.parse_args()
    store = FundDataStore(args.db)
    try:
        if args.command == "holdings":
            result = store.import_holdings_csv(args.csv_file.read_bytes())
        elif args.command == "nav":
            result = store.import_nav_csv(args.csv_file.read_bytes())
        else:
            result = store.month_snapshots(args.fund_code, args.month)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
