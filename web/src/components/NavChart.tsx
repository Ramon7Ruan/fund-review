import * as echarts from "echarts";
import { useEffect, useRef } from "react";

import type { NavPoint } from "../core/api";

/** 净值曲线。数据为空时显示提示，不渲染空图。 */
export function NavChart({ points }: { points: NavPoint[] }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current || points.length === 0) return;

    const chart = echarts.init(ref.current);
    chart.setOption({
      grid: { left: 48, right: 16, top: 24, bottom: 32 },
      tooltip: {
        trigger: "axis",
        valueFormatter: (value: number) => value.toFixed(4),
      },
      xAxis: {
        type: "category",
        data: points.map((p) => p.date),
        axisLine: { lineStyle: { color: "#cbd5e1" } },
        axisLabel: { color: "#64748b", fontSize: 11 },
      },
      yAxis: {
        type: "value",
        scale: true,
        splitLine: { lineStyle: { color: "#f1f5f9" } },
        axisLabel: { color: "#64748b", fontSize: 11 },
      },
      series: [
        {
          name: "单位净值",
          type: "line",
          smooth: false,
          showSymbol: false,
          data: points.map((p) => p.nav),
          lineStyle: { width: 2, color: "#0f172a" },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "rgba(15,23,42,0.16)" },
              { offset: 1, color: "rgba(15,23,42,0.01)" },
            ]),
          },
        },
      ],
    });

    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [points]);

  if (points.length === 0) {
    return <p className="py-8 text-center text-xs text-ink-500">该区间没有净值数据</p>;
  }

  return <div ref={ref} data-testid="nav-chart" className="h-64 w-full" />;
}
