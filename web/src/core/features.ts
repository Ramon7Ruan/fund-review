/**
 * 前端插件收集器。
 *
 * 这是"新增功能 = 新建目录"在前端的落地点：
 * 用 Vite 的 import.meta.glob 扫描 src/features/*，自动收集 manifest 与 Panel。
 * 组员不需要修改本文件，也不需要修改路由或菜单。
 */

import type { ComponentType } from "react";

import type { FundInfo, Holding, NavPoint, PluginResult } from "./api";

export interface FeatureManifest {
  /** 对应后端插件 id，例如 returns.interval */
  id: string;
  title: string;
  /** 卡片排序，数字小的在前 */
  order?: number;
  /** 卡片占位宽度：1 = 单列，2 = 双列 */
  span?: 1 | 2;
}

export interface PanelProps {
  /** 后端该插件的执行结果；本地视图（如净值曲线）没有对应插件时为 undefined */
  result?: PluginResult;
  fund: FundInfo;
  month: string;
  navSeries: NavPoint[];
  holdings: Holding[];
  meta: Record<string, Record<string, unknown>>;
}

export type PanelComponent = ComponentType<PanelProps>;

export interface Feature {
  id: string;
  title: string;
  order: number;
  span: 1 | 2;
  dir: string;
  Panel: PanelComponent;
}

const manifestModules = import.meta.glob<{ default: FeatureManifest }>("../features/*/manifest.ts", {
  eager: true,
});

const panelModules = import.meta.glob<{ default: PanelComponent }>("../features/*/Panel.tsx", {
  eager: true,
});

function dirOf(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 2] ?? "";
}

export function collectFeatures(): Feature[] {
  const panels = new Map<string, PanelComponent>();
  for (const [path, mod] of Object.entries(panelModules)) {
    panels.set(dirOf(path), mod.default);
  }

  const features: Feature[] = [];
  for (const [path, mod] of Object.entries(manifestModules)) {
    const dir = dirOf(path);
    const manifest = mod.default;
    const Panel = panels.get(dir);
    if (!manifest?.id || !Panel) {
      // 缺少 manifest 或 Panel 的目录会被忽略，不影响其他功能
      continue;
    }
    features.push({
      id: manifest.id,
      title: manifest.title || manifest.id,
      order: manifest.order ?? 100,
      span: manifest.span ?? 1,
      dir,
      Panel,
    });
  }

  return features.sort((a, b) => a.order - b.order || a.title.localeCompare(b.title));
}

export const features: Feature[] = collectFeatures();
