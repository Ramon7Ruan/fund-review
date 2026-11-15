"""基金信息接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_service
from data_pipeline.service import DataService
from data_pipeline.sources.akshare_source import SourceUnavailable

router = APIRouter(prefix="/api/funds", tags=["funds"])


@router.get("/{code}")
def get_fund(code: str, service: DataService = Depends(get_service)) -> dict[str, object]:
    if not (code.isdigit() and len(code) == 6):
        raise HTTPException(status_code=400, detail="基金代码应为 6 位数字")
    try:
        return service.get_fund(code)
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
