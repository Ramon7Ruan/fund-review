"""运行：python -m data_pipeline.import_data <holdings|nav|sync-nav|adjusted-nav|month> ..."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_pipeline.fund_store import FundDataStore
from data_pipeline.service import DataService
from engine.returns.dividend import total_return_index


def main() -> None:
    parser = argparse.ArgumentParser(description="导入基金持仓快照或基金净值")
    parser.add_argument("--db", default="data/cache/fund_review.db", help="SQLite 文件路径")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("holdings").add_argument("csv_file", type=Path)
    commands.add_parser("nav").add_argument("csv_file", type=Path)
    commands.add_parser("sync-nav").add_argument("fund_code")
    commands.add_parser("adjusted-nav").add_argument("fund_code")
    month = commands.add_parser("month")
    month.add_argument("fund_code")
    month.add_argument("month")
    args = parser.parse_args()
    service = DataService(fund_store=FundDataStore(args.db))
    try:
        if args.command == "holdings":
            result = service.import_holdings_csv(args.csv_file.read_bytes())
        elif args.command == "nav":
            result = service.import_nav_csv(args.csv_file.read_bytes())
        elif args.command == "sync-nav":
            result = service.sync_nav(args.fund_code)
        elif args.command == "adjusted-nav":
            result = total_return_index(service.fund_store.nav_points(args.fund_code))
        else:
            result = service.month_snapshots(args.fund_code, args.month)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        service.close()


if __name__ == "__main__":
    main()
