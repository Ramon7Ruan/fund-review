import type { PanelProps } from "../../core/features";

/**
 * 待接入占位。正常路径下由 Workbench 统一渲染 StubCard，
 * 这里的实现保证该目录自身结构完整、可单独预览。
 */
export default function Panel({ result }: PanelProps) {
  return (
    <div className="card border-dashed">
      <h3 className="text-sm font-semibold text-ink-900">Brinson 归因</h3>
      <p className="mt-2 text-xs text-ink-500">
        {result?.notes?.[0] ?? "该算法尚未接入"}
      </p>
    </div>
  );
}
