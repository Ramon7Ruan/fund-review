"""插件自动发现与加载。

核心约定：新增功能 = 新建目录，不修改任何已有文件。

加载规则：
- 扫描 engine.plugins 包下的每个子目录（以 "_" 开头的跳过，用于放模板）。
- 每个目录下必须有 plugin.py，并导出名为 PLUGIN 的 AlgorithmPlugin 实例。
- 任何一个插件导入失败，只把它标记为 unavailable，不影响其他插件与应用启动。
- 重复 id 保留先加载的，后一个标记为 unavailable 并说明原因。
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
import time
import traceback
from dataclasses import dataclass
from typing import Any

from engine.runtime.errors import PluginExecutionError
from engine.runtime.plugin import AlgorithmPlugin, PluginContext, PluginResult

logger = logging.getLogger(__name__)

DEFAULT_PACKAGE = "engine.plugins"
MODULE_NAME = "plugin"
EXPORT_NAME = "PLUGIN"
TEMPLATE_PREFIX = "_"


@dataclass
class LoadedPlugin:
    """加载结果。plugin 为 None 时表示加载失败，error 说明原因。"""

    module: str
    plugin: AlgorithmPlugin | None = None
    error: str | None = None
    load_ms: float = 0.0

    @property
    def id(self) -> str:
        return self.plugin.id if self.plugin else self.module

    @property
    def available(self) -> bool:
        return self.plugin is not None and self.error is None

    def describe(self) -> dict[str, Any]:
        if self.plugin is None:
            return {
                "id": self.module,
                "title": self.module.rsplit(".", 2)[-2],
                "version": "-",
                "status": "unavailable",
                "description": "",
                "inputs": "",
                "outputs": "",
                "owner": "",
                "tags": [],
                "error": self.error,
                "load_ms": round(self.load_ms, 2),
            }
        meta = self.plugin.describe()
        meta["error"] = self.error
        meta["load_ms"] = round(self.load_ms, 2)
        return meta


class PluginRegistry:
    """全局插件注册表。整进程一个实例，启动时加载一次。"""

    def __init__(self, package: str = DEFAULT_PACKAGE) -> None:
        self.package = package
        self._items: dict[str, LoadedPlugin] = {}
        self._failed: dict[str, LoadedPlugin] = {}
        self._loaded = False

    # ---------- 加载 ----------

    def load(self) -> None:
        self._items.clear()
        self._failed.clear()
        self._loaded = False
        importlib.invalidate_caches()

        try:
            pkg = importlib.import_module(self.package)
        except ModuleNotFoundError:
            logger.warning("插件包 %s 不存在，跳过加载", self.package)
            self._loaded = True
            return

        for info in pkgutil.iter_modules(pkg.__path__):
            if info.name.startswith(TEMPLATE_PREFIX):
                continue
            self._load_one(info.name)

        self._loaded = True
        total = len(self._items) + len(self._failed)
        logger.info(
            "插件加载完成：%d 个，其中可用 %d 个",
            total,
            len(self._items),
        )
        for item in self._items.values():
            logger.info("  - %s ok", item.id)
        for item in self._failed.values():
            logger.warning("  - %s failed(%s)", item.id, item.error)

    def _load_one(self, name: str) -> None:
        module_name = f"{self.package}.{name}.{MODULE_NAME}"
        started = time.perf_counter()
        try:
            module = importlib.import_module(module_name)
            plugin = getattr(module, EXPORT_NAME, None)
            if not isinstance(plugin, AlgorithmPlugin):
                raise TypeError(f"{module_name} 没有导出 AlgorithmPlugin 类型的 {EXPORT_NAME}")
        except Exception as exc:  # noqa: BLE001 - 任何异常都要隔离
            elapsed = (time.perf_counter() - started) * 1000
            detail = f"{type(exc).__name__}: {exc}"
            logger.warning("插件 %s 加载失败：%s", module_name, detail)
            logger.debug("%s", traceback.format_exc())
            self._failed[module_name] = LoadedPlugin(
                module=module_name, error=detail, load_ms=elapsed
            )
            return

        elapsed = (time.perf_counter() - started) * 1000
        if plugin.id in self._items:
            self._failed[module_name] = LoadedPlugin(
                module=module_name,
                error=f"插件 id 与 {self._items[plugin.id].module} 重复：{plugin.id}",
                load_ms=elapsed,
            )
            return

        self._items[plugin.id] = LoadedPlugin(module=module_name, plugin=plugin, load_ms=elapsed)

    # ---------- 访问 ----------

    @property
    def loaded(self) -> bool:
        return self._loaded

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def get(self, plugin_id: str) -> LoadedPlugin | None:
        self.ensure_loaded()
        return self._items.get(plugin_id)

    def all(self) -> list[LoadedPlugin]:
        self.ensure_loaded()
        return [*self._items.values(), *self._failed.values()]

    def ids(self) -> list[str]:
        """仅返回可用插件的 id。失败记录只在 all()/describe() 里出现。"""
        return [item.id for item in self.all() if item.available]

    def describe(self) -> list[dict[str, Any]]:
        return [item.describe() for item in self.all()]

    # ---------- 动态注册（测试与后续扩展用） ----------

    def register(self, plugin: AlgorithmPlugin) -> None:
        """手动注册一个插件。目录自动发现之外的补充入口。"""
        self._items[plugin.id] = LoadedPlugin(module=f"<manual:{plugin.id}>", plugin=plugin)

    def unregister(self, plugin_id: str) -> None:
        self._items.pop(plugin_id, None)
        self._failed.pop(plugin_id, None)

    # ---------- 执行 ----------

    def execute(self, plugin_id: str, ctx: PluginContext) -> PluginResult:
        item = self.get(plugin_id)
        if item is None:
            raise PluginExecutionError(f"插件不存在：{plugin_id}")
        if not item.available or item.plugin is None:
            raise PluginExecutionError(f"插件不可用：{plugin_id}（{item.error}）")
        try:
            result = item.plugin.run(ctx)
        except Exception as exc:  # noqa: BLE001 - 运行期异常统一转换
            raise PluginExecutionError(
                f"{plugin_id} 执行失败：{type(exc).__name__}: {exc}"
            ) from exc
        if not isinstance(result, PluginResult):
            raise PluginExecutionError(f"{plugin_id} 返回值不是 PluginResult")
        return result

    def execute_safely(
        self, plugin_id: str, ctx: PluginContext
    ) -> tuple[PluginResult | None, str | None]:
        """执行插件但不抛异常，返回 (结果, 错误信息)。供聚合接口逐插件调用。"""
        try:
            return self.execute(plugin_id, ctx), None
        except PluginExecutionError as exc:
            return None, str(exc)


registry = PluginRegistry()
