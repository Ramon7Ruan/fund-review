import { TermNote } from "../../components/TermNote";
import type { PanelProps } from "../../core/features";

export default function Panel({ result }: PanelProps) {
  return (
    <div className="card border-dashed">
      <h3 className="text-sm font-semibold text-ink-900">
        <TermNote term="anomaly">异动清单</TermNote>
      </h3>
      <p className="mt-2 text-xs text-ink-500">{result?.notes?.[0] ?? "该规则尚未接入"}</p>
    </div>
  );
}
