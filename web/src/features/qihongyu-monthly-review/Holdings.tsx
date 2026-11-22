/**
 * 持仓变动：本期披露持仓的权重分布与行业分布。
 *
 * 数据只来自 /api/review 返回的 holdings 与 meta.holdings，不在前端做任何收益计算。
 * 上一期持仓尚未接入时，明确提示"较上期增减待接入"，不编造变动、不渲染空白。
 */

import * as echarts from "echarts";
import type { EChartsOption } from "echarts";
import { useEffect, useMemo, useRef } from "react";

import type { Holding } from "../../core/api";
import type { PanelProps } from "../../core/features";

const NEUTRAL = "#2563eb";

/** 展示上限：超过后只在表里滚动，图表只画权重最大的若干只。 */
const CHART_LIMIT = 12;

/** 行业色板：蓝系分级，与红涨绿跌的语义色区分开。 */
const INDUSTRY_PALETTE = ["#1d4ed8", "#2563eb", "#3b82f6", "#60a5fa", "#7dd3fc", "#93c5fd", "#bfdbfe"];

interface HoldingRow extends Holding {
  industry?: string;
}

function pct(value: unknown, digits = 2): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

/** 权重条形图：横向条形，长度即披露权重。 */
function weightOption(rows: HoldingRow[]): EChartsOption {
  const sorted = [...rows].sort((a, b) => b.weight - a.weight);
  return {
    animation: false,
    grid: { left: 8, right: 56, top: 8, bottom: 8, containLabel: true },
    tooltip: { trigger: "item", valueFormatter: (value) => pct(Number(value)) },
    xAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "#f1f5f9" } },
      axisLabel: { color: "#64748b", fontSize: 11, formatter: (value: number) => pct(value, 1) },
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: sorted.map((row) => row.name || row.code),
      axisLine: { lineStyle: { color: "#cbd5e1" } },
      axisTick: { show: false },
      axisLabel: { color: "#64748b", fontSize: 11 },
    },
    series: [
      {
        name: "披露权重",
        type: "bar",
        barWidth: "58%",
        itemStyle: { color: NEUTRAL, borderRadius: [0, 2, 2, 0] },
        data: sorted.map((row) => row.weight),
        label: {
          show: true,
          position: "right",
          color: "#334155",
          fontSize: 11,
          formatter: (params: { value?: unknown }) => pct(Number(params.value ?? 0)),
        },
      },
    ],
  };
}

/** 行业分布：横向堆叠条，一段一个行业，长度即披露权重。 */
function industryStackOption(buckets: Array<{ industry: string; weight: number; count: number }>): EChartsOption {
  const total = buckets.reduce((sum, bucket) => sum + bucket.weight, 0) || 1;
  const palette = INDUSTRY_PALETTE;

  return {
    animation: false,
    grid: { left: 0, right: 0, top: 6, bottom: 22 },
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(255,255,255,0.96)",
      borderColor: "#e2e8f0",
      textStyle: { color: "#0f172a", fontSize: 11 },
      extraCssText: "box-shadow:0 4px 16px rgba(15,23,42,0.10);border-radius:8px;",
      formatter: (params: unknown) => {
        const one = params as { seriesName?: string; value?: unknown };
        const value = Number(one.value ?? 0);
        return `${one.seriesName}：<b>${pct(value)}</b><br/>占总披露权重 ${pct(value / total, 1)}`;
      },
    },
    xAxis: { type: "value", show: false, max: total },
    yAxis: { type: "category", show: false, data: ["行业"] },
    series: buckets.map((bucket, index) => ({
      type: "bar" as const,
      name: bucket.industry,
      stack: "industry",
      barWidth: 22,
      data: [bucket.weight],
      itemStyle: { color: palette[index % palette.length] },
      label: {
        show: bucket.weight / total >= 0.1,
        position: "inside",
        // 浅蓝段用深蓝字，避免白字看不清
        color: index < 3 ? "#ffffff" : "#1e3a8a",
        fontSize: 9,
        formatter: () => pct(bucket.weight / total, 0),
      },
    })),
  };
}

/** 行业分布：把持仓权重按行业归并，null/未映射单列。 */
function industryBuckets(rows: HoldingRow[]): Array<{ industry: string; weight: number; count: number }> {
  const buckets = new Map<string, { weight: number; count: number }>();
  for (const row of rows) {
    const key = row.industry?.trim() || "未映射";
    const bucket = buckets.get(key) ?? { weight: 0, count: 0 };
    bucket.weight += row.weight;
    bucket.count += 1;
    buckets.set(key, bucket);
  }
  return [...buckets.entries()]
    .map(([industry, bucket]) => ({ industry, ...bucket }))
    .sort((a, b) => b.weight - a.weight);
}

function Chart({ option, height, testId }: { option: EChartsOption; height: number; testId?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chartRef.current = chart;
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, true);
  }, [option]);

  return <div ref={ref} data-testid={testId} className="w-full" style={{ height }} />;
}

export default function Panel({ holdings, meta }: PanelProps) {
  const rows = (Array.isArray(holdings) ? holdings : []) as HoldingRow[];
  const holdingsMeta = (meta.holdings ?? {}) as {
    quarter?: string;
    count?: number;
    source?: string;
    cached?: boolean;
  };

  const totalWeight = rows.reduce((sum, row) => sum + (Number.isFinite(row.weight) ? row.weight : 0), 0);
  const chartRows = useMemo(
    () => [...rows].sort((a, b) => b.weight - a.weight).slice(0, CHART_LIMIT),
    [rows],
  );
  const industries = useMemo(() => industryBuckets(rows), [rows]);
  const weightChart = useMemo(() => weightOption(chartRows), [chartRows]);
  const industryChart = useMemo(() => industryStackOption(industries), [industries]);

  if (rows.length === 0) {
    return (
      <div className="card h-full border-dashed">
        <h3 className="text-sm font-semibold text-ink-900">持仓变动</h3>
        <p className="mt-3 text-sm text-ink-700">未获取到本月披露的持仓数据</p>
        <p className="mt-1 text-xs text-ink-500">
          可能是该基金当期尚未披露季报，或数据源暂时不可用。换一个月份或基金代码后重试；
          持仓缺失不影响收益与净值部分的展示。
        </p>
        {holdingsMeta.source && (
          <p className="mt-2 font-mono text-xs text-ink-500">
            数据来源：{holdingsMeta.source}
            {holdingsMeta.cached ? "（缓存）" : ""}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="card h-full">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink-900">持仓变动</h3>
        <span className="text-xs text-ink-500">
          {holdingsMeta.quarter || "最近一期披露"} · {rows.length} 只
        </span>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-3">
        <div>
          <dt className="label">披露权重合计</dt>
          <dd className="mt-1 text-base font-semibold text-ink-900">{pct(totalWeight)}</dd>
        </div>
        <div>
          <dt className="label">覆盖行业</dt>
          <dd className="mt-1 text-base font-semibold text-ink-900">{industries.length}</dd>
        </div>
        <div>
          <dt className="label">数据来源</dt>
          <dd className="mt-1 font-mono text-sm text-ink-700">
            {holdingsMeta.source || "—"}
            {holdingsMeta.cached ? "（缓存）" : ""}
          </dd>
        </div>
      </dl>

      <div className="mt-4">
        <div className="text-xs font-medium text-ink-700">
          本期披露权重{chartRows.length < rows.length ? `（仅展示前 ${chartRows.length} 只）` : ""}
        </div>
        <Chart
          option={weightChart}
          height={Math.max(180, chartRows.length * 28 + 40)}
          testId="holdings-weight-chart"
        />
      </div>

      <div className="mt-4">
        <div className="text-xs font-medium text-ink-700">行业分布（按披露权重占比）</div>
        <Chart option={industryChart} height={56} testId="holdings-industry-chart" />
        <ul className="mt-1 grid grid-cols-1 gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
          {industries.map((bucket, index) => (
            <li key={bucket.industry} className="flex items-center justify-between gap-3 border-b border-ink-100/60 py-1">
              <span className="flex items-center gap-1.5 text-ink-700">
                <span
                  className="h-2 w-2 shrink-0 rounded-sm"
                  style={{ backgroundColor: INDUSTRY_PALETTE[index % INDUSTRY_PALETTE.length] }}
                />
                {bucket.industry}
                <span className="text-ink-500">{bucket.count} 只</span>
              </span>
              <span className="tabular-nums text-ink-700">{pct(bucket.weight)}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-4 overflow-x-auto">
        <div className="text-xs font-medium text-ink-700">持仓明细</div>
        <table className="mt-1 w-full text-left text-xs">
          <thead className="text-ink-500">
            <tr className="border-b border-ink-100">
              <th className="py-1 pr-3 font-medium">股票</th>
              <th className="py-1 pr-3 font-medium">行业</th>
              <th className="py-1 text-right font-medium">披露权重</th>
            </tr>
          </thead>
          <tbody className="text-ink-700">
            {[...rows]
              .sort((a, b) => b.weight - a.weight)
              .map((row) => (
                <tr key={row.code} className="border-b border-ink-100/60">
                  <td className="py-1 pr-3">
                    {row.name || "—"}
                    <span className="ml-1 font-mono text-ink-500">{row.code}</span>
                  </td>
                  <td className="py-1 pr-3">{row.industry?.trim() || "未映射"}</td>
                  <td className="py-1 text-right tabular-nums">{pct(row.weight)}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      <ul className="mt-3 list-disc space-y-1 pl-4 text-xs text-ink-500">
        <li>权重取最近一期季报披露值，未做区间前漂移；季报只披露前十大重仓，合计不足 100% 属正常，差额计入残差。</li>
        <li>较上期的增持、减持与退出对比需要数据层提供上一期持仓，接入前本卡不展示增减列，避免用推算值冒充披露值。</li>
      </ul>
    </div>
  );
}
