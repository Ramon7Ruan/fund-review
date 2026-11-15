"""健康检查。CI 与前端联调都靠它判断后端是否活着。"""

from __future__ import annotations

from fastapi import APIRouter

from api import __version__
from engine.runtime import registry

router = APIRouter(tags=["system"])


@router.get("/api/health")
def health() -> dict[str, object]:
    registry.ensure_loaded()
    items = registry.all()
    return {
        "status": "ok",
        "version": __version__,
        "plugins": {
            "total": len(items),
            "ready": sum(1 for i in items if i.plugin and i.plugin.status == "ready"),
            "stub": sum(1 for i in items if i.plugin and i.plugin.status == "stub"),
            "unavailable": sum(1 for i in items if not i.available),
        },
    }


@router.get("/api/plugins")
def plugins() -> dict[str, object]:
    registry.ensure_loaded()
    return {"items": registry.describe()}
