# tests/fixtures —— 真实数据验收样本

这份数据是全组统一的**验收基准**：真实、有来源、可复现。
任何插件的测试都应该优先用这里的数据，而不是自己编一组数字。

## 数据来源

全部通过 `akshare` 抓自公开数据源：

| 数据 | 来源 |
|---|---|
| 基金净值、基金持仓 | 东方财富 |
| 个股日线 | 新浪财经（失败时转腾讯财经） |
| 申万一级行业指数 | 申万宏源研究 |

生成时间与抓取失败记录见 `manifest.json`，**没有任何编造的数值**。

## 覆盖范围

三只基金，对应三个申万一级行业，模拟一个基金投资用户的持仓结构：

| 基金代码 | 名称 | 主要行业 |
|---|---|---|
| 110022 | 易方达消费行业 | 食品饮料 |
| 003095 | 中欧医疗健康混合 | 医药生物 |
| 519674 | 银河创新成长混合 | 电子 |

每只基金包含当月净值序列与最近一期披露的**前十大持仓**；
每只个股包含当月日线（开高低收、成交量、成交额）。

样本刻意控制在小体量：够做收益计算、贡献度、行业拆解与异动检测的验收，
但不追求覆盖全市场。

## 文件结构

```
fixtures/
  manifest.json      # 生成时间、来源、统计、失败记录
  funds.json         # {基金代码: {fund, month, nav_series, holdings}}
  quotes.json        # {股票代码: {code, name, source, bars[]}}
  industries.json    # 三个申万一级行业的指数日线
  expected.json      # 已知答案：区间收益、最大回撤、前十大权重和
```

## 在测试里怎么用

```python
import json
from pathlib import Path

import pytest

from engine.returns import NavPoint, compute_interval_return

FIXTURES = Path(__file__).parent / "fixtures"
funds = json.loads((FIXTURES / "funds.json").read_text(encoding="utf-8"))
expected = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))


def test_interval_return_matches_known_answer():
    points = [NavPoint(**p) for p in funds["110022"]["nav_series"]]
    summary = compute_interval_return(points)
    assert summary.period_return == pytest.approx(
        expected["110022"]["period_return"], abs=1e-6
    )
```

**断言应该对照 `expected.json` 里的已知答案，不要写死数字。**

## 重新生成

```bash
.venv/bin/python -m pip install akshare   # 如未安装
python scripts/build_fixtures.py --month 2026-10
```

换月份或换基金时，改 `scripts/build_fixtures.py` 顶部的 `FUNDS` 与 `--month`。

## 使用注意

1. **净值是单位净值，未做分红复权**。验收区间收益时口径要一致。
2. **持仓披露期可能不同**。季报披露有滞后，各基金最近一期不一定是同一季度，
   文件里的 `disclosure_quarter` 写明了实际披露期。
3. **前十大权重之和小于 1 是正常现象**，差额是未披露部分，验收贡献度时必须保留残差项。
4. 本样本只用于开发验收，**不构成任何投资建议**。
