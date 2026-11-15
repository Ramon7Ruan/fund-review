import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ReviewResponse } from "../core/api";

vi.mock("echarts", () => ({
  init: () => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() }),
  graphic: {
    LinearGradient: class {
      constructor() {
        return {};
      }
    },
  },
}));

const reviewMock = vi.fn();

vi.mock("../core/api", async () => {
  const actual = await vi.importActual<typeof import("../core/api")>("../core/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      review: (...args: Parameters<typeof actual.api.review>) => reviewMock(...args),
    },
  };
});

const fakeReview: ReviewResponse = {
  fund: { code: "110022", name: "易方达消费行业", type: "混合型" },
  month: "2026-10",
  nav_series: [
    { date: "2026-10-08", nav: 2.761 },
    { date: "2026-10-30", nav: 2.871 },
  ],
  holdings: [{ code: "600519", name: "贵州茅台", weight: 0.0974, quarter: "2026年1季度股票投资明细" }],
  results: {
    "returns.interval": {
      status: "ready",
      title: "区间收益",
      data: { period_return: 0.0398, max_drawdown: -0.0326 },
      notes: [],
    },
    "attribution.brinson": {
      status: "stub",
      title: "Brinson 归因",
      data: {},
      notes: ["Brinson 归因尚未接入"],
    },
    "example.momentum_summary": {
      status: "ready",
      title: "涨跌天数分布",
      data: { up_days: 9, down_days: 7, flat_days: 0, up_ratio: 0.5625 },
      notes: [],
    },
  },
  plugins: [
    {
      id: "attribution.brinson",
      title: "Brinson 归因",
      version: "0.1.0",
      status: "stub",
      description: "",
      inputs: "positions[]",
      outputs: "AttributionResult",
      owner: "",
      tags: [],
    },
  ],
  errors: [],
  meta: {},
};

// 放在 mock 之后导入，确保拿到被替换过的 api
const { Workbench } = await import("./Workbench");

describe("月度回顾工作台", () => {
  beforeEach(() => {
    reviewMock.mockReset();
  });

  it("空输入时提交按钮不可用", () => {
    render(<Workbench />);
    expect(screen.getByRole("button", { name: "生成月度回顾" })).toBeDisabled();
  });

  it("代码格式错误时给出内联提示", () => {
    render(<Workbench />);
    fireEvent.change(screen.getByLabelText("基金代码"), { target: { value: "abc" } });
    expect(screen.getByText("基金代码应为 6 位数字")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "生成月度回顾" })).toBeDisabled();
  });

  it("成功提交后渲染概览、区间收益与占位卡", async () => {
    reviewMock.mockResolvedValue(fakeReview);
    render(<Workbench />);

    fireEvent.change(screen.getByLabelText("基金代码"), { target: { value: "110022" } });
    fireEvent.click(screen.getByRole("button", { name: "生成月度回顾" }));

    await waitFor(() => {
      expect(screen.getByText("易方达消费行业")).toBeInTheDocument();
    });

    expect(reviewMock).toHaveBeenCalledWith({ fund_code: "110022", month: expect.any(String) });
    expect(screen.getByText("3.98%")).toBeInTheDocument();
    expect(screen.getByText("待接入")).toBeInTheDocument();
    expect(screen.getByText("Brinson 归因尚未接入")).toBeInTheDocument();
    expect(screen.getByText("涨跌天数分布")).toBeInTheDocument();
  });

  it("请求失败时展示后端错误信息", async () => {
    reviewMock.mockRejectedValue(new Error("净值数据不可用：akshare 未安装"));
    render(<Workbench />);

    fireEvent.change(screen.getByLabelText("基金代码"), { target: { value: "110022" } });
    fireEvent.click(screen.getByRole("button", { name: "生成月度回顾" }));

    await waitFor(() => {
      expect(screen.getByText("净值数据不可用：akshare 未安装")).toBeInTheDocument();
    });
  });
});
