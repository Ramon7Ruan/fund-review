/**
 * 报告导出。
 *
 * 后端只吐出自包含 HTML，PDF 由浏览器自己的打印引擎生成：
 * 这样中文不会因为 CI 缺字体变成方块，也不用往锁定文件里加 PDF 依赖。
 * 打印样式（A4、页边距、表头重复）写在服务端模板的 @page 里，这里只负责调起。
 */

import { useState } from "react";

import { api, type ReviewResponse } from "../core/api";

type Mode = "pdf" | "html";

const GHOST_BUTTON =
  "rounded-lg border border-ink-300 px-4 py-2 text-sm font-medium text-ink-700 transition " +
  "hover:border-ink-700 disabled:cursor-not-allowed disabled:text-ink-300";

/** 把 HTML 写进隐藏 iframe 再调起打印，避免新窗口被拦截。 */
function printDocument(documentHtml: string): void {
  const frame = document.createElement("iframe");
  frame.setAttribute("aria-hidden", "true");
  frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;";
  document.body.appendChild(frame);

  const win = frame.contentWindow;
  const doc = win?.document;
  if (!win || !doc) {
    frame.remove();
    throw new Error("当前浏览器无法创建打印视图");
  }

  doc.open();
  doc.write(documentHtml);
  doc.close();

  let removed = false;
  const cleanup = () => {
    if (removed) return;
    removed = true;
    frame.remove();
  };
  win.addEventListener("afterprint", cleanup, { once: true });

  // 等内联样式与 SVG 完成布局再打印，否则可能打出空白页。
  window.setTimeout(() => {
    try {
      win.focus();
      win.print();
    } finally {
      window.setTimeout(cleanup, 1000);
    }
  }, 350);
}

function downloadHtml(name: string, content: string): void {
  const blob = new Blob([content], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function ExportReport({ data }: { data: ReviewResponse }) {
  const [busy, setBusy] = useState<Mode | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleExport(mode: Mode) {
    if (busy) return;
    setBusy(mode);
    setError(null);
    try {
      const documentHtml = await api.report(data);
      if (mode === "pdf") {
        printDocument(documentHtml);
      } else {
        downloadHtml(`fund-review-${data.month}.html`, documentHtml);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn"
          disabled={busy !== null}
          onClick={() => handleExport("pdf")}
        >
          {busy === "pdf" ? "生成中…" : "导出 PDF"}
        </button>
        <button
          type="button"
          className={GHOST_BUTTON}
          disabled={busy !== null}
          onClick={() => handleExport("html")}
        >
          {busy === "html" ? "生成中…" : "下载 HTML"}
        </button>
      </div>
      {error && <span className="text-xs text-red-600">{error}</span>}
    </div>
  );
}
