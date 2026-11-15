import type { PluginMeta, PluginResult } from "../core/api";
import { StatusBadge } from "./StatusBadge";

interface Props {
  title: string;
  meta?: PluginMeta;
  result?: PluginResult;
}

/**
 * 未接入功能的统一占位卡。
 * 显示契约摘要，让组员知道要实现什么，同时保证页面不空白、不报错。
 */
export function StubCard({ title, meta, result }: Props) {
  const notes = result?.notes ?? [];
  return (
    <div className="card flex h-full flex-col justify-between border-dashed">
      <div>
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-ink-900">{title}</h3>
          <StatusBadge status="stub" />
        </div>
        {notes.length > 0 && <p className="mt-2 text-xs text-ink-500">{notes[0]}</p>}
      </div>

      <dl className="mt-4 space-y-1.5 text-xs text-ink-500">
        {meta?.inputs && (
          <div>
            <dt className="inline text-ink-700">输入：</dt>
            <dd className="inline font-mono">{meta.inputs}</dd>
          </div>
        )}
        {meta?.outputs && (
          <div>
            <dt className="inline text-ink-700">输出：</dt>
            <dd className="inline font-mono">{meta.outputs}</dd>
          </div>
        )}
      </dl>
    </div>
  );
}
