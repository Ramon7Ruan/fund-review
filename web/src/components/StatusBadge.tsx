import type { PluginStatus, ResultStatus } from "../core/api";

type AnyStatus = PluginStatus | ResultStatus;

const STYLES: Record<AnyStatus, { label: string; className: string }> = {
  ready: { label: "已接入", className: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  stub: { label: "待接入", className: "bg-ink-100 text-ink-500 border-ink-300" },
  unavailable: { label: "不可用", className: "bg-red-50 text-red-700 border-red-200" },
  error: { label: "执行失败", className: "bg-red-50 text-red-700 border-red-200" },
};

export function StatusBadge({ status }: { status: AnyStatus }) {
  const style = STYLES[status] ?? STYLES.stub;
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${style.className}`}
    >
      {style.label}
    </span>
  );
}
