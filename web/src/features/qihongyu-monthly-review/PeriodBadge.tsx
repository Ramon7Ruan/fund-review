import type { NavPoint } from "../../core/api";

export function netValuePeriod(points: NavPoint[]): string {
  const first = points[0]?.date;
  const last = points.at(-1)?.date;
  if (!first || !last) return "暂无净值日期";
  return first === last ? first : `${first} 至 ${last}`;
}

export function disclosurePeriod(
  meta: Record<string, unknown> | undefined,
  rowQuarter?: string,
): string {
  if (meta?.source === "local_import") {
    return typeof meta.as_of === "string" && meta.as_of
      ? `本地快照 · ${meta.as_of}`
      : "本地快照 · 日期未提供";
  }
  const quarter = meta?.quarter || rowQuarter;
  return typeof quarter === "string" && quarter ? quarter : "披露期未提供";
}

export function PeriodBadge({
  label, value, kind = "range",
}: {
  label: string;
  value: string;
  kind?: "range" | "disclosure" | "comparison";
}) {
  const style = {
    range: "border-sky-200 bg-sky-50 text-sky-900",
    disclosure: "border-violet-200 bg-violet-50 text-violet-900",
    comparison: "border-amber-200 bg-amber-50 text-amber-900",
  }[kind];
  return (
    <span className={`inline-flex max-w-full flex-wrap items-baseline gap-x-2 rounded-lg border px-2.5 py-1 text-xs ${style}`}>
      <span>{label}</span>
      <strong className="font-semibold tabular-nums">{value}</strong>
    </span>
  );
}
