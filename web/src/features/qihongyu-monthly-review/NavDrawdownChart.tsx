/**
 * 净值曲线（含回撤水下图）。
 *
 * 上格是单位净值走势，下格是相对区间内历史高点的回撤幅度，两格共用一条时间轴，
 * 这样"跌得多不多"不用在两个图上对日期。
 *
 * 口径说明：本图上格是**单位净值**（未复权），下格的"水下深度"只是绘图用的派生曲线；
 * 卡片右上角的"最大回撤"数字优先取后端 returns.interval 的 max_drawdown（分红复权口径），
 * 拿不到后端结果时才退回单位净值派生值，并在文案中注明来源。
 * 前端不参与收益口径计算。
 */

import * as echarts from "echarts";
import type { EChartsOption } from "echarts";
import { useEffect, useMemo, useRef } from "react";

import type { NavPoint } from "../../core/api";

const BLUE = "#2563eb";
const WATER = "#059669";

function pct(value: number, digits = 2): string {
  return `${(value * 100).toFixed(digits)}%`;
}

interface DrawdownPoint {
  date: string;
  nav: number;
  drawdown: number;
  peakIndex: number;
}

/** 由净值序列派生运行最高点与水下幅度，仅用于绘图。 */
function buildDrawdown(points: NavPoint[]): DrawdownPoint[] {
  let peak = points[0]?.nav ?? 0;
  let peakIndex = 0;
  return points.map((point, index) => {
    if (point.nav > peak) {
      peak = point.nav;
      peakIndex = index;
    }
    return {
      date: point.date,
      nav: point.nav,
      drawdown: peak === 0 ? 0 : point.nav / peak - 1,
      peakIndex,
    };
  });
}

function drawdownOption(points: NavPoint[]): EChartsOption {
  const rows = buildDrawdown(points);
  const worst = rows.reduce((acc, row) => (row.drawdown < acc.drawdown ? row : acc), rows[0]);
  const valleyIndex = rows.findIndex((row) => row.drawdown === worst.drawdown);
  const peakIndex = valleyIndex >= 0 ? rows[valleyIndex].peakIndex : 0;
  const dates = rows.map((row) => row.date);
  const worstWindow =
    valleyIndex > peakIndex ? [dates[peakIndex], dates[valleyIndex]] : null;

  return {
    // 首屏直接呈现完整图形，避免初次渲染只看到空坐标轴
    animation: false,
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: "#94a3b8", width: 1 } },
      backgroundColor: "rgba(255,255,255,0.96)",
      borderColor: "#e2e8f0",
      textStyle: { color: "#0f172a", fontSize: 11 },
      extraCssText: "box-shadow:0 4px 16px rgba(15,23,42,0.10);border-radius:8px;",
      formatter: (params: unknown) => {
        const list = Array.isArray(params) ? params : [params];
        const first = list[0] as { axisValue?: string; dataIndex?: number } | undefined;
        const index = first?.dataIndex ?? 0;
        const row = rows[index];
        if (!row) return "";
        const head = `<div style="font-weight:600;margin-bottom:3px">${row.date}</div>`;
        const nav = `<div>单位净值：<b>${row.nav.toFixed(4)}</b></div>`;
        const draw =
          row.drawdown === 0
            ? `<div style="color:${WATER}">处于区间新高</div>`
            : `<div>距区间高点：<b style="color:${WATER}">${pct(row.drawdown)}</b></div>`;
        return head + nav + draw;
      },
    },
    grid: [
      { left: 52, right: 18, top: 20, height: "48%" },
      { left: 52, right: 18, bottom: 44, height: "19%" },
    ],
    xAxis: [
      {
        type: "category",
        data: dates,
        gridIndex: 0,
        boundaryGap: false,
        axisLine: { lineStyle: { color: "#e2e8f0" } },
        axisTick: { show: false },
        axisLabel: { show: false },
        axisPointer: { show: true, label: { show: false }, lineStyle: { color: "#cbd5e1" } },
      },
      {
        type: "category",
        data: dates,
        gridIndex: 1,
        boundaryGap: false,
        axisLine: { lineStyle: { color: "#e2e8f0" } },
        axisTick: { show: false },
        axisLabel: { color: "#64748b", fontSize: 10, hideOverlap: true },
        axisPointer: { show: true, label: { show: false }, lineStyle: { color: "#cbd5e1" } },
      },
    ],
    yAxis: [
      {
        type: "value",
        gridIndex: 0,
        scale: true,
        splitNumber: 3,
        splitLine: { lineStyle: { color: "#f1f5f9" } },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: "#64748b", fontSize: 10, formatter: (value: number) => value.toFixed(2) },
      },
      {
        type: "value",
        gridIndex: 1,
        max: 0,
        min: Math.min(-0.01, Math.floor((worst?.drawdown ?? 0) * 100) / 100 - 0.01),
        splitNumber: 2,
        splitLine: { lineStyle: { color: "#f1f5f9" } },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: "#64748b", fontSize: 10, formatter: (value: number) => pct(value, 0) },
      },
    ],
    series: [
      {
        name: "单位净值",
        type: "line",
        xAxisIndex: 0,
        yAxisIndex: 0,
        showSymbol: false,
        data: rows.map((row) => row.nav),
        lineStyle: { width: 2, color: BLUE },
        itemStyle: { color: BLUE },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(37,99,235,0.18)" },
            { offset: 1, color: "rgba(37,99,235,0.02)" },
          ]),
        },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: "#94a3b8", type: "dashed", width: 1 },
          label: { formatter: "区间高点", position: "insideEndTop", color: "#64748b", fontSize: 10 },
          data: [{ yAxis: Math.max(...rows.map((row) => row.nav)) }],
        },
        markPoint: {
          symbol: "circle",
          symbolSize: 7,
          data: [{ coord: [dates[valleyIndex] ?? dates[0], rows[valleyIndex]?.nav ?? 0], value: "低点" }],
          itemStyle: { color: WATER },
          label: {
            formatter: () => "最低",
            position: "bottom",
            color: WATER,
            fontSize: 10,
          },
        },
        markArea: worstWindow
          ? {
              silent: true,
              itemStyle: { color: "rgba(5,150,105,0.06)" },
              data: [[{ xAxis: worstWindow[0] }, { xAxis: worstWindow[1] }]],
            }
          : undefined,
      },
      {
        name: "回撤",
        type: "line",
        xAxisIndex: 1,
        yAxisIndex: 1,
        showSymbol: false,
        data: rows.map((row) => Number(row.drawdown.toFixed(4))),
        lineStyle: { width: 1.5, color: WATER },
        itemStyle: { color: WATER },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(5,150,105,0.02)" },
            { offset: 1, color: "rgba(5,150,105,0.28)" },
          ]),
        },
        markPoint: {
          symbol: "circle",
          symbolSize: 6,
          data: [{ coord: [dates[valleyIndex] ?? dates[0], worst?.drawdown ?? 0] }],
          itemStyle: { color: WATER },
          label: {
            formatter: () => `最深 ${pct(worst?.drawdown ?? 0)}`,
            position: "top",
            color: WATER,
            fontSize: 10,
          },
        },
      },
    ],
  } as EChartsOption;
}

export function NavDrawdownChart({ points }: { points: NavPoint[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const option = useMemo(() => drawdownOption(points), [points]);

  useEffect(() => {
    if (!ref.current || points.length === 0) return;
    const chart = echarts.init(ref.current);
    chart.setOption(option);
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [option, points]);

  return <div ref={ref} data-testid="nav-drawdown-chart" className="h-72 w-full" />;
}
