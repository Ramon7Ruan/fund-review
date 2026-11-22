import type { FeatureManifest } from "../../core/features";

const manifest: FeatureManifest = {
  // 本地视图 id 与后端归因插件不同；用 resultId 直接复用归因结果，避免二次请求。
  id: "local.monthly-review",
  resultId: "attribution.brinson",
  title: "月度回顾",
  order: 15,
  span: 2,
};

export default manifest;
