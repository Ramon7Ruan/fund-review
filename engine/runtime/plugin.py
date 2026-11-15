"""插件契约。

组员新增算法时，只需要在自己的目录里构造一个 AlgorithmPlugin 并导出为 PLUGIN，
不需要修改本文件，也不需要修改任何注册表。

约定（必须遵守，否则加载器会拒绝）：
1. id 采用点分小写命名，例如 "attribution.brinson"，全局唯一。
2. run 必须是纯函数：不发起网络请求、不读写数据库。
3. 数据从 ctx.data 取，结果放进 PluginResult.data。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from engine.runtime.errors import PluginContractError

PluginStatus = Literal["ready", "stub", "unavailable"]
ResultStatus = Literal["ready", "stub"]

_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")


@dataclass(frozen=True)
class PluginContext:
    """调用插件时传入的上下文。"""

    fund: Mapping[str, Any] = field(default_factory=dict)
    month: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PluginResult:
    """插件返回结果。status=stub 表示该算法尚未接入。"""

    status: ResultStatus = "ready"
    data: Mapping[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    @classmethod
    def stub(cls, note: str = "该算法尚未接入") -> PluginResult:
        return cls(status="stub", data={}, notes=(note,))


@dataclass(frozen=True)
class AlgorithmPlugin:
    """一个算法插件的全部元信息与执行入口。"""

    id: str
    title: str
    run: Callable[[PluginContext], PluginResult]
    version: str = "0.1.0"
    status: PluginStatus = "stub"
    description: str = ""
    inputs: str = ""
    outputs: str = ""
    owner: str = ""
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _ID_PATTERN.match(self.id):
            raise PluginContractError(
                f"插件 id 非法：{self.id!r}，应为点分小写，例如 attribution.brinson"
            )
        if not self.title:
            raise PluginContractError(f"插件 {self.id} 缺少 title")
        if not callable(self.run):
            raise PluginContractError(f"插件 {self.id} 的 run 不可调用")
        if self.status not in ("ready", "stub"):
            raise PluginContractError(f"插件 {self.id} 的 status 只能是 ready 或 stub")

    def describe(self) -> dict[str, Any]:
        """给 /api/plugins 与前端卡片使用的元信息，不含 run。"""
        return {
            "id": self.id,
            "title": self.title,
            "version": self.version,
            "status": self.status,
            "description": self.description,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "owner": self.owner,
            "tags": list(self.tags),
        }
