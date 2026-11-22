/**
 * 补取后端插件结果（本地视图专用）。
 *
 * 背景：工作台只把「本插件 id 对应的那一份结果」交给 Panel，本地视图（如本卡）的
 * id 与 attribution.brinson 不同，因此拿不到归因与区间收益。前端插件契约里没有
 * 暴露整张 results 表，且本 PR 不改 core/，所以这里用已有的 core/api.review
 * 再取一次同一组数据，只读 results 里的两份结果。
 *
 * 约定：
 * - 只在需要时才请求（调用方传入 enabled）；
 * - 同一 fund + month 只请求一次，结果缓存在模块内，重复挂载直接命中；
 * - 请求失败不抛错、不白屏，由调用方按「数据未返回」降级展示。
 */

import { useEffect, useState } from "react";

import type { PluginResult } from "../../core/api";
import { api } from "../../core/api";

/** 归因（收益拆解）结果的后端插件 id */
export const ATTRIBUTION_ID = "attribution.brinson";
/** 区间收益（复权口径）结果的后端插件 id */
export const INTERVAL_ID = "returns.interval";

export interface ReviewExtras {
  attribution?: PluginResult;
  interval?: PluginResult;
}

const cache = new Map<string, ReviewExtras>();

export function useReviewExtras(
  fundCode: string | undefined,
  month: string | undefined,
  enabled: boolean,
): { extras: ReviewExtras; loading: boolean } {
  const key = `${fundCode ?? ""}|${month ?? ""}`;
  const [extras, setExtras] = useState<ReviewExtras>(() => cache.get(key) ?? {});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!enabled || !fundCode || !month) {
      setExtras({});
      setLoading(false);
      return;
    }

    const hit = cache.get(key);
    if (hit) {
      setExtras(hit);
      return;
    }

    let alive = true;
    setLoading(true);
    api
      .review({ fund_code: fundCode, month })
      .then((data) => {
        const picked: ReviewExtras = {
          attribution: data.results?.[ATTRIBUTION_ID],
          interval: data.results?.[INTERVAL_ID],
        };
        cache.set(key, picked);
        if (alive) setExtras(picked);
      })
      .catch(() => {
        if (alive) setExtras({});
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [key, enabled, fundCode, month]);

  return { extras, loading };
}
