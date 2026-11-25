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
  it("分别标记归因持仓和跨期对比，避免混用不同披露期的增减", () => {
    render(
      <Panel
        {...baseProps}
        result={readyResult}
        navSeries={navSeries}
        holdings={holdings}
        meta={{ holdings: { quarter: "2026年1季度" } }}
        holdingsCompare={{ previous_quarter: "2026年2季度", current_quarter: "2026年3季度" }}
      />,
    );
    expect(screen.getByText("归因持仓披露期").parentElement).toHaveTextContent("2026年1季度");
    expect(screen.getByText("持仓明细披露期").parentElement).toHaveTextContent("2026年1季度");
    expect(screen.getByText("变动对比期").parentElement).toHaveTextContent("2026年2季度 → 2026年3季度");
    expect(screen.queryByRole("columnheader", { name: "较上期" })).not.toBeInTheDocument();
  });

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

  it("工作台按 resultId 传入结果后，拆解与复权回撤直接可见", () => {
    const navSeriesForTest = [
      { date: "2021-08-09", nav: 3.13 },
      { date: "2021-08-10", nav: 3.01 },
      { date: "2021-08-11", nav: 3.05 },
    ];
    const results = {
      "attribution.brinson": readyResult,
      "returns.interval": {
        status: "ready" as const,
        title: "区间收益",
        notes: ["区间收益按分红复权指数计算"],
        data: { period_return: 0.0123, max_drawdown: -0.1608 },
      },
    };

    render(
      <Panel
        {...baseProps}
        result={readyResult}
        results={results}
        fund={{ code: "003095", name: "分红月样本" }}
        month="2021-08"
        navSeries={navSeriesForTest}
        holdings={holdings}
      />
    );

    expect(screen.getByTestId("waterfall-chart")).toBeInTheDocument();
    expect(screen.getByTestId("industry-compare-chart")).toBeInTheDocument();
    // 回撤数字取后端复权口径（-16.08%），不是单位净值派生的值
    expect(screen.getByText(/区间最大回撤（复权口径）/)).toBeInTheDocument();
    expect(screen.getByText(/-16\.08%/)).toBeInTheDocument();
  });

  it("有上一期时展示新增/减持与较上期列", () => {
    render(
      <Panel
        {...baseProps}
        navSeries={navSeries}
        holdings={holdings}
        holdingsChanges={[
          {
            code: "600519",
            name: "贵州茅台",
            industry: "食品饮料",
            current_weight: 0.12,
            previous_weight: 0.0974,
            delta: 0.0226,
            status: "increased",
          },
          {
            code: "000858",
            name: "五粮液",
            industry: "食品饮料",
            current_weight: 0.0612,
            previous_weight: 0.08,
            delta: -0.0188,
            status: "decreased",
          },
          {
            code: "000001",
            name: "平安银行",
            industry: "银行",
            current_weight: 0.03,
            previous_weight: 0,
            delta: 0.03,
            status: "added",
          },
        ]}
        holdingsCompare={{
          current_quarter: "2026年3季度",
          previous_quarter: "2026年2季度",
          note: "两期均按前 10 大截取后比较",
        }}
      />
    );

    expect(screen.getByText("本期变化（前十大口径）")).toBeInTheDocument();
    expect(screen.getAllByText("新增").length).toBeGreaterThan(0);
    expect(screen.getAllByText("增持").length).toBeGreaterThan(0);
    expect(screen.getAllByText("减持").length).toBeGreaterThan(0);
    expect(screen.getAllByText("+3.00%").length).toBeGreaterThan(0);
    expect(screen.getByText("两期均按前 10 大截取后比较")).toBeInTheDocument();
  });

  it("缺上一期时明确说明，不展示变动区块", () => {
    render(
      <Panel
        {...baseProps}
        navSeries={navSeries}
        holdings={holdings}
        holdingsCompare={{ note: "上一期持仓未披露，无法计算变动" }}
      />
    );

    expect(screen.getAllByText("上一期持仓未披露，无法计算变动").length).toBeGreaterThan(0);
    expect(screen.queryByText("本期变化（前十大口径）")).not.toBeInTheDocument();
  });
});
