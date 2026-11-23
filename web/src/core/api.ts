/**
 * 后端接口封装。
 * 所有错误统一从 {"error": {"code", "message"}} 取 message，前端只处理一种错误形状。
 */

export type PluginStatus = "ready" | "stub" | "unavailable";
export type ResultStatus = "ready" | "stub" | "error";

export interface PluginMeta {
  id: string;
  title: string;
  version: string;
  status: PluginStatus;
  description: string;
  inputs: string;
  outputs: string;
  owner: string;
  tags: string[];
  error?: string | null;
  load_ms?: number;
}

export interface PluginResult {
  status: ResultStatus;
  title: string;
  data: Record<string, unknown>;
  notes: string[];
  error?: string | null;
}

export interface NavPoint {
  date: string;
  nav: number;
}

export interface Holding {
  code: string;
  name: string;
  weight: number;
  quarter: string;
  industry?: string;
}

export type HoldingChangeStatus = "added" | "removed" | "increased" | "decreased" | "unchanged";

export interface HoldingChange {
  code: string;
  name: string;
  industry: string;
  current_weight: number;
  previous_weight: number;
  delta: number;
  status: HoldingChangeStatus;
}

export interface HoldingCompare {
  current_quarter?: string;
  previous_quarter?: string;
  current_count?: number;
  previous_count?: number;
  note?: string;
}

export interface FundInfo {
  code: string;
  name: string;
  type?: string;
  company?: string;
  cached?: boolean;
}

export interface ReviewResponse {
  fund: FundInfo;
  month: string;
  nav_series: NavPoint[];
  holdings: Holding[];
  holdings_previous?: Holding[];
  holdings_changes?: HoldingChange[];
  holdings_compare?: HoldingCompare;
  results: Record<string, PluginResult>;
  plugins: PluginMeta[];
  errors: string[];
  meta: Record<string, Record<string, unknown>>;
}

export interface HealthResponse {
  status: string;
  version: string;
  plugins: { total: number; ready: number; stub: number; unavailable: number };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new Error("无法连接后端服务，请确认 make backend 已启动");
  }

  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const body = (await response.json()) as { error?: { message?: string } };
      if (body.error?.message) message = body.error.message;
    } catch {
      // 响应不是 JSON 时保留默认文案
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

/**
 * 请求返回纯文本（报告导出用，后端回的是 HTML 而不是 JSON）。
 */
async function requestText(path: string, init?: RequestInit): Promise<string> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new Error("无法连接后端服务，请确认 make backend 已启动");
  }

  if (!response.ok) {
    let message = `报告生成失败（${response.status}）`;
    try {
      const body = (await response.json()) as { error?: { message?: string } };
      if (body.error?.message) message = body.error.message;
    } catch {
      // 响应不是 JSON 时保留默认文案
    }
    throw new Error(message);
  }

  return await response.text();
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  plugins: () => request<{ items: PluginMeta[] }>("/api/plugins"),
  review: (payload: { fund_code: string; month: string }) =>
    request<ReviewResponse>("/api/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  /**
   * 把已经渲染过的回顾快照原样交给后端生成报告。
   * 不重新取数，因此报告里的数字与页面必然一致。
   */
  report: (snapshot: ReviewResponse) =>
    requestText("/api/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(snapshot),
    }),
};
