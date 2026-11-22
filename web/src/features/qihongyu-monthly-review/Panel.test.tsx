import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PanelProps } from "../../core/features";

vi.mock("echarts", () => ({
  init: () => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() }),
  graphic: {
    LinearGradient: class {
      stops: unknown[];
      constructor(_x0: number, _y0: number, _x1: number, _y1: number, stops: unknown[]) {
        this.stops = stops;
      }
    },
  },
}));

const { default: Panel } = await import("./Panel");

const baseProps: PanelProps = {
  fund: { code: "110022", name: "易方达消费行业" },
  month: "2026-10",
  navSeries: [],
  holdings: [],
  meta: {},
};

const navSeries = [
  { date: "2026-10-09", nav: 1.02 },
  { date: "2026-10-12", nav: 1.01 },
  { date: "2026-10-13", nav: 1.03 },
];

const holdings = [
  { code: "600519", name: "贵州茅台", weight: 0.0974, quarter: "2026Q3" },
  { code: "000858", name: "五粮液", weight: 0.0612, quarter: "2026Q3" },
];

const readyResult = {
  status: "ready" as const,
  title: "收益拆解",
  notes: ["残差包含未披露持仓、债券、现金与费用，不摊薄到已知项"],
  data: {
    month: "2026-10",
    fund_return: 0.0398,
    total_contribution: 0.0312,
    residual_return: 0.0086,
    coverage: 0.5628,
    items: [
      {
        code: "600519",
        name: "贵州茅台",
        industry: "食品饮料",
        weight: 0.0974,
        period_return: 0.0521,
        contribution: 0.0051,
      },
      {
        code: "000858",
        name: "五粮液",
        industry: "食品饮料",
        weight: 0.0612,
        period_return: -0.0312,
        contribution: -0.0019,
      },
    ],
    industries: [
      { industry: "食品饮料", weight: 0.1586, contribution: 0.0032, codes: ["600519", "000858"] },
    ],
  },
};

describe("月度回顾视图插件", () => {
  it("整月没有数据时给引导，不白屏", () => {
    render(<Panel {...baseProps} />);
    expect(screen.getByText("这个月还没有可回顾的数据")).toBeInTheDocument();
    expect(screen.queryByTestId("waterfall-chart")).not.toBeInTheDocument();
  });

  it("有净值但没有拆解结果时，收益概况与净值卡片仍在，拆解降级为引导", async () => {
    render(<Panel {...baseProps} navSeries={navSeries} holdings={holdings} />);
    expect(screen.getByText("净值与回撤")).toBeInTheDocument();
    expect(screen.getByText("交易日历")).toBeInTheDocument();
    // 取数失败或没结果时，拆解块停在引导态
    expect(await screen.findByText("本月收益拆解尚未返回数据")).toBeInTheDocument();
  });

  it("数据齐全时三块内容都可见，并带固定免责声明", () => {
    render(
      <Panel {...baseProps} result={readyResult} navSeries={navSeries} holdings={holdings} />
    );
    expect(screen.getByText("净值与回撤")).toBeInTheDocument();
    expect(screen.getByText("交易日历")).toBeInTheDocument();
    expect(screen.getByTestId("waterfall-chart")).toBeInTheDocument();
    expect(screen.getByTestId("industry-compare-chart")).toBeInTheDocument();
    expect(screen.getAllByText("贵州茅台").length).toBeGreaterThan(0);
    // 免责声明只保留一条：卡片底部
    expect(screen.getAllByText(/不构成投资建议/)).toHaveLength(1);
  });

  it("工作台没有传 result 时，自己按 results 键取回归因结果，拆解图可见", async () => {
    // 模拟工作台的取数路径：manifest.id 是 local.monthly-review，
    // results 里只有 attribution.brinson / returns.interval
    const payload = {
      fund: { code: "003095", name: "分红月样本" },
      month: "2021-08",
      nav_series: [
        { date: "2021-08-09", nav: 3.13 },
        { date: "2021-08-10", nav: 3.01 },
        { date: "2021-08-11", nav: 3.05 },
      ],
      holdings,
      plugins: [],
      errors: [],
      meta: {},
      results: {
        "attribution.brinson": readyResult,
        "returns.interval": {
          status: "ready" as const,
          title: "区间收益",
          notes: ["区间收益按分红复权指数计算"],
          data: { period_return: 0.0123, max_drawdown: -0.1608 },
        },
      },
    };
    const fetchMock = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve(payload) })
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <Panel
        {...baseProps}
        fund={{ code: "003095", name: "分红月样本" }}
        month="2021-08"
        navSeries={payload.nav_series}
        holdings={holdings}
      />
    );

    expect(await screen.findByTestId("waterfall-chart")).toBeInTheDocument();
    expect(screen.getByTestId("industry-compare-chart")).toBeInTheDocument();
    // 回撤数字取后端复权口径（-16.08%），不是单位净值派生的值
    expect(screen.getByText(/区间最大回撤（复权口径）/)).toBeInTheDocument();
    expect(screen.getByText(/-16\.08%/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });
});
