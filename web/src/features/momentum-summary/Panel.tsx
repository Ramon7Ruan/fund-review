import { TermNote } from "../../components/TermNote";
import type { PanelProps } from "../../core/features";

interface MomentumData {
  up_days?: number;
  down_days?: number;
  flat_days?: number;
  best_day?: number;
  worst_day?: number;
  up_ratio?: number;
}

const pct = (value?: number) =>
  typeof value === "number" ? `${(value * 100).toFixed(2)}%` : "—";

export default function Panel({ result }: PanelProps) {
  const data = (result?.data ?? {}) as MomentumData;

  return (
    <div className="card h-full">
      <h3 className="text-sm font-semibold text-ink-900">
        <TermNote term="dailyReturns">涨跌天数分布</TermNote>
      </h3>
      <dl className="mt-3 space-y-2 text-xs">
        <div className="flex justify-between">
          <dt className="text-ink-500">上涨 / 下跌 / 持平</dt>
          <dd className="text-ink-700">
            {data.up_days ?? 0} / {data.down_days ?? 0} / {data.flat_days ?? 0}
          </dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-ink-500">
            <TermNote term="upRatio">上涨天数占比</TermNote>
          </dt>
          <dd className="text-ink-700">{pct(data.up_ratio)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-ink-500">
            <TermNote term="bestDay">最佳单日</TermNote>
          </dt>
          <dd className="text-red-600">{pct(data.best_day)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-ink-500">
            <TermNote term="worstDay">最差单日</TermNote>
          </dt>
          <dd className="text-emerald-600">{pct(data.worst_day)}</dd>
        </div>
      </dl>
      <p className="mt-3 text-xs text-ink-500">示例插件：只做统计，不构成判断。</p>
    </div>
  );
}
