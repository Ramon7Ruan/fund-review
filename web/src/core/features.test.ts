import { describe, expect, it } from "vitest";

import { collectFeatures, features } from "./features";

describe("前端插件收集器", () => {
  it("自动收集 features 目录下的全部视图", () => {
    const ids = features.map((f) => f.id);
    expect(ids).toContain("local.fund-overview");
    expect(ids).toContain("local.nav-chart");
    expect(ids).toContain("attribution.brinson");
    expect(ids).toContain("screening.anomaly");
    expect(ids).toContain("example.momentum_summary");
  });

  it("按 order 升序排列", () => {
    const orders = features.map((f) => f.order);
    const sorted = [...orders].sort((a, b) => a - b);
    expect(orders).toEqual(sorted);
  });

  it("每个 feature 都带可渲染的组件", () => {
    for (const feature of features) {
      expect(typeof feature.Panel).toBe("function");
      expect(feature.dir.length).toBeGreaterThan(0);
    }
  });

  it("重复调用结果稳定", () => {
    expect(collectFeatures().map((f) => f.id)).toEqual(features.map((f) => f.id));
  });
});
