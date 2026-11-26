import { useMemo, useState } from "react";

import { ErrorBoundary } from "../components/ErrorBoundary";
import { ExportReport } from "../components/ExportReport";
import { StubCard } from "../components/StubCard";
import { TermNote } from "../components/TermNote";
import { api, type ReviewResponse } from "../core/api";
import { features } from "../core/features";
import type { ReviewTerm } from "../core/reviewTerms";

type Phase = "idle" | "loading" | "done" | "error";

const CODE_PATTERN = /^\d{6}$/;
const STUB_TERMS: Partial<Record<string, ReviewTerm>> = {
  "attribution.brinson": "brinson",
  "screening.anomaly": "anomaly",
};

function defaultMonth(): string {
  const now = new Date();
  const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  return `${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, "0")}`;
}

function formatPct(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

export function Workbench() {
  const [code, setCode] = useState("");
  const [month, setMonth] = useState(defaultMonth);
  const [phase, setPhase] = useState<Phase>("idle");
  const [data, setData] = useState<ReviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const codeValid = CODE_PATTERN.test(code);
  const codeTouched = code.length > 0;
  const canSubmit = codeValid && month.length === 7 && phase !== "loading";

  const interval = useMemo(() => {
    const result = data?.results["returns.interval"];
    if (!result || result.status !== "ready") return null;
    const payload = result.data as { period_return?: number; max_drawdown?: number };
    return payload;
  }, [data]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;

    setPhase("loading");
    setError(null);
    try {
      const response = await api.review({ fund_code: code, month });
      setData(response);
      setPhase("done");
    } catch (err) {
      setData(null);
      setError(err instanceof Error ? err.message : String(err));
      setPhase("error");
    }
  }

  return (
    <div className="space-y-5">
      <form onSubmit={handleSubmit} className="card">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex flex-col gap-1">
            <div className="label">
              <TermNote term="fundCode" htmlFor="fund-code">基金代码</TermNote>
            </div>
            <input
              id="fund-code"
              className="input w-40 font-mono"
              placeholder="110022"
              value={code}
              maxLength={6}
              inputMode="numeric"
              onChange={(e) => setCode(e.target.value.trim())}
            />
          </div>

          <div className="flex flex-col gap-1">
            <div className="label">
              <TermNote term="reviewMonth" htmlFor="month">回顾月份</TermNote>
            </div>
            <input
              id="month"
              type="month"
              className="input w-44"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
            />
          </div>

          <button type="submit" className="btn" disabled={!canSubmit}>
            {phase === "loading" ? "生成中…" : "生成月度回顾"}
          </button>

          {phase === "done" && data && <ExportReport data={data} />}

          <span className="text-xs text-ink-500">
            {phase === "loading" && "正在抓取净值与持仓，首次可能需要几秒"}
            {phase === "done" && data && `已加载 ${data.plugins.length} 个功能`}
          </span>
        </div>

        {codeTouched && !codeValid && (
          <p className="mt-3 text-xs text-red-600">基金代码应为 6 位数字</p>
        )}
      </form>

      {phase === "error" && error && (
        <div className="card border-red-200">
          <div className="text-sm font-medium text-red-700">生成失败</div>
          <p className="mt-1 text-xs text-ink-500">{error}</p>
        </div>
      )}

      {phase === "idle" && (
        <div className="card border-dashed py-10 text-center">
          <p className="text-sm text-ink-700">输入基金代码，生成本月回顾</p>
          <p className="mt-1 text-xs text-ink-500">
            页面会依次展示基金概览、净值曲线，以及各算法功能卡片
          </p>
        </div>
      )}

      {phase === "loading" && (
        <div className="card py-10 text-center">
          <p className="animate-pulse text-sm text-ink-700">正在抓取数据并计算…</p>
        </div>
      )}

      {phase === "done" && data && (
        <>
          {data.errors.length > 0 && (
            <div className="card border-amber-200 bg-amber-50">
              <div className="text-sm font-medium text-amber-800">部分数据不可用</div>
              <ul className="mt-1 list-disc pl-5 text-xs text-amber-700">
                {data.errors.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {interval && (
              <div className="card md:col-span-2">
                <div className="flex flex-wrap items-baseline gap-6">
                  <div>
                    <div className="label">
                      <TermNote term="fundReturn">区间收益</TermNote>
                    </div>
                    <div
                      className={`text-2xl font-semibold ${
                        (interval.period_return ?? 0) >= 0 ? "text-red-600" : "text-emerald-600"
                      }`}
                    >
                      {formatPct(interval.period_return ?? 0)}
                    </div>
                  </div>
                  <div>
                    <div className="label">
                      <TermNote term="maxDrawdown">最大回撤</TermNote>
                    </div>
                    <div className="text-2xl font-semibold text-emerald-600">
                      {formatPct(interval.max_drawdown ?? 0)}
                    </div>
                  </div>
                  <div>
                    <div className="label">区间</div>
                    <div className="text-sm text-ink-700">
                      {data.nav_series[0]?.date} → {data.nav_series.at(-1)?.date}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {features.map((feature) => {
              const result = data.results[feature.resultId ?? feature.id];
              const meta = data.plugins.find((p) => p.id === feature.id);

              // 本地视图（配了 resultId）不能因为共享结果不可用就整卡替换，
              // 否则会连带丢掉净值、日历等不依赖该结果的内容；由 Panel 自行降级。
              if (!feature.resultId && result?.status === "stub") {
                return (
                  <div key={feature.id} className={feature.span === 2 ? "md:col-span-2" : ""}>
                    <StubCard title={feature.title} meta={meta} result={result} term={STUB_TERMS[feature.id]} />
                  </div>
                );
              }

              if (!feature.resultId && result?.status === "error") {
                return (
                  <div key={feature.id} className={feature.span === 2 ? "md:col-span-2" : ""}>
                    <div className="card border-red-200">
                      <div className="text-sm font-medium text-red-700">{feature.title} 执行失败</div>
                      <p className="mt-1 text-xs text-ink-500">{result.error}</p>
                    </div>
                  </div>
                );
              }

              const Panel = feature.Panel;
              return (
                <div key={feature.id} className={feature.span === 2 ? "md:col-span-2" : ""}>
                  <ErrorBoundary title={feature.title}>
                    <Panel
                      result={result}
                      results={data.results}
                      fund={data.fund}
                      month={data.month}
                      navSeries={data.nav_series}
                      holdings={data.holdings}
                      holdingsPrevious={data.holdings_previous}
                      holdingsChanges={data.holdings_changes}
                      holdingsCompare={data.holdings_compare}
                      meta={data.meta}
                    />
                  </ErrorBoundary>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
