/**
 * 收益拆解图：贡献度瀑布 + 行业拆解。
 *
 * 对应后端 attribution.brinson 的结果，只做展示，不在前端重算任何收益。
 * 数据为空或插件未接入时显示引导文案，不渲染空图、不抛出异常。
 */

import * as echarts from "echarts";
import type { EChartsOption } from "echarts";
import { useEffect, useMemo, useRef } from "react";

import { TermNote } from "../../components/TermNote";
import type { PanelProps } from "../../core/features";
import { disclosurePeriod, netValuePeriod, PeriodBadge } from "./PeriodBadge";

const UP = "#dc2626";
const DOWN = "#059669";
// 图表里不再用黑色：基金收益/零轴等中性元素统一用蓝色
const INK = "#2563eb";

interface ContributionItem {
  code?: string;
  name?: string;
  industry?: string;
  weight?: number;
  period_return?: number;
  contribution?: number;
  industry_part?: number | null;
  selection_part?: number | null;
}

interface IndustryGroup {
  industry?: string;
  weight?: number;
  contribution?: number;
  codes?: string[];
}

interface AttributionData {
  month?: string;
  fund_return?: number;
  total_contribution?: number;
  residual_return?: number;
  coverage?: number;
  items?: ContributionItem[];
  industries?: IndustryGroup[];
}

type FlowKind = "item" | "residual" | "total";

interface FlowPoint {
  label: string;
  value: number;
  kind: FlowKind;
}

/** 小数收益转百分比，缺失值显示占位符。 */
function pct(value: unknown, digits = 2): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

function signedPct(value: number): string {
  const text = pct(value);
  return value >= 0 ? `+${text}` : text;
}

function shortLabel(label: string): string {
  return label.length > 6 ? `${label.slice(0, 6)}…` : label;
}

/** 通用图表容器：只在数据就绪时初始化，卸载时销毁。 */
function Chart({
  option,
  className,
  height,
  testId,
}: {
  option: EChartsOption;
  className: string;
  height?: number;
  testId?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chartRef.current = chart;
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    // 容器自身尺寸变化（例如栅格从单列变双列）也要重排，否则画布会沿用旧宽度
    const box = typeof ResizeObserver !== "undefined" ? new ResizeObserver(onResize) : null;
    box?.observe(ref.current);
    // 首帧布局可能还没稳定，补一次延迟重排
    const timer = setTimeout(onResize, 60);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("resize", onResize);
      box?.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, true);
    chartRef.current?.resize();
  }, [option]);

  return (
    <div
      ref={ref}
      data-testid={testId}
      className={className}
      style={{ ...(height ? { height } : {}), width: "100%", minWidth: 0 }}
    />
  );
}

interface WaterfallDatum {
  value: [number, number, number];
  name: string;
  kind: FlowKind;
  itemStyle: { color: string; borderRadius: number[] };
}

/**
 * 瀑布图：每根柱子从上一处的累计值画到下一处，正贡献向上、负贡献向下，
 * 末尾两根是残差与基金区间收益，用来肉眼核对"分项之和 ≈ 基金收益"。
 *
 * 用 custom 系列而不是堆叠柱：累计值可能由正转负，堆叠柱在负基准上会把柱子画反。
 */
function waterfallOption(points: FlowPoint[]): EChartsOption {
  const data: WaterfallDatum[] = [];
  let cumulative = 0;

  points.forEach((point, index) => {
    if (point.kind === "total") {
      data.push({
        value: [index, 0, point.value],
        name: point.label,
        kind: point.kind,
        itemStyle: { color: INK, borderRadius: [2, 2, 0, 0] },
      });
      return;
    }
    data.push({
      value: [index, cumulative, cumulative + point.value],
      name: point.label,
      kind: point.kind,
      itemStyle: { color: point.value >= 0 ? UP : DOWN, borderRadius: [1, 1, 0, 0] },
    });
    cumulative += point.value;
  });

  return {
    animation: false,
    grid: { left: 56, right: 16, top: 16, bottom: 56 },
    tooltip: {
      trigger: "item",
      formatter: (params: { data?: unknown }) => {
        const datum = params.data as WaterfallDatum | undefined;
        if (!datum) return "";
        const delta = datum.value[2] - datum.value[1];
        return [
          datum.name,
          `${datum.kind === "total" ? "区间收益" : datum.kind === "residual" ? "残差" : "贡献"}：${signedPct(delta)}`,
          `累计：${pct(datum.value[2])}`,
        ].join("<br/>");
      },
    },
    xAxis: {
      type: "category",
      data: points.map((p) => shortLabel(p.label)),
      axisLine: { lineStyle: { color: "#cbd5e1" } },
      axisTick: { show: false },
      axisLabel: { color: "#64748b", fontSize: 11, interval: 0, rotate: points.length > 8 ? 30 : 0 },
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "#f1f5f9" } },
      axisLabel: { color: "#64748b", fontSize: 11, formatter: (value: number) => pct(value, 1) },
    },
    series: [
      {
        type: "custom",
        name: "贡献度瀑布",
        encode: { x: 0, y: [1, 2] },
        data,
        // eslint 不参与，这里的 params/api 只有 echarts 自定义系列在运行时提供
        renderItem: (params: { coordSys: { x: number; y: number; width: number; height: number } }, api: {
          value: (dim: number) => number;
          coord: (point: [number, number]) => [number, number];
          size: (range: [number, number]) => [number, number];
          style: () => Record<string, unknown>;
        }) => {
          const index = api.value(0);
          const from = api.coord([index, api.value(1)]);
          const to = api.coord([index, api.value(2)]);
          const [width] = api.size([1, 0]);
          const barWidth = width * 0.52;
          const rect = echarts.graphic.clipRectByRect(
            {
              x: from[0] - barWidth / 2,
              y: Math.min(from[1], to[1]),
              width: barWidth,
              height: Math.abs(from[1] - to[1]),
            },
            params.coordSys,
          );
          if (!rect || rect.height < 1) return undefined;
          // 柱子顶部标数值：瀑布本身只表达"从哪到哪"，差额要靠标签读出来
          const delta = api.value(2) - api.value(1);
          const isUp = delta >= 0;
          return {
            type: "group",
            children: [
              { type: "rect", shape: rect, style: api.style() },
              {
                type: "text",
                style: {
                  text: data[index]?.kind === "total" ? pct(delta) : signedPct(delta),
                  x: from[0],
                  // 上涨柱标在上沿、下跌柱标在下沿，避免标签压在柱身或邻近柱上
                  y: isUp ? Math.min(from[1], to[1]) - 4 : Math.max(from[1], to[1]) + 4,
                  align: "center",
                  verticalAlign: isUp ? "bottom" : "top",
                  fill: isUp ? "#b91c1c" : "#047857",
                  font: "10px ui-sans-serif, system-ui, sans-serif",
                },
              },
            ],
          };
        },
      },
      {
        // 零轴单独一条实线：柱子从正跨到负时，靠底色网格看不出"过零"
        type: "line",
        name: "零轴",
        data: [],
        silent: true,
        markLine: {
          symbol: "none",
          silent: true,
          lineStyle: { color: "#cbd5e1", width: 1 },
          label: { show: false },
          data: [{ yAxis: 0 }],
        },
      },
    ],
  } as EChartsOption;
}

/** 持仓贡献象限：横轴披露权重、纵轴区间收益、气泡大小=贡献绝对值。 */
function scatterOption(items: ContributionItem[]): EChartsOption {
  const usable = items.filter(
    (item) => typeof item.weight === "number" && typeof item.period_return === "number",
  );
  const maxAbs = Math.max(...usable.map((item) => Math.abs(item.contribution ?? 0)), 1e-6);
  const sortedWeights = usable
    .map((item) => item.weight as number)
    .sort((a, b) => a - b);
  const medianWeight =
    sortedWeights.length === 0
      ? 0
      : sortedWeights.length % 2 === 1
        ? sortedWeights[(sortedWeights.length - 1) / 2]
        : (sortedWeights[sortedWeights.length / 2 - 1] + sortedWeights[sortedWeights.length / 2]) / 2;

  const labels = usable.map((item) => item.name || item.code || "未命名持仓");

  const points = usable.map((item) => {
    const contribution = item.contribution ?? 0;
    const size = 9 + 24 * Math.sqrt(Math.abs(contribution) / maxAbs);
    return {
      name: item.name || item.code || "未命名持仓",
      value: [Number(((item.weight as number) * 100).toFixed(2)), Number(((item.period_return as number) * 100).toFixed(2))],
      symbolSize: size,
      itemStyle: {
        color: contribution >= 0 ? UP : DOWN,
        opacity: 0.82,
        borderColor: "#ffffff",
        borderWidth: 1,
      },
      label: {
        show: true,
        position: "top",
        distance: 2,
        color: "#475569",
        fontSize: 9,
        formatter: (params: { dataIndex?: number }) => labels[params.dataIndex ?? 0] ?? "",
      },
      // 自定义字段供 tooltip 使用
      raw: {
        weight: item.weight,
        period_return: item.period_return,
        contribution,
      },
    };
  });

  return {
    animation: false,
    grid: { left: 56, right: 44, top: 34, bottom: 36 },
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(255,255,255,0.96)",
      borderColor: "#e2e8f0",
      textStyle: { color: "#0f172a", fontSize: 11 },
      extraCssText: "box-shadow:0 4px 16px rgba(15,23,42,0.10);border-radius:8px;",
      formatter: (params: { data?: unknown }) => {
        const point = params.data as (typeof points)[number] | undefined;
        if (!point) return "";
        return [
          `<div style="font-weight:600;margin-bottom:3px">${point.name}</div>`,
          `披露权重：${pct(point.raw.weight)}`,
          `区间收益：${signedPct(point.raw.period_return ?? 0)}`,
          `贡献：<b style="color:${point.raw.contribution >= 0 ? UP : DOWN}">${signedPct(point.raw.contribution)}</b>`,
        ].join("<br/>");
      },
    },
    xAxis: {
      type: "value",
      name: "披露权重",
      nameLocation: "middle",
      nameGap: 26,
      nameTextStyle: { color: "#94a3b8", fontSize: 10 },
      scale: true,
      splitLine: { lineStyle: { color: "#f1f5f9" } },
      axisLine: { lineStyle: { color: "#e2e8f0" } },
      axisLabel: { color: "#64748b", fontSize: 10, formatter: (value: number) => `${value.toFixed(1)}%` },
    },
    yAxis: {
      type: "value",
      name: "区间收益",
      nameLocation: "middle",
      nameGap: 40,
      nameTextStyle: { color: "#94a3b8", fontSize: 10 },
      scale: true,
      splitLine: { lineStyle: { color: "#f1f5f9" } },
      axisLine: { show: false },
      axisLabel: { color: "#64748b", fontSize: 10, formatter: (value: number) => `${value.toFixed(1)}%` },
    },
    series: [
      {
        type: "scatter",
        name: "持仓贡献",
        data: points,
        emphasis: { scale: 1.15 },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: "#cbd5e1", type: "dashed", width: 1 },
          label: { color: "#94a3b8", fontSize: 10 },
          data: [
            { yAxis: 0, label: { formatter: "零收益", position: "insideEndTop" } },
            { xAxis: medianWeight * 100, label: { formatter: "权重中位", position: "end" } },
          ],
        },
      },
    ],
  } as EChartsOption;
}

/** 行业权重 × 贡献对照条：同一行业左右并排，看"钱压在哪"与"赚亏来自哪"是否错配。 */
function industryCompareOption(industries: IndustryGroup[]): EChartsOption {
  const sorted = [...industries].sort((a, b) => (b.weight ?? 0) - (a.weight ?? 0));
  const labels = sorted.map((item) => item.industry || "未映射");
  const weights = sorted.map((item) => Number(((item.weight ?? 0) * 100).toFixed(2)));
  const contributions = sorted.map((item) => Number(((item.contribution ?? 0) * 100).toFixed(3)));
  const maxWeight = Math.max(...weights, 1);

  return {
    animation: false,
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: "rgba(37,99,235,0.06)" } },
      backgroundColor: "rgba(255,255,255,0.96)",
      borderColor: "#e2e8f0",
      textStyle: { color: "#0f172a", fontSize: 11 },
      extraCssText: "box-shadow:0 4px 16px rgba(15,23,42,0.10);border-radius:8px;",
      formatter: (params: unknown) => {
        const list = Array.isArray(params) ? params : [params];
        const first = list[0] as { dataIndex?: number } | undefined;
        const index = first?.dataIndex ?? 0;
        return [
          `<div style="font-weight:600;margin-bottom:3px">${labels[index]}</div>`,
          `披露权重：<b>${weights[index]?.toFixed(2)}%</b>`,
          `行业贡献：<b style="color:${(contributions[index] ?? 0) >= 0 ? UP : DOWN}">${signedPct(
            (contributions[index] ?? 0) / 100,
          )}</b>`,
        ].join("<br/>");
      },
    },
    grid: [
      { left: 56, width: "34%", top: 20, bottom: 22 },
      { left: "56%", right: 46, top: 20, bottom: 22 },
    ],
    xAxis: [
      {
        type: "value",
        gridIndex: 0,
        min: 0,
        max: Math.max(1, Math.ceil((maxWeight * 1.15) / 5) * 5),
        splitLine: { lineStyle: { color: "#f1f5f9" } },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: "#64748b", fontSize: 9, formatter: (value: number) => `${value}%` },
      },
      {
        type: "value",
        gridIndex: 1,
        splitLine: { lineStyle: { color: "#f1f5f9" } },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: "#64748b", fontSize: 9, formatter: (value: number) => `${value}%` },
      },
    ],
    yAxis: [
      {
        type: "category",
        gridIndex: 0,
        inverse: true,
        data: labels,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: "#475569", fontSize: 10 },
      },
      {
        type: "category",
        gridIndex: 1,
        inverse: true,
        data: labels,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { show: false },
      },
    ],
    series: [
      {
        name: "披露权重",
        type: "bar",
        xAxisIndex: 0,
        yAxisIndex: 0,
        barWidth: "52%",
        data: weights,
        itemStyle: { color: "#2563eb", borderRadius: [0, 2, 2, 0] },
        label: {
          show: true,
          position: "right",
          color: "#1e40af",
          fontSize: 9,
          formatter: (params: { value?: unknown }) => `${Number(params.value ?? 0).toFixed(1)}%`,
        },
      },
      {
        name: "行业贡献",
        type: "bar",
        xAxisIndex: 1,
        yAxisIndex: 1,
        barWidth: "52%",
        data: contributions.map((value) => ({
          value,
          itemStyle: { color: value >= 0 ? UP : DOWN, borderRadius: value >= 0 ? [0, 2, 2, 0] : [2, 0, 0, 2] },
        })),
        label: {
          show: true,
          position: "right",
          color: "#334155",
          fontSize: 9,
          formatter: (params: { value?: unknown }) => {
            const value = Number(params.value ?? 0);
            return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
          },
        },
      },
    ],
  } as EChartsOption;
}

/** 收益构成环形图：已披露持仓的贡献与残差各占多少。 */
function compositionOption(
  totalContribution: number,
  residual: number,
  fundReturn: number | undefined,
): EChartsOption {
  const held = Math.abs(totalContribution);
  const rest = Math.abs(residual);
  const total = held + rest || 1;

  return {
    animation: false,
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(255,255,255,0.96)",
      borderColor: "#e2e8f0",
      textStyle: { color: "#0f172a", fontSize: 11 },
      extraCssText: "box-shadow:0 4px 16px rgba(15,23,42,0.10);border-radius:8px;",
      formatter: (params: unknown) => {
        const one = params as { name?: string; value?: unknown; percent?: number };
        const value = Number(one.value ?? 0) / 100;
        return `${one.name}：<b style="color:${value >= 0 ? UP : DOWN}">${signedPct(value)}</b><br/>占拆解幅度 ${
          (one.percent ?? 0).toFixed(1)
        }%`;
      },
    },
    title: [
      {
        text: pct(fundReturn),
        // 覆盖度已在卡片表头展示，环心只放收益，避免窄栏里文字压到环上
        subtext: "本月区间收益",
        left: "center",
        top: "43%",
        textStyle: {
          // 后端没给 fund_return 时显示占位符，不臆造 0.00%
          color:
            typeof fundReturn !== "number" ? INK : fundReturn >= 0 ? UP : DOWN,
          fontSize: 16,
          fontWeight: 600,
        },
        subtextStyle: { color: "#94a3b8", fontSize: 8 },
      },
    ],
    series: [
      {
        type: "pie",
        radius: ["56%", "74%"],
        center: ["50%", "50%"],
        avoidLabelOverlap: true,
        label: { show: false },
        labelLine: { show: false },
        data: [
          {
            name: "已披露持仓贡献",
            value: Number((held * 100).toFixed(3)),
            itemStyle: { color: totalContribution >= 0 ? UP : DOWN, opacity: 0.95 },
          },
          {
            name: "残差（未披露/债券/现金/费用）",
            value: Number((rest * 100).toFixed(3)),
            itemStyle: { color: "#93c5fd" },
          },
        ],
      },
    ],
    graphic: [
      {
        type: "text",
        left: "center",
        bottom: 0,
        style: {
          text: `贡献构成：持仓 ${((held / total) * 100).toFixed(0)}% · 残差 ${((rest / total) * 100).toFixed(0)}%`,
          fill: "#94a3b8",
          font: "10px ui-sans-serif, system-ui, sans-serif",
        },
      },
    ],
  } as EChartsOption;
}

function EmptyState({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="card h-full border-dashed">
      <h3 className="text-sm font-semibold text-ink-900">
        <TermNote term="attribution">收益拆解</TermNote>
      </h3>
      <p className="mt-3 text-sm text-ink-700">{title}</p>
      <p className="mt-1 text-xs text-ink-500">{hint}</p>
    </div>
  );
}

export default function Panel({
  result, month, loading, meta, holdings, navSeries,
}: PanelProps & { loading?: boolean }) {
  const data = (result?.data ?? {}) as AttributionData;
  const items = Array.isArray(data.items) ? data.items : [];
  const industries = Array.isArray(data.industries) ? data.industries : [];
  const fundReturnRaw = typeof data.fund_return === "number" ? data.fund_return : undefined;
  const fundReturn = fundReturnRaw ?? 0;
  const residual = typeof data.residual_return === "number" ? data.residual_return : 0;

  const flow = useMemo<FlowPoint[]>(() => {
    // 排序跟《归因口径》2.6 一致：分项按贡献度升序，同一份结果每次排法都一样
    const sorted = [...items].sort((a, b) => (a.contribution ?? 0) - (b.contribution ?? 0));
    const points = sorted.map<FlowPoint>((item) => ({
      label: item.name || item.code || "未命名持仓",
      value: item.contribution ?? 0,
      kind: "item",
    }));
    points.push({ label: "残差", value: residual, kind: "residual" });
    points.push({ label: "基金区间收益", value: fundReturn, kind: "total" });
    return points;
  }, [items, residual, fundReturn]);

  const waterfall = useMemo(() => waterfallOption(flow), [flow]);
  const scatterChart = useMemo(() => scatterOption(items), [items]);
  const compareChart = useMemo(() => industryCompareOption(industries), [industries]);
  const compositionChart = useMemo(
    () =>
      compositionOption(
        data.total_contribution ?? 0,
        data.residual_return ?? 0,
        fundReturnRaw,
      ),
    [data.total_contribution, data.residual_return, fundReturnRaw],
  );

  if (!result) {
    return (
      <EmptyState
        title={loading ? "正在读取收益拆解…" : "本月收益拆解尚未返回数据"}
        hint={
          loading
            ? "数据来自后端 attribution.brinson，加载完成后自动显示。"
            : "拆解数据由后端 attribution.brinson 提供；若该插件本月没有产出（例如持仓或行情缺失），这里只给引导，不报错。"
        }
      />
    );
  }

  if (result.status !== "ready") {
    // 不直接搬后端 notes 文案：那张「待接入」占位卡已经显示过，重复会撞车
    return (
      <EmptyState
        title={result.status === "stub" ? "收益拆解待数据接入" : "收益拆解执行失败"}
        hint={
          result.status === "stub"
            ? "归因插件本月还没产出结果，接入后瀑布、象限、行业对照与收益构成会显示在这里。"
            : (result.error ?? "请稍后重试，或换一个有持仓披露的月份。")
        }
      />
    );
  }

  if (items.length === 0) {
    return (
      <EmptyState
        title="本月没有可拆解的持仓贡献"
        hint="可能缺少持仓披露、个股行情或行业映射。换一个月份或基金代码后重试。"
      />
    );
  }

  const totalContribution =
    typeof data.total_contribution === "number" ? data.total_contribution : 0;
  const reconcileGap = Math.abs(totalContribution + residual - fundReturn);
  const reconciled = reconcileGap < 0.001;

  return (
    <div className="card h-full">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink-900">
          <TermNote term="attribution">收益拆解</TermNote>
        </h3>
        <span className="text-xs text-ink-500">
          {data.month || month} · <TermNote term="attributionCoverage">覆盖披露权重</TermNote> {pct(data.coverage)}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap gap-2">
        <PeriodBadge label="归因收益区间" value={netValuePeriod(navSeries)} />
        <PeriodBadge
          label="归因持仓披露期"
          value={disclosurePeriod(meta.holdings, holdings[0]?.quarter)}
          kind="disclosure"
        />
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
        <div>
          <dt className="label">
            <TermNote term="fundReturn">基金区间收益</TermNote>
          </dt>
          <dd className={`mt-1 text-base font-semibold ${fundReturn >= 0 ? "text-red-600" : "text-emerald-600"}`}>
            {pct(fundReturn)}
          </dd>
        </div>
        <div>
          <dt className="label">
            <TermNote term="sumContributions">分项合计</TermNote>
          </dt>
          <dd className="mt-1 text-base font-semibold text-ink-900">{pct(totalContribution)}</dd>
        </div>
        <div>
          <dt className="label">
            <TermNote term="residual">残差</TermNote>
          </dt>
          <dd className="mt-1 text-base font-semibold text-ink-700">{pct(residual)}</dd>
        </div>
        <div>
          <dt className="label">
            <TermNote term="reconcile">对账</TermNote>
          </dt>
          <dd className="mt-1">
            <span
              className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${
                reconciled
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : "border-amber-200 bg-amber-50 text-amber-700"
              }`}
            >
              {reconciled ? "通过" : "偏差"} {pct(reconcileGap)}
            </span>
          </dd>
        </div>
      </dl>

      <div className="mt-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-xs font-medium text-ink-700">
            <TermNote term="contributionWaterfall">贡献度瀑布</TermNote>
          </div>
          <div className="flex items-center gap-3 text-xs text-ink-500">
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-red-600" />
              <TermNote term="positiveContribution">正贡献</TermNote>
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-emerald-600" />
              <TermNote term="negativeContribution">负贡献</TermNote>
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-blue-600" />
              <TermNote term="fundReturn">基金收益</TermNote>
            </span>
          </div>
        </div>
        <Chart option={waterfall} className="mt-1 h-64 w-full" testId="waterfall-chart" />
        <p className="mt-1 text-xs text-ink-500">
          每根柱子是一只持仓的区间贡献（正红负绿），末尾为残差与基金实际收益。
        </p>
      </div>

      <div className="mt-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div className="text-xs font-medium text-ink-700">
            <TermNote term="contributionQuadrant">持仓贡献象限</TermNote>
          </div>
          <span className="text-xs text-ink-500">气泡越大，贡献越显著</span>
        </div>
        <Chart option={scatterChart} className="mt-1 h-72 w-full" testId="contribution-scatter" />
        <p className="mt-1 text-xs text-ink-500">
          右上 = 仓位重且区间上涨，正贡献较大；右下 = 仓位重但区间下跌，负贡献较大。
          竖虚线为披露权重中位数。
        </p>
      </div>

      {industries.length > 0 ? (
        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-5">
          <div className="min-w-0 lg:col-span-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <div className="text-xs font-medium text-ink-700">
                <TermNote term="industryContribution">行业权重 × 贡献对照</TermNote>
              </div>
              <span className="text-xs text-ink-500">左：钱压在哪　右：赚亏来自哪</span>
            </div>
            <Chart
              option={compareChart}
              className="mt-1 w-full min-w-0"
              height={Math.max(200, industries.length * 28 + 52)}
              testId="industry-compare-chart"
            />
          </div>
          <div className="min-w-0 lg:col-span-2">
            <div className="text-xs font-medium text-ink-700">
              <TermNote term="composition">收益构成</TermNote>
            </div>
            <Chart
              option={compositionChart}
              className="mt-1 w-full min-w-0"
              height={Math.max(200, industries.length * 28 + 52)}
              testId="composition-chart"
            />
          </div>
        </div>
      ) : (
        <div className="mt-4">
          <p className="rounded-lg border border-dashed border-ink-300 px-3 py-2 text-xs text-ink-500">
            本期没有可用的<TermNote term="industryIndex">行业指数收益</TermNote>，行业对照缺失，仅展示持仓层贡献与收益构成。
          </p>
          <div className="mt-3">
            <div className="text-xs font-medium text-ink-700">
              <TermNote term="composition">收益构成</TermNote>
            </div>
            <Chart option={compositionChart} className="mt-1 w-full" height={220} testId="composition-chart" />
          </div>
        </div>
      )}

      <details className="mt-4">
        <summary className="cursor-pointer text-xs text-ink-500">
          贡献明细（{items.length} 项）
        </summary>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-ink-500">
              <tr className="border-b border-ink-100">
                <th className="py-1 pr-3 font-medium">股票</th>
                <th className="py-1 pr-3 font-medium">
                  <TermNote term="industry">行业</TermNote>
                </th>
                <th className="py-1 pr-3 text-right font-medium">
                  <TermNote term="weight">披露权重</TermNote>
                </th>
                <th className="py-1 pr-3 text-right font-medium">
                  <TermNote term="stockReturn">区间收益</TermNote>
                </th>
                <th className="py-1 text-right font-medium">
                  <TermNote term="contribution">贡献</TermNote>
                </th>
              </tr>
            </thead>
            <tbody className="text-ink-700">
              {items.map((item) => (
                <tr key={item.code ?? item.name} className="border-b border-ink-100/60">
                  <td className="py-1 pr-3">
                    {item.name || "—"}
                    <span className="ml-1 font-mono text-ink-500">{item.code}</span>
                  </td>
                  <td className="py-1 pr-3">{item.industry || "未映射"}</td>
                  <td className="py-1 pr-3 text-right">{pct(item.weight)}</td>
                  <td className="py-1 pr-3 text-right">{pct(item.period_return)}</td>
                  <td
                    className={`py-1 text-right ${
                      (item.contribution ?? 0) >= 0 ? "text-red-600" : "text-emerald-600"
                    }`}
                  >
                    {signedPct(item.contribution ?? 0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      {result.notes && result.notes.length > 0 && (
        <ul className="mt-3 list-disc space-y-1 pl-4 text-xs text-ink-500">
          {result.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
