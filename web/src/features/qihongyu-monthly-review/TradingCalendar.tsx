/**
 * 交易日历热力图：把每个交易日的涨跌放到日历格子里。
 *
 * 只做展示：日涨跌由相邻两个净值点相除得到（首个交易日没有前值，显示为"首个交易日"），
 * 不参与收益口径计算；页面上"区间收益""最大回撤"仍取后端结果。
 *
 * 配色沿用国内习惯：涨=红，跌=绿，平=浅蓝灰。
 */

import type { CSSProperties } from "react";

import type { NavPoint } from "../../core/api";

const WEEK_LABELS = ["一", "二", "三", "四", "五", "六", "日"];

interface DayCell {
  day: number;
  date: string;
  ret: number | null;
  nav?: number;
  isFirst: boolean;
}

function pct(value: number, digits = 2): string {
  return `${(value * 100).toFixed(digits)}%`;
}

function signedPct(value: number, digits = 2): string {
  const text = pct(value, digits);
  return value >= 0 ? `+${text}` : text;
}

/** 日期 → 当日涨跌。首个净值点没有前值，ret 记 null。 */
function buildCells(points: NavPoint[], month: string): { cells: DayCell[]; maxAbs: number } {
  const [yearText, monthText] = month.split("-");
  const year = Number(yearText);
  const monthIndex = Number(monthText) - 1;
  const daysInMonth = new Date(year, monthIndex + 1, 0).getDate();

  const byDay = new Map<number, { ret: number | null; nav: number; isFirst: boolean }>();
  points.forEach((point, index) => {
    const parsed = Number(point.date.slice(8, 10));
    if (!Number.isFinite(parsed)) return;
    const prev = points[index - 1];
    const ret = prev && prev.nav !== 0 ? point.nav / prev.nav - 1 : null;
    byDay.set(parsed, { ret, nav: point.nav, isFirst: index === 0 });
  });

  const cells: DayCell[] = [];
  for (let day = 1; day <= daysInMonth; day += 1) {
    const entry = byDay.get(day);
    cells.push({
      day,
      date: `${month}-${String(day).padStart(2, "0")}`,
      ret: entry?.ret ?? null,
      nav: entry?.nav,
      isFirst: entry?.isFirst ?? false,
    });
  }

  const maxAbs = Math.max(
    ...cells.map((cell) => Math.abs(cell.ret ?? 0)),
    0.0005,
  );
  return { cells, maxAbs };
}

function cellStyle(ret: number | null, maxAbs: number): CSSProperties {
  if (ret === null) return { backgroundColor: "#f8fafc", color: "#94a3b8" };
  if (Math.abs(ret) < 0.00005) return { backgroundColor: "#eff6ff", color: "#1e3a8a" };
  const intensity = Math.min(1, Math.abs(ret) / maxAbs);
  const alpha = 0.12 + 0.78 * intensity;
  return ret > 0
    ? { backgroundColor: `rgba(220,38,38,${alpha})`, color: intensity > 0.5 ? "#ffffff" : "#7f1d1d" }
    : { backgroundColor: `rgba(5,150,105,${alpha})`, color: intensity > 0.5 ? "#ffffff" : "#065f46" };
}

export function TradingCalendar({ points, month }: { points: NavPoint[]; month: string }) {
  const { cells, maxAbs } = buildCells(points, month);

  // 首日前面留空，按周一开头排版
  const leading = cells.length > 0 ? (new Date(`${month}-01T00:00:00`).getDay() + 6) % 7 : 0;
  const traded = cells.filter((cell) => cell.ret !== null);
  const upDays = traded.filter((cell) => (cell.ret ?? 0) > 0).length;
  const downDays = traded.filter((cell) => (cell.ret ?? 0) < 0).length;
  const bestDay = traded.reduce<DayCell | null>(
    (best, cell) => (!best || (cell.ret ?? 0) > (best.ret ?? 0) ? cell : best),
    null,
  );
  const worstDay = traded.reduce<DayCell | null>(
    (worst, cell) => (!worst || (cell.ret ?? 0) < (worst.ret ?? 0) ? cell : worst),
    null,
  );

  if (points.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-ink-300 px-4 py-6 text-center text-xs text-ink-500">
        该月份没有净值数据，日历无法生成。
      </p>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-ink-500">
        <span className="inline-flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: "#dc2626" }} />
          上涨 {upDays} 天
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: "#059669" }} />
          下跌 {downDays} 天
        </span>
        {bestDay?.ret != null && (
          <span className="rounded-full bg-red-50 px-2 py-0.5 text-red-700">
            最强 {bestDay.date.slice(5)} {signedPct(bestDay.ret)}
          </span>
        )}
        {worstDay?.ret != null && (
          <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-700">
            最弱 {worstDay.date.slice(5)} {signedPct(worstDay.ret)}
          </span>
        )}
      </div>

      <div className="mt-2 grid grid-cols-7 gap-1 text-center text-[10px] text-ink-500">
        {WEEK_LABELS.map((label) => (
          <div key={label} className="pb-0.5 font-medium">
            {label}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-1">
        {Array.from({ length: leading }, (_, index) => (
          <div key={`blank-${index}`} />
        ))}
        {cells.map((cell) => (
          <div
            key={cell.date}
            title={
              cell.ret === null
                ? `${cell.date}：首个交易日，无前值可比较`
                : `${cell.date}：${signedPct(cell.ret)}${cell.nav ? `，净值 ${cell.nav.toFixed(4)}` : ""}（单位净值未复权，除息日会出现跳变）`
            }
            style={cellStyle(cell.ret, maxAbs)}
            className="flex aspect-square flex-col items-center justify-center rounded-md border border-white/60 transition hover:ring-2 hover:ring-blue-200"
          >
            <span className="text-[9px] opacity-70">{cell.day}</span>
            {cell.ret === null ? (
              cell.isFirst ? <span className="text-[9px] opacity-70">首</span> : null
            ) : (
              <span className="text-[10px] font-medium tabular-nums">
                {(cell.ret * 100).toFixed(1)}
              </span>
            )}
          </div>
        ))}
      </div>

      <p className="mt-2 text-xs text-ink-500">
        格内数字为当日涨跌幅（%），颜色深浅表示幅度大小；悬停可看当日净值。
        日涨跌由<b className="font-medium text-ink-700">单位净值（未复权）</b>派生：除息日当天会因分红除权出现一次性下跳，
        并不代表真实亏损，请结合页面顶部的区间收益（复权口径）一起看。
      </p>
    </div>
  );
}
