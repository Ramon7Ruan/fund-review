"""报告导出接口。

设计要点：请求体是前端**已经拿到并渲染过**的 ReviewResponse 快照，后端不再取数、
不再跑一遍插件。这样「报告里的数字与页面完全一致」由数据流结构保证，不依赖事后对账。
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from api.report import render
from api.schemas import ReviewResponse

router = APIRouter(prefix="/api", tags=["report"])


@router.post("/report", response_class=HTMLResponse)
def export_report(payload: ReviewResponse) -> HTMLResponse:
    """把月度回顾快照渲染成自包含 HTML（可直接打印为 PDF）。"""
    document = render(payload.model_dump())
    return HTMLResponse(
        content=document,
        headers={
            # 前端用 fetch 取回字符串后自行决定打印还是下载，
            # 这里不让浏览器直接当作附件下载，避免多一种数据路径。
            "Content-Disposition": 'inline; filename="fund-review-report.html"',
            "Cache-Control": "no-store",
        },
    )
