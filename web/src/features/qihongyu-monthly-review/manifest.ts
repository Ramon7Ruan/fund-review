import type { FeatureManifest } from "../../core/features";

const manifest: FeatureManifest = {
  // 本地视图：内容来自 nav_series / holdings，不依赖某个后端插件的执行结果，
  // 所以用 local. 前缀，与 nav-chart（local.nav-chart）保持同一种命名。
  id: "local.monthly-review",
  title: "月度回顾",
  order: 15,
  span: 2,
};

export default manifest;
