import { useEffect, useState } from "react";

import { StatusBadge } from "../components/StatusBadge";
import { api, type PluginMeta } from "../core/api";
import { features } from "../core/features";

export function PluginsPage() {
  const [items, setItems] = useState<PluginMeta[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .plugins()
      .then((res) => setItems(res.items))
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="space-y-4">
      <div className="card">
        <h2 className="text-sm font-semibold text-ink-900">后端已加载插件</h2>
        <p className="mt-1 text-xs text-ink-500">
          这里列出 engine/plugins 下所有被发现的插件。新增目录后刷新即可看到。
        </p>
      </div>

      {error && (
        <div className="card border-red-200">
          <p className="text-xs text-red-700">{error}</p>
        </div>
      )}

      <div className="card overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-ink-500">
            <tr className="border-b border-ink-100">
              <th className="py-2 pr-4 font-medium">插件 id</th>
              <th className="py-2 pr-4 font-medium">标题</th>
              <th className="py-2 pr-4 font-medium">状态</th>
              <th className="py-2 pr-4 font-medium">耗时</th>
              <th className="py-2 font-medium">说明</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} className="border-b border-ink-100 last:border-0">
                <td className="py-2 pr-4 font-mono">{item.id}</td>
                <td className="py-2 pr-4">{item.title}</td>
                <td className="py-2 pr-4">
                  <StatusBadge status={item.status} />
                </td>
                <td className="py-2 pr-4 text-ink-500">
                  {typeof item.load_ms === "number" ? `${item.load_ms} ms` : "—"}
                </td>
                <td className="py-2 text-ink-500">{item.error || item.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2 className="text-sm font-semibold text-ink-900">前端已发现视图</h2>
        <p className="mt-1 text-xs text-ink-500">
          由 import.meta.glob 自动收集 src/features 下的目录，无需注册。
        </p>
        <ul className="mt-3 space-y-2 text-xs">
          {features.map((feature) => (
            <li key={feature.id} className="flex items-center justify-between gap-4">
              <span className="font-mono text-ink-700">{feature.id}</span>
              <span className="text-ink-500">
                {feature.title} · 顺序 {feature.order} · 目录 {feature.dir}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
