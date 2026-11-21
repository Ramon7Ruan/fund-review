/**
 * 月度回顾（视图层插件）。
 *
 * 对应 Issue #3「视图层：月度回顾页面」：把某一支基金某一个月的
 * 收益概况、净值与回撤、交易日历、收益拆解、持仓变动放在同一张卡里。
 *
 * 依赖说明：
 * - 月份选择与请求由工作台（pages/Workbench.tsx）统一完成，本卡只负责渲染，
 *   因此不重复放表单、不改路由、不碰 core/。
 * - 收益拆解取本插件对应后端结果（manifest.id = attribution.brinson），
 *   持仓取 /api/review 的 holdings，净值取 nav_series。
 * - 空数据约定：任一模块缺数据只降级该模块并给引导，不报错、不白屏。
 * - 配色约定：红=上涨/正贡献，绿=下跌/负贡献，蓝=中性（净值、权重、零轴），不用黑色。
 */

import { useMemo } from "react";

import type { PanelProps } from "../../core/features";

import Attribution from "./Attribution";
import Holdings from "./Holdings";
import { NavDrawdownChart } from "./NavDrawdownChart";
import { TradingCalendar } from "./TradingCalendar";

const GREEN = "#059669";
const BLUE = "#2563eb";

const DISCLAIMER =
  "以下内容为数据拆解与公开事件整理。事件与涨跌同时出现只代表时间上的相关性，不代表因果关系，不构成投资建议。";

interface AttributionShape {
  fund_return?: number;
  max_drawdown?: number;
}

/** 由净值序列算区间最深水下幅度，只用于展示，不参与收益口径。 */
function derivedDrawdown(points: { nav: number }[]): number | undefined {
  let peak = Number.NEGATIVE_INFINITY;
  let depth = 0;
  for (const point of points) {
    if (!Number.isFinite(point.nav)) continue;
    peak = Math.max(peak, point.nav);
    if (peak > 0) depth = Math.min(depth, point.nav / peak - 1);
  }
  return points.length > 1 ? depth : undefined;
}


function pct(value: unknown, digits = 2): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

function nav(value: unknown, digits = 4): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

function Kpi({
  label,
  value,
  hint,
  color,
  dense,
}: {
  label: string;
  value: string;
  hint?: string;
  color?: "up" | "down" | "base";
  /** 数值较长时用小一号字，避免撑宽栅格 */
  dense?: boolean;
}) {
  const text =
    color === "up" ? "text-red-600" : color === "down" ? "text-emerald-600" : "text-ink-900";
  const surface =
    color === "up"
      ? "border-red-100 bg-red-50/40"
      : color === "down"
        ? "border-emerald-100 bg-emerald-50/40"
        : "border-blue-100 bg-blue-50/40";
  return (
    <div className={`min-w-0 rounded-xl border px-3 py-2.5 ${surface}`} data-testid="review-kpi">
      <div className="label">{label}</div>
      <div
        className={`mt-1 font-semibold tabular-nums ${dense ? "text-sm leading-6" : "text-xl"} ${text}`}
      >
        {value}
      </div>
      {hint && <div className="mt-0.5 text-xs text-ink-500">{hint}</div>}
    </div>
  );
}

export default function Panel({ result, fund, month, navSeries, holdings, meta }: PanelProps) {
  const attribution = (result?.data ?? {}) as AttributionShape;
  const quarter = String((meta?.holdings as { quarter?: string } | undefined)?.quarter ?? "");
  const navSource = String((meta?.nav as { source?: string } | undefined)?.source ?? "");

  const firstPoint = navSeries[0];
  const lastPoint = navSeries.at(-1);
  const drawdown = useMemo(() => derivedDrawdown(navSeries), [navSeries]);
  // 本卡是本地视图，拿不到其他插件的结果；回撤按净值读数派生并显式标注，
  // 收益口径仍由页面顶部的区间收益卡（后端结果）负责，这里不重复显示。
  const maxDrawdown = attribution.max_drawdown ?? drawdown;
  // 前十大披露权重之和，供「披露覆盖度」快速读数
  const weightSum = useMemo(
    () => holdings.reduce((sum, item) => sum + (Number.isFinite(item.weight) ? item.weight : 0), 0),
    [holdings]
  );
  const isEmpty = navSeries.length === 0 && holdings.length === 0 && !result;

  if (isEmpty) {
    return (
      <div className="card border-dashed py-10 text-center">
        <p className="text-sm font-medium text-ink-700">这个月还没有可回顾的数据</p>
        <p className="mt-1 text-xs text-ink-500">
          换一个月份或基金代码再试。若所有月份都为空，可能是该基金当月没有披露净值。
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <section className="card">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div className="flex flex-wrap items-baseline gap-2">
            {/* 基金名称由上方概览卡展示，这里不重复，避免与页面已有文案撞车 */}
            <h3 className="text-base font-semibold text-ink-900">月度回顾</h3>
            <span className="font-mono text-xs text-ink-500">{fund?.code}</span>
            <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-700">
              {month}
            </span>
          </div>
          <span className="text-xs text-ink-500">净值来源：{navSource || "—"}</span>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Kpi
            label="起止净值"
            value={`${nav(firstPoint?.nav)} → ${nav(lastPoint?.nav)}`}
            hint="单位净值（抓取值）"
            dense
          />
          <Kpi label="交易日" value={`${navSeries.length}`} hint="有效净值点个数" />
          <Kpi
            label="披露持仓"
            value={`${holdings.length} 只`}
            hint={quarter || "最近一期季报"}
          />
          <Kpi
            label="披露权重合计"
            value={pct(weightSum)}
            hint="前十大占基金净资产比例之和"
          />
        </div>

        {navSeries.length === 0 && (
          <p className="mt-3 rounded-lg border border-dashed border-blue-200 bg-blue-50/40 px-4 py-3 text-xs text-ink-500">
            本月没有可用净值：收益概况只保留接口返回的部分，净值曲线与日历等数据恢复后再显示。
          </p>
        )}

        <p className="mt-3 text-xs text-ink-500">
          收益按分红复权口径由后端计算；持仓为最近一期季报披露的前十大，未披露部分在拆解里以残差列示。
        </p>
      </section>

      <section className="card">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h4 className="text-sm font-semibold text-ink-900">净值与回撤</h4>
          <span className="text-xs text-ink-500">{month} · {navSeries.length} 个交易日</span>
        </div>
        <div className="mt-3">
          {navSeries.length > 1 ? (
            <>
              <div className="mb-1 flex flex-wrap items-center gap-3 text-xs text-ink-500">
                <span className="inline-flex items-center gap-1">
                  <span className="h-2 w-2 rounded-sm" style={{ background: BLUE }} />
                  单位净值
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="h-2 w-2 rounded-sm" style={{ background: GREEN }} />
                  距区间高点的回撤
                </span>
                {maxDrawdown !== undefined && (
                  <span className="ml-auto rounded-full bg-blue-50 px-2 py-0.5 text-blue-700">
                    区间最大回撤 {pct(maxDrawdown)}
                  </span>
                )}
              </div>
              <NavDrawdownChart points={navSeries} />
              <p className="mt-1 text-xs text-ink-500">
                下格是同一时间轴上的水下深度，越深表示离区间高点越远，阴影带标记最深回撤那一段。
                回撤曲线由净值读数派生，仅用于画图；口径数字取后端结果。
              </p>
            </>
          ) : (
            <p className="rounded-lg border border-dashed border-blue-200 px-4 py-6 text-center text-xs text-ink-500">
              这个月没有足够的净值点，画不出曲线。换一个月试试。
            </p>
          )}
        </div>
      </section>

      <section className="card">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h4 className="text-sm font-semibold text-ink-900">交易日历</h4>
          <span className="text-xs text-ink-500">红涨绿跌 · 格内为该日涨跌幅</span>
        </div>
        <div className="mt-3">
          {navSeries.length > 1 ? (
            <div className="max-w-2xl">
              <TradingCalendar points={navSeries} month={month} />
            </div>
          ) : (
            <p className="rounded-lg border border-dashed border-blue-200 px-4 py-6 text-center text-xs text-ink-500">
              没有连续两个交易日的净值，算不出日涨跌。
            </p>
          )}
        </div>
      </section>

      <Attribution
        result={result}
        fund={fund}
        month={month}
        navSeries={navSeries}
        holdings={holdings}
        meta={meta}
      />

      <Holdings
        result={undefined}
        fund={fund}
        month={month}
        navSeries={navSeries}
        holdings={holdings}
        meta={meta}
      />

      <p className="px-1 text-xs text-ink-500">{DISCLAIMER}</p>
    </div>
  );
}
