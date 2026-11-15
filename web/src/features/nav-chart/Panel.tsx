import { NavChart } from "../../components/NavChart";
import type { PanelProps } from "../../core/features";

export default function Panel({ navSeries, month }: PanelProps) {
  return (
    <div className="card h-full">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-ink-900">单位净值</h3>
        <span className="text-xs text-ink-500">
          {month} · {navSeries.length} 个交易日
        </span>
      </div>
      <NavChart points={navSeries} />
    </div>
  );
}
