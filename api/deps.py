"""依赖注入：让测试可以替换数据服务。"""

from __future__ import annotations

from data_pipeline.service import DataService

_service: DataService | None = None


def get_service() -> DataService:
    global _service
    if _service is None:
        _service = DataService()
    return _service


def set_service(service: DataService | None) -> None:
    global _service
    _service = service
