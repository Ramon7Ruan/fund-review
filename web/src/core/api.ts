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

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  plugins: () => request<{ items: PluginMeta[] }>("/api/plugins"),
  review: (payload: { fund_code: string; month: string }) =>
    request<ReviewResponse>("/api/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
};
