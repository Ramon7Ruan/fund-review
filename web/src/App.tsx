import { NavLink, Route, Routes } from "react-router-dom";

import { PluginsPage } from "./pages/PluginsPage";
import { Workbench } from "./pages/Workbench";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-3 py-1.5 text-sm transition ${
    isActive ? "bg-ink-900 text-white" : "text-ink-700 hover:bg-ink-100"
  }`;

export default function App() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-ink-100 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <div className="flex items-baseline gap-2">
            <span className="text-base font-semibold text-ink-900">fund-review</span>
            <span className="text-xs text-ink-500">基金月度回顾</span>
          </div>
          <nav className="flex gap-2">
            <NavLink to="/" className={navClass} end>
              工作台
            </NavLink>
            <NavLink to="/plugins" className={navClass}>
              功能与插件
            </NavLink>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-6">
        <Routes>
          <Route path="/" element={<Workbench />} />
          <Route path="/plugins" element={<PluginsPage />} />
        </Routes>
      </main>

      <footer className="mx-auto max-w-6xl px-6 pb-8 pt-2 text-xs text-ink-500">
        数据来源：akshare（东方财富、新浪、腾讯）。计算结果仅供参考，不构成投资建议。
      </footer>
    </div>
  );
}
