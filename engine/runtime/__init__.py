"""插件运行时：契约、加载器、异常。"""

from engine.runtime.errors import (
    PluginContractError,
    PluginError,
    PluginExecutionError,
    PluginLoadError,
)
from engine.runtime.loader import LoadedPlugin, PluginRegistry, registry
from engine.runtime.plugin import AlgorithmPlugin, PluginContext, PluginResult

__all__ = [
    "AlgorithmPlugin",
    "LoadedPlugin",
    "PluginContext",
    "PluginContractError",
    "PluginError",
    "PluginExecutionError",
    "PluginLoadError",
    "PluginRegistry",
    "PluginResult",
    "registry",
]
