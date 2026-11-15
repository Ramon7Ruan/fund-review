import type { PanelProps } from "../../core/features";

export default function Panel({ fund, holdings, month, meta }: PanelProps) {
  const navMeta = meta.nav ?? {};
  const holdingsMeta = meta.holdings ?? {};

  return (
    <div className="card h-full">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-ink-900">{fund.name}</h3>
        <span className="font-mono text-xs text-ink-500">{fund.code}</span>
      </div>
      <dl className="mt-3 space-y-2 text-xs">
        <div className="flex justify-between">
          <dt className="text-ink-500">类型</dt>
          <dd className="text-ink-700">{fund.type || "—"}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-ink-500">回顾月份</dt>
          <dd className="text-ink-700">{month}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-ink-500">持仓披露</dt>
          <dd className="text-ink-700">{String(holdingsMeta.quarter ?? "—")}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-ink-500">持仓数量</dt>
          <dd className="text-ink-700">{holdings.length}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-ink-500">数据来源</dt>
          <dd className="font-mono text-ink-700">
            {String(navMeta.source ?? "—")}
            {navMeta.cached ? "（缓存）" : ""}
          </dd>
        </div>
      </dl>
    </div>
  );
}
