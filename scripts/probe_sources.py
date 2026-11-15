"""用真实网络验证数据源可用性。

不参与 CI（CI 全程不访问外网）。本地手动执行：make probe
用于在改动数据层后快速确认哪些接口还活着、哪些需要切备用源。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_pipeline.sources import akshare_source  # noqa: E402

CODE = "110022"


def check(label: str, fn) -> None:
    started = time.perf_counter()
    try:
        result = fn()
        elapsed = (time.perf_counter() - started) * 1000
        size = len(result) if hasattr(result, "__len__") else "-"
        print(f"[OK]   {label:<28} {elapsed:7.0f}ms  条数={size}")
    except Exception as exc:  # noqa: BLE001 - 探针要报告一切失败
        elapsed = (time.perf_counter() - started) * 1000
        print(f"[FAIL] {label:<28} {elapsed:7.0f}ms  {type(exc).__name__}: {exc}")


def main() -> None:
    print(f"数据源探针（基金 {CODE}）")
    print("-" * 70)
    check("基金净值", lambda: akshare_source.fetch_fund_nav(CODE))
    check("基金持仓", lambda: akshare_source.fetch_fund_holdings(CODE, "2025"))
    check("基金基本信息", lambda: [akshare_source.fetch_fund_basic(CODE)])
    print("-" * 70)
    print("东财行情接口在本机历史上不可用时，请确认 data_pipeline 是否已配置备用源。")


if __name__ == "__main__":
    main()
