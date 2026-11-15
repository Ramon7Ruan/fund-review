"""FastAPI 应用装配。

启动时加载插件；所有异常统一成 {"error": {"code", "message"}} 结构，
前端只需要处理一种错误形状。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api import __version__
from api.routes import funds, health, review
from engine.runtime import registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    registry.load()
    items = registry.all()
    logger.info(
        "启动完成：插件 %d 个，可用 %d 个",
        len(items),
        sum(1 for i in items if i.available),
    )
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="fund-review",
        version=__version__,
        description="基金投后月度回顾与涨跌归因",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(funds.router)
    app.include_router(review.router)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.status_code, "message": str(exc.detail)}},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(x) for x in first.get("loc", []) if x != "body")
        message = f"参数校验失败：{location} {first.get('msg', '')}".strip()
        return JSONResponse(
            status_code=422,
            content={"error": {"code": 422, "message": message}},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("未捕获异常：%s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": 500, "message": f"服务内部错误：{type(exc).__name__}"}},
        )

    return app


app = create_app()
